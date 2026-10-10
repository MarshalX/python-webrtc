#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Events: on/once/off, delivery on the event loop, and states that change along with their events."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import gc
import threading
import weakref
from typing import TYPE_CHECKING, Literal

import pytest

import webrtc
from tests.helpers import QUIET_PERIOD, called, collect, connect, wait_for_event, wait_until
from webrtc.utils.loops import LoopState

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.mark.asyncio
async def test_on_decorator_once_and_off(pc: webrtc.RTCPeerConnection) -> None:
    """Handlers registered with the decorator and once are called, a handler removed with off isn't."""
    calls: list[tuple[object, ...]] = []

    @pc.on('negotiationneeded')
    def decorated(event: webrtc.Event) -> None:
        calls.append(('decorated', event.type, event.target is pc))

    def once(event: webrtc.Event) -> None:
        calls.append(('once', event.type))

    def removed(_event: webrtc.Event) -> None:
        calls.append(('removed',))

    pc.once('negotiationneeded', once)
    pc.on('negotiationneeded', removed)
    pc.off('negotiationneeded', removed)

    pc.add_transceiver(webrtc.MediaType.audio)
    await wait_for_event(pc, 'negotiationneeded')

    assert ('decorated', 'negotiationneeded', True) in calls
    assert ('once', 'negotiationneeded') in calls
    assert ('removed',) not in calls


@pytest.mark.asyncio
async def test_async_handlers_run_as_tasks(pc: webrtc.RTCPeerConnection) -> None:
    """A coroutine function handler is run as a task on the loop."""
    done = asyncio.get_running_loop().create_future()

    @pc.on('negotiationneeded')
    async def handler(event: webrtc.Event) -> None:
        await asyncio.sleep(0)
        if not done.done():
            done.set_result(event.type)

    pc.create_data_channel('events')
    assert await asyncio.wait_for(done, 5) == 'negotiationneeded'


@pytest.mark.asyncio
async def test_listeners_and_their_removal(pc: webrtc.RTCPeerConnection) -> None:
    """Listing and removing handlers."""

    def first(_event: webrtc.Event) -> None: ...

    def second(_event: webrtc.Event) -> None: ...

    def on_track(_event: webrtc.RTCTrackEvent) -> None: ...

    assert pc.event_names() == set()
    assert pc.listeners('negotiationneeded') == []

    _ = pc.on('negotiationneeded', first)
    _ = pc.once('negotiationneeded', second)
    _ = pc.on('negotiationneeded', first)  # no duplicates
    _ = pc.on('track', on_track)
    assert pc.listeners('negotiationneeded') == [first, second]
    assert pc.event_names() == {'negotiationneeded', 'track'}

    pc.add_transceiver(webrtc.MediaType.audio)
    _ = await wait_for_event(pc, 'negotiationneeded')
    assert pc.listeners('negotiationneeded') == [first]

    _ = pc.on('negotiationneeded', second)
    pc.remove_listener('negotiationneeded', first)
    assert pc.listeners('negotiationneeded') == [second]
    pc.remove_all_listeners('negotiationneeded')
    assert pc.event_names() == {'track'}

    _ = pc.on('negotiationneeded', first)
    pc.off()
    assert pc.event_names() == set()
    assert pc.listeners('track') == []

    _ = pc.on('negotiationneeded', first)
    pc.remove_all_listeners()
    assert pc.event_names() == set()


@pytest.mark.asyncio
async def test_off_everything_stops_delivery(pc: webrtc.RTCPeerConnection) -> None:
    """off() removes every handler."""
    calls: list[str] = []
    _ = pc.on('negotiationneeded', lambda event: calls.append(event.type))
    _ = pc.on('signalingstatechange', lambda event: calls.append(event.type))
    pc.off()

    pc.add_transceiver(webrtc.MediaType.audio)
    await pc.set_local_description(await pc.create_offer())
    await asyncio.sleep(QUIET_PERIOD)
    assert calls == []


def test_event_names_come_from_the_literal() -> None:
    """Event names come from the Literal parameter."""
    assert webrtc.MediaStream._events == ('addtrack', 'removetrack')
    assert set(webrtc.RTCPeerConnection._events) == {
        'negotiationneeded',
        'signalingstatechange',
        'iceconnectionstatechange',
        'icegatheringstatechange',
        'connectionstatechange',
        'icecandidate',
        'icecandidateerror',
        'track',
        'datachannel',
    }
    assert webrtc.MediaStreamTrackProcessor._events == ()


@pytest.mark.parametrize('method', ['listeners', 'remove_all_listeners', 'off'])
def test_unknown_event_in_removal(pc: webrtc.RTCPeerConnection, method: str) -> None:
    """Unknown events are rejected."""
    with pytest.raises(ValueError, match="no event 'nosuchevent'"):
        getattr(pc, method)('nosuchevent')


def test_unknown_event(pc: webrtc.RTCPeerConnection) -> None:
    """Registering a handler of an event the object doesn't have is a ValueError."""
    with pytest.raises(ValueError, match="no event 'nosuchevent'"):
        pc.on('nosuchevent', lambda _: None)  # pyrefly: ignore[no-matching-overload, implicit-any-lambda]


def test_handlers_need_a_running_loop(pc: webrtc.RTCPeerConnection) -> None:
    """Handlers are called on the loop they were registered from, so registering needs a running loop."""
    with pytest.raises(RuntimeError):
        pc.on('track', lambda _: None)


@pytest.mark.asyncio
async def test_signaling_state_changes_with_its_event(pc: webrtc.RTCPeerConnection) -> None:
    """Every signalingstatechange event sees its state, and comes before the operation that changed it resolves."""
    states: list[webrtc.RTCSignalingState] = []

    def on_change(_event: webrtc.Event) -> None:
        states.append(pc.signaling_state)

    pc.on('signalingstatechange', on_change)
    pc.add_transceiver(webrtc.MediaType.audio)

    await pc.set_local_description()
    assert states == [webrtc.RTCSignalingState.have_local_offer]
    await pc.set_local_description(webrtc.RTCSessionDescriptionInit('rollback'))
    assert states == [webrtc.RTCSignalingState.have_local_offer, webrtc.RTCSignalingState.stable]


@pytest.mark.asyncio
async def test_closed_connection_emits_nothing(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Closing a connection changes its states without emitting their events."""
    events: list[str] = []

    def on_event(event: webrtc.Event) -> None:
        events.append(event.type)

    for name in ('connectionstatechange', 'iceconnectionstatechange', 'signalingstatechange'):
        caller.on(name, on_event)

    caller.create_data_channel('media')
    await connect(caller, callee)
    events.clear()
    caller.close()
    callee.close()
    await asyncio.sleep(QUIET_PERIOD)

    assert events == []
    assert caller.connection_state == webrtc.RTCPeerConnectionState.closed


@pytest.mark.asyncio
async def test_ice_candidates_and_end_of_candidates(pc: webrtc.RTCPeerConnection) -> None:
    """Candidates are parsed, each transport ends with an empty one, and the final None adds a=end-of-candidates."""
    candidates: list[webrtc.RTCIceCandidate | None] = []

    def on_candidate(event: webrtc.RTCPeerConnectionIceEvent) -> None:
        candidates.append(event.candidate)

    def end_of_candidates(event: webrtc.Event) -> bool:
        assert isinstance(event, webrtc.RTCPeerConnectionIceEvent)
        return event.candidate is None

    pc.on('icecandidate', on_candidate)
    gathered = wait_for_event(pc, 'icecandidate', predicate=end_of_candidates)
    pc.add_transceiver(webrtc.MediaType.audio)
    await pc.set_local_description()
    await gathered

    host = [c for c in candidates if c is not None and c.candidate != '']
    assert len(host) > 0, candidates
    assert all(c.type is not None for c in host), candidates
    assert any(c is not None and c.candidate == '' for c in candidates), candidates
    assert pc.local_description is not None
    assert 'a=end-of-candidates' in pc.local_description.sdp, pc.local_description.sdp


@pytest.mark.asyncio
async def test_descriptions_change_with_signaling_events(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """An offer received in have-local-offer rolls back first: each signalingstatechange sees its descriptions."""
    await caller.set_local_description(await caller.create_offer())
    seen: list[dict[str, object]] = []

    def on_change(_event: webrtc.Event) -> None:
        seen.append({
            'state': caller.signaling_state,
            'local': caller.pending_local_description,
            'remote': caller.pending_remote_description,
        })

    caller.on('signalingstatechange', on_change)
    await caller.set_remote_description(await callee.create_offer())

    rolled_back, received = seen
    assert rolled_back == {'state': webrtc.RTCSignalingState.stable, 'local': None, 'remote': None}
    assert received['state'] == webrtc.RTCSignalingState.have_remote_offer
    assert received['local'] is None
    remote = received['remote']
    assert isinstance(remote, webrtc.RTCSessionDescription)
    assert remote.type == webrtc.RTCSdpType.offer


@pytest.mark.asyncio
async def test_restart_ice_before_negotiation_needs_nothing(pc: webrtc.RTCPeerConnection) -> None:
    """restart_ice before the first negotiation doesn't fire negotiationneeded."""
    events: list[webrtc.Event] = []
    pc.on('negotiationneeded', events.append)
    pc.restart_ice()
    await asyncio.sleep(QUIET_PERIOD)
    assert events == []


class _LoopObjects:
    """The objects of the first loop, used from the second."""

    caller: webrtc.RTCPeerConnection
    callee: webrtc.RTCPeerConnection
    channel: webrtc.RTCDataChannel


def test_objects_used_from_another_loop_see_their_events() -> None:
    """Once its first loop is closed, an object is updated on the loop of its handlers."""
    objects = _LoopObjects()

    async def first() -> None:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        channel = caller.create_data_channel('loops')
        opened = wait_for_event(channel, 'open')
        await connect(caller, callee)
        await opened
        objects.caller, objects.callee, objects.channel = caller, callee, channel

    async def second() -> None:
        channel = objects.channel
        closed = wait_for_event(channel, 'close')
        objects.callee.close()
        await closed
        assert channel.ready_state == webrtc.RTCDataChannelState.closed
        objects.caller.close()

    asyncio.run(first())
    asyncio.run(second())


@pytest.mark.asyncio
async def test_event_after_its_wrapper_died_still_changes_the_state(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Events update a recreated wrapper."""
    channel = caller.create_data_channel('views')
    opened = wait_for_event(channel, 'open')
    await connect(caller, callee)
    await opened
    native = channel._native_obj
    ref = weakref.ref(channel)
    del channel
    collect()
    assert ref() is None

    callee.close()
    await wait_until(
        lambda: webrtc.RTCDataChannel._wrap(native).ready_state == webrtc.RTCDataChannelState.closed,
        'the close event to reach the channel',
    )


@contextlib.contextmanager
def _loop_in_a_thread() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        yield loop
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(5)
        loop.close()


def _register_from(
    loop: asyncio.AbstractEventLoop,
    target: webrtc.RTCDataChannel,
    name: Literal['open', 'close'],
    *,
    seen: list[asyncio.AbstractEventLoop],
) -> None:
    """Records the loop a handler runs on, from another thread."""
    registered: concurrent.futures.Future[None] = concurrent.futures.Future()

    def record(_event: webrtc.Event) -> None:
        seen.append(asyncio.get_running_loop())

    def register() -> None:
        target.on(name, record)
        registered.set_result(None)

    loop.call_soon_threadsafe(register)
    registered.result(5)


def test_handlers_on_two_loops() -> None:
    """Handlers run on their own loops."""
    seen: list[asyncio.AbstractEventLoop] = []

    async def main() -> asyncio.AbstractEventLoop:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        channel = caller.create_data_channel('loops')
        opened = wait_for_event(channel, 'open')
        channel.on('close', lambda _event: seen.append(asyncio.get_running_loop()))
        _register_from(other, channel, 'close', seen=seen)
        await connect(caller, callee)
        await opened
        callee.close()
        await wait_until(lambda: len(seen) == 2, 'the close event on both loops')
        caller.close()
        return asyncio.get_running_loop()

    with _loop_in_a_thread() as other:
        main_loop = asyncio.run(main())
    assert sorted(seen, key=id) == sorted([main_loop, other], key=id)


def test_handler_registered_from_another_loop_than_the_binding_loop() -> None:
    """Forwards to a handler on another loop."""
    seen: list[asyncio.AbstractEventLoop] = []

    async def main() -> None:
        caller, callee = webrtc.RTCPeerConnection(), webrtc.RTCPeerConnection()
        channel = caller.create_data_channel('elsewhere')
        _register_from(other, channel, 'open', seen=seen)
        await connect(caller, callee)
        await wait_until(lambda: len(seen) == 1, 'the open event on the other loop')
        caller.close()
        callee.close()

    with _loop_in_a_thread() as other:
        asyncio.run(main())
    assert seen == [other]


@pytest.mark.asyncio
async def test_off_from_a_handler(pc: webrtc.RTCPeerConnection) -> None:
    """Removing all handlers mid-dispatch stops delivery."""
    calls: list[str] = []

    def first(_event: webrtc.Event) -> None:
        calls.append('first')
        pc.off()

    def second(_event: webrtc.Event) -> None:
        calls.append('second')

    pc.on('negotiationneeded', first)
    pc.on('negotiationneeded', second)
    pc.on('signalingstatechange', lambda event: calls.append(event.type))
    pc.add_transceiver(webrtc.MediaType.audio)
    await wait_until(lambda: len(calls) > 0, 'the first handler')
    await pc.set_local_description()
    await asyncio.sleep(QUIET_PERIOD)
    assert calls == ['first']
    assert pc.event_names() == set()


@pytest.mark.asyncio
async def test_async_handler_exception_goes_to_the_loop(pc: webrtc.RTCPeerConnection) -> None:
    """An async handler's exception reaches the loop's exception handler."""
    loop = asyncio.get_running_loop()
    reported = loop.create_future()
    loop.set_exception_handler(lambda _loop, context: reported.done() or reported.set_result(context))
    try:

        @pc.on('negotiationneeded')
        async def handler(_event: webrtc.Event) -> None:
            await asyncio.sleep(0)
            msg = 'handler'
            raise ValueError(msg)

        pc.create_data_channel('events')
        context = await asyncio.wait_for(reported, 5)
        assert context['message'] == "Exception in 'negotiationneeded' event handler"
        assert isinstance(context['exception'], ValueError)
        assert isinstance(context['event'], webrtc.Event)
    finally:
        loop.set_exception_handler(None)


@pytest.mark.asyncio
async def test_handler_removed_during_dispatch_is_skipped(pc: webrtc.RTCPeerConnection) -> None:
    """A handler removed mid-dispatch is skipped."""
    calls: list[str] = []

    def first(_event: webrtc.Event) -> None:
        calls.append('first')
        pc.off('negotiationneeded', second)

    def second(_event: webrtc.Event) -> None:
        calls.append('second')

    pc.on('negotiationneeded', first)
    pc.on('negotiationneeded', second)
    negotiation = wait_for_event(pc, 'negotiationneeded')
    _ = pc.add_transceiver(webrtc.MediaType.audio)
    _ = await negotiation
    await asyncio.sleep(QUIET_PERIOD)
    assert calls == ['first']


class _CollectingHandler:
    """A handler whose comparison runs gc under the handlers lock."""

    def __call__(self, _event: webrtc.Event) -> None:
        pass

    def __eq__(self, other: object) -> bool:
        gc.collect()
        return self is other

    __hash__ = object.__hash__


def _from_a_closed_loop(_event: webrtc.Event) -> None:
    pass


def test_handlers_updated_while_the_collector_releases_a_loop() -> None:
    """GC release under on()/off() loses no update."""
    pc = webrtc.RTCPeerConnection()
    loop = asyncio.new_event_loop()
    # this loop's state exists, so registering sweeps nothing
    _ = LoopState.of(loop)

    def register() -> None:
        pc.on('connectionstatechange', _from_a_closed_loop)

    def update() -> None:
        handler = _CollectingHandler()
        # comparing with the closed loop's handler releases that loop mid-registration
        pc.on('connectionstatechange', handler)
        assert pc.listeners('connectionstatechange') == [handler]
        pc.off('connectionstatechange', handler)
        assert pc.listeners('connectionstatechange') == []

    try:
        # the closed loop's state stays until a sweep
        asyncio.run(called(register))
        gc.disable()
        try:
            loop.run_until_complete(called(update))
        finally:
            gc.enable()
    finally:
        loop.close()
        pc.close()
