import discord

import rpc.client


class RemoteVoiceClient(discord.VoiceClient):
    async def disconnect(self, silent=False):
        if not self._connected.is_set():
            return

        self.socket.close()
        self._connected.clear()
        await self.ws.close()

        if not silent:
            await self.main_ws.voice_state(self.guild_id, None, self_mute=True)


class RemoteUser(object):
    def __init__(self, id):
        self.id = id


class RemoteGateway(object):
    def __init__(self, client):
        self.client = client

    async def voice_state(self, *args, **kwargs):
        await self.client.call('main_ws_voice_state', *args, **kwargs)


class RemoteVoiceClientWrapper(object):
    def __init__(self, client, remote_ref):
        self.client = client
        self.remote_ref = remote_ref
        self.voice_client = None

    def __init_voice_client__(self, *args, **kwargs):
        if self.voice_client:
            return

        user_id = kwargs.pop('user_id')
        self.voice_client = RemoteVoiceClient(
            *args,
            channel=None, user=RemoteUser(user_id), loop=self.client.loop, main_ws=RemoteGateway(self),
            **kwargs
        )

    def connect(self):
        return self.voice_client.connect()

    async def disconnect(self, silent=False):
        await self.voice_client.disconnect(silent=silent)
        self.voice_client = None
        self.client.remove_remote_voice_client_wrapper(self.remote_ref)

    async def play(self, what, *, ytdl_options):
        player = await self.voice_client.create_ytdl_player(what, ytdl_options=ytdl_options)
        player.start()
        return str(player)


class Client(rpc.client.Client):
    def __init__(self, *args, **kwargs):
        super(Client, self).__init__(*args, **kwargs)
        self._voice_client_ref_seq = 0
        self._voice_clients = {}
        self._max_clients = 15
        self._acceptable_regions = [
            'us-west', 'us-east'
        ]

    async def handle_ready(self, info):
        print("Connected to HQ:", info)

    def get_remote_voice_client_wrapper(self, remote_ref):
        if remote_ref not in self._voice_clients:
            self._voice_clients[remote_ref] = RemoteVoiceClientWrapper(self, remote_ref)
            self.cast('client_count_update', len(self._voice_clients))

        return self._voice_clients[remote_ref]

    def remove_remote_voice_client_wrapper(self, remote_ref):
        if remote_ref in self._voice_clients:
            del self._voice_clients[remote_ref]
            self.cast('client_count_update', len(self._voice_clients))

    def handle_call_make_voice_client_ref(self):
        self._voice_client_ref_seq += 1
        remote_ref = self._voice_client_ref_seq
        return remote_ref

    def handle_call_remote_voice_client__call(self, func, remote_ref, *args, **kwargs):
        print("handle call remote", func, remote_ref, args, kwargs)
        return getattr(self.get_remote_voice_client_wrapper(remote_ref), func)(*args, **kwargs)

    def handle_close(self, reason=None):
        for voice_client in self._voice_clients.values():
            self.loop.create_task(voice_client.disconnect(silent=True))

        self._voice_clients.clear()

    def get_client_info(self):
        return {
            "max_clients": self._max_clients,
            "acceptable_regions": self._acceptable_regions
        }
