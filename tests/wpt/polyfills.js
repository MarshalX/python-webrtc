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
  globalThis.structuredClone ??= function structuredClone(value) {
    if (value === null || typeof value !== 'object') return value;
    if (value instanceof ArrayBuffer) return value.slice(0);
    if (ArrayBuffer.isView(value)) return new value.constructor(value);
    if (value instanceof Blob) return value;
    if (Array.isArray(value)) return value.map(structuredClone);
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, structuredClone(v)]));
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
