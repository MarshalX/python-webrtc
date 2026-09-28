/*
 *  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
 *
 *  Use of this source code is governed by a BSD-style license
 *  that can be found in the LICENSE.md file in the root of the project.
 */

// Exposes python-webrtc to web-platform-tests as the browser WebRTC API.
//
// This file must stay a binding and never become an implementation. It does what WebIDL bindings do in a
// browser: maps names, converts enums and dictionaries, keeps object identity and turns errors into the
// right exception types. Behavior belongs to the library, so a failing test points at a gap in the library.
//
// Expects globalThis.__wpt = {bridge, unsupported, complete} to be set by the runner.

(() => {
  'use strict';

  const {bridge, unsupported} = globalThis.__wpt;

  // Globals a browser has and a shell doesn't
  globalThis.self = globalThis;
  globalThis.queueMicrotask ??= (callback) => Promise.resolve().then(callback);
  globalThis.test_driver = {
    set_permission: async () => {},
  };

  const pyObjects = new WeakMap(); // JS wrapper to Python object
  const wrappersById = new Map(); // native object id to JS wrapper, for [SameObject] and === comparisons
  const INTERNAL = Symbol('internal');

  function fromPy(value) {
    if (value === undefined || value === null) return null;
    if (Array.isArray(value)) return Array.from(value, fromPy);
    if (typeof value !== 'object') return value;
    if ('__enum' in value) return value.__enum.replace(/_/g, '-');
    if ('__type' in value) {
      const cls = interfaces[value.__type];
      if (!cls) throw new Error(`No JS interface for ${value.__type}`);
      return wrappersById.get(value.__id) ?? new cls(INTERNAL, value);
    }
    return value;
  }

  function toPy(value) {
    if (Array.isArray(value)) return value.map(toPy);
    if (value !== null && typeof value === 'object' && pyObjects.has(value)) return pyObjects.get(value);
    return value;
  }

  // WebIDL rejects an argument of the wrong interface before the implementation sees it
  function requireInterface(value, cls, method) {
    if (!(value instanceof cls)) {
      throw new TypeError(`${method}: argument is not of type ${cls.name}`);
    }
    return value;
  }

  // strict is false for DOMString arguments that the library validates itself
  const pyEnum = (name, value, strict = true) => ({__enum: name, value: String(value), strict});

  // Follows how Chromium turns webrtc::RTCErrorType into DOM exceptions
  const DOM_EXCEPTION_BY_RTC_ERROR = {
    INVALID_PARAMETER: 'InvalidAccessError',
    UNSUPPORTED_PARAMETER: 'InvalidAccessError',
    UNSUPPORTED_OPERATION: 'OperationError',
    SYNTAX_ERROR: 'SyntaxError',
    INVALID_STATE: 'InvalidStateError',
    INVALID_MODIFICATION: 'InvalidModificationError',
    NETWORK_ERROR: 'NetworkError',
    RESOURCE_EXHAUSTED: 'OperationError',
    INTERNAL_ERROR: 'OperationError',
    OPERATION_ERROR_WITH_DATA: 'OperationError',
  };

  function toJsError({kind, code, message}) {
    if (kind === 'TypeError') return new TypeError(message);
    if (kind === 'RTCException' && code === 'INVALID_RANGE') return new RangeError(message);
    if (kind === 'RTCException' && code in DOM_EXCEPTION_BY_RTC_ERROR) {
      return new DOMException(message, DOM_EXCEPTION_BY_RTC_ERROR[code]);
    }
    // PythonWebRTCException has no error type, so there's no DOMException name to give it
    return new Error(`${kind}: ${message}`);
  }

  function unwrap(result) {
    if (result.error) throw toJsError(result.error);
    return fromPy(result.ok);
  }

  function construct(name, kwargs = {}) {
    const result = bridge.construct(name, kwargs);
    if (result.error) throw toJsError(result.error);
    return result.ok;
  }

  const getAttr = (self, name) => unwrap(bridge.get_attr(pyObjects.get(self), name));
  const setAttr = (self, name, value) => unwrap(bridge.set_attr(pyObjects.get(self), name, value));
  const callMethod = (self, name, ...args) =>
    unwrap(bridge.call_method(pyObjects.get(self), name, args.map(toPy)));
  const callAsyncMethod = async (self, name, ...args) =>
    unwrap(await bridge.call_async_method(pyObjects.get(self), name, args.map(toPy)));

  // Members the library doesn't support are reported rather than silently dropped
  function convertDictionary(dict, dictName, members) {
    const converted = {};
    for (const [key, value] of Object.entries(dict ?? {})) {
      if (value === undefined) continue;
      if (!(key in members)) {
        unsupported(`${dictName}.${key}`);
        continue;
      }
      const [pyName, convert = (v) => v] = members[key];
      converted[pyName] = convert(value);
    }
    return converted;
  }

  class Interface {
    constructor(token, ref) {
      if (token !== INTERNAL) throw new TypeError('Illegal constructor');
      pyObjects.set(this, ref.__obj);
      wrappersById.set(ref.__id, this);
      // Sealed, so that in strict mode setting a member the library lacks (like onicecandidate) throws
      // instead of being silently ignored
      Object.seal(this);
    }
  }

  function defineAttributes(cls, attributes) {
    for (const [jsName, pyName, convertOnSet] of attributes) {
      const descriptor = {
        get() { return getAttr(this, pyName); },
        enumerable: true,
        configurable: true,
      };
      if (convertOnSet) {
        descriptor.set = function (value) { setAttr(this, pyName, convertOnSet(value)); };
      }
      Object.defineProperty(cls.prototype, jsName, descriptor);
    }
  }

  class MediaStreamTrack extends Interface {
    stop() { callMethod(this, 'stop'); }
    clone() { return callMethod(this, 'clone'); }
  }
  defineAttributes(MediaStreamTrack, [
    ['id', 'id'],
    ['kind', 'kind'],
    ['enabled', 'enabled', Boolean],
    ['muted', 'muted'],
    ['readyState', 'ready_state'],
  ]);

  class MediaStream extends Interface {
    constructor(...args) {
      if (args[0] === INTERNAL) {
        super(...args);
        return;
      }
      if (args.length) unsupported('MediaStream constructor arguments');
      super(INTERNAL, construct('MediaStream'));
    }

    getTracks() { return callMethod(this, 'get_tracks'); }
    getAudioTracks() { return callMethod(this, 'get_audio_tracks'); }
    getVideoTracks() { return callMethod(this, 'get_video_tracks'); }
    getTrackById(id) { return callMethod(this, 'get_track_by_id', id); }
    addTrack(track) {
      callMethod(this, 'add_track', requireInterface(track, MediaStreamTrack, 'MediaStream.addTrack'));
    }

    removeTrack(track) {
      callMethod(this, 'remove_track', requireInterface(track, MediaStreamTrack, 'MediaStream.removeTrack'));
    }

    clone() { return callMethod(this, 'clone'); }
  }
  defineAttributes(MediaStream, [
    ['id', 'id'],
    ['active', 'active'],
  ]);

  class RTCSessionDescription extends Interface {
    constructor(...args) {
      if (args[0] === INTERNAL) {
        super(...args);
        return;
      }
      const init = args[0] ?? {};
      super(INTERNAL, construct('RTCSessionDescription', {
        type: pyEnum('RTCSdpType', init.type),
        sdp: init.sdp ?? '',
      }));
    }

    toJSON() { return {type: this.type, sdp: this.sdp}; }
  }
  defineAttributes(RTCSessionDescription, [
    ['type', 'type'],
    ['sdp', 'sdp'],
  ]);

  class RTCIceTransport extends Interface {}
  defineAttributes(RTCIceTransport, [
    ['component', 'component'],
    ['gatheringState', 'gathering_state'],
    ['role', 'role'],
    ['state', 'state'],
  ]);

  class RTCDtlsTransport extends Interface {}
  defineAttributes(RTCDtlsTransport, [
    ['iceTransport', 'ice_transport'],
    ['state', 'state'],
  ]);

  class RTCSctpTransport extends Interface {}

  class RTCRtpSender extends Interface {}
  defineAttributes(RTCRtpSender, [
    ['track', 'track'],
    ['transport', 'transport'],
  ]);

  class RTCRtpReceiver extends Interface {}
  defineAttributes(RTCRtpReceiver, [
    ['track', 'track'],
    ['transport', 'transport'],
  ]);

  class RTCRtpTransceiver extends Interface {
    stop() { callMethod(this, 'stop'); }
  }
  defineAttributes(RTCRtpTransceiver, [
    ['mid', 'mid'],
    ['sender', 'sender'],
    ['receiver', 'receiver'],
    ['stopped', 'stopped'],
    ['direction', 'direction', (v) => pyEnum('TransceiverDirection', v)],
    ['currentDirection', 'current_direction'],
  ]);

  const ENCODING_PARAMETERS = {
    active: ['active', Boolean],
    maxBitrate: ['max_bitrate'],
    maxFramerate: ['max_framerate'],
    rid: ['rid', String],
    scaleResolutionDownBy: ['scale_resolution_down_by'],
  };

  const TRANSCEIVER_INIT = {
    direction: ['direction', (v) => pyEnum('TransceiverDirection', v)],
    streams: ['streams', (v) => Array.from(v, toPy)],
    sendEncodings: [
      'send_encodings',
      (v) => Array.from(v, (e) => convertDictionary(e, 'RTCRtpEncodingParameters', ENCODING_PARAMETERS)),
    ],
  };

  function toSessionDescription(description) {
    if (description === undefined || description === null) return undefined;
    if (description instanceof RTCSessionDescription) return description;
    return new RTCSessionDescription(description);
  }

  class RTCPeerConnection extends Interface {
    constructor(...args) {
      if (args[0] === INTERNAL) {
        super(...args);
        return;
      }
      const configuration = args[0];
      for (const key of Object.keys(configuration ?? {})) unsupported(`RTCConfiguration.${key}`);
      super(INTERNAL, construct('RTCPeerConnection'));
    }

    createOffer(options) {
      if (options !== undefined) unsupported('RTCOfferOptions');
      return callAsyncMethod(this, 'create_offer');
    }

    createAnswer(options) {
      if (options !== undefined) unsupported('RTCAnswerOptions');
      return callAsyncMethod(this, 'create_answer');
    }

    async setLocalDescription(description) {
      const args = description === undefined ? [] : [toSessionDescription(description)];
      return callAsyncMethod(this, 'set_local_description', ...args);
    }

    async setRemoteDescription(description) {
      return callAsyncMethod(this, 'set_remote_description', toSessionDescription(description));
    }

    addTrack(track, ...streams) {
      requireInterface(track, MediaStreamTrack, 'RTCPeerConnection.addTrack');
      streams.forEach((stream) => requireInterface(stream, MediaStream, 'RTCPeerConnection.addTrack'));
      return callMethod(this, 'add_track', track, streams.length ? streams : null);
    }

    addTransceiver(trackOrKind, init) {
      const trackOrPyKind = typeof trackOrKind === 'string'
        ? pyEnum('MediaType', trackOrKind, false)
        : requireInterface(trackOrKind, MediaStreamTrack, 'RTCPeerConnection.addTransceiver');
      if (init === undefined) return callMethod(this, 'add_transceiver', trackOrPyKind);
      const pyInit = construct('RtpTransceiverInit', convertDictionary(init, 'RTCRtpTransceiverInit', TRANSCEIVER_INIT));
      return callMethod(this, 'add_transceiver', trackOrPyKind, pyInit.__obj);
    }

    getTransceivers() { return callMethod(this, 'get_transceivers'); }
    getSenders() { return callMethod(this, 'get_senders'); }
    getReceivers() { return callMethod(this, 'get_receivers'); }
    removeTrack(sender) {
      callMethod(this, 'remove_track', requireInterface(sender, RTCRtpSender, 'RTCPeerConnection.removeTrack'));
    }

    restartIce() { callMethod(this, 'restart_ice'); }
    close() { callMethod(this, 'close'); }
  }
  defineAttributes(RTCPeerConnection, [
    ['localDescription', 'local_description'],
    ['remoteDescription', 'remote_description'],
    ['signalingState', 'signaling_state'],
    ['connectionState', 'connection_state'],
    ['iceConnectionState', 'ice_connection_state'],
    ['iceGatheringState', 'ice_gathering_state'],
    ['sctp', 'sctp'],
  ]);

  const interfaces = {
    MediaStreamTrack,
    MediaStream,
    RTCSessionDescription,
    RTCIceTransport,
    RTCDtlsTransport,
    RTCSctpTransport,
    RTCRtpSender,
    RTCRtpReceiver,
    RTCRtpTransceiver,
    RTCPeerConnection,
  };
  Object.assign(globalThis, interfaces);

  globalThis.navigator = {
    mediaDevices: {
      async getUserMedia(constraints = {}) {
        if (constraints.video) unsupported('getUserMedia video');
        return unwrap(bridge.get_user_media());
      },
    },
  };
})();
