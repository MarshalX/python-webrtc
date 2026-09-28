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
  globalThis.window = globalThis;
  // an event handler attribute of the window, which scripts assign as a global
  globalThis.onmessage ??= null;
  // The global is an EventTarget, where exceptions of event listeners are reported (testharness listens there)
  const globalTarget = new EventTarget();
  for (const method of ['addEventListener', 'removeEventListener', 'dispatchEvent']) {
    globalThis[method] ??= globalTarget[method].bind(globalTarget);
  }
  if (!globalThis.performance) {
    const timeOrigin = bridge.now();
    globalThis.performance = {timeOrigin, now: () => bridge.now() - timeOrigin};
  }

  // UTF-8 only
  globalThis.TextEncoder ??= class TextEncoder {
    get encoding() { return 'utf-8'; }
    encode(input = '') {
      const wellFormed = String(input).replace(
        /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g, '\uFFFD');
      return Uint8Array.from(unescape(encodeURIComponent(wellFormed)), (c) => c.charCodeAt(0));
    }
  };
  globalThis.TextDecoder ??= class TextDecoder {
    get encoding() { return 'utf-8'; }
    decode(input = new Uint8Array()) {
      const bytes = input instanceof ArrayBuffer
        ? new Uint8Array(input) : new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
      let binary = '';
      for (const byte of bytes) binary += String.fromCharCode(byte);
      try {
        return decodeURIComponent(escape(binary));
      } catch {
        return binary;
      }
    }
  };

  // Blob and structuredClone as far as tests of WebRTC use them: in-memory bytes and plain data
  globalThis.Blob ??= class Blob {
    #bytes;
    #type;

    constructor(parts = [], options = {}) {
      const chunks = Array.from(parts, (part) => {
        if (part instanceof Blob) return part.#bytes;
        if (part instanceof ArrayBuffer) return new Uint8Array(part.slice(0));
        if (ArrayBuffer.isView(part)) return new Uint8Array(part.buffer.slice(part.byteOffset, part.byteOffset + part.byteLength));
        return new TextEncoder().encode(String(part));
      });
      this.#bytes = new Uint8Array(chunks.reduce((n, c) => n + c.length, 0));
      let offset = 0;
      for (const chunk of chunks) {
        this.#bytes.set(chunk, offset);
        offset += chunk.length;
      }
      this.#type = String(options.type ?? '').toLowerCase();
    }

    get size() { return this.#bytes.length; }
    get type() { return this.#type; }
    async arrayBuffer() { return this.#bytes.slice().buffer; }
    async text() { return new TextDecoder().decode(this.#bytes); }
    slice(start = 0, end = this.size, type = '') { return new Blob([this.#bytes.slice(start, end)], {type}); }
    static bytesOf(blob) { return blob.#bytes; }
  };
  globalThis.FileReader ??= class FileReader extends EventTarget {
    result = null;
    readyState = 0;
    error = null;
    onload = null;
    onloadend = null;
    onerror = null;

    #read(blob, convert) {
      this.readyState = 1;
      setTimeout(() => {
        this.result = convert(Blob.bytesOf(blob));
        this.readyState = 2;
        this.dispatchEvent(new Event('load'));
        this.dispatchEvent(new Event('loadend'));
      }, 0);
    }

    readAsArrayBuffer(blob) { this.#read(blob, (bytes) => bytes.slice().buffer); }
    readAsText(blob) { this.#read(blob, (bytes) => new TextDecoder().decode(bytes)); }
  };
  globalThis.structuredClone ??= function structuredClone(value) {
    if (value === null || typeof value !== 'object') return value;
    if (value instanceof ArrayBuffer) return value.slice(0);
    if (ArrayBuffer.isView(value)) return new value.constructor(value);
    if (value instanceof Blob) return value;
    if (Array.isArray(value)) return value.map(structuredClone);
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, structuredClone(v)]));
  };

  function reportException(error) {
    const event = new Event('error');
    Object.assign(event, {error, message: String(error?.message ?? error), filename: '', lineno: 0, colno: 0});
    globalThis.dispatchEvent(event);
  }
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
    if ('__bytes' in value) return Uint8Array.from(value.__bytes).buffer;
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

  // USVString conversion replaces lone surrogates
  const toUSVString = (value) => String(value).replace(
    /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g, '\uFFFD');

  // [EnforceRange] integer conversion
  function enforceRange(value, min, max) {
    const number = Number(value);
    if (!Number.isFinite(number)) throw new TypeError(`${value} is not a finite number`);
    const integer = Math.trunc(number);
    if (integer < min || integer > max) throw new TypeError(`${value} is out of range`);
    return integer;
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
    InvalidSyntaxError: 'SyntaxError',
    InvalidCharacterError: 'InvalidCharacterError',
  };
  const JS_ERROR_BY_CLASS = {
    TypeError,
    InvalidRangeError: RangeError,
    ValueError: TypeError,
    OverflowError: TypeError,
  };

  function toJsError({kind, message, init}) {
    if (kind === 'RTCError') return new RTCError(init, message);
    if (kind in JS_ERROR_BY_CLASS) return new JS_ERROR_BY_CLASS[kind](message);
    if (kind in DOM_EXCEPTION_BY_CLASS) return new DOMException(message, DOM_EXCEPTION_BY_CLASS[kind]);
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
  const callMethodWithKeywords = (self, name, args, kwargs) =>
    unwrap(bridge.call_method(pyObjects.get(self), name, args.map(toPy), kwargs));
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

  // EventTarget as in the DOM. The library emits events through on(), subscribed to when the first listener
  // of a type is added; its events are then dispatched to the JS listeners.
  const listenersOf = new WeakMap(); // target to Map(type to [{callback, once}])
  const subscriptionsOf = new WeakMap(); // target to Set(type)
  const eventHandlersOf = new WeakMap(); // target to Map(type to {handler, listener})

  class Interface {
    constructor(token, ref) {
      if (token !== INTERNAL) throw new TypeError('Illegal constructor');
      pyObjects.set(this, ref.__obj);
      wrappersById.set(ref.__id, this);
      // not sealed: tests add their own properties, as scripts can in a browser; event handler attributes
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
      if (index >= 0) list[index].removed = true, list.splice(index, 1);
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
          // like a browser, an exception of a listener is reported and doesn't stop the others
          reportException(e);
        }
      }
      return true;
    }
  }

  function subscribe(target, type) {
    if (!subscriptionsOf.has(target)) subscriptionsOf.set(target, new Set());
    const subscriptions = subscriptionsOf.get(target);
    if (subscriptions.has(type)) return;
    subscriptions.add(type);
    const result = bridge.subscribe(pyObjects.get(target), type, (pyEvent) => {
      const event = fromPy(pyEvent);
      // a binary message is converted to the binaryType of the channel
      if (target instanceof RTCDataChannel && event.data instanceof ArrayBuffer && target.binaryType === 'blob') {
        event.data = new Blob([event.data]);
      }
      target.dispatchEvent(event);
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
        if (arguments.length < 1) throw new TypeError(`${name}: 1 argument required`);
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
  }
  defineAttributes(MediaStreamTrack, [
    ['id', 'id'],
    ['kind', 'kind'],
    ['label', 'label'],
    ['enabled', 'enabled', Boolean],
    ['muted', 'muted'],
    ['readyState', 'ready_state'],
  ]);
  defineEventHandlers(MediaStreamTrack, ['mute', 'unmute', 'ended']);

  class MediaStream extends Interface {
    constructor(...args) {
      if (args[0] === INTERNAL) {
        super(...args);
        return;
      }
      let tracks = [];
      if (args.length && args[0] !== undefined) {
        const source = args[0];
        tracks = source instanceof MediaStream ? source.getTracks() : Array.from(source,
          (track) => requireInterface(track, MediaStreamTrack, 'MediaStream constructor'));
      }
      super(INTERNAL, construct('MediaStream', {tracks: tracks.map(toPy)}));
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

  function toAlgorithm(algorithm) {
    if (typeof algorithm !== 'object' || algorithm === null) return String(algorithm);
    const converted = {name: String(algorithm.name)};
    if (algorithm.namedCurve !== undefined) converted.namedCurve = String(algorithm.namedCurve);
    if (algorithm.modulusLength !== undefined) converted.modulusLength = enforceRange(algorithm.modulusLength, 0, 2 ** 32 - 1);
    if (algorithm.publicExponent !== undefined) converted.publicExponent = algorithm.publicExponent;
    if (algorithm.hash !== undefined) {
      converted.hash = typeof algorithm.hash === 'object' ? String(algorithm.hash.name) : String(algorithm.hash);
    }
    return converted;
  }

  class RTCIceCandidate extends Interface {
    constructor(...args) {
      if (args[0] === INTERNAL) {
        super(...args);
        return;
      }
      const init = args[0] ?? {};
      super(INTERNAL, construct('RTCIceCandidate', {
        candidate: init.candidate === undefined ? '' : String(init.candidate),
        sdp_mid: init.sdpMid === undefined || init.sdpMid === null ? null : String(init.sdpMid),
        sdp_m_line_index: init.sdpMLineIndex ?? null,
        username_fragment: init.usernameFragment ?? null,
        relay_protocol: init.relayProtocol ?? null,
        url: init.url ?? null,
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

  class RTCIceTransport extends Interface {
    constructor(...args) {
      if (args[0] === INTERNAL) {
        super(...args);
        return;
      }
      super(INTERNAL, construct('RTCIceTransport', {}));
    }

    gather(options) {
      const init = requireDictionary(options, 'RTCIceGatherOptions') ?? {};
      const kwargs = {};
      if (init.gatherPolicy !== undefined) kwargs.gather_policy = pyEnum('RTCIceTransportPolicy', init.gatherPolicy);
      if (init.iceServers !== undefined) {
        if (init.iceServers === null) throw new TypeError('iceServers is not a sequence');
        kwargs.ice_servers = Array.from(init.iceServers, toIceServer);
      }
      callMethodWithKeywords(this, 'gather', [], kwargs);
    }

    start(remoteParameters, role = 'controlled') {
      const init = requireDictionary(remoteParameters, 'RTCIceParameters') ?? {};
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

    getSelectedCandidatePair() {
      const pair = callMethod(this, 'get_selected_candidate_pair');
      return pair === null ? null : {local: pair[0], remote: pair[1]};
    }
    getLocalCandidates() { return callMethod(this, 'get_local_candidates'); }
    getRemoteCandidates() { return callMethod(this, 'get_remote_candidates'); }
    getLocalParameters() { return toIceParameters(callMethod(this, 'get_local_parameters')); }
    getRemoteParameters() { return toIceParameters(callMethod(this, 'get_remote_parameters')); }
  }
  const toIceParameters = (parameters) =>
    parameters === null ? null : {usernameFragment: parameters[0], password: parameters[1]};
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
      encodings: Array.from(parameters.encodings, (e) => pyModel('RTCRtpEncodingParameters',
        convertDictionary(e, 'RTCRtpEncodingParameters', ENCODING_PARAMETERS))),
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

  const callStatic = (className, name, ...args) => unwrap(bridge.call_static(className, name, args.map(toPy)));

  class RTCDTMFSender extends Interface {
    insertDTMF(tones, duration, interToneGap) {
      if (arguments.length < 1) throw new TypeError('RTCDTMFSender.insertDTMF: 1 argument required');
      const args = [String(tones)];
      if (duration !== undefined) args.push(Math.trunc(Number(duration)) >>> 0);
      if (interToneGap !== undefined) args.push(Math.trunc(Number(interToneGap)) >>> 0);
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
      const encodingOptions = requireDictionary(options, 'RTCSetParameterOptions')?.encodingOptions;
      if (encodingOptions === undefined) return callAsyncMethod(this, 'set_parameters', converted);
      const keyFrames = Array.from(encodingOptions, (option) => Boolean(option?.keyFrame));
      return unwrap(await bridge.call_async_method(pyObjects.get(this), 'set_parameters', [toPy(converted)],
        {key_frames: keyFrames}));
    }

    async replaceTrack(track) {
      if (arguments.length < 1) throw new TypeError('RTCRtpSender.replaceTrack: 1 argument required');
      if (track !== null) requireInterface(track, MediaStreamTrack, 'RTCRtpSender.replaceTrack');
      return callAsyncMethod(this, 'replace_track', track);
    }

    setStreams(...streams) {
      streams.forEach((stream) => requireInterface(stream, MediaStream, 'RTCRtpSender.setStreams'));
      callMethod(this, 'set_streams', ...streams);
    }

    static getCapabilities(kind) {
      if (arguments.length < 1) throw new TypeError('RTCRtpSender.getCapabilities: 1 argument required');
      return callStatic('RTCRtpSender', 'get_capabilities', String(kind));
    }
  }
  defineAttributes(RTCRtpSender, [
    ['track', 'track'],
    ['transport', 'transport'],
    ['dtmf', 'dtmf'],
  ]);

  class RTCRtpReceiver extends Interface {
    getParameters() { return callMethod(this, 'get_parameters'); }
    async getStats() { return callAsyncMethod(this, 'get_stats'); }
    getSynchronizationSources() { return callMethod(this, 'get_synchronization_sources'); }
    getContributingSources() { return callMethod(this, 'get_contributing_sources'); }

    static getCapabilities(kind) {
      if (arguments.length < 1) throw new TypeError('RTCRtpReceiver.getCapabilities: 1 argument required');
      return callStatic('RTCRtpReceiver', 'get_capabilities', String(kind));
    }
  }
  defineAttributes(RTCRtpReceiver, [
    ['track', 'track'],
    ['transport', 'transport'],
    // a nullable DOMHighResTimeStamp
    ['jitterBufferTarget', 'jitter_buffer_target', (v) => (v === null ? null : Number(v))],
  ]);

  class RTCRtpTransceiver extends Interface {
    stop() { callMethod(this, 'stop'); }

    setCodecPreferences(codecs) {
      if (arguments.length < 1) throw new TypeError('RTCRtpTransceiver.setCodecPreferences: 1 argument required');
      callMethod(this, 'set_codec_preferences', Array.from(codecs, (codec) => toCodec(codec)));
    }

    getHeaderExtensionsToNegotiate() { return callMethod(this, 'get_header_extensions_to_negotiate'); }
    getNegotiatedHeaderExtensions() { return callMethod(this, 'get_negotiated_header_extensions'); }
    setHeaderExtensionsToNegotiate(extensions) {
      if (arguments.length < 1) {
        throw new TypeError('RTCRtpTransceiver.setHeaderExtensionsToNegotiate: 1 argument required');
      }
      callMethod(this, 'set_header_extensions_to_negotiate', Array.from(extensions, (e) => {
        requireMembers(e, 'RTCRtpHeaderExtensionCapability', ['uri']);
        return pyModel('RTCRtpHeaderExtensionCapability', {
          uri: String(e.uri),
          ...(e.direction === undefined ? {} : {direction: pyEnum('TransceiverDirection', e.direction)}),
        });
      }));
    }
  }
  defineAttributes(RTCRtpTransceiver, [
    ['mid', 'mid'],
    ['sender', 'sender'],
    ['receiver', 'receiver'],
    ['stopped', 'stopped'],
    ['direction', 'direction', (v) => pyEnum('TransceiverDirection', v)],
    ['currentDirection', 'current_direction'],
  ]);

  const binaryTypes = new WeakMap();

  class RTCDataChannel extends Interface {
    get binaryType() { return binaryTypes.get(this) ?? 'arraybuffer'; }
    // an enum attribute ignores values it doesn't have
    set binaryType(value) {
      if (value === 'arraybuffer' || value === 'blob') binaryTypes.set(this, value);
    }

    send(data) {
      if (arguments.length < 1) throw new TypeError('RTCDataChannel.send: 1 argument required');
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
    // unsigned long long, which wraps around
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

  const TRANSCEIVER_INIT = {
    direction: ['direction', (v) => pyEnum('TransceiverDirection', v)],
    streams: ['streams', (v) => Array.from(v, toPy)],
    sendEncodings: [
      'send_encodings',
      (v) => Array.from(v, (e) => convertDictionary(e, 'RTCRtpEncodingParameters', ENCODING_PARAMETERS)),
    ],
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

  const ANSWER_OPTIONS = {
    voiceActivityDetection: ['voice_activity_detection', Boolean],
  };
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
      return {sdp};
    }
    return {type: pyEnum('RTCSdpType', init.type), sdp};
  }


  class RTCPeerConnection extends Interface {
    constructor(...args) {
      if (args[0] === INTERNAL) {
        super(...args);
        return;
      }
      super(INTERNAL, construct('RTCPeerConnection', {configuration: toConfiguration(args[0])}));
    }

    async createOffer(options) {
      const kwargs = convertDictionary(requireDictionary(options, 'RTCOfferOptions'), 'RTCOfferOptions', OFFER_OPTIONS);
      return unwrap(await bridge.call_async_method(pyObjects.get(this), 'create_offer', [], kwargs));
    }

    async createAnswer(options) {
      const kwargs = convertDictionary(requireDictionary(options, 'RTCAnswerOptions'), 'RTCAnswerOptions',
        ANSWER_OPTIONS);
      return unwrap(await bridge.call_async_method(pyObjects.get(this), 'create_answer', [], kwargs));
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

    createDataChannel(label, init = {}) {
      if (arguments.length < 1) throw new TypeError('RTCPeerConnection.createDataChannel: 1 argument required');
      const kwargs = convertDictionary(requireDictionary(init, 'RTCDataChannelInit'), 'RTCDataChannelInit',
        DATA_CHANNEL_INIT);
      return callMethodWithKeywords(this, 'create_data_channel', [toUSVString(label)], kwargs);
    }

    async addIceCandidate(candidate) {
      if (candidate instanceof RTCIceCandidate) return callAsyncMethod(this, 'add_ice_candidate', candidate);
      const init = candidate ?? {};
      return callAsyncMethod(this, 'add_ice_candidate', {
        candidate: init.candidate === undefined ? '' : String(init.candidate),
        sdpMid: init.sdpMid ?? null,
        sdpMLineIndex: init.sdpMLineIndex ?? null,
        usernameFragment: init.usernameFragment ?? null,
      });
    }

    async getStats(selector) {
      if (selector !== undefined && selector !== null) {
        requireInterface(selector, MediaStreamTrack, 'RTCPeerConnection.getStats');
      }
      return callAsyncMethod(this, 'get_stats', ...(selector ? [selector] : []));
    }

    static async generateCertificate(algorithm) {
      if (arguments.length < 1) throw new TypeError('RTCPeerConnection.generateCertificate: 1 argument required');
      const args = [toAlgorithm(algorithm)];
      if (typeof algorithm === 'object' && algorithm !== null && algorithm.expires !== undefined) {
        args.push(enforceRange(algorithm.expires, 0, Number.MAX_SAFE_INTEGER));
      }
      return unwrap(await bridge.call_async_static('RTCPeerConnection', 'generate_certificate', args));
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
      if (init === undefined || init === null || init.errorDetail === undefined) {
        throw new TypeError('RTCError: missing required member errorDetail');
      }
      // the library validates the error detail, an RTCErrorDetailType
      construct('RTCError', {error_detail: pyEnum('RTCErrorDetailType', init.errorDetail), message: String(message)});
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
  };

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
  };
  Object.assign(globalThis, interfaces);
  const {Event: _, ...eventInterfaces} = events;
  Object.assign(globalThis, eventInterfaces, {RTCError, RTCStatsReport});

  globalThis.navigator = {
    mediaDevices: {
      async getUserMedia(constraints = {}) {
        if (!constraints.audio && !constraints.video) throw new TypeError('audio or video must be requested');
        const kwargs = {audio: Boolean(constraints.audio), video: Boolean(constraints.video)};
        // a number, or the ideal or exact value of a constraint
        const value = (constraint) => (typeof constraint === 'object' && constraint !== null
          ? constraint.exact ?? constraint.ideal ?? constraint.max ?? constraint.min : constraint);
        if (typeof constraints.video === 'object') {
          for (const [js, py] of [['width', 'width'], ['height', 'height'], ['frameRate', 'frame_rate']]) {
            const v = value(constraints.video[js]);
            if (typeof v === 'number') kwargs[py] = v;
          }
        }
        return unwrap(bridge.get_user_media(kwargs));
      },
    },
  };
})();
