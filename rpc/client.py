import asyncio
import asyncio.streams
import codecs
import hashlib
import hmac
import os

from rpc.base import s, b, ClientBase, HandshakeError


class Client(ClientBase):
    def __init__(self, loop, host: str, port: int, client_id: str, client_secret: str):
        super(Client, self).__init__(loop)
        self.host = host
        self.port = port
        self.client_id = client_id
        self.client_secret = client_secret

    async def do_handshake(self):
        # Prove we are who we say we are by signing the client_id using the client_secret.
        client_nonce = codecs.encode(os.urandom(32), 'hex')
        mac_payload = '%s:%s' % (s(self.client_id), s(client_nonce))
        mac_digest = hmac.new(b(self.client_secret), b(mac_payload), digestmod=hashlib.sha256).hexdigest()
        await self.write_packet("auth:login", {
            "client_id": s(self.client_id),
            "client_nonce": s(client_nonce),
            "digest": s(mac_digest),
        }, drain=True)

        op, data = await self.next_packet('auth:fail', 'auth:success')
        # The server doesn't recognize us, or our signed message.
        if op == 'auth:fail':
            raise HandshakeError(data['reason'])

        # The server generates a new digest the shared secret and the previous payload
        # to prove that it also knows the secret.
        server_digest = data.pop('digest')
        server_mac_payload = '%s:%s:%s' % (
            s(self.client_id),
            s(client_nonce),
            s(mac_digest)
        )
        expected_digest = hmac.new(b(self.client_secret), b(server_mac_payload), digestmod=hashlib.sha256).hexdigest()

        # We check it and let the server know we're happy.
        if not hmac.compare_digest(b(server_digest), b(expected_digest)):
            await self.write_packet('auth:fail', {"reason": "Server hash mismatch"}, drain=True)
            raise HandshakeError("Server hash mismatch")

        # Take the heartbeat interval from the server.
        self.heartbeat_interval = data.pop('heartbeat_interval', self.heartbeat_interval)

        # Send the server our info.
        await self.write_packet('auth:success', {"info": self.get_client_info()}, drain=True)

        # Return the server's info.
        return data['info']

    async def start(self):
        self.reader, self.writer = await asyncio.streams.open_connection(self.host, self.port, loop=self.loop)
        try:
            self.remote_info = await asyncio.wait_for(self.do_handshake(), self.handshake_timeout, loop=self.loop)
            await self.start_main_loop()
        finally:
            self.writer.close()

    def get_client_info(self):
        return {}
