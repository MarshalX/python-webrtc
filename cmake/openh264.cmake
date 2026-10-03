# Fetches what H.264 is compiled from: libwebrtc's own encoder, which the prebuilts compile out, and the OpenH264
# API headers. OpenH264 itself is Cisco's binary, loaded at runtime (webrtc.openh264).
#
# Sets OPENH264_INCLUDE_DIR and OPENH264_ENCODER_SRC.

set(OPENH264_VERSION 2.6.0)
set(OPENH264_ENCODER_PATH modules/video_coding/codecs/h264/h264_encoder_impl.cc)
set(OPENH264_ENCODER_SHA256 374ddc39508eee79e6743de3e562e2ec332f573ca28cfd62c283e3e325c2723d)

if(LIBWEBRTC_CACHE_DIR)
  set(_dir "${LIBWEBRTC_CACHE_DIR}/openh264-${OPENH264_VERSION}-webrtc-${LIBWEBRTC_VERSION}")
else()
  set(_dir "${CMAKE_BINARY_DIR}/openh264")
endif()
set(OPENH264_INCLUDE_DIR "${_dir}/include")
set(OPENH264_ENCODER_SRC "${_dir}/webrtc/${OPENH264_ENCODER_PATH}")

file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/openh264.sha256" _manifest_hash)
set(_stamp "${_dir}/.complete")
set(_stamp_content "${LIBWEBRTC_COMMIT};${OPENH264_ENCODER_SHA256};${_manifest_hash}")
set(_stamp_current "")
if(EXISTS "${_stamp}")
  file(READ "${_stamp}" _stamp_current)
endif()

if(NOT _stamp_current STREQUAL _stamp_content)
  message(STATUS "Fetching the OpenH264 ${OPENH264_VERSION} headers and libwebrtc's H.264 encoder")
  file(REMOVE_RECURSE "${_dir}")
  _fetch_pinned("${CMAKE_CURRENT_LIST_DIR}/openh264.sha256"
      "https://raw.githubusercontent.com/cisco/openh264/v${OPENH264_VERSION}"
      "${OPENH264_INCLUDE_DIR}/third_party/openh264/src")

  # googlesource serves files only base64-encoded
  set(_encoded "${_dir}/encoder.b64")
  foreach(_attempt RANGE 1 4)
    file(DOWNLOAD "https://webrtc.googlesource.com/src/+/${LIBWEBRTC_COMMIT}/${OPENH264_ENCODER_PATH}?format=TEXT"
        "${_encoded}" STATUS _status TLS_VERIFY ON)
    list(GET _status 0 _code)
    if(_code EQUAL 0)
      execute_process(
          COMMAND "${Python_EXECUTABLE}" -c
              "import base64, pathlib, sys; p = pathlib.Path(sys.argv[2]); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(base64.b64decode(pathlib.Path(sys.argv[1]).read_bytes()))"
              "${_encoded}" "${OPENH264_ENCODER_SRC}"
          RESULT_VARIABLE _decoded)
      if(_decoded EQUAL 0)
        file(SHA256 "${OPENH264_ENCODER_SRC}" _actual)
        if(_actual STREQUAL OPENH264_ENCODER_SHA256)
          break()
        endif()
        set(_status "SHA256 mismatch: ${_actual}")
      else()
        set(_status "can't decode it")
      endif()
    endif()
    if(_attempt EQUAL 4)
      message(FATAL_ERROR "Failed to fetch ${OPENH264_ENCODER_PATH} at ${LIBWEBRTC_COMMIT}: ${_status}")
    endif()
    execute_process(COMMAND "${CMAKE_COMMAND}" -E sleep ${_attempt})
  endforeach()
  file(REMOVE "${_encoded}")

  file(WRITE "${_stamp}" "${_stamp_content}")
endif()
