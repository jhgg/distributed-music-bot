import inspect
import json
import struct
import time

import asyncio
import traceback
from collections import deque

PACKET_SIZE_STRUCT = struct.Struct('!I')


def s(b_or_s):
    if isinstance(b_or_s, bytes):
        return b_or_s.decode('utf-8')

    return b_or_s


def b(b_or_s):
    if isinstance(b_or_s, str):
        return bytes(b_or_s, encoding='utf-8')

    return b_or_s


class HandshakeError(Exception):
    pass


class CallException(Exception):
    pass


class CallExceptionNotFound(CallException):
    pass


class CallExceptionTimeout(CallException):
    pass


class CallExceptionDown(CallException):
    pass


class CallExceptionUnknown(CallException):
    pass


class ClientBase(object):
    heartbeat_interval = 30
    handshake_timeout = 15

    def __init__(self, loop, reader=None, writer=None):
        self.loop = loop
        self.writer = writer
        self.reader = reader
        self.remote_info = None

        self._ping_was_ponged = False
        self._ping_loop_task = None
        self._main_loop_task = None
        self._ref_seq = 0
        self._ref_futures = {}
        self._last_ping_time = 0
        self._pings = deque(maxlen=15)

    async def write_packet(self, op, data, drain=False):
        serialized_data = json.dumps({"op": op, "d": data})
        data_len = len(serialized_data)
        packet = PACKET_SIZE_STRUCT.pack(data_len) + bytes(serialized_data, encoding='utf-8')
        self.writer.write(packet)

        if drain:
            await self.writer.drain()

    async def _read_packet(self):
        packet_len_data = await self.reader.readexactly(PACKET_SIZE_STRUCT.size)
        packet_len, = PACKET_SIZE_STRUCT.unpack(packet_len_data)
        packet = await self.reader.readexactly(packet_len)
        data = json.loads(str(packet, encoding='utf-8'))
        return data['op'], data['d']

    async def next_packet(self, *expected_opcodes):
        opcode, data = await self._read_packet()
        if expected_opcodes and opcode not in expected_opcodes:
            raise ValueError("Was expecting opcodes %r, but got %s" % (expected_opcodes, opcode))

        if len(expected_opcodes) == 1:
            return data

        return opcode, data

    async def _main_loop(self):
        close_reason = None

        self._start_ping_loop()

        try:
            self._maybe_task(self.handle_ready(self.remote_info))

            while True:
                op, data = await self.next_packet()
                if not await self._handle_internal(op, data):
                    await self.handle_info(op, data)

        except asyncio.IncompleteReadError:
            close_reason = 'IncompleteReadError'

        except asyncio.CancelledError:
            if not self._ping_was_ponged:
                close_reason = 'Ping Timeout'

        except Exception as e:
            close_reason = str(e)

        finally:
            self._main_loop_task = None
            self._stop_ping_loop()
            self._kill_futures()
            self._maybe_task(self.handle_close(reason=close_reason))

    def start_main_loop(self):
        self._main_loop_task = self.loop.create_task(self._main_loop())
        return self._main_loop_task

    def stop_main_loop(self):
        if self._main_loop_task:
            self._main_loop_task.cancel()
            self._main_loop_task = None

    def _start_ping_loop(self):
        self._ping_loop_task = self.loop.create_task(self._ping_loop())

    def _stop_ping_loop(self):
        if self._ping_loop_task:
            self._ping_loop_task.cancel()
            self._ping_loop_task = None

    async def _ping_loop(self):
        self._ping_was_ponged = True

        try:
            while True:
                if not self._ping_was_ponged:
                    await self.handle_ping_timeout()
                    return

                else:
                    self._last_ping_time = time.time()
                    await self.write_packet("ping", True)

                await asyncio.sleep(self.heartbeat_interval)

        except asyncio.CancelledError:
            pass

        finally:
            self._ping_loop_task = None

    def _maybe_task(self, maybe_awaitable):
        if asyncio.iscoroutine(maybe_awaitable):
            self.loop.create_task(maybe_awaitable)

    async def _handle_internal(self, opcode, data):
        if opcode == "ping":
            await self.write_packet("pong", data)
            return True

        elif opcode == "pong":
            self._ping_was_ponged = True
            latest_latency = time.time() - self._last_ping_time
            self._pings.append(latest_latency)
            self._maybe_task(self.handle_pong(latest_latency))
            return True

        if opcode == 'call':
            self.handle_call(data)
            return True

        if opcode == 'call:response':
            self.handle__call_response(data)
            return True

        if opcode == 'cast':
            self.handle_cast(data)
            return True

    async def handle_ping_timeout(self):
        self.stop_main_loop()
        print("ping timeout")

    async def handle_info(self, op, data):
        print("unknown packet", op, data)

    def get_handler(self, handler_type, handler_name):
        handler_fn_name = 'handle_%s_%s' % (handler_type, handler_name)
        return getattr(self, handler_fn_name, None)

    def handle_call(self, data):
        handler = self.get_handler('call', data['f'])
        if handler:
            self.loop.create_task(self.do_call(handler, data['ref'], data['args'], data['kwargs']))
        else:
            self.loop.create_task(self.write_packet('call:response', {"ref": data['ref'], "exception": "not_exists"}))

    def handle_cast(self, data):
        handler = self.get_handler('cast', data['f'])
        if handler:
            self.loop.create_task(self.do_cast(handler, data['args'], data['kwargs']))
        else:
            print("no handler for", data['f'])

    async def do_call(self, handler, ref, args, kwargs):
        try:
            result = handler(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result

            self.loop.create_task(self.write_packet('call:response', {"ref": ref, "result": result}))

        except Exception as e:
            traceback.print_exc()
            self.loop.create_task(self.write_packet('call:response', {"ref": ref, "exception": {"message": str(e)}}))

    async def do_cast(self, handler, args, kwargs):
        try:
            result = handler(*args, **kwargs)
            if inspect.isawaitable(result):
                await result

        except Exception:
            traceback.print_exc()

    def call(self, f, *args, **kwargs):
        if not self._main_loop_task:
            raise CallException("Trying to call on not connected client.")

        ref_seq = self._ref_seq
        self._ref_seq += 1
        timeout = kwargs.pop('_timeout', None)

        self.loop.create_task(self.write_packet('call', {
            'f': f,
            'ref': ref_seq,
            'args': args,
            'kwargs': kwargs
        }))
        fut = asyncio.Future()
        timeout_handle = None
        if timeout is not None:
            timeout_handle = self.loop.call_later(timeout, self.handle__call_timeout, ref_seq)

        self._ref_futures[ref_seq] = f, fut, timeout_handle
        return fut

    def cast(self, f, *args, **kwargs):
        self.loop.create_task(self.write_packet('cast', {
            'f': f,
            'args': args,
            'kwargs': kwargs
        }))

    def handle__call_response(self, data):
        ref = data['ref']
        f = self._ref_futures.pop(ref, None)
        if not f:
            print("no future found oh well.")

        else:
            func, future, timeout_handle = f
            if timeout_handle:
                timeout_handle.cancel()

            if 'result' in data:
                future.set_result(data['result'])
                return

            exception = data.pop('exception', 'not_exists')
            if exception == 'unknown':
                exception = CallExceptionUnknown()

            elif exception == 'not_exists':
                exception = CallExceptionNotFound(func)

            else:
                exception = CallException(exception['message'])

            future.set_exception(exception)

    def handle__call_timeout(self, ref_seq):
        f = self._ref_futures.pop(ref_seq, None)
        if not f:
            print("call timeout cancelling nonexistent ref")

        func, future, timeout_handle = f
        future.set_exception(CallExceptionTimeout(func))

    def _kill_futures(self):
        futures = self._ref_futures
        self._ref_futures = {}

        for func, future, timeout_handle in futures.values():
            if timeout_handle:
                timeout_handle.cancel()

            future.set_exception(CallExceptionDown(func))

    def handle_close(self, reason=None):
        pass

    def handle_ready(self, remote_info):
        pass

    def handle_pong(self, latest_latency):
        pass

    @property
    def latest_ping(self):
        if self._pings:
            return self._pings[-1]

        return 0
