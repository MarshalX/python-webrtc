Pins for Chromium's libc++, which the Linux libwebrtc prebuilt is compiled against (`std::__Cr` ABI
namespace). The prebuilt ships only its `*.h` headers; CMake downloads the rest into the libwebrtc cache
and verifies them against these lists:

- `headers.sha256` — the extensionless libc++ headers (`<vector>`, `<__config>`, …), fetched from
  llvm-project at `LIBCXX_LLVM_COMMIT`.
- `config.sha256` — Chromium's build-generated `__config_site` and `__assertion_handler`, fetched from
  `buildtools/third_party/libc++/` at `LIBCXX_CHROMIUM_TAG`.
- `runtime.sha256` — the libc++ and libc++abi sources Chromium builds (from its `BUILD.gn` at
  `LIBCXX_CHROMIUM_TAG`) and every file they include, fetched from llvm-project at `LIBCXX_LLVM_COMMIT`,
  `LIBCXXABI_LLVM_COMMIT` and `LLVM_LIBC_COMMIT`. The linux-arm64 prebuilt lacks the compiled runtime, so
  CMake builds it from these into a static `chromium_libcxx`.

The commits are the ones WebRTC's `DEPS` pins libc++, libc++abi and llvm-libc at, resolved from Chromium's
per-directory mirrors to llvm-project. All variables live in `cmake/libwebrtc.cmake`. When bumping
`LIBWEBRTC_VERSION`, unpack the new `libwebrtc-linux-x64.tar.xz` and run

    python cmake/libcxx/update.py <unpacked>/include/third_party/libc++/src/include \
        --webrtc-branch <WebRTC branch, e.g. 7977> --chromium-tag <chromium tag of the WebRTC branch>

then set the variables to the printed values.
