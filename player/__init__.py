from syncer.voice_syncer import VoiceStateSyncer


class Playlist(object):
    def __init__(self, player_state):
        self.player_state = player_state
        self.syncer = player_state.syncer
        self.syncer.on('client:connected', self._handle_client_connected)

    def _handle_client_connected(self, remote_client):
        # We should never capture the client here. All interaction with the client will be done via the syncer.
        remote_client.on('playback:start', self._handle_playback_start)
        remote_client.on('playback:done', self._handle_playback_done)
        remote_client.on('playback:progress', self._handle_playback_progress)
        remote_client.once('remote:down', self._handle_remote_down)

        self.player_state.say('Voice client connected %r' % remote_client)

    def _handle_playback_start(self, playback_ref):
        print("playback start", playback_ref)
        self.player_state.say('Voice client playback start %r' % playback_ref)

    def _handle_playback_done(self, playback_ref):
        print("playback stop", playback_ref)
        self.player_state.say('Voice client playback stop %r' % playback_ref)

    def _handle_remote_down(self, reason=None):
        self.player_state.say('Remote client split, reason: %s' % reason)

    def _handle_playback_progress(self, playback_ref, progress):
        pass


class PlayerState(object):
    def __init__(self, bot):
        self.bot = bot
        self.syncer = VoiceStateSyncer(self).start()
        self.playlist = Playlist(self)
        self.channel = None

    def say(self, message):
        if self.channel:
            self.bot.loop.create_task(self.bot.send_message(self.channel, message))

_player_states = {}


def get_player_state(server, bot=None, create=False):
    state = _player_states.get(server.id)
    if state is None and create:
        assert bot
        state = PlayerState(bot)
        _player_states[server.id] = state

    return state