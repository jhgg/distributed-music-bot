import codecs
import os

import rpc.server
from rpc.base import s


class RemoteVoiceClient(object):
    def __init__(self, client, remote_ref):
        self.client = client
        self.remote_ref = remote_ref
        self.channel = None

    async def __call__(self, *args, **kwargs):
        kwargs.pop('main_ws')
        kwargs.pop('loop')
        self.channel = kwargs.pop('channel')
        self.guild_id = kwargs['data']['guild_id']

        await self.remote_call('__init_voice_client__', *args, **kwargs)
        return self

    def remote_call(self, func, *args, **kwargs):
        print('remote call', func, args, kwargs)
        return self.client.call('remote_voice_client__call', func, self.remote_ref, *args, **kwargs, _timeout=10)

    @property
    def server(self):
        return self.channel.server

    async def disconnect(self):
        await self.client.server.discord.ws.voice_state(self.guild_id, None, self_mute=True)
        return await self.remote_call('disconnect', silent=True)

    def __getattr__(self, item):
        def remote_function(*args, **kwargs):
            return self.remote_call(item, *args, **kwargs)

        return remote_function


class ClientHandler(rpc.server.ClientHandler):
    def __init__(self, *args, **kwargs):
        super(ClientHandler, self).__init__(*args, **kwargs)
        self.refs = {}
        self.client_count = 0
        self.client_connection_id = None

    def handle_call_info(self):
        return self.server.discord.user.name

    def handle_call_main_ws_voice_state(self, *args, **kwargs):
        return self.server.discord.ws.voice_state(*args, **kwargs)

    def handle_cast_client_count_update(self, client_count):
        self.client_count = client_count

    def handle_close(self, reason=None):
        for voice_client in self.refs.values():
            self.loop.create_task(self.server.discord.ws.voice_state(voice_client.guild_id, None))

        self.refs.clear()

    async def make_voice_client_ref(self):
        ref = await self.call('make_voice_client_ref')
        remote_voice_client = self.refs[ref] = RemoteVoiceClient(self, ref)
        return remote_voice_client

    def __repr__(self):
        if self.addr:
            addr = '%s:%s' % (self.addr[0], self.addr[1])
        else:
            addr = 'unknown peer'

        return '<ClientHandler %s/%s>' % (self.client_connection_id, addr)


class Server(rpc.server.Server):
    client_handler_class = ClientHandler

    def __init__(self, *args, **kwargs):
        self.discord = kwargs.pop('discord')
        self.clients_by_connection_id = {}

        super(Server, self).__init__(*args, **kwargs)

    def get_client_secret(self, client_id):
        if client_id == "1512":
            return "hello_world"

    def get_server_info(self, client):
        return {
            'username': self.discord.user.name
        }

    def handle_client_disconnected(self, client):
        print("Client disconnected", client)
        self.clients_by_connection_id.pop(client.client_connection_id, None)

    def handle_client_connected(self, client):
        client.client_connection_id = self.generate_id(client.client_id)
        self.clients_by_connection_id[client.client_connection_id] = client

    def select_client(self, region):
        eligible_clients = []
        for client in self.clients:
            if client.client_count > client.remote_info['max_clients']:
                continue

            acceptable_regions = client.remote_info['acceptable_regions']
            if acceptable_regions == 'all' or region in acceptable_regions:
                eligible_clients.append((client, (
                    region not in acceptable_regions,
                    client.client_count
                )))

        if not eligible_clients:
            return None

        eligible_clients.sort(key=lambda c: c[1])
        return eligible_clients[0][0]

    async def make_voice_client_proxy(self, region):
        client = self.select_client(region)
        if not client:
            raise RuntimeError("no servers available to handle this client")

        return await client.make_voice_client_ref()

    def generate_id(self, client_id):
        while True:
            connection_id = '%s-%s' % (client_id, s(codecs.encode(os.urandom(4), 'hex')))
            if connection_id not in self.clients_by_connection_id:
                return connection_id
