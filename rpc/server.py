import asyncio
import asyncio.streams
import hashlib
import hmac

from rpc.base import ClientBase, b, s, HandshakeError


class ClientHandler(ClientBase):
    def __init__(self, server: 'Server', reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        super(ClientHandler, self).__init__(server.loop, reader, writer)
        self.server = server
        self.client_id = None
        self.addr = self.writer.get_extra_info('peername')

    async def do_handshake(self):
        # The client should send us an auth:login op when it connects.
        data = await self.next_packet('auth:login')
        # Clients are identified by an id/secret pair, that is retrieved by the get_client_secret function
        # that should be implemented in the subclass of the Server
        self.client_id = client_id = s(data['client_id'])
        client_secret = self.server.get_client_secret(client_id)

        # We don't know of a client with that ID.
        if not client_secret:
            await self.write_packet("auth:fail", {"reason": "Unknown Client ID"}, drain=True)
            raise HandshakeError("Unknown Client %s" % client_id)

        # The client sends a nonce that along with it's ID that it creates a hmac digest with
        # using the secret as the key.
        client_nonce = data['client_nonce']
        client_digest = data['digest']
        mac_payload = '%s:%s' % (s(client_id), s(client_nonce))
        expected_client_digest = hmac.new(b(client_secret), b(mac_payload), digestmod=hashlib.sha256).hexdigest()

        # This proves that the client knows the secret.
        if not hmac.compare_digest(b(client_digest), b(expected_client_digest)):
            await self.write_packet("auth:fail", {"reason": "Bad Secret"}, drain=True)
            raise HandshakeError("Bad Secret for Client %s" % client_id)

        # Now we have to prove to the client that we also know the secret.
        server_mac_payload = '%s:%s:%s' % (
            s(client_id),
            s(client_nonce),
            s(client_digest)
        )

        server_mac = hmac.new(b(client_secret), b(server_mac_payload), digestmod=hashlib.sha256).hexdigest()

        # We send the client our proof that we are who we are,
        # along with the server info, and some protocol level information.
        await self.write_packet('auth:success', {
            "digest": server_mac,
            "heartbeat_interval": self.heartbeat_interval,
            "info": self.server.get_server_info(self)
        }, drain=True)

        # Finally, we ensure that the client accepted our secret. If it responds with auth:success as well,
        # the handshake is done.
        op, data = await self.next_packet('auth:success', 'auth:fail')
        if op == 'auth:fail':
            raise HandshakeError(data['reason'])

        return data['info']

    async def start(self):
        try:
            self.remote_info = await asyncio.wait_for(self.do_handshake(), self.handshake_timeout, loop=self.loop)
            self.server.client_connected(self)
            await self.start_main_loop()

        finally:
            self.writer.close()
            self.server.client_disconnected(self)

    def __repr__(self):
        return '<ClientHandler: %s (via %s)>' % (self.client_id, self.addr)


class Server(object):
    client_handler_class = ClientHandler

    def __init__(self, loop, port=3000, host=None):
        self.clients = set()
        self.loop = loop
        self.host = host
        self.port = port
        self.stream_server = None

    def start(self):
        server = self.loop.run_until_complete(
            asyncio.streams.start_server(self._accept_client, host=self.host, port=self.port, loop=self.loop)
        )
        self.stream_server = server

    def client_disconnected(self, client):
        if client in self.clients:
            self.clients.discard(client)
            self.handle_client_disconnected(client)

    def client_connected(self, client):
        self.clients.add(client)
        self.handle_client_connected(client)

    async def _accept_client(self, reader, writer):
        client = self.client_handler_class(self, reader, writer)
        self.loop.create_task(client.start())

    def get_server_info(self, client):
        return {}

    def get_client_secret(self, client_id):
        raise NotImplemented

    def handle_client_disconnected(self, client):
        pass

    def handle_client_connected(self, client):
        pass
