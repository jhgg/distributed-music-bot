import asyncio
import discord
import discord.ext.commands


class Client(discord.Client):
    ## This works for now but is not ideal. The shim works though.
    @asyncio.coroutine
    def join_voice_channel(self, channel):
        if isinstance(channel, discord.Object):
            channel = self.get_channel(channel.id)

        if getattr(channel, 'type', discord.ChannelType.text) != discord.ChannelType.voice:
            raise discord.InvalidArgument('Channel passed must be a voice channel')

        server = channel.server

        if self.is_voice_connected(server):
            raise discord.ClientException('Already connected to a voice channel in this server')

        proxy = yield from self.rpc_server.make_voice_client_proxy(str(server.region))

        # log.info('attempting to join voice channel {0.name}'.format(channel))

        def session_id_found(data):
            user_id = data.get('user_id')
            return user_id == self.user.id

        # register the futures for waiting
        session_id_future = self.ws.wait_for('VOICE_STATE_UPDATE', session_id_found)
        voice_data_future = self.ws.wait_for('VOICE_SERVER_UPDATE', lambda d: True)

        # request joining
        yield from self.ws.voice_state(server.id, channel.id)
        session_id_data = yield from asyncio.wait_for(session_id_future, timeout=10.0, loop=self.loop)
        data = yield from asyncio.wait_for(voice_data_future, timeout=10.0, loop=self.loop)

        kwargs = {
            'user_id': self.user.id,
            'channel': channel,
            'data': data,
            'loop': self.loop,
            'session_id': session_id_data.get('session_id'),
            'main_ws': self.ws
        }

        voice = yield from proxy(**kwargs)

        try:
            yield from voice.connect()

        except Exception as e:

            try:
                yield from voice.disconnect()
            except:
                # we don't care if disconnect failed because connection failed
                pass

            raise e # re-raise

        self.connection._add_voice_client(server.id, voice)
        return voice


class Bot(discord.ext.commands.Bot, Client):
    pass
