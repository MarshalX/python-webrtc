#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#

"""Data channels: opening, messages, closing, and their limits."""

from __future__ import annotations

import asyncio
import math
import re
import sys
from typing import Callable, cast

import pytest
from typing_extensions import TypedDict, Unpack

import webrtc
import wrtc
from tests.helpers import (
    connect,
    mistyped,
    stats_of_type,
    wait_for_event,
    wait_for_ice_gathering_complete,
    wait_until,
)
from tests.timing import seconds
from webrtc.utils import loops

#: The most a channel queues to send, in bytes
SEND_QUEUE_LIMIT = 16 * 1024 * 1024


class ChannelOptions(TypedDict, total=False, closed=True):
    """Options of RTCDataChannelInit the tests set."""

    max_packet_life_time: int
    max_retransmits: int
    protocol: str
    negotiated: bool
    id: int


class Negotiation(TypedDict, total=False, closed=True):
    """Whether a channel is negotiated, and its id."""

    negotiated: bool
    id: int


async def open_pair(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, **options: Unpack[ChannelOptions]
) -> tuple[webrtc.RTCDataChannel, webrtc.RTCDataChannel]:
    """Opens a channel of the caller and returns it with its remote end."""
    init = webrtc.RTCDataChannelInit(**options)
    channel = caller.create_data_channel('chat', init)
    if init.negotiated:
        remote = callee.create_data_channel('chat', init)
        opened = [wait_for_event(channel, 'open'), wait_for_event(remote, 'open')]
        await connect(caller, callee)
        await asyncio.gather(*opened)
        return channel, remote

    opened = wait_for_event(channel, 'open')
    announced = wait_for_event(callee, 'datachannel')
    await connect(caller, callee)
    event = await announced
    assert isinstance(event, webrtc.RTCDataChannelEvent)
    remote = event.channel
    await opened
    return channel, remote


@pytest.mark.asyncio
@pytest.mark.parametrize('options', [{}, {'negotiated': True, 'id': 3}], ids=['announced', 'negotiated'])
async def test_messages_both_ways(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, options: Negotiation
) -> None:
    """Both ends of an announced or negotiated channel have its options and id, and messages arrive in order."""
    channel, remote = await open_pair(caller, callee, protocol='proto', **options)

    assert remote.label == 'chat'
    assert remote.protocol == 'proto'
    assert channel.ready_state == remote.ready_state == webrtc.RTCDataChannelState.open
    assert channel.id == remote.id

    received: list[str | bytes | webrtc.Blob] = []
    got_all = asyncio.get_running_loop().create_future()

    @remote.on('message')
    def on_message(event: webrtc.MessageEvent) -> None:
        received.append(event.data)
        if len(received) == 3 and not got_all.done():
            got_all.set_result(None)

    channel.send('text')
    channel.send(b'\x00\x01')
    channel.send(bytearray(b'\x02'))
    await asyncio.wait_for(got_all, seconds(5))
    assert received == ['text', b'\x00\x01', b'\x02']


@pytest.mark.asyncio
async def test_buffered_amount_and_low_event(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A message sent is buffered until it's handed to SCTP, then bufferedamountlow is fired."""
    channel, _ = await open_pair(caller, callee)
    channel.buffered_amount_low_threshold = 0

    channel.send('hello')
    assert channel.buffered_amount == 5
    await wait_for_event(channel, 'bufferedamountlow')
    assert channel.buffered_amount == 0


@pytest.mark.asyncio
async def test_close_states_and_events(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Closing a channel makes it closing at once; the remote end fires closing then close, the local end nothing."""
    channel, remote = await open_pair(caller, callee)
    remote_events: list[tuple[str, webrtc.RTCDataChannelState]] = []

    def on_remote_closing(_event: webrtc.Event) -> None:
        remote_events.append(('closing', remote.ready_state))

    remote.on('closing', on_remote_closing)
    remote_closed = wait_for_event(remote, 'close')
    local_closing: list[webrtc.Event] = []
    channel.on('closing', local_closing.append)

    channel.close()
    assert channel.ready_state == webrtc.RTCDataChannelState.closing
    await remote_closed

    assert remote_events == [('closing', webrtc.RTCDataChannelState.closing)]
    assert remote.ready_state == webrtc.RTCDataChannelState.closed
    assert local_closing == []
    with pytest.raises(webrtc.InvalidStateError):
        channel.send('late')


@pytest.mark.asyncio
async def test_remote_connection_closed_fires_error(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """The remote close aborts the association with sctp-failure."""
    channel, _remote = await open_pair(caller, callee)
    events: list[webrtc.Event] = []
    channel.on('error', events.append)
    closed = wait_for_event(channel, 'close')

    callee.close()
    events.append(await closed)

    error_event, close_event = events
    assert isinstance(error_event, webrtc.RTCErrorEvent)
    assert error_event.type == 'error'
    assert isinstance(error_event.error, webrtc.RTCError)
    assert error_event.error.error_detail == webrtc.RTCErrorDetailType.sctp_failure
    # User-Initiated Abort (RFC 9260)
    assert error_event.error.sctp_cause_code == 12
    assert repr(error_event).startswith("RTCErrorEvent(type='error', error=RTCError(")
    assert close_event.type == 'close'
    assert channel.ready_state == webrtc.RTCDataChannelState.closed


races_remote_close = pytest.mark.skipif(
    sys.platform == 'win32', reason="libwebrtc's Windows socket server runs posted tasks after pending socket events"
)


def send_racing_remote_close(
    channel: webrtc.RTCDataChannel, remote: webrtc.RTCDataChannel, messages: list[str | bytes]
) -> None:
    """Sends once libwebrtc has the channel closing by the remote end, before its closing event is emitted."""
    wrtc._testing.park('datachannel.closing')
    try:
        remote.close()
        assert wrtc._testing.parked('datachannel.closing', seconds(10))
        # still open for Python, so libwebrtc fails these sends
        for message in messages:
            channel.send(message)
    finally:
        wrtc._testing.release('datachannel.closing')


@races_remote_close
@pytest.mark.asyncio
async def test_send_racing_a_remote_close_fires_error(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A send libwebrtc fails as the remote end closes fires error with data-channel-failure, then close."""
    channel, remote = await open_pair(caller, callee)
    unraisable: list[sys.UnraisableHookArgs] = []
    monkeypatch.setattr(sys, 'unraisablehook', unraisable.append)
    loop = asyncio.get_running_loop()
    reported: list[dict[str, object]] = []
    loop.set_exception_handler(lambda _loop, context: reported.append(context))
    try:
        events: list[webrtc.Event] = []
        channel.on('error', events.append)
        closed = wait_for_event(channel, 'close')

        send_racing_remote_close(channel, remote, ['late'])
        events.append(await closed)
    finally:
        loop.set_exception_handler(None)

    error_event, close_event = events
    assert isinstance(error_event, webrtc.RTCErrorEvent)
    assert isinstance(error_event.error, webrtc.RTCError)
    assert error_event.error.error_detail == webrtc.RTCErrorDetailType.data_channel_failure
    assert close_event.type == 'close'
    assert channel.ready_state == webrtc.RTCDataChannelState.closed
    assert reported == []
    assert unraisable == []


@races_remote_close
@pytest.mark.asyncio
async def test_buffered_amount_when_sends_race_a_remote_close(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """The bytes of sends libwebrtc fails stay in bufferedAmount, which libwebrtc never reports sent."""
    channel, remote = await open_pair(caller, callee)
    channel.send(b'drained')
    await wait_for_event(channel, 'bufferedamountlow')
    assert channel.buffered_amount == 0

    observed: list[tuple[str, int]] = []

    def observe(event: webrtc.Event) -> None:
        observed.append((event.type, channel.buffered_amount))

    for name in ('bufferedamountlow', 'closing', 'error'):
        channel.on(name, observe)
    closed = wait_for_event(channel, 'close')
    messages: list[str | bytes] = ['late', bytes(1000), 'é']
    pending = len('late') + 1000 + len('é'.encode())

    send_racing_remote_close(channel, remote, messages)
    assert channel.buffered_amount == pending
    observe(await closed)

    assert observed == [('closing', pending), ('error', pending), ('close', pending)]


@pytest.mark.asyncio
async def test_native_send_takes_only_bytes(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """The native send reads its data without the GIL, so it refuses a bytearray that could be resized meanwhile."""
    channel, _ = await open_pair(caller, callee)
    native = channel._native_obj
    for data in (bytearray(b'data'), 'data'):
        with pytest.raises(TypeError):
            native.send(data, binary=True)  # pyrefly: ignore[bad-argument-type]


@pytest.mark.asyncio
async def test_messages_round_trip(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Text and binary messages arrive unchanged, empty and as large as the SCTP transport takes."""
    channel, remote = await open_pair(caller, callee)
    assert caller.sctp is not None
    large = 256 * 1024
    max_message_size = caller.sctp.max_message_size
    assert max_message_size is not None
    assert max_message_size >= large
    messages: list[str | bytes] = [
        '',
        b'',
        'héllo, мир, 世界 🎉',
        bytes(range(256)) * (large // 256),
        'é' * (large // 2),
        '\x00text',
    ]
    received: list[str | bytes | webrtc.Blob] = []
    got_all = asyncio.get_running_loop().create_future()

    @remote.on('message')
    def on_message(event: webrtc.MessageEvent) -> None:
        received.append(event.data)
        if len(received) == len(messages) + 1 and not got_all.done():
            got_all.set_result(None)

    for message in messages:
        channel.send(message)
    # a lone surrogate becomes U+FFFD
    channel.send('a\ud800b')
    await asyncio.wait_for(got_all, seconds(10))
    assert received == [*messages, 'a\ufffdb']


@pytest.mark.parametrize(
    ('init', 'error'),
    [
        ({'max_packet_life_time': 1, 'max_retransmits': 1}, 'can not both be set'),
        ({'negotiated': True}, 'needs an id'),
        ({'negotiated': True, 'id': 65535}, 'id must be from 0 to 65534'),
        ({'id': 65536}, 'id must be from 0 to 65535'),
        ({'max_retransmits': -1}, 'max_retransmits must be from 0 to 65535'),
        ({'max_packet_life_time': 65536}, 'max_packet_life_time must be from 0 to 65535'),
        ({'protocol': 'x' * 65536}, 'protocol is longer than 65535 bytes'),
    ],
    ids=['both limits', 'negotiated without id', 'reserved id', 'id out of range', 'negative', 'too long', 'protocol'],
)
def test_invalid_data_channel_init(pc: webrtc.RTCPeerConnection, init: ChannelOptions, error: str) -> None:
    """Invalid options raise TypeError."""
    with pytest.raises(TypeError, match=error):
        pc.create_data_channel('x', webrtc.RTCDataChannelInit(**init))


def test_id_is_ignored_unless_negotiated(pc: webrtc.RTCPeerConnection) -> None:
    """The id of a channel that isn't negotiated is chosen once SCTP is up."""
    assert pc.create_data_channel('x', webrtc.RTCDataChannelInit(id=65535)).id is None


def test_label_too_long(pc: webrtc.RTCPeerConnection) -> None:
    """A label longer than 65535 bytes in UTF-8 raises TypeError."""
    with pytest.raises(TypeError, match='label is longer than 65535 bytes'):
        pc.create_data_channel('я' * 32768)


def test_id_taken(pc: webrtc.RTCPeerConnection) -> None:
    """Two negotiated channels can't have the same id."""
    pc.create_data_channel('taken', webrtc.RTCDataChannelInit(negotiated=True, id=1))
    with pytest.raises(webrtc.OperationError):
        pc.create_data_channel('again', webrtc.RTCDataChannelInit(negotiated=True, id=1))


def test_data_channel_options(pc: webrtc.RTCPeerConnection) -> None:
    """A new channel has its options and is connecting, and only sends text and bytes."""
    channel = pc.create_data_channel(
        'x', webrtc.RTCDataChannelInit(priority=webrtc.RTCPriorityType.high, ordered=False)
    )
    assert channel.priority == webrtc.RTCPriorityType.high
    assert channel.ordered is False
    assert channel.ready_state == webrtc.RTCDataChannelState.connecting
    with pytest.raises(TypeError):
        channel.send(mistyped(42))


@pytest.mark.parametrize(
    ('options', 'expected'),
    [
        ({}, (None, None, False)),
        ({'max_packet_life_time': 100}, (100, None, False)),
        ({'max_retransmits': 2}, (None, 2, False)),
        ({'negotiated': True, 'id': 1}, (None, None, True)),
    ],
    ids=['defaults', 'life time', 'retransmits', 'negotiated'],
)
def test_reliability_and_negotiated_reflect_the_init(
    pc: webrtc.RTCPeerConnection, options: ChannelOptions, expected: tuple[int | None, int | None, bool]
) -> None:
    """Unlimited and announced by default."""
    channel = pc.create_data_channel('x', webrtc.RTCDataChannelInit(**options))
    assert (channel.max_packet_life_time, channel.max_retransmits, channel.negotiated) == expected


def test_buffered_amount_low_threshold(pc: webrtc.RTCPeerConnection) -> None:
    """0 by default; keeps the value set."""
    channel = pc.create_data_channel('x')
    assert channel.buffered_amount_low_threshold == 0
    channel.buffered_amount_low_threshold = 1024
    assert channel.buffered_amount_low_threshold == 1024
    for value in (-1, 2**64):
        with pytest.raises(ValueError, match='buffered_amount_low_threshold'):
            channel.buffered_amount_low_threshold = value
    assert channel.buffered_amount_low_threshold == 1024


@pytest.mark.asyncio
async def test_close_twice(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Closing a closing channel does nothing."""
    channel, _ = await open_pair(caller, callee)
    channel.close()
    channel.close()
    assert channel.ready_state == webrtc.RTCDataChannelState.closing


@pytest.mark.asyncio
async def test_closed_in_the_datachannel_handler_never_opens(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """The queued open event is dropped when the handler closes the channel."""
    channel = caller.create_data_channel('chat')
    events: list[str] = []
    closed: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def on_datachannel(event: webrtc.RTCDataChannelEvent) -> None:
        remote = event.channel
        remote.close()
        remote.on('open', lambda _event: events.append(remote.ready_state))
        remote.on('close', lambda _event: closed.set_result(None))

    callee.on('datachannel', on_datachannel)
    remote_closed = wait_for_event(channel, 'close')
    await connect(caller, callee)
    await closed
    await remote_closed
    assert events == []


@pytest.mark.asyncio
async def test_messages_sent_on_open_reach_a_handler_added_on_datachannel(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """Messages that arrive before the remote channel is announced follow its datachannel event, in order."""
    channel = caller.create_data_channel('burst')
    count = 50
    channel.on('open', lambda _event: [channel.send(str(number)) for number in range(count)])
    received: list[str | bytes | webrtc.Blob] = []
    done: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def on_message(event: webrtc.MessageEvent) -> None:
        received.append(event.data)
        if len(received) == count:
            done.set_result(None)

    callee.on('datachannel', lambda event: event.channel.on('message', on_message))
    await connect(caller, callee)
    await asyncio.wait_for(done, seconds(10))
    assert received == [str(number) for number in range(count)]


@pytest.mark.asyncio
async def test_sent_from_the_datachannel_handler_before_libwebrtc_opens_it(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A send from the datachannel handler arrives, though libwebrtc opens the channel later."""
    opened = wait_for_event(caller.create_data_channel('setup'), 'open')
    announced = wait_for_event(callee, 'datachannel')
    for local, remote in ((caller, callee), (callee, caller)):
        await local.set_local_description()
        await wait_for_ice_gathering_complete(local)
        description = local.local_description
        assert description is not None
        await remote.set_remote_description(description)

    await asyncio.gather(opened, announced)

    # answered on the signaling thread, so it's past the setup channel's announcement

    await callee.get_stats()
    sent: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def send(event: webrtc.RTCDataChannelEvent) -> None:
        event.channel.send('early')
        sent.set_result(None)

    async def received() -> bool:
        report = await caller.get_stats()
        channels = cast('list[webrtc.RTCDataChannelStats]', stats_of_type(report, 'data-channel'))
        return any(stats.label == 'early' and stats.messages_received == 1 for stats in channels)

    callee.on('datachannel', send)
    wrtc._testing.park('connection.datachannel')
    try:
        # off the loop: creating it waits for the parked signaling thread too
        creating = asyncio.ensure_future(asyncio.to_thread(caller.create_data_channel, 'early'))
        await asyncio.wait_for(sent, seconds(10))
    finally:
        wrtc._testing.release('connection.datachannel')
    await creating
    await wait_until(received, 'the message')


@pytest.mark.asyncio
async def test_once_handles_the_first_message_only(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    channel, remote = await open_pair(caller, callee)
    first: list[str | bytes | webrtc.Blob] = []
    remote.once('message', lambda event: first.append(event.data))
    second = wait_for_event(remote, 'message', predicate=lambda e: isinstance(e, webrtc.MessageEvent) and e.data == 'b')

    channel.send('a')
    channel.send('b')
    await second
    assert first == ['a']
    assert 'message' not in remote.event_names()


@pytest.mark.asyncio
async def test_send_past_the_send_queue_limit(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """The send fails and the channel stays open."""
    channel, _ = await open_pair(caller, callee)
    assert caller.sctp is not None
    size = caller.sctp.max_message_size
    assert size is not None
    message = bytes(int(size))
    # the queue only drains in event loop tasks
    fitting = SEND_QUEUE_LIMIT // len(message)
    for _ in range(fitting):
        channel.send(message)

    with pytest.raises(webrtc.OperationError, match='send queue'):
        channel.send(message)
    assert channel.buffered_amount == fitting * len(message)
    assert channel.ready_state == webrtc.RTCDataChannelState.open


def test_create_data_channel_on_closed_connection(pc: webrtc.RTCPeerConnection) -> None:
    """A closed connection can't create channels."""
    pc.close()
    with pytest.raises(webrtc.InvalidStateError):
        pc.create_data_channel('x')


@pytest.mark.asyncio
async def test_max_message_size_before_an_answer(pc: webrtc.RTCPeerConnection) -> None:
    """The max message size is 65536 until an answer negotiates the max-message-size of the remote peer."""
    pc.create_data_channel('size')
    await pc.set_local_description()
    assert pc.sctp is not None
    assert pc.sctp.max_message_size == 65536


@pytest.mark.asyncio
async def test_max_message_size_kept_once_closed(pc: webrtc.RTCPeerConnection) -> None:
    """webrtc-pc: close() leaves [[MaxMessageSize]]."""
    pc.create_data_channel('size')
    await pc.set_local_description()
    sctp = pc.sctp
    assert sctp is not None
    size = sctp.max_message_size
    assert size is not None
    pc.close()
    assert sctp.max_message_size == size


@pytest.mark.asyncio
async def test_max_message_size_once_the_data_section_is_rejected(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A dropped transport keeps the max message size negotiated last."""
    caller.create_data_channel('size')
    await connect(caller, callee)
    sctp = callee.sctp
    assert sctp is not None
    assert sctp.max_message_size == 262144

    offer = await caller.create_offer()
    await callee.set_remote_description(
        webrtc.RTCSessionDescriptionInit('offer', re.sub(r'm=application \d+', 'm=application 0', offer.sdp))
    )
    await callee.set_local_description()

    assert callee.sctp is None
    assert sctp.max_message_size == 262144


@pytest.mark.asyncio
async def test_send_larger_than_max_message_size(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A message larger than the negotiated max message size isn't sent, and the channel stays open."""
    channel, _ = await open_pair(caller, callee)
    assert caller.sctp is not None
    size = caller.sctp.max_message_size
    assert size is not None
    assert size > 65536

    with pytest.raises(TypeError, match='larger than the maxMessageSize'):
        channel.send(bytes(int(size) + 1))
    assert channel.buffered_amount == 0
    assert channel.ready_state == webrtc.RTCDataChannelState.open


@pytest.mark.asyncio
async def test_stats_are_current(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """The stats of a channel count a message right after it's received."""
    channel, remote = await open_pair(caller, callee)

    async def bytes_received() -> int | None:
        [stats] = stats_of_type(await callee.get_stats(), 'data-channel')
        assert isinstance(stats, webrtc.RTCDataChannelStats)
        return stats.bytes_received

    before = await bytes_received()
    received = wait_for_event(remote, 'message')
    channel.send('hello')
    await received
    # libwebrtc reuses a report for 50 ms: the stats right after a message count it
    after = await bytes_received()
    assert before is not None
    assert after == before + 5


@pytest.mark.asyncio
async def test_concurrent_stats_share_a_collection(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stats requests of one loop iteration share a collection, one after an observed message starts another."""
    channel, remote = await open_pair(caller, callee)
    started: list[str] = []
    start = loops._start_native

    def counted(state: loops.LoopState, method: Callable[..., None], *args: object) -> asyncio.Future[object]:
        # late trickled candidates also start native calls
        if method.__name__ == 'getStats':
            started.append(method.__name__)
        return start(state, method, *args)

    monkeypatch.setattr(loops, '_start_native', counted)

    reports = await asyncio.gather(*(callee.get_stats() for _ in range(5)))
    assert started == ['getStats']
    # each caller gets its own report
    assert len({id(report) for report in reports}) == len(reports)
    assert len({id(stats) for report in reports for stats in report.values()}) == sum(map(len, reports))

    received = wait_for_event(remote, 'message')
    channel.send('hello')
    await received
    [stats] = stats_of_type(await callee.get_stats(), 'data-channel')
    assert started == ['getStats', 'getStats']
    assert isinstance(stats, webrtc.RTCDataChannelStats)
    assert stats.messages_received == 1


@pytest.mark.asyncio
async def test_a_delivered_message_ends_the_stats_batch(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    """A stats request made in a message handler doesn't join one started before the message, in any loop."""
    channel, remote = await open_pair(caller, callee)
    state = loops.LoopState.of(asyncio.get_running_loop())
    batched: list[bool] = []

    @remote.on('message')
    def on_message(_: object) -> None:
        batched.append(callee in state.batches)

    received = wait_for_event(remote, 'message')
    # a batch still open when the message arrives, as on loops that drain records in the same iteration
    state.batches[callee] = asyncio.get_running_loop().create_future()
    channel.send('hello')
    await received
    assert batched == [False]


@pytest.mark.asyncio
async def test_max_channels_once_connected(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """The max number of channels is known once SCTP is connected."""
    caller.create_data_channel('channels')
    await caller.set_local_description()
    assert caller.sctp is not None
    assert caller.sctp.max_channels is None

    await connect(caller, callee)

    def connected() -> bool:
        assert callee.sctp is not None
        return callee.sctp.state == webrtc.RTCSctpTransportState.connected

    await wait_until(connected, 'SCTP to connect')
    assert callee.sctp is not None
    assert callee.sctp.max_channels is not None
    assert callee.sctp.max_channels > 0


@pytest.mark.asyncio
async def test_binary_type(caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection) -> None:
    """Binary messages arrive as bytes, or as a Blob once binary_type is 'blob'; a Blob is sent as binary."""
    channel, remote = await open_pair(caller, callee)
    assert remote.binary_type == webrtc.BinaryType.arraybuffer == remote.binaryType

    first = wait_for_event(remote, 'message')
    channel.send(b'\x01\x02')
    message = await first
    assert isinstance(message, webrtc.MessageEvent)
    assert message.data == b'\x01\x02'

    remote.binary_type = 'blob'
    assert remote.binaryType == webrtc.BinaryType.blob
    second = wait_for_event(remote, 'message')
    channel.send(webrtc.Blob([b'\x03', 'a', webrtc.Blob([b'\x04'])]))
    message = await second
    assert isinstance(message, webrtc.MessageEvent)
    blob = message.data
    assert isinstance(blob, webrtc.Blob)
    assert blob.size == 3
    assert await blob.array_buffer() == b'\x03a\x04'

    text = wait_for_event(remote, 'message')
    channel.send('text')
    message = await text
    assert isinstance(message, webrtc.MessageEvent)
    assert message.data == 'text'

    with pytest.raises(ValueError, match='not a valid BinaryType'):
        remote.binary_type = mistyped('buffer')
    assert remote.binary_type == webrtc.BinaryType.blob


@pytest.mark.asyncio
async def test_binary_type_back_to_arraybuffer(
    caller: webrtc.RTCPeerConnection, callee: webrtc.RTCPeerConnection
) -> None:
    channel, remote = await open_pair(caller, callee)
    remote.binary_type = 'blob'
    remote.binary_type = 'arraybuffer'
    assert remote.binary_type == webrtc.BinaryType.arraybuffer
    received = wait_for_event(remote, 'message')
    channel.send(b'\x05')
    message = await received
    assert isinstance(message, webrtc.MessageEvent)
    assert message.data == b'\x05'


def test_lone_surrogate_label_is_replaced(pc: webrtc.RTCPeerConnection) -> None:
    """A lone surrogate label becomes U+FFFD."""
    channel = pc.create_data_channel('\ud800')
    assert channel.label == '�'


def test_send_lone_surrogate_on_closed_channel(pc: webrtc.RTCPeerConnection) -> None:
    """A closed channel raises InvalidStateError."""
    channel = pc.create_data_channel('chat')
    pc.close()
    with pytest.raises(webrtc.InvalidStateError):
        channel.send('a\ud800b')


def test_closed_check_comes_before_the_label_check(pc: webrtc.RTCPeerConnection) -> None:
    """A closed connection raises InvalidStateError first."""
    pc.close()
    with pytest.raises(webrtc.InvalidStateError):
        pc.create_data_channel('x' * 70000)


def with_max_message_size(sdp: str, size: str | None) -> str:
    return sdp if size is None else re.sub(r'a=max-message-size:\d+', f'a=max-message-size:{size}', sdp)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('local', 'remote', 'expected'),
    [('1000', None, 1000), (None, '0', 262144), ('0', '1000', 1000), ('0', '0', math.inf)],
)
async def test_max_message_size_of_the_negotiated_descriptions(
    caller: webrtc.RTCPeerConnection,
    callee: webrtc.RTCPeerConnection,
    *,
    local: str | None,
    remote: str | None,
    expected: float,
) -> None:
    """The smaller of both sides' max-message-size, where 0 means no limit."""
    caller.create_data_channel('size')
    offer = await caller.create_offer()
    offer.sdp = with_max_message_size(offer.sdp, local)
    await caller.set_local_description(offer)
    await callee.set_remote_description(offer)
    answer = await callee.create_answer()
    answer.sdp = with_max_message_size(answer.sdp, remote)

    await caller.set_remote_description(answer)

    assert caller.sctp is not None
    assert caller.sctp.max_message_size == expected
