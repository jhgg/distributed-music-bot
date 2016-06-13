from copy import copy
import asyncio

from lib.event_emitter import EventEmitter
from time import time

class SyncerState(object):
    AWAITING_CLIENT = "AWAITING CLIENT"
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    HALT = "HALT"


class VoiceStateSyncer(EventEmitter):
    def __init__(self, player_state):
        super(VoiceStateSyncer, self).__init__()

        self.state = dict(
            fsm_state=SyncerState.DISCONNECTED,
            volume=1.0,
            playback_started_timestamp=None,
            playback_progress=None,
            playback_ref=None,
            client=None
        )

        self.bot = player_state.bot
        self._loop_task = None
        self._queue = asyncio.Queue()

    def start(self):
        if not self._loop_task:
            self._loop_task = self.bot.loop.create_task(self.main_loop())

        return self

    def send(self, op, **data):
        message = dict(op=op, **data)
        self.bot.loop.call_soon(self._queue.put_nowait, message)

    async def main_loop(self):
        try:
            while True:
                item = await self._queue.get()
                prev_state = copy(self.state)
                # Prev State -> Update -> Next State -> Did Update -> Final State
                next_state = await self.state_update(prev_state, item)
                self.state = await self.state_did_update(prev_state, next_state)

                if self.state['fsm_state'] == SyncerState.HALT:
                    return

        finally:
            self._loop_task = None

    async def state_did_update(self, prev_state, next_state):
        fsm_state = next_state.get('fsm_state')

        if fsm_state == SyncerState.AWAITING_CLIENT:
            return await self.state_do_connect(prev_state, next_state)

        elif fsm_state == SyncerState.CONNECTED:
            return await self.state_do_sync(prev_state, next_state)

        elif fsm_state == SyncerState.HALT:
            return await self.state_do_halt(prev_state, next_state)

        return next_state

    @staticmethod
    async def state_update(state, data):
        op = data['op']
        if op == 'connect':
            return dict(state, channel=data['channel'], fsm_state=SyncerState.AWAITING_CLIENT)

        if op == 'down':
            return dict(state, client=None, fsm_state=SyncerState.AWAITING_CLIENT)

        if op == 'play':
            return dict(state, playing_url=data['url'], playback_progress=0)

        if op == 'stop':
            return dict(state, playing_url=None, playback_started_timestamp=None)

        if op == 'volume':
            return dict(state, volume=data['volume'])

        if op == 'playback_progress':
            if data['playback_ref'] == state['playback_ref']:
                return dict(state, playback_started_timestamp=time() - data['playback_progress'])

            return state

        if op == 'halt':
            return dict(state, fsm_state=SyncerState.HALT)

        return state

    async def state_do_connect(self, prev_state, next_state):
        # FSM Wants a client, so let's try and get one.

        timeout = next_state.pop('timeout', None)
        if timeout:
            timeout.cancel()

        old_client = next_state.pop('client', None)
        if old_client:
            await old_client.disconnect()

        client = await self.bot.join_voice_channel(next_state['channel'])

        if client:
            client.once('remote:down', self._down)
            client.on('playback:progress', self._sync_playback_progress)
            self.emit('client:connected', client)
            return await self.state_do_sync(
                prev_state,
                dict(next_state, client=client, playback_ref=None, fsm_state=SyncerState.CONNECTED)
            )

        timeout = self.bot.loop.call_later(2, self.send, 'progress')
        return dict(next_state, timeout=timeout)

    @staticmethod
    async def state_do_halt(prev_state, next_state):
        # FSM is getting ready to halt. Stop all the things.
        timeout = next_state.pop('timeout', None)
        if timeout:
            timeout.cancel()

        old_client = next_state.pop('client', None)
        if old_client:
            await old_client.disconnect()

        return next_state

    @staticmethod
    async def state_do_sync(prev_state, next_state):
        # FSM Wants us to sync the state.
        prev_url = prev_state.get('playing_url')
        next_url = next_state.get('playing_url')
        next_volume = next_state.get('volume')
        client = next_state['client']

        # We don't have a URL, so we should stop.
        if not next_url and prev_url:
            await client.stop()
            return dict(next_state, playing_url=None, playback_ref=None)

        is_new_client = prev_state.get('client') != client
        # We have a next url, or the client changed, so we should tell the client to play the new URL.
        if next_url and (prev_url != next_url or is_new_client):
            if not is_new_client:
                estimated_progress = 0
            else:
                estimated_progress = time() - (next_state.get('playback_started_timestamp', None) or time())

            playback_ref = await client.play(next_volume, next_url, estimated_progress)
            new_state = dict(next_state, playback_ref=playback_ref)

            if not is_new_client:
                new_state['playback_started_timestamp'] = time()

            return new_state

        prev_volume = prev_state.get('volume')
        if prev_volume != next_volume:
            await client.set_volume(next_volume)

        return next_state

    def connect(self, channel):
        self.send('connect', channel=channel)

    def play(self, url):
        self.send('play', url=url)

    def volume(self, volume):
        self.send('volume', volume=volume)

    def stop(self):
        self.send('stop')

    def _down(self, reason=None):
        self.send('down')

    def _sync_playback_progress(self, playback_ref, playback_progress):
        self.send('playback_progress', playback_ref=playback_ref, playback_progress=playback_progress)

    def disconnect(self):
        self.send('halt')

    @property
    def fsm_state(self):
        return self.state['fsm_state']

    @property
    def playback_ref(self):
        return self.state.get('playback_ref')

    @property
    def estimated_progress(self):
        return time() - (self.state.get('playback_started_timestamp', None) or time())