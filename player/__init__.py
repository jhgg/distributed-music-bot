from syncer.voice_syncer import VoiceStateSyncer


class Playlist(object):
    def __init__(self, player_state):
        self.syncer = player_state.syncer


class PlayerState(object):
    def __init__(self, bot):
        self.bot = bot
        self.syncer = VoiceStateSyncer(self).start()
        self.playlist = Playlist(self)

_player_states = {}


def get_player_state(server, bot=None, create=False):
    state = _player_states.get(server.id)
    if state is None and create:
        assert bot
        state = PlayerState(bot)
        _player_states[server.id] = state

    return state