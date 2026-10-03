//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "openh264.h"
#include "openh264_decoder.h"

#include <api/video_codecs/h264_profile_level_id.h>
#include <modules/video_coding/codecs/h264/h264_encoder_impl.h>
#include <modules/video_coding/codecs/h264/include/h264.h>
#include <third_party/openh264/src/codec/api/wels/codec_api.h>
#include <third_party/openh264/src/codec/api/wels/codec_ver.h>

#include <atomic>
#include <mutex>
#include <stdexcept>
#include <string>

#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace {

  struct Library {
    std::string path;
    int (*createEncoder)(ISVCEncoder **) = nullptr;
    void (*destroyEncoder)(ISVCEncoder *) = nullptr;
    long (*createDecoder)(ISVCDecoder **) = nullptr;
    void (*destroyDecoder)(ISVCDecoder *) = nullptr;
    void (*version)(OpenH264Version *) = nullptr;
  };

  struct State {
    std::mutex mutex;
    Library library;
    std::atomic<bool> loaded{false};
    // Cisco's license: the user can disable and re-enable it, which only stops offering H.264
    std::atomic<bool> enabled{false};
  };

  State &state() {
    static State instance;
    return instance;
  }

#ifdef _WIN32
  void *Open(const std::string &path) {
    const int size = MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, nullptr, 0);
    std::wstring wide(size, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, path.c_str(), -1, wide.data(), size);
    return LoadLibraryW(wide.c_str());
  }

  void *Symbol(void *handle, const char *name) {
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast): GetProcAddress returns functions untyped
    return reinterpret_cast<void *>(GetProcAddress(static_cast<HMODULE>(handle), name));
  }

  void Close(void *handle) {
    FreeLibrary(static_cast<HMODULE>(handle));
  }

  std::string OpenError() {
    return "error " + std::to_string(GetLastError());
  }
#else
  void *Open(const std::string &path) {
    return dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
  }

  void *Symbol(void *handle, const char *name) {
    return dlsym(handle, name);
  }

  void Close(void *handle) {
    dlclose(handle);
  }

  std::string OpenError() {
    // NOLINTNEXTLINE(concurrency-mt-unsafe): called under the loader's mutex
    const char *error = dlerror();
    return error != nullptr ? error : "unknown error";
  }
#endif

  template <typename F>
  void Resolve(void *handle, const char *name, F &function) {
    // NOLINTNEXTLINE(cppcoreguidelines-pro-type-reinterpret-cast): symbols are looked up untyped
    function = reinterpret_cast<F>(Symbol(handle, name));
    if (function == nullptr) {
      Close(handle);
      throw std::runtime_error(std::string("Not an OpenH264 library, no ") + name);
    }
  }

  std::string VersionString(const OpenH264Version &version) {
    return std::to_string(version.uMajor) + "." + std::to_string(version.uMinor) + "." +
           std::to_string(version.uRevision);
  }

  std::string Load(const std::string &path) {
    auto &current = state();
    const std::scoped_lock lock(current.mutex);
    if (current.loaded) {
      if (current.library.path != path) {
        throw std::runtime_error("OpenH264 is already loaded from " + current.library.path);
      }
    } else {
      void *handle = Open(path);
      if (handle == nullptr) {
        throw std::runtime_error("Can't load " + path + ": " + OpenError());
      }

      Library candidate{.path = path};
      Resolve(handle, "WelsCreateSVCEncoder", candidate.createEncoder);
      Resolve(handle, "WelsDestroySVCEncoder", candidate.destroyEncoder);
      Resolve(handle, "WelsCreateDecoder", candidate.createDecoder);
      Resolve(handle, "WelsDestroyDecoder", candidate.destroyDecoder);
      Resolve(handle, "WelsGetCodecVersionEx", candidate.version);

      // the interfaces are C++ vtables, so the binary must match the headers we're built against
      OpenH264Version version{};
      candidate.version(&version);
      if (version.uMajor != OPENH264_MAJOR || version.uMinor != OPENH264_MINOR) {
        Close(handle);
        throw std::runtime_error("OpenH264 " + VersionString(version) + " doesn't match " +
                                 VersionString(g_stCodecVersion));
      }

      // never unloaded: encoders and decoders may outlive any owner we could tie it to
      current.library = candidate;
      current.loaded = true;
    }

    current.enabled = true;
    OpenH264Version version{};
    current.library.version(&version);
    return VersionString(version);
  }

  std::vector<webrtc::SdpVideoFormat> Formats(const std::vector<webrtc::H264Profile> &profiles,
                                              bool addScalabilityModes) {
    std::vector<webrtc::SdpVideoFormat> formats;
    for (const auto profile : profiles) {
      for (const auto *mode : {"1", "0"}) {
        formats.push_back(webrtc::CreateH264Format(profile, webrtc::H264Level::kLevel3_1, mode, addScalabilityModes));
      }
    }
    return formats;
  }

} // namespace

// the entry points the upstream encoder and our decoder call, forwarded to the loaded library
extern "C" {
int WelsCreateSVCEncoder(ISVCEncoder **encoder) {
  return state().loaded ? state().library.createEncoder(encoder) : 1;
}

void WelsDestroySVCEncoder(ISVCEncoder *encoder) {
  if (state().loaded) {
    state().library.destroyEncoder(encoder);
  }
}

long WelsCreateDecoder(ISVCDecoder **decoder) {
  return state().loaded ? state().library.createDecoder(decoder) : 1;
}

void WelsDestroyDecoder(ISVCDecoder *decoder) {
  if (state().loaded) {
    state().library.destroyDecoder(decoder);
  }
}
}

namespace python_webrtc {

  bool OpenH264::Enabled() {
    return state().enabled;
  }

  void OpenH264::Init(pybind11::module &m) {
    m.def("loadOpenH264", &Load, pybind11::arg("path"));
    m.def("disableOpenH264", []() { state().enabled = false; });
    m.def("openH264Enabled", &OpenH264::Enabled);
  }

  std::vector<webrtc::SdpVideoFormat> OpenH264EncoderAdapter::SupportedFormats() {
    if (!state().enabled) {
      return {};
    }
    // the encoder produces Constrained Baseline, which decoders of these profiles all accept
    return Formats({webrtc::H264Profile::kProfileConstrainedBaseline, webrtc::H264Profile::kProfileBaseline,
                    webrtc::H264Profile::kProfileMain},
                   true);
  }

  std::unique_ptr<webrtc::VideoEncoder> OpenH264EncoderAdapter::CreateEncoder(const webrtc::Environment &env,
                                                                              const webrtc::SdpVideoFormat &format) {
    if (!state().loaded) {
      return nullptr;
    }
    return std::make_unique<webrtc::H264EncoderImpl>(env, webrtc::H264EncoderSettings::Parse(format));
  }

  bool OpenH264EncoderAdapter::IsScalabilityModeSupported(webrtc::ScalabilityMode mode) {
    return mode == webrtc::ScalabilityMode::kL1T1 || mode == webrtc::ScalabilityMode::kL1T2 ||
           mode == webrtc::ScalabilityMode::kL1T3;
  }

  std::vector<webrtc::SdpVideoFormat> OpenH264DecoderAdapter::SupportedFormats() {
    if (!state().enabled) {
      return {};
    }
    return Formats({webrtc::H264Profile::kProfileConstrainedBaseline, webrtc::H264Profile::kProfileBaseline,
                    webrtc::H264Profile::kProfileMain, webrtc::H264Profile::kProfileConstrainedHigh,
                    webrtc::H264Profile::kProfileHigh},
                   false);
  }

  std::unique_ptr<webrtc::VideoDecoder>
  OpenH264DecoderAdapter::CreateDecoder(const webrtc::Environment & /*env*/,
                                        const webrtc::SdpVideoFormat & /*format*/) {
    if (!state().loaded) {
      return nullptr;
    }
    return std::make_unique<OpenH264Decoder>();
  }

} // namespace python_webrtc
