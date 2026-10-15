# Fetches the libwebrtc sources the Windows prebuilt compiles out: the simulcast encoder adapter, and the encoder
# fallback wrapper it creates.
#
# Sets LIBWEBRTC_WINDOWS_SRC.

set(_sources
    "media/engine/simulcast_encoder_adapter.cc"
    "0fac2e2e51e3bf0a595d10b3ce5e197b1c40e4d11cbd8852d84e1fcf104a6e45"
    "api/video_codecs/video_encoder_software_fallback_wrapper.cc"
    "52251651cb273455adcc8db4dfe1dc654a243e709beb5a528bdbb0279f614908")

if(LIBWEBRTC_CACHE_DIR)
  set(_dir "${LIBWEBRTC_CACHE_DIR}/libwebrtc-windows-src-${LIBWEBRTC_VERSION}")
else()
  set(_dir "${CMAKE_BINARY_DIR}/libwebrtc-windows-src")
endif()

set(LIBWEBRTC_WINDOWS_SRC "")
set(_stamp "${_dir}/.complete")
set(_stamp_content "${LIBWEBRTC_COMMIT};${_sources}")
set(_stamp_current "")
if(EXISTS "${_stamp}")
  file(READ "${_stamp}" _stamp_current)
endif()
set(_fetch FALSE)
if(NOT _stamp_current STREQUAL _stamp_content)
  message(STATUS "Fetching libwebrtc's simulcast encoder adapter, which the Windows prebuilt lacks")
  file(REMOVE_RECURSE "${_dir}")
  set(_fetch TRUE)
endif()

list(LENGTH _sources _count)
math(EXPR _last "${_count} - 1")
foreach(_i RANGE 0 ${_last} 2)
  math(EXPR _j "${_i} + 1")
  list(GET _sources ${_i} _path)
  list(GET _sources ${_j} _sha)
  if(_fetch)
    _fetch_webrtc("${_path}" "${_sha}" "${_dir}/${_path}")
  endif()
  list(APPEND LIBWEBRTC_WINDOWS_SRC "${_dir}/${_path}")
endforeach()

if(_fetch)
  file(WRITE "${_stamp}" "${_stamp_content}")
endif()
