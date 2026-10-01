/*
 *  Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
 *
 *  Use of this source code is governed by a BSD-style license
 *  that can be found in the LICENSE.md file in the root of the project.
 */

// Globals a browser has and the PythonMonkey shell doesn't, as far as tests of WebRTC use them. They have
// nothing to do with WebRTC, which is mapped by shim.js, evaluated after this script.
//
// Expects globalThis.__wpt = {bridge, ...} to be set by the runner.

(() => {
  'use strict';

  const {bridge} = globalThis.__wpt;

  globalThis.self = globalThis;
  globalThis.window = globalThis;
  // an event handler attribute of the window, which scripts assign as a global
  globalThis.onmessage ??= null;
  // The global is an EventTarget, where exceptions of event listeners are reported (testharness listens there)
  const globalTarget = new EventTarget();
  for (const method of ['addEventListener', 'removeEventListener', 'dispatchEvent']) {
    globalThis[method] ??= globalTarget[method].bind(globalTarget);
  }
  globalThis.queueMicrotask ??= (callback) => Promise.resolve().then(callback);
  if (!globalThis.performance) {
    const timeOrigin = bridge.now();
    globalThis.performance = {timeOrigin, now: () => bridge.now() - timeOrigin};
  }
  // in place of testdriver.js
  globalThis.test_driver = {
    set_permission: async () => {},
  };

  // UTF-8 only
  globalThis.TextEncoder ??= class TextEncoder {
    get encoding() { return 'utf-8'; }
    encode(input = '') {
      return Uint8Array.from(unescape(encodeURIComponent(String(input).toWellFormed())), (c) => c.charCodeAt(0));
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

  // WebCrypto as far as tests of WebRTC use it: secret keys imported from raw bytes, which the SFrame transforms
  // of shim.js take (Symbol.for('wpt.keyData'))
  const KEY_DATA = Symbol.for('wpt.keyData');
  globalThis.CryptoKey ??= class CryptoKey {
    #algorithm;
    #extractable;
    #usages;

    constructor(token, data, algorithm, extractable, usages) {
      if (token !== KEY_DATA) throw new TypeError('Illegal constructor');
      Object.defineProperty(this, KEY_DATA, {value: data});
      this.#algorithm = Object.freeze({...algorithm});
      this.#extractable = extractable;
      this.#usages = Object.freeze([...usages]);
    }

    get type() { return 'secret'; }
    get extractable() { return this.#extractable; }
    get algorithm() { return this.#algorithm; }
    get usages() { return this.#usages; }
  };
  globalThis.crypto ??= {};
  globalThis.crypto.subtle ??= {
    async importKey(format, keyData, algorithm, extractable, usages) {
      if (format !== 'raw') throw new DOMException(`Unsupported key format ${format}`, 'NotSupportedError');
      const view = keyData instanceof ArrayBuffer
        ? new Uint8Array(keyData) : new Uint8Array(keyData.buffer, keyData.byteOffset, keyData.byteLength);
      const name = typeof algorithm === 'object' ? String(algorithm.name) : String(algorithm);
      return new CryptoKey(KEY_DATA, Uint8Array.from(view), {name}, Boolean(extractable), Array.from(usages, String));
    },
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
    // not in a browser: the shim sends the bytes of a Blob without reading it asynchronously
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
  // platform objects that are [Serializable] define how they're cloned (see shim.js)
  const SERIALIZE = Symbol.for('wpt.serialize');
  // transferred objects are kept as they are: the worker of polyfills below runs in this realm
  function cloneWith(value, transferred) {
    if (value === null || typeof value !== 'object') return value;
    if (transferred.has(value)) return value;
    if (typeof value[SERIALIZE] === 'function') return value[SERIALIZE]();
    if (value instanceof ArrayBuffer) return value.slice(0);
    if (ArrayBuffer.isView(value)) return new value.constructor(value);
    if (value instanceof Blob) return value;
    if (Array.isArray(value)) return value.map((item) => cloneWith(item, transferred));
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, cloneWith(v, transferred)]));
  }
  const transferList = (transferOrOptions) =>
    (Array.isArray(transferOrOptions) ? transferOrOptions : transferOrOptions?.transfer ?? []);
  globalThis.structuredClone ??= (value, options) => cloneWith(value, new Set(transferList(options)));

  // Messages between a worker and the window cross threads in a browser, which takes a little while, and each is a
  // task of its own: tests start listening for the next message once a message is handled
  const CROSS_THREAD_DELAY_MS = 5;

  // runs callbacks one after another, each a while after the previous one ran
  class Mailbox {
    #queue = [];

    post(callback) {
      this.#queue.push(callback);
      if (this.#queue.length === 1) setTimeout(() => this.#next(), CROSS_THREAD_DELAY_MS);
    }

    #next() {
      const callback = this.#queue[0];
      try {
        callback();
      } finally {
        this.#queue.shift();
        if (this.#queue.length > 0) setTimeout(() => this.#next(), CROSS_THREAD_DELAY_MS);
      }
    }
  }

  // MessageChannel: messages are cloned and delivered as tasks, once the port is started (or has onmessage)
  class MessagePort extends EventTarget {
    #other = null;
    #mailbox = new Mailbox();
    #queue = [];
    #started = false;
    #onmessage = null;

    static entangle(port1, port2) {
      port1.#other = port2;
      port2.#other = port1;
    }

    postMessage(message, transferOrOptions) {
      const other = this.#other;
      const data = cloneWith(message, new Set(transferList(transferOrOptions)));
      other.#mailbox.post(() => other.#receive(data));
    }

    start() {
      this.#started = true;
      for (const data of this.#queue.splice(0)) this.#deliver(data);
    }

    close() { this.#other = null; }

    get onmessage() { return this.#onmessage; }

    set onmessage(handler) {
      this.#onmessage = handler;
      this.start();
    }

    #receive(data) {
      if (this.#started) this.#deliver(data);
      else this.#queue.push(data);
    }

    #deliver(data) {
      const event = new Event('message');
      Object.defineProperty(event, 'data', {value: data});
      // dispatchEvent calls the on<type> handler too
      this.dispatchEvent(event);
    }
  }
  globalThis.MessagePort ??= MessagePort;
  globalThis.MessageChannel ??= class MessageChannel {
    constructor() {
      this.port1 = new MessagePort();
      this.port2 = new MessagePort();
      MessagePort.entangle(this.port1, this.port2);
    }
  };

  // Worker, in process: the script runs on this global with a scope of its own (self, postMessage, on* handlers,
  // its globals), on the same event loop. Transferred objects (ports, streams, channels) pass as they are.
  const messageEvent = (data) => {
    const event = new Event('message');
    Object.defineProperty(event, 'data', {value: data});
    return event;
  };

  function workerScript(url) {
    if (url.startsWith('data:')) {
      const comma = url.indexOf(',');
      const body = url.slice(comma + 1);
      return url.slice(0, comma).endsWith(';base64') ? atob(body) : decodeURIComponent(body);
    }
    const base = globalThis.location.pathname;
    const path = url.startsWith('/') ? url : base.slice(0, base.lastIndexOf('/') + 1) + url;
    const result = bridge.read_text(path);
    if (result.error) throw new Error(`Worker: can't load ${url}: ${result.error.message}`);
    return result.ok;
  }

  globalThis.Worker ??= class Worker extends EventTarget {
    #scope;
    #ready;
    #mailbox = new Mailbox();
    onmessage = null;
    onerror = null;

    constructor(url) {
      super();
      const worker = this;
      const own = new EventTarget();
      const locals = {
        postMessage(message, transferOrOptions) {
          const data = cloneWith(message, new Set(transferList(transferOrOptions)));
          worker.#mailbox.post(() => worker.#dispatch(worker, messageEvent(data)));
        },
        addEventListener: own.addEventListener.bind(own),
        removeEventListener: own.removeEventListener.bind(own),
        dispatchEvent: own.dispatchEvent.bind(own),
        close() {},
        onmessage: null,
        onrtctransform: null,
      };
      this.#scope = new Proxy(locals, {
        has: (target, key) => key !== Symbol.unscopables,
        get(target, key) {
          if (key === 'self' || key === 'globalThis') return worker.#scope;
          if (key in target) return target[key];
          const value = globalThis[key];
          // global functions called through the scope get it as this
          return typeof value === 'function' && !('prototype' in value) ? value.bind(globalThis) : value;
        },
        set(target, key, value) {
          target[key] = value;
          return true;
        },
      });
      const code = workerScript(String(url));
      this.#ready = new Promise((resolve) => setTimeout(resolve, 0)).then(() => {
        // eslint-disable-next-line no-new-func
        new Function('scope', `with (scope) {\n${code}\n}`)(this.#scope);
      }).catch((error) => this.#error(error));
    }

    postMessage(message, transferOrOptions) {
      const data = cloneWith(message, new Set(transferList(transferOrOptions)));
      this.#ready.then(() => this.#dispatch(this.#scope, messageEvent(data)));
    }

    terminate() {}

    // delivers an event of the platform to the scope of the worker, like rtctransform
    __dispatchInScope(event) {
      this.#ready.then(() => this.#dispatch(this.#scope, event));
    }

    #dispatch(target, event) {
      try {
        if (target === this) {
          this.dispatchEvent(event);
          return;
        }
        target.dispatchEvent(event);
        const handler = target[`on${event.type}`];
        if (typeof handler === 'function') {
          const result = handler.call(target, event);
          if (result instanceof Promise) result.catch((error) => this.#error(error));
        }
      } catch (error) {
        this.#error(error);
      }
    }

    #error(error) {
      const event = new Event('error');
      Object.defineProperty(event, 'message', {value: String(error?.message ?? error)});
      Object.defineProperty(event, 'error', {value: error});
      this.dispatchEvent(event);
    }
  };

  // the geometry of the visible rect of a VideoFrame
  globalThis.DOMRectReadOnly ??= class DOMRectReadOnly {
    #x;
    #y;
    #width;
    #height;

    constructor(x = 0, y = 0, width = 0, height = 0) {
      [this.#x, this.#y, this.#width, this.#height] = [x, y, width, height].map(Number);
    }

    get x() { return this.#x; }
    get y() { return this.#y; }
    get width() { return this.#width; }
    get height() { return this.#height; }
    get top() { return Math.min(this.#y, this.#y + this.#height); }
    get right() { return Math.max(this.#x, this.#x + this.#width); }
    get bottom() { return Math.max(this.#y, this.#y + this.#height); }
    get left() { return Math.min(this.#x, this.#x + this.#width); }
    toJSON() { return {x: this.x, y: this.y, width: this.width, height: this.height}; }
  };
})();
