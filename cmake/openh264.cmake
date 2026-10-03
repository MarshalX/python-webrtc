# Fetches what H.264 is compiled from: libwebrtc's own encoder, which the prebuilts compile out, and the OpenH264
# API headers. OpenH264 itself is Cisco's binary, loaded at runtime (webrtc.openh264).
#
# Sets OPENH264_INCLUDE_DIR and OPENH264_ENCODER_SRC.

set(OPENH264_VERSION 2.6.0)
set(_encoder modules/video_coding/codecs/h264/h264_encoder_impl)
set(OPENH264_ENCODER_SHA256 374ddc39508eee79e6743de3e562e2ec332f573ca28cfd62c283e3e325c2723d)
set(OPENH264_ENCODER_HEADER_SHA256 2bdcc58e352e611d5eff196fcada153a0d019c22d935ec9f31e18f26544c030f)

if(LIBWEBRTC_CACHE_DIR)
  set(_dir "${LIBWEBRTC_CACHE_DIR}/openh264-${OPENH264_VERSION}-webrtc-${LIBWEBRTC_VERSION}")
else()
  set(_dir "${CMAKE_BINARY_DIR}/openh264")
endif()
set(OPENH264_INCLUDE_DIR "${_dir}/include")
set(OPENH264_ENCODER_SRC "${_dir}/webrtc/${_encoder}.cc")

# Downloads a file of libwebrtc at LIBWEBRTC_COMMIT; googlesource serves files only base64-encoded
function(_fetch_webrtc path sha256 dest)
  set(_encoded "${dest}.b64")
  foreach(_attempt RANGE 1 4)
    file(DOWNLOAD "https://webrtc.googlesource.com/src/+/${LIBWEBRTC_COMMIT}/${path}?format=TEXT"
        "${_encoded}" STATUS _status TLS_VERIFY ON)
    list(GET _status 0 _code)
    if(_code EQUAL 0)
      execute_process(
          COMMAND "${Python_EXECUTABLE}" -c
              "import base64, pathlib, sys; p = pathlib.Path(sys.argv[2]); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(base64.b64decode(pathlib.Path(sys.argv[1]).read_bytes()))"
              "${_encoded}" "${dest}"
          RESULT_VARIABLE _decoded)
      if(_decoded EQUAL 0)
        file(SHA256 "${dest}" _actual)
        if(_actual STREQUAL sha256)
          file(REMOVE "${_encoded}")
          return()
        endif()
        set(_status "SHA256 mismatch: ${_actual}")
      else()
        set(_status "can't decode it")
      endif()
    endif()
    if(_attempt EQUAL 4)
      message(FATAL_ERROR "Failed to fetch ${path} at ${LIBWEBRTC_COMMIT}: ${_status}")
    endif()
    execute_process(COMMAND "${CMAKE_COMMAND}" -E sleep ${_attempt})
  endforeach()
endfunction()

file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/openh264.sha256" _manifest_hash)
set(_stamp "${_dir}/.complete")
set(_stamp_content
    "${LIBWEBRTC_COMMIT};${OPENH264_ENCODER_SHA256};${OPENH264_ENCODER_HEADER_SHA256};${_manifest_hash}")
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
  _fetch_webrtc("${_encoder}.cc" "${OPENH264_ENCODER_SHA256}" "${OPENH264_ENCODER_SRC}")

  # The header refuses MSVC, because libwebrtc's H.264 decoder is FFmpeg's, which dropped MSVC (bugs.webrtc.org/9213).
  # The encoder doesn't need FFmpeg, so the copy shadowing the prebuilt's one goes without that guard.
  set(_header "${OPENH264_INCLUDE_DIR}/${_encoder}.h")
  _fetch_webrtc("${_encoder}.h" "${OPENH264_ENCODER_HEADER_SHA256}" "${_header}")
  file(READ "${_header}" _content)
  set(_guard "#if defined(WEBRTC_WIN) && !defined(__clang__)\n#error \"See: bugs.webrtc.org/9213#c13.\"\n#endif\n")
  string(FIND "${_content}" "${_guard}" _at)
  if(_at EQUAL -1)
    message(FATAL_ERROR "The MSVC guard of ${_encoder}.h changed, update cmake/openh264.cmake")
  endif()
  string(REPLACE "${_guard}" "" _content "${_content}")
  file(WRITE "${_header}" "${_content}")

  file(WRITE "${_stamp}" "${_stamp_content}")
endif()
