//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "sframe.h"

#include <array>
#include <cstring>
#include <limits>
#include <string_view>
#include <utility>

#include <pybind11/stl.h>

#include "../utils/buffer.h"
#include "../utils/gil.h"
#include "boringssl.h"

namespace python_webrtc {

  // Nh, Nka, Nk, Nt of RFC 9605 Section 4.5 (Nn is 12 for all), and the primitives
  struct SFrameKey::Suite {
    SFrameCipherSuite id;
    const EVP_MD *(*hash)();
    size_t hashSize;
    size_t encryptionKeySize;
    size_t keySize;
    size_t tagSize;
    const EVP_CIPHER *(*ctr)();
    const EVP_AEAD *(*gcm)();
  };

  struct SFrameKey::AeadContext {
    EVP_AEAD_CTX *ctx;

    explicit AeadContext(EVP_AEAD_CTX *context) : ctx(context) {}

    ~AeadContext() { EVP_AEAD_CTX_free(ctx); }

    AeadContext(const AeadContext &) = delete;
    AeadContext &operator=(const AeadContext &) = delete;
  };

  namespace {

    constexpr size_t kNonceSize = 12;
    constexpr size_t kAesBlockSize = 16;
    constexpr size_t kMaxHashSize = 64;
    constexpr uint8_t kExtendedFlag = 0x08;
    constexpr uint8_t kValueMask = 0x07;
    constexpr int kKeyIdShift = 4;
    constexpr int kBitsPerByte = 8;

    using Suite = SFrameKey::Suite;
    using Cipher = SFrameCipherSuite;

    // NOLINTBEGIN(cppcoreguidelines-avoid-magic-numbers,readability-magic-numbers): the table of the RFC
    const std::array<Suite, 8> kSuites{{
        {.id = Cipher::kAes128CtrHmacSha256_80,
         .hash = EVP_sha256,
         .hashSize = 32,
         .encryptionKeySize = 16,
         .keySize = 48,
         .tagSize = 10,
         .ctr = EVP_aes_128_ctr,
         .gcm = nullptr},
        {.id = Cipher::kAes128CtrHmacSha256_64,
         .hash = EVP_sha256,
         .hashSize = 32,
         .encryptionKeySize = 16,
         .keySize = 48,
         .tagSize = 8,
         .ctr = EVP_aes_128_ctr,
         .gcm = nullptr},
        {.id = Cipher::kAes128CtrHmacSha256_32,
         .hash = EVP_sha256,
         .hashSize = 32,
         .encryptionKeySize = 16,
         .keySize = 48,
         .tagSize = 4,
         .ctr = EVP_aes_128_ctr,
         .gcm = nullptr},
        {.id = Cipher::kAes128GcmSha256_128,
         .hash = EVP_sha256,
         .hashSize = 32,
         .encryptionKeySize = 0,
         .keySize = 16,
         .tagSize = 16,
         .ctr = nullptr,
         .gcm = EVP_aead_aes_128_gcm},
        {.id = Cipher::kAes256GcmSha512_128,
         .hash = EVP_sha512,
         .hashSize = 64,
         .encryptionKeySize = 0,
         .keySize = 32,
         .tagSize = 16,
         .ctr = nullptr,
         .gcm = EVP_aead_aes_256_gcm},
        {.id = Cipher::kAes256CtrHmacSha512_80,
         .hash = EVP_sha512,
         .hashSize = 64,
         .encryptionKeySize = 32,
         .keySize = 96,
         .tagSize = 10,
         .ctr = EVP_aes_256_ctr,
         .gcm = nullptr},
        {.id = Cipher::kAes256CtrHmacSha512_64,
         .hash = EVP_sha512,
         .hashSize = 64,
         .encryptionKeySize = 32,
         .keySize = 96,
         .tagSize = 8,
         .ctr = EVP_aes_256_ctr,
         .gcm = nullptr},
        {.id = Cipher::kAes256CtrHmacSha512_32,
         .hash = EVP_sha512,
         .hashSize = 64,
         .encryptionKeySize = 32,
         .keySize = 96,
         .tagSize = 4,
         .ctr = EVP_aes_256_ctr,
         .gcm = nullptr},
    }};
    // NOLINTEND(cppcoreguidelines-avoid-magic-numbers,readability-magic-numbers)

    const Suite *FindSuite(SFrameCipherSuite id) {
      for (const auto &suite : kSuites) {
        if (suite.id == id) {
          return &suite;
        }
      }
      return nullptr;
    }

    // NOLINTNEXTLINE(bugprone-easily-swappable-parameters): a value and its size
    void AppendBigEndian(Octets &out, uint64_t value, size_t size) {
      for (size_t i = size; i > 0; --i) {
        out.push_back(static_cast<uint8_t>(value >> (kBitsPerByte * (i - 1))));
      }
    }

    size_t MinimalSize(uint64_t value) {
      size_t size = 1;
      while (size < sizeof(value) && (value >> (kBitsPerByte * size)) != 0) {
        ++size;
      }
      return size;
    }

    std::pair<uint8_t, size_t> HeaderField(uint64_t value) {
      if (value <= kValueMask) {
        return {static_cast<uint8_t>(value), 0};
      }
      const size_t size = MinimalSize(value);
      return {static_cast<uint8_t>(kExtendedFlag | (size - 1)), size};
    }

    std::array<uint8_t, kNonceSize> Nonce(const Octets &salt, uint64_t counter) {
      std::array<uint8_t, kNonceSize> nonce{};
      for (size_t i = 0; i < kNonceSize; ++i) {
        const size_t shift = kNonceSize - 1 - i;
        const auto byte = shift < sizeof(counter) ? static_cast<uint8_t>(counter >> (kBitsPerByte * shift)) : 0;
        nonce.at(i) = static_cast<uint8_t>(salt.at(i) ^ byte);
      }
      return nonce;
    }

    bool AesCtr(const Suite &suite, OctetSpan key, const std::array<uint8_t, kNonceSize> &nonce, OctetSpan input,
                uint8_t *out) {
      if (input.empty()) {
        return true;
      }
      if (input.size() > static_cast<size_t>(std::numeric_limits<int>::max())) {
        return false;
      }
      std::array<uint8_t, kAesBlockSize> block{};
      std::memcpy(block.data(), nonce.data(), nonce.size());
      const std::unique_ptr<EVP_CIPHER_CTX, decltype(&EVP_CIPHER_CTX_free)> ctx(EVP_CIPHER_CTX_new(),
                                                                                &EVP_CIPHER_CTX_free);
      int written = 0;
      return ctx && EVP_EncryptInit_ex(ctx.get(), suite.ctr(), nullptr, key.data(), block.data()) == 1 &&
             EVP_EncryptUpdate(ctx.get(), out, &written, input.data(), static_cast<int>(input.size())) == 1 &&
             static_cast<size_t>(written) == input.size();
    }

    // compute_tag of RFC 9605 Section 4.5.1, the first Nt bytes of the HMAC
    std::optional<std::array<uint8_t, kMaxHashSize>> CtrTag(const Suite &suite, OctetSpan authKey,
                                                            const std::array<uint8_t, kNonceSize> &nonce, OctetSpan aad,
                                                            OctetSpan ciphertext) {
      Octets data;
      data.reserve((3 * sizeof(uint64_t)) + nonce.size() + aad.size() + ciphertext.size());
      AppendBigEndian(data, aad.size(), sizeof(uint64_t));
      AppendBigEndian(data, ciphertext.size(), sizeof(uint64_t));
      AppendBigEndian(data, suite.tagSize, sizeof(uint64_t));
      data.insert(data.end(), nonce.begin(), nonce.end());
      data.insert(data.end(), aad.begin(), aad.end());
      data.insert(data.end(), ciphertext.begin(), ciphertext.end());
      std::array<uint8_t, kMaxHashSize> tag{};
      unsigned int size = 0;
      if (HMAC(suite.hash(), authKey.data(), authKey.size(), data.data(), data.size(), tag.data(), &size) == nullptr ||
          size != suite.hashSize) {
        return std::nullopt;
      }
      return tag;
    }

    Octets Label(std::string_view prefix, uint64_t keyId, SFrameCipherSuite suite) {
      Octets label(prefix.begin(), prefix.end());
      AppendBigEndian(label, keyId, sizeof(keyId));
      AppendBigEndian(label, static_cast<uint16_t>(suite), sizeof(uint16_t));
      return label;
    }

  } // namespace

  SFrameCipherSuite CipherSuiteOf(int id) {
    for (const auto &suite : kSuites) {
      if (static_cast<int>(suite.id) == id) {
        return suite.id;
      }
    }
    throw pybind11::value_error("Unknown SFrame cipher suite");
  }

  void AppendSFrameHeader(Octets &out, uint64_t keyId, uint64_t counter) {
    const auto [keyIdBits, keyIdSize] = HeaderField(keyId);
    const auto [counterBits, counterSize] = HeaderField(counter);
    out.push_back(static_cast<uint8_t>((keyIdBits << kKeyIdShift) | counterBits));
    AppendBigEndian(out, keyId, keyIdSize);
    AppendBigEndian(out, counter, counterSize);
  }

  std::optional<SFrameHeader> ParseSFrameHeader(OctetSpan data) {
    if (data.empty()) {
      return std::nullopt;
    }
    SFrameHeader header;
    header.size = 1;
    auto field = [&](uint8_t bits, uint64_t &value) {
      if ((bits & kExtendedFlag) == 0) {
        value = bits & kValueMask;
        return true;
      }
      const size_t size = (bits & kValueMask) + 1U;
      if (data.size() - header.size < size) {
        return false;
      }
      value = 0;
      for (size_t i = 0; i < size; ++i) {
        value = (value << kBitsPerByte) | data[header.size + i];
      }
      header.size += size;
      return true;
    };
    const uint8_t config = data[0];
    if (!field(static_cast<uint8_t>(config >> kKeyIdShift), header.keyId) ||
        !field(static_cast<uint8_t>(config & (kExtendedFlag | kValueMask)), header.counter)) {
      return std::nullopt;
    }
    return header;
  }

  SFrameKey::SFrameKey(const Suite &suite, uint64_t keyId) : _suite(suite), _keyId(keyId) {}

  SFrameKey::~SFrameKey() {
    OPENSSL_cleanse(_key.data(), _key.size());
    OPENSSL_cleanse(_salt.data(), _salt.size());
  }

  size_t SFrameKey::TagSize() const {
    return _suite.tagSize;
  }

  std::shared_ptr<const SFrameKey> SFrameKey::Derive(SFrameCipherSuite id, uint64_t keyId, OctetSpan baseKey) {
    const Suite *suite = FindSuite(id);
    if (suite == nullptr) {
      return nullptr;
    }
    // HKDF-Extract with an empty salt: a non-null pointer, as a null HMAC key means the previous one
    static constexpr uint8_t kNoSalt = 0;
    std::array<uint8_t, kMaxHashSize> secret{};
    size_t secretSize = 0;
    const std::shared_ptr<SFrameKey> key(new SFrameKey(*suite, keyId));
    key->_key.resize(suite->keySize);
    key->_salt.resize(kNonceSize);
    const auto keyLabel = Label("SFrame 1.0 Secret key ", keyId, id);
    const auto saltLabel = Label("SFrame 1.0 Secret salt ", keyId, id);
    const bool derived =
        HKDF_extract(secret.data(), &secretSize, suite->hash(), baseKey.data(), baseKey.size(), &kNoSalt, 0) == 1 &&
        HKDF_expand(key->_key.data(), key->_key.size(), suite->hash(), secret.data(), secretSize, keyLabel.data(),
                    keyLabel.size()) == 1 &&
        HKDF_expand(key->_salt.data(), key->_salt.size(), suite->hash(), secret.data(), secretSize, saltLabel.data(),
                    saltLabel.size()) == 1;
    OPENSSL_cleanse(secret.data(), secret.size());
    if (!derived) {
      return nullptr;
    }
    if (suite->gcm != nullptr) {
      auto *ctx = EVP_AEAD_CTX_new(suite->gcm(), key->_key.data(), key->_key.size(), suite->tagSize);
      if (ctx == nullptr) {
        return nullptr;
      }
      key->_aead = std::make_unique<AeadContext>(ctx);
    }
    return key;
  }

  // NOLINTNEXTLINE(bugprone-easily-swappable-parameters): in the order of the RFC
  std::optional<Octets> SFrameKey::Encrypt(uint64_t counter, OctetSpan metadata, OctetSpan plaintext) const {
    Octets out;
    AppendSFrameHeader(out, _keyId, counter);
    const size_t headerSize = out.size();
    Octets aad(out);
    aad.insert(aad.end(), metadata.begin(), metadata.end());
    const auto nonce = Nonce(_salt, counter);
    out.resize(headerSize + plaintext.size() + _suite.tagSize);
    uint8_t *ciphertext = out.data() + headerSize;
    if (_aead) {
      size_t written = 0;
      if (EVP_AEAD_CTX_seal(_aead->ctx, ciphertext, &written, out.size() - headerSize, nonce.data(), nonce.size(),
                            plaintext.data(), plaintext.size(), aad.data(), aad.size()) != 1 ||
          written != out.size() - headerSize) {
        return std::nullopt;
      }
      return out;
    }
    const OctetSpan key(_key);
    if (!AesCtr(_suite, key.first(_suite.encryptionKeySize), nonce, plaintext, ciphertext)) {
      return std::nullopt;
    }
    const auto tag = CtrTag(_suite, key.subspan(_suite.encryptionKeySize), nonce, aad, {ciphertext, plaintext.size()});
    if (!tag) {
      return std::nullopt;
    }
    std::memcpy(ciphertext + plaintext.size(), tag->data(), _suite.tagSize);
    return out;
  }

  std::optional<Octets> SFrameKey::Decrypt(const SFrameHeader &header, OctetSpan metadata,
                                           OctetSpan sframeCiphertext) const {
    if (sframeCiphertext.size() < header.size + _suite.tagSize) {
      return std::nullopt;
    }
    Octets aad(sframeCiphertext.begin(), sframeCiphertext.begin() + static_cast<ptrdiff_t>(header.size));
    aad.insert(aad.end(), metadata.begin(), metadata.end());
    const auto nonce = Nonce(_salt, header.counter);
    const auto ciphertext = sframeCiphertext.subspan(header.size);
    const size_t plaintextSize = ciphertext.size() - _suite.tagSize;
    Octets plaintext(plaintextSize);
    if (_aead) {
      size_t written = 0;
      if (EVP_AEAD_CTX_open(_aead->ctx, plaintext.data(), &written, plaintext.size(), nonce.data(), nonce.size(),
                            ciphertext.data(), ciphertext.size(), aad.data(), aad.size()) != 1 ||
          written != plaintextSize) {
        return std::nullopt;
      }
      return plaintext;
    }
    const OctetSpan key(_key);
    const auto inner = ciphertext.first(plaintextSize);
    const auto tag = CtrTag(_suite, key.subspan(_suite.encryptionKeySize), nonce, aad, inner);
    if (!tag || CRYPTO_memcmp(tag->data(), ciphertext.data() + plaintextSize, _suite.tagSize) != 0) {
      return std::nullopt;
    }
    if (!AesCtr(_suite, key.first(_suite.encryptionKeySize), nonce, inner, plaintext.data())) {
      return std::nullopt;
    }
    return plaintext;
  }

  bool SFrameContext::SetEncryptionKey(OctetSpan key, uint64_t keyId) {
    auto derived = SFrameKey::Derive(_suite, keyId, key);
    if (!derived) {
      return false;
    }
    const std::scoped_lock lock(_mutex);
    _encryptionKey = std::move(derived);
    return true;
  }

  bool SFrameContext::AddDecryptionKey(OctetSpan key, uint64_t keyId) {
    auto derived = SFrameKey::Derive(_suite, keyId, key);
    if (!derived) {
      return false;
    }
    const std::scoped_lock lock(_mutex);
    _decryptionKeys[keyId] = std::move(derived);
    return true;
  }

  void SFrameContext::RemoveDecryptionKey(uint64_t keyId) {
    std::shared_ptr<const SFrameKey> removed;
    const std::scoped_lock lock(_mutex);
    auto it = _decryptionKeys.find(keyId);
    if (it != _decryptionKeys.end()) {
      removed = std::move(it->second);
      _decryptionKeys.erase(it);
    }
  }

  std::optional<Octets> SFrameContext::Encrypt(OctetSpan plaintext) {
    std::shared_ptr<const SFrameKey> key;
    uint64_t counter = 0;
    {
      const std::scoped_lock lock(_mutex);
      if (!_encryptionKey || _countersUsedUp) {
        return std::nullopt;
      }
      key = _encryptionKey;
      counter = _counter;
      if (_counter == std::numeric_limits<uint64_t>::max()) {
        _countersUsedUp = true;
      } else {
        ++_counter;
      }
    }
    return key->Encrypt(counter, {}, plaintext);
  }

  SFrameContext::Decrypted SFrameContext::Decrypt(OctetSpan ciphertext) {
    Decrypted result;
    const auto header = ParseSFrameHeader(ciphertext);
    if (!header) {
      result.error = SFrameError::kSyntax;
      return result;
    }
    std::shared_ptr<const SFrameKey> key;
    {
      const std::scoped_lock lock(_mutex);
      auto it = _decryptionKeys.find(header->keyId);
      if (it != _decryptionKeys.end()) {
        key = it->second;
      }
    }
    if (!key) {
      result.error = SFrameError::kKeyId;
      result.keyId = header->keyId;
      return result;
    }
    if (ciphertext.size() < header->size + key->TagSize()) {
      result.error = SFrameError::kSyntax;
      return result;
    }
    auto plaintext = key->Decrypt(*header, {}, ciphertext);
    if (!plaintext) {
      result.error = SFrameError::kAuthentication;
      return result;
    }
    result.data = std::move(*plaintext);
    return result;
  }

  void SFrameContext::Init(pybind11::module &m) {
    m.def(
        "_sframeHeader",
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters): in the order of the header
        [](uint64_t keyId, uint64_t counter) {
          Octets out;
          AppendSFrameHeader(out, keyId, counter);
          return Bytes(out.data(), out.size());
        },
        pybind11::arg("keyId"), pybind11::arg("counter"));
    m.def(
        "_sframeParseHeader",
        [](const pybind11::buffer &data) -> std::optional<std::tuple<uint64_t, uint64_t, size_t>> {
          pybind11::buffer_info info;
          auto header = ParseSFrameHeader(BufferSpan(data, info));
          if (!header) {
            return std::nullopt;
          }
          return std::make_tuple(header->keyId, header->counter, header->size);
        },
        pybind11::arg("data"));
    m.def(
        "_sframeDerive",
        [](int cipherSuite, const pybind11::buffer &baseKey, uint64_t keyId) {
          pybind11::buffer_info info;
          auto key = SFrameKey::Derive(CipherSuiteOf(cipherSuite), keyId, BufferSpan(baseKey, info));
          if (!key) {
            throw pybind11::value_error("The key can't be derived");
          }
          return std::make_pair(Bytes(key->Key().data(), key->Key().size()),
                                Bytes(key->Salt().data(), key->Salt().size()));
        },
        pybind11::arg("cipherSuite"), pybind11::arg("baseKey"), pybind11::arg("keyId"));
    m.def(
        "_sframeEncrypt",
        // NOLINTNEXTLINE(bugprone-easily-swappable-parameters): in the order of the RFC
        [](int cipherSuite, const pybind11::buffer &baseKey, uint64_t keyId, uint64_t counter,
           const pybind11::buffer &metadata, const pybind11::buffer &plaintext) {
          pybind11::buffer_info keyInfo;
          pybind11::buffer_info metadataInfo;
          pybind11::buffer_info plaintextInfo;
          auto key = SFrameKey::Derive(CipherSuiteOf(cipherSuite), keyId, BufferSpan(baseKey, keyInfo));
          auto out =
              key ? key->Encrypt(counter, BufferSpan(metadata, metadataInfo), BufferSpan(plaintext, plaintextInfo))
                  : std::nullopt;
          if (!out) {
            throw pybind11::value_error("The plaintext can't be encrypted");
          }
          return Bytes(out->data(), out->size());
        },
        pybind11::arg("cipherSuite"), pybind11::arg("baseKey"), pybind11::arg("keyId"), pybind11::arg("counter"),
        pybind11::arg("metadata"), pybind11::arg("plaintext"));
    m.def(
        "_sframeDecrypt",
        [](int cipherSuite, const pybind11::buffer &baseKey, const pybind11::buffer &metadata,
           const pybind11::buffer &ciphertext) -> std::optional<pybind11::bytes> {
          pybind11::buffer_info keyInfo;
          pybind11::buffer_info metadataInfo;
          pybind11::buffer_info ciphertextInfo;
          const auto data = BufferSpan(ciphertext, ciphertextInfo);
          const auto header = ParseSFrameHeader(data);
          if (!header) {
            return std::nullopt;
          }
          auto key = SFrameKey::Derive(CipherSuiteOf(cipherSuite), header->keyId, BufferSpan(baseKey, keyInfo));
          auto out = key ? key->Decrypt(*header, BufferSpan(metadata, metadataInfo), data) : std::nullopt;
          if (!out) {
            return std::nullopt;
          }
          return Bytes(out->data(), out->size());
        },
        pybind11::arg("cipherSuite"), pybind11::arg("baseKey"), pybind11::arg("metadata"), pybind11::arg("ciphertext"));
  }

} // namespace python_webrtc
