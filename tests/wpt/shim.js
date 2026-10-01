/*
 *  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
 *
 *  Use of this source code is governed by a BSD-style license
 *  that can be found in the LICENSE.md file in the root of the project.
 */

// Exposes python-webrtc to web-platform-tests as the browser WebRTC API. Like WebIDL bindings, it only maps
// names, types, identity, errors and events: behavior belongs to the library.

(() => {
  'use strict';

  const {bridge, unsupported} = globalThis.__wpt;

  function reportException(error) {
    const event = new Event('error');
    Object.assign(event, {error, message: String(error?.message ?? error), filename: '', lineno: 0, colno: 0});
    globalThis.dispatchEvent(event);
  }

  const pyObjects = new WeakMap(); // JS wrapper to Python object
  const wrappersById = new Map(); // native object id to JS wrapper, for [SameObject] and === comparisons
  const INTERNAL = Symbol('internal');

  function fromPy(value) {
    if (value === undefined || value === null) return null;
    if (Array.isArray(value)) return Array.from(value, fromPy);
    if (typeof value !== 'object') return value;
    if ('__type' in value) {
      const cls = interfaces[value.__type];
      if (!cls) throw new Error(`No JS interface for ${value.__type}`);
      return wrappersById.get(value.__id) ?? new cls(INTERNAL, value);
    }
    if ('__bytes' in value) return Uint8Array.from(value.__bytes).buffer;
    if ('__blob' in value) return new Blob([Uint8Array.from(value.__blob)], {type: value.type});
    if ('__rect' in value) return new DOMRectReadOnly(...value.__rect);
    if ('__error' in value) return toJsError(value.__error);
    if ('__statsReport' in value) {
      return new RTCStatsReport(INTERNAL, Array.from(value.__statsReport, ([id, stats]) => [id, fromPy(stats)]));
    }
    if ('__event' in value) {
      const cls = events[value.__event];
      if (!cls) throw new Error(`No JS event interface for ${value.__event}`);
      return new cls(value.type, fromPy(value.init));
    }
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, fromPy(v)]));
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
  // a dictionary the library takes as a keyword model
  const pyModel = (name, kwargs) => ({__model: name, kwargs});
  // a dictionary with the members JS gives, converted by the from_json of the library's model
  const pyJson = (name, value) => ({__json: name, value});

  // USVString conversion replaces lone surrogates
  const toUSVString = (value) => String(value).toWellFormed();

  // [EnforceRange] integer conversion
  function enforceRange(value, min, max) {
    const number = Number(value);
    if (!Number.isFinite(number)) throw new TypeError(`${value} is not a finite number`);
    const integer = Math.trunc(number);
    if (integer < min || integer > max) throw new TypeError(`${value} is out of range`);
    return integer;
  }

  // unsigned long integer conversion, which wraps around
  const toUnsignedLong = (value) => Math.trunc(Number(value)) >>> 0;

  function requireArguments(args, count, method) {
    if (args.length < count) {
      throw new TypeError(`${method}: ${count} argument${count === 1 ? '' : 's'} required`);
    }
  }

  function requireDictionary(value, name) {
    if (value !== undefined && value !== null && typeof value !== 'object' && typeof value !== 'function') {
      throw new TypeError(`${name} is not a dictionary`);
    }
    return value ?? {};
  }

  // webrtc exception classes, by the DOMException name they stand for
  const DOM_EXCEPTION_BY_CLASS = {
    InvalidStateError: 'InvalidStateError',
    InvalidAccessError: 'InvalidAccessError',
    InvalidModificationError: 'InvalidModificationError',
    OperationError: 'OperationError',
    NotSupportedError: 'NotSupportedError',
    NetworkError: 'NetworkError',
    DataCloneError: 'DataCloneError',
    InvalidSyntaxError: 'SyntaxError',
    InvalidCharacterError: 'InvalidCharacterError',
    NotFoundError: 'NotFoundError',
    NotAllowedError: 'NotAllowedError',
  };
  const JS_ERROR_BY_CLASS = {
    TypeError,
    InvalidRangeError: RangeError,
    ValueError: TypeError,
    OverflowError: TypeError,
  };

  function toJsError({kind, message, init, constraint}) {
    if (kind === 'RTCError') return new RTCError(INTERNAL, {init, message});
    if (kind === 'OverconstrainedError') return new OverconstrainedError(constraint, message);
    if (kind in JS_ERROR_BY_CLASS) return new JS_ERROR_BY_CLASS[kind](message);
    if (kind in DOM_EXCEPTION_BY_CLASS) return new DOMException(message, DOM_EXCEPTION_BY_CLASS[kind]);
    // PythonWebRTCException has no error type, so there's no DOMException name to give it
    return new Error(`${kind}: ${message}`);
  }

  function unwrap(result) {
    if (result.error) throw toJsError(result.error);
    return fromPy(result.ok);
  }

  // positional-only parameters take args
  function construct(name, kwargs = {}, args = []) {
    const result = bridge.construct(name, kwargs, args);
    if (result.error) throw toJsError(result.error);
    return result.ok;
  }

  const getAttr = (self, name) => unwrap(bridge.get_attr(pyObjects.get(self), name));
  const setAttr = (self, name, value) => unwrap(bridge.set_attr(pyObjects.get(self), name, value));
  const callMethod = (self, name, ...args) => callMethodWithKeywords(self, name, args, {});
  const callMethodWithKeywords = (self, name, args, kwargs) =>
    unwrap(bridge.call_method(pyObjects.get(self), name, {args: args.map(toPy), kwargs}));
  const callAsyncMethod = async (self, name, ...args) => callAsyncMethodWithKeywords(self, name, args, {});
  const callAsyncMethodWithKeywords = async (self, name, args, kwargs) =>
    unwrap(await bridge.call_async_method(pyObjects.get(self), name, {args: args.map(toPy), kwargs}));
  const callStatic = (className, name, ...args) => unwrap(bridge.call_static(className, name, args.map(toPy)));
  // an attribute that is a promise, like the closed one of a reader
  const awaitAttr = async (self, name) => unwrap(await bridge.await_attr(pyObjects.get(self), name));

  // the bytes of a BufferSource, sharing its memory
  function bytesOf(source, name) {
    if (source instanceof ArrayBuffer) return new Uint8Array(source);
    if (ArrayBuffer.isView(source)) return new Uint8Array(source.buffer, source.byteOffset, source.byteLength);
    throw new TypeError(`${name} is not a BufferSource`);
  }

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

  // Not the native EventTarget, which has no hook to subscribe to the library when the first listener is added
  const listenersOf = new WeakMap(); // target to Map(type to [{callback, once}])
  const subscriptionsOf = new WeakMap(); // target to Set(type)
  const eventHandlersOf = new WeakMap(); // target to Map(type to {handler, listener})

  class Interface {
    constructor(token, ref) {
      if (token !== INTERNAL) throw new TypeError('Illegal constructor');
      pyObjects.set(this, ref.__obj);
      wrappersById.set(ref.__id, this);
      // not sealed: tests add their own properties; event handler attributes
      // are defined for every event of the specification and report the ones the library lacks
    }

    addEventListener(type, callback, options) {
      if (callback === null || callback === undefined) return;
      const once = typeof options === 'object' && options !== null && Boolean(options.once);
      if (!listenersOf.has(this)) listenersOf.set(this, new Map());
      const listeners = listenersOf.get(this);
      if (!listeners.has(type)) listeners.set(type, []);
      const list = listeners.get(type);
      if (list.some((l) => l.callback === callback)) return;
      list.push({callback, once});
      subscribe(this, type);
    }

    removeEventListener(type, callback) {
      const list = listenersOf.get(this)?.get(type);
      if (!list) return;
      const index = list.findIndex((l) => l.callback === callback);
      if (index >= 0) {
        list[index].removed = true;
        list.splice(index, 1);
      }
    }

    dispatchEvent(event) {
      Object.defineProperty(event, 'target', {value: this, configurable: true});
      Object.defineProperty(event, 'currentTarget', {value: this, configurable: true});
      for (const listener of [...(listenersOf.get(this)?.get(event.type) ?? [])]) {
        if (listener.removed) continue;
        if (listener.once) this.removeEventListener(event.type, listener.callback);
        try {
          if (typeof listener.callback === 'function') listener.callback.call(this, event);
          else listener.callback.handleEvent(event);
        } catch (e) {
          // an exception of a listener is reported and doesn't stop the others
          reportException(e);
        }
      }
      return true;
    }
  }

  // The Python object of an interface constructed by a script (created from the arguments), or of a wrapper
  // the shim creates for an existing one
  const pyObjectOf = (args, create) => (args[0] === INTERNAL ? args[1] : create(...args));

  function subscribe(target, type) {
    if (!subscriptionsOf.has(target)) subscriptionsOf.set(target, new Set());
    const subscriptions = subscriptionsOf.get(target);
    if (subscriptions.has(type)) return;
    subscriptions.add(type);
    const result = bridge.subscribe(pyObjects.get(target), type, (pyEvent) => {
      target.dispatchEvent(fromPy(pyEvent));
    });
    if (result.error) unsupported(`${target.constructor.name} event ${type}`);
  }

  // on<type> attributes, which are listeners added at the first assignment
  function defineEventHandlers(cls, types) {
    for (const type of types) {
      Object.defineProperty(cls.prototype, `on${type}`, {
        get() { return eventHandlersOf.get(this)?.get(type)?.handler ?? null; },
        set(handler) {
          if (!eventHandlersOf.has(this)) eventHandlersOf.set(this, new Map());
          const handlers = eventHandlersOf.get(this);
          if (!handlers.has(type)) {
            const entry = {handler: null};
            entry.listener = function (event) {
              if (typeof entry.handler === 'function') return entry.handler.call(this, event);
            };
            handlers.set(type, entry);
            this.addEventListener(type, entry.listener);
          }
          handlers.get(type).handler = typeof handler === 'function' ? handler : null;
        },
        enumerable: true,
        configurable: true,
      });
    }
  }

  // Events carry their init dictionary as attributes; required members are checked like WebIDL does
  function defineEvent(name, required = [], defaults = {}, types = {}) {
    const cls = class extends Event {
      constructor(type, init) {
        requireArguments(arguments, 1, name);
        super(String(type));
        Object.defineProperty(this, 'bubbles', {value: Boolean(init?.bubbles), configurable: true});
        Object.defineProperty(this, 'cancelable', {value: Boolean(init?.cancelable), configurable: true});
        for (const key of required) {
          if (init?.[key] === undefined) throw new TypeError(`${name}: missing required member ${key}`);
        }
        const members = {...defaults};
        for (const [key, value] of Object.entries(init ?? {})) {
          if (value !== undefined) members[key] = value;
        }
        for (const [key, value] of Object.entries(members)) {
          // members of an interface type take an object of it (or null, if nullable)
          const nullable = defaults[key] === null;
          if (key in types && !(value === null ? nullable : value instanceof types[key]())) {
            throw new TypeError(`${name}: ${key} is not of the expected interface`);
          }
          if (key !== 'bubbles' && key !== 'cancelable' && key !== 'composed') this[key] = value;
        }
      }
    };
    Object.defineProperty(cls, 'name', {value: name});
    return cls;
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
    getSettings() { return callMethod(this, 'get_settings'); }
    getCapabilities() { return callMethod(this, 'get_capabilities'); }
    getConstraints() { return callMethod(this, 'get_constraints'); }
    applyConstraints(constraints) {
      return callAsyncMethod(this, 'apply_constraints',
        pyJson('MediaTrackConstraints', requireDictionary(constraints, 'MediaTrackConstraints')));
    }
  }
  defineAttributes(MediaStreamTrack, [
    ['id', 'id'],
    ['kind', 'kind'],
    ['label', 'label'],
    ['enabled', 'enabled', Boolean],
    ['muted', 'muted'],
    ['readyState', 'ready_state'],
    ['contentHint', 'content_hint', String],
  ]);
  defineEventHandlers(MediaStreamTrack, ['mute', 'unmute', 'ended']);

  class MediaStream extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, (source) => {
        let tracks = [];
        if (source !== undefined) {
          tracks = source instanceof MediaStream ? source.getTracks() : Array.from(source,
            (track) => requireInterface(track, MediaStreamTrack, 'MediaStream constructor'));
        }
        return construct('MediaStream', {tracks: tracks.map(toPy)});
      }));
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
  defineEventHandlers(MediaStream, ['addtrack', 'removetrack']);

  class RTCCertificate extends Interface {
    getFingerprints() { return callMethod(this, 'get_fingerprints'); }
  }
  defineAttributes(RTCCertificate, [['expires', 'expires']]);

  // the WebCrypto dictionary an algorithm normalizes to, as far as its members are given
  function toAlgorithm(algorithm) {
    if (typeof algorithm !== 'object' || algorithm === null) return String(algorithm);
    const converted = {name: String(algorithm.name)};
    if (algorithm.expires !== undefined) converted.expires = enforceRange(algorithm.expires, 0, Number.MAX_SAFE_INTEGER);
    if (algorithm.namedCurve !== undefined) converted.namedCurve = String(algorithm.namedCurve);
    if (algorithm.modulusLength !== undefined) converted.modulusLength = enforceRange(algorithm.modulusLength, 0, 2 ** 32 - 1);
    if (algorithm.publicExponent !== undefined) converted.publicExponent = algorithm.publicExponent;
    if (algorithm.hash !== undefined) {
      converted.hash = typeof algorithm.hash === 'object' ? String(algorithm.hash.name) : String(algorithm.hash);
    }
    const name = converted.name.toUpperCase();
    if (name === 'ECDSA' && converted.namedCurve !== undefined) return pyJson('EcKeyGenParams', converted);
    const rsa = ['modulusLength', 'publicExponent', 'hash'].every((key) => converted[key] !== undefined);
    if (name === 'RSASSA-PKCS1-V1_5' && rsa) return pyJson('RsaHashedKeyGenParams', converted);
    return pyJson('Algorithm', {name: converted.name, expires: converted.expires});
  }

  class RTCIceCandidate extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, (init) => {
        init ??= {};
        return construct('RTCIceCandidate', {
          candidate: init.candidate === undefined ? '' : String(init.candidate),
          sdp_mid: init.sdpMid === undefined || init.sdpMid === null ? null : String(init.sdpMid),
          sdp_m_line_index: init.sdpMLineIndex ?? null,
          username_fragment: init.usernameFragment ?? null,
          relay_protocol: init.relayProtocol ?? null,
          url: init.url ?? null,
        });
      }));
    }

    toJSON() { return callMethod(this, 'to_json'); }
  }
  defineAttributes(RTCIceCandidate, [
    ['candidate', 'candidate'],
    ['sdpMid', 'sdp_mid'],
    ['sdpMLineIndex', 'sdp_m_line_index'],
    ['usernameFragment', 'username_fragment'],
    ['foundation', 'foundation'],
    ['component', 'component'],
    ['priority', 'priority'],
    ['address', 'address'],
    ['protocol', 'protocol'],
    ['port', 'port'],
    ['type', 'type'],
    ['tcpType', 'tcp_type'],
    ['relatedAddress', 'related_address'],
    ['relatedPort', 'related_port'],
    ['relayProtocol', 'relay_protocol'],
    ['url', 'url'],
  ]);

  class RTCSessionDescription extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, (init) => construct('RTCSessionDescription', {
        type: pyEnum('RTCSdpType', init?.type),
        sdp: init?.sdp ?? '',
      })));
    }

    toJSON() { return callMethod(this, 'to_json'); }
  }
  defineAttributes(RTCSessionDescription, [
    ['type', 'type'],
    ['sdp', 'sdp'],
  ]);

  class RTCIceTransport extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, () => construct('RTCIceTransport')));
    }

    gather(options) {
      const init = requireDictionary(options, 'RTCIceGatherOptions');
      const kwargs = {};
      if (init.gatherPolicy !== undefined) kwargs.gather_policy = pyEnum('RTCIceTransportPolicy', init.gatherPolicy);
      if (init.iceServers !== undefined) {
        if (init.iceServers === null) throw new TypeError('iceServers is not a sequence');
        kwargs.ice_servers = Array.from(init.iceServers, toIceServer);
      }
      callMethod(this, 'gather', pyModel('RTCIceGatherOptions', kwargs));
    }

    start(remoteParameters, role = 'controlled') {
      const init = requireDictionary(remoteParameters, 'RTCIceParameters');
      if (init.usernameFragment === undefined || init.password === undefined) {
        throw new TypeError('RTCIceParameters: usernameFragment and password are required');
      }
      const parameters = pyModel('RTCIceParameters',
        {username_fragment: String(init.usernameFragment), password: String(init.password)});
      callMethod(this, 'start', parameters, pyEnum('RTCIceRole', role));
    }

    stop() { callMethod(this, 'stop'); }

    addRemoteCandidate(candidate) {
      callMethod(this, 'add_remote_candidate',
        candidate instanceof RTCIceCandidate ? candidate : new RTCIceCandidate(candidate));
    }

    getSelectedCandidatePair() { return callMethod(this, 'get_selected_candidate_pair'); }
    getLocalCandidates() { return callMethod(this, 'get_local_candidates'); }
    getRemoteCandidates() { return callMethod(this, 'get_remote_candidates'); }
    getLocalParameters() { return callMethod(this, 'get_local_parameters'); }
    getRemoteParameters() { return callMethod(this, 'get_remote_parameters'); }
  }
  defineAttributes(RTCIceTransport, [
    ['component', 'component'],
    ['gatheringState', 'gathering_state'],
    ['role', 'role'],
    ['state', 'state'],
  ]);
  defineEventHandlers(RTCIceTransport,
    ['statechange', 'gatheringstatechange', 'selectedcandidatepairchange', 'icecandidate']);

  class RTCDtlsTransport extends Interface {
    getRemoteCertificates() { return callMethod(this, 'get_remote_certificates'); }
  }
  defineAttributes(RTCDtlsTransport, [
    ['iceTransport', 'ice_transport'],
    ['state', 'state'],
  ]);
  defineEventHandlers(RTCDtlsTransport, ['statechange', 'error']);

  class RTCSctpTransport extends Interface {}
  defineAttributes(RTCSctpTransport, [
    ['transport', 'transport'],
    ['state', 'state'],
    ['maxMessageSize', 'max_message_size'],
    ['maxChannels', 'max_channels'],
  ]);
  defineEventHandlers(RTCSctpTransport, ['statechange']);

  function requireMembers(dict, name, members) {
    if (dict === null || typeof dict !== 'object') throw new TypeError(`${name} is not a dictionary`);
    for (const member of members) {
      if (dict[member] === undefined) throw new TypeError(`${name}: missing required member ${member}`);
    }
    return dict;
  }

  const CODEC = {
    mimeType: ['mime_type', String],
    clockRate: ['clock_rate', (v) => enforceRange(v, 0, 2 ** 32 - 1)],
    channels: ['channels', (v) => enforceRange(v, 0, 65535)],
    sdpFmtpLine: ['sdp_fmtp_line', String],
  };
  const toCodec = (codec, name = 'RTCRtpCodec') =>
    pyModel('RTCRtpCodec', convertDictionary(requireMembers(codec, name, ['mimeType', 'clockRate']), name, CODEC));

  const CODEC_PARAMETERS = {...CODEC, payloadType: ['payload_type', (v) => enforceRange(v, 0, 255)]};
  const HEADER_EXTENSION_PARAMETERS = {
    uri: ['uri', String],
    id: ['id', (v) => enforceRange(v, 0, 65535)],
    encrypted: ['encrypted', Boolean],
  };
  const RTCP_PARAMETERS = {cname: ['cname', String], reducedSize: ['reduced_size', Boolean]};

  function toSendParameters(parameters) {
    requireMembers(parameters, 'RTCRtpSendParameters', ['transactionId', 'encodings']);
    return pyModel('RTCRtpSendParameters', {
      transaction_id: String(parameters.transactionId),
      encodings: toEncodings(parameters.encodings),
      codecs: Array.from(parameters.codecs ?? [], (c) => pyModel('RTCRtpCodecParameters', convertDictionary(
        requireMembers(c, 'RTCRtpCodecParameters', ['payloadType', 'mimeType', 'clockRate']),
        'RTCRtpCodecParameters', CODEC_PARAMETERS))),
      header_extensions: Array.from(parameters.headerExtensions ?? [], (e) => pyModel(
        'RTCRtpHeaderExtensionParameters', convertDictionary(
          requireMembers(e, 'RTCRtpHeaderExtensionParameters', ['uri', 'id']),
          'RTCRtpHeaderExtensionParameters', HEADER_EXTENSION_PARAMETERS))),
      rtcp: pyModel('RTCRtcpParameters', convertDictionary(parameters.rtcp ?? {}, 'RTCRtcpParameters', RTCP_PARAMETERS)),
      ...(parameters.degradationPreference === undefined ? {} : {
        degradation_preference: pyEnum('RTCDegradationPreference', parameters.degradationPreference),
      }),
    });
  }

  class RTCDTMFSender extends Interface {
    insertDTMF(tones, duration, interToneGap) {
      requireArguments(arguments, 1, 'RTCDTMFSender.insertDTMF');
      const args = [String(tones)];
      if (duration !== undefined) args.push(toUnsignedLong(duration));
      if (interToneGap !== undefined) args.push(toUnsignedLong(interToneGap));
      callMethod(this, 'insert_dtmf', ...args);
    }
  }
  defineAttributes(RTCDTMFSender, [
    ['toneBuffer', 'tone_buffer'],
    ['canInsertDTMF', 'can_insert_dtmf'],
  ]);
  defineEventHandlers(RTCDTMFSender, ['tonechange']);

  class RTCRtpSender extends Interface {
    getParameters() { return callMethod(this, 'get_parameters'); }
    async getStats() { return callAsyncMethod(this, 'get_stats'); }
    async setParameters(parameters, options) {
      const converted = toSendParameters(parameters);
      const {encodingOptions} = requireDictionary(options, 'RTCSetParameterOptions');
      if (encodingOptions === undefined) return callAsyncMethod(this, 'set_parameters', converted);
      const encodingOptionsList = Array.from(encodingOptions,
        (option) => pyModel('RTCEncodingOptions', {key_frame: Boolean(option?.keyFrame)}));
      return callAsyncMethod(this, 'set_parameters', converted,
        pyModel('RTCSetParameterOptions', {encoding_options: encodingOptionsList}));
    }

    async replaceTrack(track) {
      requireArguments(arguments, 1, 'RTCRtpSender.replaceTrack');
      if (track !== null) requireInterface(track, MediaStreamTrack, 'RTCRtpSender.replaceTrack');
      return callAsyncMethod(this, 'replace_track', track);
    }

    setStreams(...streams) {
      streams.forEach((stream) => requireInterface(stream, MediaStream, 'RTCRtpSender.setStreams'));
      callMethod(this, 'set_streams', ...streams);
    }

    static getCapabilities(kind) {
      requireArguments(arguments, 1, 'RTCRtpSender.getCapabilities');
      return callStatic('RTCRtpSender', 'get_capabilities', String(kind));
    }
  }
  const toTransform = (sframe) => (value) => {
    if (value === null || value === undefined) return null;
    if (!(value instanceof RTCRtpScriptTransform) && !(value instanceof sframe())) {
      throw new TypeError(`transform: argument is not of type RTCRtpScriptTransform or ${sframe().name}`);
    }
    return toPy(value);
  };

  defineAttributes(RTCRtpSender, [
    ['track', 'track'],
    ['transport', 'transport'],
    ['dtmf', 'dtmf'],
    ['transform', 'transform', toTransform(() => RTCRtpSFrameEncryptor)],
  ]);

  class RTCRtpReceiver extends Interface {
    getParameters() { return callMethod(this, 'get_parameters'); }
    async getStats() { return callAsyncMethod(this, 'get_stats'); }
    getSynchronizationSources() { return callMethod(this, 'get_synchronization_sources'); }
    getContributingSources() { return callMethod(this, 'get_contributing_sources'); }

    static getCapabilities(kind) {
      requireArguments(arguments, 1, 'RTCRtpReceiver.getCapabilities');
      return callStatic('RTCRtpReceiver', 'get_capabilities', String(kind));
    }
  }
  defineAttributes(RTCRtpReceiver, [
    ['track', 'track'],
    ['transport', 'transport'],
    // a nullable DOMHighResTimeStamp
    ['jitterBufferTarget', 'jitter_buffer_target', (v) => (v === null ? null : Number(v))],
    ['transform', 'transform', toTransform(() => RTCRtpSFrameDecryptor)],
  ]);

  class RTCRtpTransceiver extends Interface {
    stop() { callMethod(this, 'stop'); }

    setCodecPreferences(codecs) {
      requireArguments(arguments, 1, 'RTCRtpTransceiver.setCodecPreferences');
      callMethod(this, 'set_codec_preferences', Array.from(codecs, (codec) => toCodec(codec)));
    }

    getHeaderExtensionsToNegotiate() { return callMethod(this, 'get_header_extensions_to_negotiate'); }
    getNegotiatedHeaderExtensions() { return callMethod(this, 'get_negotiated_header_extensions'); }
    setHeaderExtensionsToNegotiate(extensions) {
      requireArguments(arguments, 1, 'RTCRtpTransceiver.setHeaderExtensionsToNegotiate');
      callMethod(this, 'set_header_extensions_to_negotiate', Array.from(extensions, (e) => {
        requireMembers(e, 'RTCRtpHeaderExtensionCapability', ['uri']);
        return pyModel('RTCRtpHeaderExtensionCapability', {
          uri: String(e.uri),
          ...(e.direction === undefined ? {} : {direction: pyEnum('RTCRtpTransceiverDirection', e.direction)}),
        });
      }));
    }
  }
  defineAttributes(RTCRtpTransceiver, [
    ['mid', 'mid'],
    ['sender', 'sender'],
    ['receiver', 'receiver'],
    ['direction', 'direction', (v) => pyEnum('RTCRtpTransceiverDirection', v)],
    ['currentDirection', 'current_direction'],
    ['stopped', 'stopped'],
  ]);

  class RTCDataChannel extends Interface {
    get binaryType() { return getAttr(this, 'binary_type'); }
    // an enum attribute ignores values it doesn't have
    set binaryType(value) {
      if (value === 'arraybuffer' || value === 'blob') setAttr(this, 'binary_type', value);
    }

    send(data) {
      requireArguments(arguments, 1, 'RTCDataChannel.send');
      if (data instanceof ArrayBuffer) return callMethod(this, 'send', data);
      if (ArrayBuffer.isView(data)) {
        return callMethod(this, 'send', new Uint8Array(data.buffer, data.byteOffset, data.byteLength));
      }
      if (data instanceof Blob) return callMethod(this, 'send', Blob.bytesOf(data));
      return callMethod(this, 'send', toUSVString(data));
    }

    close() { callMethod(this, 'close'); }
  }
  defineAttributes(RTCDataChannel, [
    ['label', 'label'],
    ['ordered', 'ordered'],
    ['maxPacketLifeTime', 'max_packet_life_time'],
    ['maxRetransmits', 'max_retransmits'],
    ['protocol', 'protocol'],
    ['negotiated', 'negotiated'],
    ['id', 'id'],
    ['priority', 'priority'],
    ['readyState', 'ready_state'],
    ['bufferedAmount', 'buffered_amount'],
    // unsigned long long: a negative value is 0 here, as a JS number can't wrap around to 2^64 exactly
    ['bufferedAmountLowThreshold', 'buffered_amount_low_threshold', (v) => Math.max(0, Math.trunc(Number(v)) || 0)],
  ]);
  defineEventHandlers(RTCDataChannel, ['open', 'bufferedamountlow', 'error', 'closing', 'close', 'message']);

  const DATA_CHANNEL_INIT = {
    ordered: ['ordered', Boolean],
    maxPacketLifeTime: ['max_packet_life_time', (v) => enforceRange(v, 0, 65535)],
    maxRetransmits: ['max_retransmits', (v) => enforceRange(v, 0, 65535)],
    protocol: ['protocol', toUSVString],
    negotiated: ['negotiated', Boolean],
    id: ['id', (v) => enforceRange(v, 0, 65535)],
    priority: ['priority', (v) => pyEnum('RTCPriorityType', v)],
  };

  const ENCODING_PARAMETERS = {
    active: ['active', Boolean],
    maxBitrate: ['max_bitrate', (v) => enforceRange(v, 0, 2 ** 32 - 1)],
    maxFramerate: ['max_framerate', Number],
    rid: ['rid', String],
    scaleResolutionDownBy: ['scale_resolution_down_by', Number],
    priority: ['priority', (v) => pyEnum('RTCPriorityType', v)],
    networkPriority: ['network_priority', (v) => pyEnum('RTCPriorityType', v)],
    scalabilityMode: ['scalability_mode', String],
    adaptivePtime: ['adaptive_ptime', Boolean],
    codec: ['codec', (v) => toCodec(v)],
  };
  const toEncodings = (encodings) => Array.from(encodings, (e) => pyModel('RTCRtpEncodingParameters',
    convertDictionary(e, 'RTCRtpEncodingParameters', ENCODING_PARAMETERS)));

  const TRANSCEIVER_INIT = {
    direction: ['direction', (v) => pyEnum('RTCRtpTransceiverDirection', v)],
    streams: ['streams', (v) => Array.from(v, toPy)],
    sendEncodings: ['send_encodings', (v) => toEncodings(v)],
  };

  const ICE_SERVER = {
    urls: ['urls', (v) => (typeof v === 'string' ? v : Array.from(v, String))],
    username: ['username', String],
    credential: ['credential', (v) => (v !== null && typeof v === 'object'
      ? pyModel('RTCOAuthCredential', {mac_key: String(v.macKey), access_token: String(v.accessToken)}) : String(v))],
    credentialType: ['credential_type', String],
  };

  function toIceServer(server) {
    if (server === null || typeof server !== 'object') throw new TypeError('RTCIceServer is not a dictionary');
    if (server.urls === undefined) throw new TypeError('RTCIceServer: missing required member urls');
    return pyModel('RTCIceServer', convertDictionary(server, 'RTCIceServer', ICE_SERVER));
  }

  const CONFIGURATION = {
    iceServers: ['ice_servers', (v) => {
      if (v === null) throw new TypeError('iceServers is not a sequence');
      return Array.from(v, toIceServer);
    }],
    iceTransportPolicy: ['ice_transport_policy', (v) => pyEnum('RTCIceTransportPolicy', v)],
    bundlePolicy: ['bundle_policy', (v) => pyEnum('RTCBundlePolicy', v)],
    rtcpMuxPolicy: ['rtcp_mux_policy', (v) => pyEnum('RTCRtcpMuxPolicy', v)],
    iceCandidatePoolSize: ['ice_candidate_pool_size', (v) => enforceRange(v, 0, 255)],
    alwaysNegotiateDataChannels: ['always_negotiate_data_channels', Boolean],
    rtpHeaderEncryptionPolicy: ['rtp_header_encryption_policy', (v) => pyEnum('RTCRtpHeaderEncryptionPolicy', v)],
    certificates: ['certificates', (v) => Array.from(v,
      (certificate) => toPy(requireInterface(certificate, RTCCertificate, 'RTCConfiguration.certificates')))],
  };

  const toConfiguration = (configuration) => pyModel('RTCConfiguration', convertDictionary(
    requireDictionary(configuration, 'RTCConfiguration'), 'RTCConfiguration', CONFIGURATION));

  const ANSWER_OPTIONS = {};
  const OFFER_OPTIONS = {
    ...ANSWER_OPTIONS,
    iceRestart: ['ice_restart', Boolean],
    offerToReceiveAudio: ['offer_to_receive_audio', Boolean],
    offerToReceiveVideo: ['offer_to_receive_video', Boolean],
  };

  // RTCSessionDescriptionInit, whose type is required unless an implicit description is allowed
  function toDescriptionInit(description, typeRequired) {
    if (description instanceof RTCSessionDescription) return description;
    const init = requireDictionary(description, 'RTCSessionDescriptionInit');
    const sdp = init.sdp === undefined ? '' : String(init.sdp);
    if (init.type === undefined) {
      if (typeRequired) throw new TypeError('RTCSessionDescriptionInit: missing required member type');
      return pyModel('RTCLocalSessionDescriptionInit', {sdp});
    }
    return pyModel('RTCSessionDescriptionInit', {type: pyEnum('RTCSdpType', init.type), sdp});
  }

  class RTCPeerConnection extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args,
        (configuration) => construct('RTCPeerConnection', {configuration: toConfiguration(configuration)})));
    }

    async createOffer(options) {
      const kwargs = convertDictionary(requireDictionary(options, 'RTCOfferOptions'), 'RTCOfferOptions', OFFER_OPTIONS);
      return callAsyncMethod(this, 'create_offer', pyModel('RTCOfferOptions', kwargs));
    }

    async createAnswer(options) {
      const kwargs = convertDictionary(requireDictionary(options, 'RTCAnswerOptions'), 'RTCAnswerOptions',
        ANSWER_OPTIONS);
      return callAsyncMethod(this, 'create_answer', pyModel('RTCAnswerOptions', kwargs));
    }

    async setLocalDescription(description) {
      return callAsyncMethod(this, 'set_local_description', toDescriptionInit(description, false));
    }

    async setRemoteDescription(description) {
      return callAsyncMethod(this, 'set_remote_description', toDescriptionInit(description, true));
    }

    addTrack(track, ...streams) {
      requireInterface(track, MediaStreamTrack, 'RTCPeerConnection.addTrack');
      streams.forEach((stream) => requireInterface(stream, MediaStream, 'RTCPeerConnection.addTrack'));
      return callMethod(this, 'add_track', track, ...streams);
    }

    addTransceiver(trackOrKind, init) {
      const trackOrPyKind = typeof trackOrKind === 'string'
        ? pyEnum('MediaType', trackOrKind, false)
        : requireInterface(trackOrKind, MediaStreamTrack, 'RTCPeerConnection.addTransceiver');
      if (init === undefined) return callMethod(this, 'add_transceiver', trackOrPyKind);
      return callMethod(this, 'add_transceiver', trackOrPyKind,
        pyModel('RTCRtpTransceiverInit', convertDictionary(init, 'RTCRtpTransceiverInit', TRANSCEIVER_INIT)));
    }

    getTransceivers() { return callMethod(this, 'get_transceivers'); }
    getSenders() { return callMethod(this, 'get_senders'); }
    getReceivers() { return callMethod(this, 'get_receivers'); }
    removeTrack(sender) {
      callMethod(this, 'remove_track', requireInterface(sender, RTCRtpSender, 'RTCPeerConnection.removeTrack'));
    }

    createDataChannel(label, init = {}) {
      requireArguments(arguments, 1, 'RTCPeerConnection.createDataChannel');
      const kwargs = convertDictionary(requireDictionary(init, 'RTCDataChannelInit'), 'RTCDataChannelInit',
        DATA_CHANNEL_INIT);
      return callMethod(this, 'create_data_channel', toUSVString(label), pyModel('RTCDataChannelInit', kwargs));
    }

    async addIceCandidate(candidate) {
      if (candidate instanceof RTCIceCandidate) return callAsyncMethod(this, 'add_ice_candidate', candidate);
      const init = candidate ?? {};
      return callAsyncMethod(this, 'add_ice_candidate', pyModel('RTCIceCandidateInit', {
        candidate: init.candidate === undefined ? '' : String(init.candidate),
        sdp_mid: init.sdpMid ?? null,
        sdp_m_line_index: init.sdpMLineIndex ?? null,
        username_fragment: init.usernameFragment ?? null,
      }));
    }

    async getStats(selector) {
      if (selector !== undefined && selector !== null) {
        requireInterface(selector, MediaStreamTrack, 'RTCPeerConnection.getStats');
      }
      return callAsyncMethod(this, 'get_stats', ...(selector ? [selector] : []));
    }

    static async generateCertificate(algorithm) {
      requireArguments(arguments, 1, 'RTCPeerConnection.generateCertificate');
      return unwrap(await bridge.call_async_static('RTCPeerConnection', 'generate_certificate', [toAlgorithm(algorithm)]));
    }

    getConfiguration() { return callMethod(this, 'get_configuration'); }
    setConfiguration(configuration) { callMethod(this, 'set_configuration', toConfiguration(configuration)); }
    restartIce() { callMethod(this, 'restart_ice'); }
    close() { callMethod(this, 'close'); }
  }
  defineAttributes(RTCPeerConnection, [
    ['localDescription', 'local_description'],
    ['remoteDescription', 'remote_description'],
    ['currentLocalDescription', 'current_local_description'],
    ['currentRemoteDescription', 'current_remote_description'],
    ['pendingLocalDescription', 'pending_local_description'],
    ['pendingRemoteDescription', 'pending_remote_description'],
    ['signalingState', 'signaling_state'],
    ['connectionState', 'connection_state'],
    ['iceConnectionState', 'ice_connection_state'],
    ['iceGatheringState', 'ice_gathering_state'],
    ['sctp', 'sctp'],
    ['canTrickleIceCandidates', 'can_trickle_ice_candidates'],
  ]);
  defineEventHandlers(RTCPeerConnection, [
    'negotiationneeded', 'icecandidate', 'icecandidateerror', 'signalingstatechange', 'iceconnectionstatechange',
    'icegatheringstatechange', 'connectionstatechange', 'track', 'datachannel',
  ]);

  // maplike<DOMString, object>
  class RTCStatsReport {
    #stats;

    constructor(token, entries) {
      if (token !== INTERNAL) throw new TypeError('Illegal constructor');
      this.#stats = new Map(entries);
    }

    get size() { return this.#stats.size; }
    get(id) { return this.#stats.get(id); }
    has(id) { return this.#stats.has(id); }
    keys() { return this.#stats.keys(); }
    values() { return this.#stats.values(); }
    entries() { return this.#stats.entries(); }
    forEach(callback, thisArg) { this.#stats.forEach((v, k) => callback.call(thisArg, v, k, this)); }
    [Symbol.iterator]() { return this.#stats[Symbol.iterator](); }
  }

  class RTCError extends DOMException {
    constructor(init, message = '') {
      if (init === INTERNAL) {
        // an error of the library, which is valid already: new RTCError(INTERNAL, {init, message})
        ({init, message} = message);
      } else {
        if (init === undefined || init === null || init.errorDetail === undefined) {
          throw new TypeError('RTCError: missing required member errorDetail');
        }
        // the library validates the error detail, an RTCErrorDetailType
        construct('RTCErrorInit', {error_detail: pyEnum('RTCErrorDetailType', init.errorDetail)});
      }
      super(message, 'OperationError');
      const detail = {
        sdpLineNumber: null, sctpCauseCode: null, receivedAlert: null, sentAlert: null, httpRequestStatusCode: null,
        ...init,
      };
      for (const [key, value] of Object.entries(detail)) {
        Object.defineProperty(this, key, {value: value ?? null, enumerable: true});
      }
    }
  }

  const events = {
    Event: defineEvent('Event'),
    RTCPeerConnectionIceEvent: defineEvent(
      'RTCPeerConnectionIceEvent', [], {candidate: null, url: null}, {candidate: () => RTCIceCandidate}),
    RTCPeerConnectionIceErrorEvent: defineEvent(
      'RTCPeerConnectionIceErrorEvent', ['errorCode'], {address: null, port: null, url: '', errorText: ''}),
    RTCTrackEvent: defineEvent('RTCTrackEvent', ['receiver', 'track', 'transceiver'], {streams: []}, {
      receiver: () => RTCRtpReceiver, track: () => MediaStreamTrack, transceiver: () => RTCRtpTransceiver}),
    RTCErrorEvent: defineEvent('RTCErrorEvent', ['error']),
    RTCDataChannelEvent: defineEvent('RTCDataChannelEvent', ['channel'], {}, {channel: () => RTCDataChannel}),
    MediaStreamTrackEvent: defineEvent('MediaStreamTrackEvent', ['track']),
    RTCDTMFToneChangeEvent: defineEvent('RTCDTMFToneChangeEvent', [], {tone: ''}),
    MessageEvent: defineEvent('MessageEvent', [], {data: null, origin: '', lastEventId: '', source: null, ports: []}),
    RTCTransformEvent: defineEvent('RTCTransformEvent', ['transformer'], {}, {transformer: () => RTCRtpScriptTransformer}),
    SFrameTransformErrorEvent: defineEvent('SFrameTransformErrorEvent', ['errorType', 'frame'], {keyID: null}),
    KeyFrameRequestEvent: class KeyFrameRequestEvent extends Event {
      constructor(type, rid) {
        requireArguments(arguments, 1, 'KeyFrameRequestEvent');
        super(String(type));
        const value = typeof rid === 'object' && rid !== null ? rid.rid : rid;
        this.rid = value === undefined || value === null ? null : String(value);
      }
    },
  };

  // Streams, frames, processors and generators of python-webrtc. Streams are the Python ones: scripts read and
  // write them, but can't construct them with a JS underlying source.
  class ReadableStream extends Interface {
    getReader(options) {
      const dict = requireDictionary(options, 'ReadableStreamGetReaderOptions');
      return callMethod(this, 'get_reader', pyJson('ReadableStreamGetReaderOptions', pick(dict, ['mode'])));
    }

    cancel() { return callAsyncMethod(this, 'cancel'); }

    pipeTo(destination, options) {
      requireInterface(destination, WritableStream, 'ReadableStream.pipeTo');
      const dict = requireDictionary(options, 'StreamPipeOptions');
      return callAsyncMethod(this, 'pipe_to', destination, pyJson('StreamPipeOptions', {
        preventClose: Boolean(dict.preventClose),
        preventAbort: Boolean(dict.preventAbort),
        preventCancel: Boolean(dict.preventCancel),
      }));
    }

    pipeThrough(transform, options) {
      const pair = requireMembers(transform, 'ReadableWritablePair', ['readable', 'writable']);
      requireInterface(pair.readable, ReadableStream, 'ReadableStream.pipeThrough');
      requireInterface(pair.writable, WritableStream, 'ReadableStream.pipeThrough');
      const dict = requireDictionary(options, 'StreamPipeOptions');
      return callMethod(this, 'pipe_through', pyModel('ReadableWritablePair', {
        readable: toPy(pair.readable), writable: toPy(pair.writable),
      }), pyJson('StreamPipeOptions', {
        preventClose: Boolean(dict.preventClose),
        preventAbort: Boolean(dict.preventAbort),
        preventCancel: Boolean(dict.preventCancel),
      }));
    }

    tee() { return callMethod(this, 'tee'); }

    async* [Symbol.asyncIterator]() {
      const reader = this.getReader();
      try {
        while (true) {
          const {value, done} = await reader.read();
          if (done) return;
          yield value;
        }
      } finally {
        reader.releaseLock();
      }
    }
  }
  defineAttributes(ReadableStream, [['locked', 'locked']]);

  class ReadableStreamDefaultReader extends Interface {
    read() { return callAsyncMethod(this, 'read'); }
    cancel() { return callAsyncMethod(this, 'cancel'); }
    releaseLock() { callMethod(this, 'release_lock'); }
    get closed() { return awaitAttr(this, 'closed').then(() => undefined); }
  }

  class WritableStream extends Interface {
    getWriter() { return callMethod(this, 'get_writer'); }
    close() { return callAsyncMethod(this, 'close'); }
    abort() { return callAsyncMethod(this, 'abort'); }
  }
  defineAttributes(WritableStream, [['locked', 'locked']]);

  class WritableStreamDefaultWriter extends Interface {
    write(chunk) { return callAsyncMethod(this, 'write', chunk).then(() => undefined); }
    close() { return callAsyncMethod(this, 'close').then(() => undefined); }
    abort() { return callAsyncMethod(this, 'abort').then(() => undefined); }
    releaseLock() { callMethod(this, 'release_lock'); }
    get ready() { return awaitAttr(this, 'ready').then(() => undefined); }
    get closed() { return awaitAttr(this, 'closed').then(() => undefined); }
  }
  defineAttributes(WritableStreamDefaultWriter, [['desiredSize', 'desired_size']]);

  // members of the WebIDL dictionaries the library takes, the others are left out as WebIDL does
  const pick = (dict, members) =>
    Object.fromEntries(members.filter((m) => dict[m] !== undefined).map((m) => [m, dict[m]]));
  // nested dictionaries, read from any object with their members (like a DOMRectReadOnly, whose members are getters)
  const toRectInit = (rect) => (rect == null ? rect : pick(rect, ['x', 'y', 'width', 'height']));
  const toColorSpaceInit = (space) => (space == null ? space : pick(space, ['primaries', 'transfer', 'matrix', 'fullRange']));
  const toLayout = (layout) => (layout == null ? layout : Array.from(layout, (plane) => pick(plane, ['offset', 'stride'])));
  const nested = (dict) => {
    const result = {...dict};
    for (const name of ['visibleRect', 'rect']) if (result[name] !== undefined) result[name] = toRectInit(result[name]);
    if (result.colorSpace !== undefined) result.colorSpace = toColorSpaceInit(result.colorSpace);
    if (result.layout !== undefined) result.layout = toLayout(result.layout);
    return result;
  };
  const VIDEO_FRAME_BUFFER_INIT = [
    'format', 'codedWidth', 'codedHeight', 'timestamp', 'duration', 'layout', 'visibleRect', 'rotation', 'flip',
    'displayWidth', 'displayHeight', 'colorSpace', 'metadata',
  ];
  const VIDEO_FRAME_INIT = [
    'duration', 'timestamp', 'alpha', 'visibleRect', 'rotation', 'flip', 'displayWidth', 'displayHeight', 'metadata',
  ];
  const copyToOptions = (options) =>
    pyJson('VideoFrameCopyToOptions', nested(pick(requireDictionary(options, 'VideoFrameCopyToOptions'), ['rect', 'layout', 'format', 'colorSpace'])));

  class VideoFrame extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, (image, init) => {
        requireArguments(args, 1, 'VideoFrame');
        const dict = requireDictionary(init, 'VideoFrameInit');
        if (image instanceof VideoFrame) {
          const init = pyJson('VideoFrameInit', nested(pick(dict, VIDEO_FRAME_INIT)));
          return construct('VideoFrame', {init}, [toPy(image)]);
        }
        if (image instanceof ArrayBuffer || ArrayBuffer.isView(image)) {
          const init = pyJson('VideoFrameBufferInit', nested(pick(dict, VIDEO_FRAME_BUFFER_INIT)));
          return construct('VideoFrame', {init}, [bytesOf(image)]);
        }
        // images, canvases and video elements are the browser's
        throw new TypeError('VideoFrame: the source is not a VideoFrame nor a BufferSource');
      }));
    }

    allocationSize(options) { return callMethod(this, 'allocation_size', copyToOptions(options)); }

    async copyTo(destination, options) {
      const bytes = bytesOf(destination, 'destination');
      const {layout, data} = unwrap(await bridge.video_frame_copy_to(pyObjects.get(this), bytes, copyToOptions(options)));
      bytes.set(new Uint8Array(data));
      return layout;
    }

    clone() { return callMethod(this, 'clone'); }
    close() { callMethod(this, 'close'); }
    metadata() { return callMethod(this, 'metadata'); }
  }
  defineAttributes(VideoFrame, [
    ['format', 'format'],
    ['codedWidth', 'coded_width'],
    ['codedHeight', 'coded_height'],
    ['codedRect', 'coded_rect'],
    ['visibleRect', 'visible_rect'],
    ['rotation', 'rotation'],
    ['flip', 'flip'],
    ['displayWidth', 'display_width'],
    ['displayHeight', 'display_height'],
    ['duration', 'duration'],
    ['timestamp', 'timestamp'],
    ['colorSpace', 'color_space'],
  ]);

  class VideoColorSpace extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, (init) => {
        const dict = requireDictionary(init, 'VideoColorSpaceInit');
        const kwargs = {};
        if (dict.primaries != null) kwargs.primaries = pyEnum('VideoColorPrimaries', dict.primaries);
        if (dict.transfer != null) kwargs.transfer = pyEnum('VideoTransferCharacteristics', dict.transfer);
        if (dict.matrix != null) kwargs.matrix = pyEnum('VideoMatrixCoefficients', dict.matrix);
        if (dict.fullRange != null) kwargs.full_range = Boolean(dict.fullRange);
        return construct('VideoColorSpace', kwargs);
      }));
    }

    toJSON() { return callMethod(this, 'to_json'); }
  }
  defineAttributes(VideoColorSpace, [
    ['primaries', 'primaries'],
    ['transfer', 'transfer'],
    ['matrix', 'matrix'],
    ['fullRange', 'full_range'],
  ]);

  const AUDIO_DATA_INIT = ['format', 'sampleRate', 'numberOfFrames', 'numberOfChannels', 'timestamp', 'data'];
  const audioCopyToOptions = (options) => pyJson('AudioDataCopyToOptions',
    pick(requireDictionary(options, 'options'), ['planeIndex', 'frameOffset', 'frameCount', 'format']));

  class AudioData extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, (init) => {
        requireArguments(args, 1, 'AudioData');
        const dict = pick(requireDictionary(init, 'AudioDataInit'), AUDIO_DATA_INIT);
        if (dict.data !== undefined) dict.data = bytesOf(dict.data, 'AudioDataInit.data');
        return construct('AudioData', {init: pyJson('AudioDataInit', dict)});
      }));
    }

    allocationSize(options) { return callMethod(this, 'allocation_size', audioCopyToOptions(options)); }

    copyTo(destination, options) {
      const bytes = bytesOf(destination, 'destination');
      const data = unwrap(bridge.audio_data_copy_to(pyObjects.get(this), bytes, audioCopyToOptions(options)));
      bytes.set(new Uint8Array(data));
    }

    clone() { return callMethod(this, 'clone'); }
    close() { callMethod(this, 'close'); }
  }
  defineAttributes(AudioData, [
    ['format', 'format'],
    ['sampleRate', 'sample_rate'],
    ['numberOfFrames', 'number_of_frames'],
    ['numberOfChannels', 'number_of_channels'],
    ['duration', 'duration'],
    ['timestamp', 'timestamp'],
  ]);

  class MediaStreamTrackProcessor extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, (init) => {
        requireArguments(args, 1, 'MediaStreamTrackProcessor');
        // Chrome also takes the track itself
        const dict = init instanceof MediaStreamTrack
          ? {track: init}
          : requireDictionary(init, 'MediaStreamTrackProcessorInit');
        requireInterface(dict.track, MediaStreamTrack, 'MediaStreamTrackProcessor');
        const kwargs = {track: toPy(dict.track)};
        if (dict.maxBufferSize !== undefined) kwargs.max_buffer_size = enforceRange(dict.maxBufferSize, 0, 65535);
        return construct('MediaStreamTrackProcessor', {init: pyModel('MediaStreamTrackProcessorInit', kwargs)});
      }));
    }
  }
  defineAttributes(MediaStreamTrackProcessor, [
    ['readable', 'readable'],
    ['discardedFrames', 'discarded_frames'],
    ['totalFrames', 'total_frames'],
  ]);

  class VideoTrackGenerator extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, () => construct('VideoTrackGenerator')));
    }
  }
  defineAttributes(VideoTrackGenerator, [
    ['writable', 'writable'],
    ['track', 'track'],
    ['muted', 'muted', Boolean],
  ]);

  class MediaStreamTrackGenerator extends MediaStreamTrack {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, (init) => {
        requireArguments(args, 1, 'MediaStreamTrackGenerator');
        const kind = typeof init === 'string' ? init : requireDictionary(init, 'MediaStreamTrackGeneratorInit').kind;
        return construct('MediaStreamTrackGenerator', {kind: String(kind)});
      }));
    }
  }
  defineAttributes(MediaStreamTrackGenerator, [['writable', 'writable']]);

  // WebRTC Encoded Transform: the worker is a Worker of polyfills.js
  const transformerOptions = new WeakMap();

  class RTCRtpScriptTransform extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, (workerOrWorkerAndParameters, options, transfer) => {
        requireArguments(args, 1, 'RTCRtpScriptTransform');
        let worker = workerOrWorkerAndParameters;
        let type;
        if (!(worker instanceof Worker)) {
          const dict = requireMembers(worker, 'WorkerAndParameters', ['worker']);
          worker = requireInterface(dict.worker, Worker, 'WorkerAndParameters.worker');
          type = dict.type;
        }
        const deliver = (pyEvent) => {
          const event = unwrap(bridge.wrap(pyEvent));
          transformerOptions.set(event.transformer, options);
          worker.__dispatchInScope(event);
        };
        const pyWorker = type === undefined
          ? deliver
          : pyModel('WorkerAndParameters', {worker: deliver, type: pyEnum('RTCRtpScriptTransformType', type)});
        const transferList = transfer === undefined ? null : Array.from(transfer, () => ({}));
        return construct('RTCRtpScriptTransform', {}, [pyWorker, null, transferList]);
      }));
    }
  }

  class RTCRtpScriptTransformer extends Interface {
    get options() { return transformerOptions.get(this); }

    generateKeyFrame(rid) {
      return callAsyncMethod(this, 'generate_key_frame', rid === undefined ? null : String(rid)).then(() => undefined);
    }

    sendKeyFrameRequest() { return callAsyncMethod(this, 'send_key_frame_request').then(() => undefined); }
  }
  defineAttributes(RTCRtpScriptTransformer, [
    ['readable', 'readable'],
    ['writable', 'writable'],
  ]);
  defineEventHandlers(RTCRtpScriptTransformer, ['keyframerequest']);

  // shares the memory of the library's bytearray, the same ArrayBuffer while that bytearray is
  const frameBuffers = new WeakMap();

  class EncodedFrame extends Interface {
    get data() {
      const result = bridge.get_buffer(pyObjects.get(this), 'data');
      if (result.error) throw toJsError(result.error);
      const [id, bytes, detached] = result.ok;
      const cached = frameBuffers.get(this);
      if (cached?.id === id) return cached.buffer;
      let {buffer} = bytes;
      if (detached) {
        buffer = new ArrayBuffer(0);
        buffer.transfer();
      }
      frameBuffers.set(this, {id, buffer});
      return buffer;
    }

    set data(value) {
      if (!(value instanceof ArrayBuffer) || value.resizable) throw new TypeError('data is not an ArrayBuffer');
      setAttr(this, 'data', value);
    }

    getMetadata() { return callMethod(this, 'get_metadata'); }

    // [Serializable]: a copy of the frame (see structuredClone in polyfills.js)
    [Symbol.for('wpt.serialize')]() { return new this.constructor(this); }
  }

  const frameConstructor = (name, optionsName) => function (args) {
    const [originalFrame, options] = args;
    requireArguments(args, 1, name);
    requireInterface(originalFrame, this, name);
    const dict = requireDictionary(options, optionsName);
    const pyOptions = dict.metadata === undefined ? null : pyJson(optionsName, {metadata: requireDictionary(dict.metadata, 'metadata')});
    return construct(name, {}, [toPy(originalFrame), pyOptions]);
  };

  class RTCEncodedVideoFrame extends EncodedFrame {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, () => frameConstructor('RTCEncodedVideoFrame', 'RTCEncodedVideoFrameOptions').call(RTCEncodedVideoFrame, args)));
    }
  }
  defineAttributes(RTCEncodedVideoFrame, [['type', 'type']]);

  class RTCEncodedAudioFrame extends EncodedFrame {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, () => frameConstructor('RTCEncodedAudioFrame', 'RTCEncodedAudioFrameOptions').call(RTCEncodedAudioFrame, args)));
    }
  }

  function keyBytes(key) {
    const data = key?.[Symbol.for('wpt.keyData')];
    if (!(data instanceof Uint8Array)) throw new TypeError('key is not a CryptoKey');
    return data;
  }

  // CryptoKeyID, (SmallCryptoKeyID or bigint): the library checks the range of a bigint
  const toKeyID = (value) => (typeof value === 'bigint' ? value : enforceRange(value, 0, Number.MAX_SAFE_INTEGER));

  const sframeOptions = (args, name, dictName, members) => {
    requireArguments(args, 1, name);
    return pyJson(dictName, pick(requireMembers(args[0], dictName, ['cipherSuite']), members));
  };

  const encryptorManager = {
    async setEncryptionKey(key, keyId) {
      requireArguments(arguments, 2, 'setEncryptionKey');
      return callAsyncMethod(this, 'set_encryption_key', keyBytes(key), toKeyID(keyId)).then(() => undefined);
    },
  };
  const decryptorManager = {
    async addDecryptionKey(key, keyId) {
      requireArguments(arguments, 2, 'addDecryptionKey');
      return callAsyncMethod(this, 'add_decryption_key', keyBytes(key), toKeyID(keyId)).then(() => undefined);
    },
    async removeDecryptionKey(keyId) {
      requireArguments(arguments, 1, 'removeDecryptionKey');
      return callAsyncMethod(this, 'remove_decryption_key', toKeyID(keyId)).then(() => undefined);
    },
  };

  class RTCRtpSFrameEncryptor extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, () => construct('RTCRtpSFrameEncryptor', {}, [
        sframeOptions(args, 'RTCRtpSFrameEncryptor', 'RTCRtpSFrameEncryptorOptions', ['cipherSuite', 'type'])])));
    }
  }
  Object.assign(RTCRtpSFrameEncryptor.prototype, encryptorManager);

  class RTCRtpSFrameDecryptor extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, () => construct('RTCRtpSFrameDecryptor', {}, [
        sframeOptions(args, 'RTCRtpSFrameDecryptor', 'SFrameTransformOptions', ['cipherSuite'])])));
    }
  }
  Object.assign(RTCRtpSFrameDecryptor.prototype, decryptorManager);
  defineEventHandlers(RTCRtpSFrameDecryptor, ['error']);

  class SFrameEncryptorStream extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, () => construct('SFrameEncryptorStream', {}, [
        sframeOptions(args, 'SFrameEncryptorStream', 'SFrameTransformOptions', ['cipherSuite'])])));
    }
  }
  Object.assign(SFrameEncryptorStream.prototype, encryptorManager);
  defineAttributes(SFrameEncryptorStream, [['readable', 'readable'], ['writable', 'writable']]);

  class SFrameDecryptorStream extends Interface {
    constructor(...args) {
      super(INTERNAL, pyObjectOf(args, () => construct('SFrameDecryptorStream', {}, [
        sframeOptions(args, 'SFrameDecryptorStream', 'SFrameTransformOptions', ['cipherSuite'])])));
    }
  }
  Object.assign(SFrameDecryptorStream.prototype, decryptorManager);
  defineAttributes(SFrameDecryptorStream, [['readable', 'readable'], ['writable', 'writable']]);
  defineEventHandlers(SFrameDecryptorStream, ['error']);

  class OverconstrainedError extends DOMException {
    constructor(constraint, message = '') {
      super(message, 'OverconstrainedError');
      this.constraint = String(constraint);
    }
  }

  const interfaces = {
    RTCCertificate,
    RTCDTMFSender,
    RTCIceCandidate,
    RTCDataChannel,
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
    ReadableStream,
    ReadableStreamDefaultReader,
    WritableStream,
    WritableStreamDefaultWriter,
    VideoFrame,
    VideoColorSpace,
    AudioData,
    MediaStreamTrackProcessor,
    VideoTrackGenerator,
    MediaStreamTrackGenerator,
    RTCRtpScriptTransform,
    RTCRtpScriptTransformer,
    RTCEncodedVideoFrame,
    RTCEncodedAudioFrame,
    RTCRtpSFrameEncryptor,
    RTCRtpSFrameDecryptor,
    SFrameEncryptorStream,
    SFrameDecryptorStream,
  };
  Object.assign(globalThis, interfaces, {OverconstrainedError});
  // the names WebKit shipped SFrame with, which WPT tests use
  Object.assign(globalThis, {
    RTCRtpSFrameEncrypter: RTCRtpSFrameEncryptor,
    RTCRtpSFrameDecrypter: RTCRtpSFrameDecryptor,
    SFrameEncrypterStream: SFrameEncryptorStream,
    SFrameDecrypterStream: SFrameDecryptorStream,
  });
  const {Event: _, ...eventInterfaces} = events;
  Object.assign(globalThis, eventInterfaces, {RTCError, RTCStatsReport});

  // each a value, or a constraint on it (ConstrainULong, ConstrainDouble) the library has a model of
  const constrain = (name) => (v) => (typeof v === 'object' && v !== null ? pyJson(name, v) : v);
  const VIDEO_CONSTRAINTS = {
    width: ['width', constrain('ConstrainULongRange')],
    height: ['height', constrain('ConstrainULongRange')],
    frameRate: ['frame_rate', constrain('ConstrainDoubleRange')],
  };

  globalThis.navigator = {
    mediaDevices: {
      async getUserMedia(constraints = {}) {
        const video = typeof constraints.video === 'object' && constraints.video !== null
          ? pyModel('MediaTrackConstraints', convertDictionary(constraints.video, 'MediaTrackConstraints', VIDEO_CONSTRAINTS))
          : Boolean(constraints.video);
        return unwrap(await bridge.get_user_media(
          pyModel('MediaStreamConstraints', {audio: Boolean(constraints.audio), video})));
      },
    },
  };
})();
