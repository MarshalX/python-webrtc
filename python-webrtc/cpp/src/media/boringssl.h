//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_BORINGSSL_H_
#define PYTHON_WEBRTC_MEDIA_BORINGSSL_H_

#include <cstddef>
#include <cstdint>

// libwebrtc links BoringSSL without its headers: declared as in boringssl@572a4c68475d284b34675f45ddbb9c158ef3c2ae
// NOLINTBEGIN(readability-identifier-naming,readability-identifier-length,modernize-use-using,bugprone-reserved-identifier)
extern "C" {

typedef struct env_md_st EVP_MD;
typedef struct evp_cipher_st EVP_CIPHER;
typedef struct evp_cipher_ctx_st EVP_CIPHER_CTX;
typedef struct evp_aead_st EVP_AEAD;
typedef struct evp_aead_ctx_st EVP_AEAD_CTX;
typedef struct engine_st ENGINE;

const EVP_MD *EVP_sha256(void);
const EVP_MD *EVP_sha512(void);

int HKDF_extract(uint8_t *out_key, size_t *out_len, const EVP_MD *digest, const uint8_t *secret, size_t secret_len,
                 const uint8_t *salt, size_t salt_len);
int HKDF_expand(uint8_t *out_key, size_t out_len, const EVP_MD *digest, const uint8_t *prk, size_t prk_len,
                const uint8_t *info, size_t info_len);

uint8_t *HMAC(const EVP_MD *evp_md, const void *key, size_t key_len, const uint8_t *data, size_t data_len, uint8_t *out,
              unsigned int *out_len);

const EVP_CIPHER *EVP_aes_128_ctr(void);
const EVP_CIPHER *EVP_aes_256_ctr(void);
EVP_CIPHER_CTX *EVP_CIPHER_CTX_new(void);
void EVP_CIPHER_CTX_free(EVP_CIPHER_CTX *ctx);
int EVP_EncryptInit_ex(EVP_CIPHER_CTX *ctx, const EVP_CIPHER *cipher, ENGINE *engine, const uint8_t *key,
                       const uint8_t *iv);
int EVP_EncryptUpdate(EVP_CIPHER_CTX *ctx, uint8_t *out, int *out_len, const uint8_t *in, int in_len);

const EVP_AEAD *EVP_aead_aes_128_gcm(void);
const EVP_AEAD *EVP_aead_aes_256_gcm(void);
EVP_AEAD_CTX *EVP_AEAD_CTX_new(const EVP_AEAD *aead, const uint8_t *key, size_t key_len, size_t tag_len);
void EVP_AEAD_CTX_free(EVP_AEAD_CTX *ctx);
int EVP_AEAD_CTX_seal(const EVP_AEAD_CTX *ctx, uint8_t *out, size_t *out_len, size_t max_out_len, const uint8_t *nonce,
                      size_t nonce_len, const uint8_t *in, size_t in_len, const uint8_t *ad, size_t ad_len);
int EVP_AEAD_CTX_open(const EVP_AEAD_CTX *ctx, uint8_t *out, size_t *out_len, size_t max_out_len, const uint8_t *nonce,
                      size_t nonce_len, const uint8_t *in, size_t in_len, const uint8_t *ad, size_t ad_len);

int CRYPTO_memcmp(const void *a, const void *b, size_t len);
void OPENSSL_cleanse(void *ptr, size_t len);
}
// NOLINTEND(readability-identifier-naming,readability-identifier-length,modernize-use-using,bugprone-reserved-identifier)

#endif // PYTHON_WEBRTC_MEDIA_BORINGSSL_H_
