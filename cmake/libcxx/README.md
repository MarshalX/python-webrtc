Pins for Chromium's libc++, which the Linux libwebrtc prebuilt is compiled against (`std::__Cr` ABI
namespace). The prebuilt ships only its `*.h` headers; CMake downloads the rest into the libwebrtc cache
and verifies them against these lists:

- `headers.sha256` — the extensionless libc++ headers (`<vector>`, `<__config>`, …), fetched from
  llvm-project at `LIBCXX_LLVM_COMMIT`.
- `config.sha256` — Chromium's build-generated `__config_site` and `__assertion_handler`, fetched from
  `buildtools/third_party/libc++/` at `LIBCXX_CHROMIUM_TAG`.

Both variables live in `cmake/libwebrtc.cmake`. When bumping `LIBWEBRTC_VERSION`, unpack the new
`libwebrtc-linux-x64.tar.xz` and run

    python cmake/libcxx/update.py <unpacked>/include/third_party/libc++/src/include \
        --chromium-tag <chromium tag of the WebRTC branch> --since ... --until ...

with a window of ~3 months before the Chromium branch point, then set both variables to the printed values.
