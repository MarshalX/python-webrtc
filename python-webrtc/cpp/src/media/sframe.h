//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_SFRAME_H_
#define PYTHON_WEBRTC_MEDIA_SFRAME_H_

#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <span>
#include <vector>

#include <pybind11/pybind11.h>

namespace python_webrtc {

  using Octets = std::vector<uint8_t>;
  using OctetSpan = std::span<const uint8_t>;

  // The cipher suites of RFC 9605 Section 4.5 and draft-barnes-sframe-iana-256, by their identifiers
  enum class SFrameCipherSuite : uint8_t {
    kAes128CtrHmacSha256_80 = 1,
    kAes128CtrHmacSha256_64 = 2,
    kAes128CtrHmacSha256_32 = 3,
    kAes128GcmSha256_128 = 4,
    kAes256GcmSha512_128 = 5,
    kAes256CtrHmacSha512_80 = 6,
    kAes256CtrHmacSha512_64 = 7,
    kAes256CtrHmacSha512_32 = 8,
  };

  // Why a ciphertext didn't decrypt, as SFrameTransformErrorEventType
  enum class SFrameError : uint8_t { kNone, kAuthentication, kKeyId, kSyntax };

  // The parsed header of RFC 9605 Section 4.3
  struct SFrameHeader {
    uint64_t keyId = 0;
    uint64_t counter = 0;
    size_t size = 0;
  };

  // the cipher suite of an identifier, ValueError for an unknown one
  SFrameCipherSuite CipherSuiteOf(int id);

  void AppendSFrameHeader(Octets &out, uint64_t keyId, uint64_t counter);

  std::optional<SFrameHeader> ParseSFrameHeader(OctetSpan data);

  // The key and salt derived from a base key for a key id (RFC 9605 Section 4.4.2), and the AEAD they're used with
  class SFrameKey {
  public:
    // null if the cipher suite isn't known or BoringSSL fails
    static std::shared_ptr<const SFrameKey> Derive(SFrameCipherSuite id, uint64_t keyId, OctetSpan baseKey);

    ~SFrameKey();

    SFrameKey(const SFrameKey &) = delete;
    SFrameKey &operator=(const SFrameKey &) = delete;

    [[nodiscard]] const Octets &Key() const { return _key; }

    [[nodiscard]] const Octets &Salt() const { return _salt; }

    // header + AEAD.Encrypt(plaintext) of RFC 9605 Section 4.4.3, with the metadata as more AAD
    [[nodiscard]] std::optional<Octets> Encrypt(uint64_t counter, OctetSpan metadata, OctetSpan plaintext) const;

    // the plaintext of an SFrame ciphertext (its header parsed), nullopt if it doesn't authenticate
    [[nodiscard]] std::optional<Octets> Decrypt(const SFrameHeader &header, OctetSpan metadata,
                                                OctetSpan sframeCiphertext) const;

    // the authentication tag size of the cipher suite, Nt
    [[nodiscard]] size_t TagSize() const;

    struct Suite;

  private:
    SFrameKey(const Suite &suite, uint64_t keyId);

    const Suite &_suite;
    const uint64_t _keyId;
    Octets _key;
    Octets _salt;
    // the AES-GCM context of the GCM suites
    struct AeadContext;
    std::unique_ptr<AeadContext> _aead;
  };

  // The keys of an SFrame encryptor or decryptor, and its counter. Used from any thread, without the GIL.
  class SFrameContext {
  public:
    explicit SFrameContext(SFrameCipherSuite suite) : _suite(suite) {}

    [[nodiscard]] SFrameCipherSuite Suite() const { return _suite; }

    // false if the key can't be derived
    bool SetEncryptionKey(OctetSpan key, uint64_t keyId);

    bool AddDecryptionKey(OctetSpan key, uint64_t keyId);

    void RemoveDecryptionKey(uint64_t keyId);

    // the SFrame ciphertext, nullopt without a key or once the counter is used up
    std::optional<Octets> Encrypt(OctetSpan plaintext);

    struct Decrypted {
      Octets data;
      SFrameError error = SFrameError::kNone;
      // the key id of the header, for a kKeyId error
      std::optional<uint64_t> keyId;
    };

    Decrypted Decrypt(OctetSpan ciphertext);

    // the private functions of tests/test_sframe.py, which checks the vectors of RFC 9605
    static void Init(pybind11::module &m);

  private:
    const SFrameCipherSuite _suite;

    std::mutex _mutex;
    std::shared_ptr<const SFrameKey> _encryptionKey;
    // the next counter, per encryptor (never reused, whatever the key)
    uint64_t _counter = 0;
    bool _countersUsedUp = false;
    std::map<uint64_t, std::shared_ptr<const SFrameKey>> _decryptionKeys;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_SFRAME_H_
