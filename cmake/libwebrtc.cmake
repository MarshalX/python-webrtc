# Provides the `libwebrtc` imported target backed by prebuilt static libwebrtc
# binaries from https://github.com/crow-misia/libwebrtc-bin.
#
# Instead of checking out Chromium's toolchain and the WebRTC tree (20+ GB) the
# prebuilt archive for the target platform is downloaded once, verified,
# unpacked into a shared cache (only the headers we actually use) and reused by
# every subsequent build, including builds for other Python versions.
#
# Cache variables:
#   LIBWEBRTC_ROOT       use an already unpacked libwebrtc (include/ + lib/)
#   LIBWEBRTC_CACHE_DIR  where archives are unpacked (env: WRTC_CACHE_DIR)

set(LIBWEBRTC_VERSION "152.7977.0.0")
set(LIBWEBRTC_URL_BASE "https://github.com/crow-misia/libwebrtc-bin/releases/download/${LIBWEBRTC_VERSION}")

# linux-arm64 is not listed: its archive lacks most of libc++ and libc++abi.
set(LIBWEBRTC_SHA256_linux-x64   5ba9bbb3392671d96f8fb300e2a2c1566d76fa4e590e3b4f959fa144da16da5c)
set(LIBWEBRTC_SHA256_macos-x64   1d4f4480316e227fa026bb928c31c3fc2fcc0e8c65f85323c314e1be4ac55b14)
set(LIBWEBRTC_SHA256_macos-arm64 3a7d3d7d10de56580d3cbe18910a92c3ab85ae07316e6f745890c7b545c0a9c7)
set(LIBWEBRTC_SHA256_win-x64     41e64b712f3777db0377e8445972051366bc333905b0880a1fc6c4bef1f5b8cf)
set(LIBWEBRTC_SHA256_win-x86     44cb24862b8deb5cbeef697d1e84bdb5a93ec416602aafa5831b6d27131d12e9)

# The Linux prebuilts are compiled against Chromium's libc++ but only ship its *.h
# headers. The extensionless ones are fetched from the matching llvm-project commit
# (see cmake/libcxx/README.md). Its build-generated config comes from the matching Chromium tag.
set(LIBCXX_LLVM_COMMIT fe2138d9ec791069edf8183a962711c96db55e3f)
set(LIBCXX_CHROMIUM_TAG 152.0.7977.0)

# Downloads every "<sha256>  <path>" entry of a manifest from <base_url>/<path> into <dest>/<path>.
function(_fetch_pinned manifest base_url dest)
  file(STRINGS "${manifest}" _lines)
  foreach(_line IN LISTS _lines)
    string(REGEX MATCH "^([0-9a-f]+)  (.+)$" _ "${_line}")
    file(DOWNLOAD "${base_url}/${CMAKE_MATCH_2}" "${dest}/${CMAKE_MATCH_2}"
        EXPECTED_HASH SHA256=${CMAKE_MATCH_1}
        STATUS _status
        TLS_VERIFY ON
    )
    list(GET _status 0 _code)
    if(NOT _code EQUAL 0)
      message(FATAL_ERROR "Failed to download ${base_url}/${CMAKE_MATCH_2}: ${_status}")
    endif()
  endforeach()
endfunction()

# Header directories (relative to include/) needed to compile against the public API.
set(LIBWEBRTC_HEADER_DIRS
    api audio call common_audio common_video logging media modules net p2p pc
    rtc_base system_wrappers video
    third_party/abseil-cpp third_party/libyuv
)

# --- target platform ---------------------------------------------------------

if(APPLE)
  list(LENGTH CMAKE_OSX_ARCHITECTURES _archs_count)
  if(_archs_count GREATER 1)
    message(FATAL_ERROR "Universal builds are not supported, build one architecture at a time")
  elseif(_archs_count EQUAL 1)
    set(_arch "${CMAKE_OSX_ARCHITECTURES}")
  else()
    set(_arch "${CMAKE_SYSTEM_PROCESSOR}")
  endif()
  set(_os macos)
elseif(WIN32)
  if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    set(_arch x64)
  else()
    set(_arch x86)
  endif()
  set(_os win)
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  set(_arch "${CMAKE_SYSTEM_PROCESSOR}")
  set(_os linux)
else()
  message(FATAL_ERROR "Unsupported platform: ${CMAKE_SYSTEM_NAME}")
endif()

string(TOLOWER "${_arch}" _arch)
if(_arch MATCHES "^(x86_64|amd64|x64)$")
  set(_arch x64)
elseif(_arch MATCHES "^(aarch64|arm64)$")
  set(_arch arm64)
endif()

set(LIBWEBRTC_PLATFORM "${_os}-${_arch}")
if(NOT DEFINED LIBWEBRTC_SHA256_${LIBWEBRTC_PLATFORM})
  message(FATAL_ERROR "No prebuilt libwebrtc for ${LIBWEBRTC_PLATFORM}")
endif()

# --- download & unpack -------------------------------------------------------

if(NOT LIBWEBRTC_ROOT)
  if(DEFINED ENV{WRTC_CACHE_DIR})
    set(_cache "$ENV{WRTC_CACHE_DIR}")
  elseif(DEFINED ENV{LOCALAPPDATA})
    set(_cache "$ENV{LOCALAPPDATA}/python-webrtc")
  elseif(DEFINED ENV{XDG_CACHE_HOME})
    set(_cache "$ENV{XDG_CACHE_HOME}/python-webrtc")
  else()
    set(_cache "$ENV{HOME}/.cache/python-webrtc")
  endif()
  file(TO_CMAKE_PATH "${_cache}" _cache)
  set(LIBWEBRTC_CACHE_DIR "${_cache}" CACHE PATH "Directory for unpacked libwebrtc prebuilts")

  set(LIBWEBRTC_ROOT "${LIBWEBRTC_CACHE_DIR}/libwebrtc-${LIBWEBRTC_VERSION}-${LIBWEBRTC_PLATFORM}")
  set(_stamp "${LIBWEBRTC_ROOT}/.complete")
  # everything that affects the unpacked tree, so changing it re-unpacks
  set(_stamp_content "${LIBWEBRTC_SHA256_${LIBWEBRTC_PLATFORM}};${LIBWEBRTC_HEADER_DIRS}")
  if(LIBWEBRTC_PLATFORM MATCHES "^linux")
    file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/libcxx/headers.sha256" _headers_hash)
    file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/libcxx/config.sha256" _config_hash)
    string(APPEND _stamp_content ";${LIBCXX_LLVM_COMMIT};${_headers_hash};${LIBCXX_CHROMIUM_TAG};${_config_hash}")
  endif()
  set(_stamp_current "")
  if(EXISTS "${_stamp}")
    file(READ "${_stamp}" _stamp_current)
  endif()

  if(NOT _stamp_current STREQUAL _stamp_content)
    if(WIN32)
      set(_file "libwebrtc-${LIBWEBRTC_PLATFORM}.7z")
      set(_lib_dir release)
    else()
      set(_file "libwebrtc-${LIBWEBRTC_PLATFORM}.tar.xz")
      set(_lib_dir lib)
    endif()
    set(_archive "${LIBWEBRTC_CACHE_DIR}/${_file}")

    message(STATUS "Downloading ${_file} (libwebrtc ${LIBWEBRTC_VERSION})")
    file(DOWNLOAD "${LIBWEBRTC_URL_BASE}/${_file}" "${_archive}"
        EXPECTED_HASH SHA256=${LIBWEBRTC_SHA256_${LIBWEBRTC_PLATFORM}}
        STATUS _status
        TLS_VERIFY ON
    )
    list(GET _status 0 _code)
    if(NOT _code EQUAL 0)
      file(REMOVE "${_archive}")
      message(FATAL_ERROR "Failed to download ${_file}: ${_status}")
    endif()

    set(_patterns "${_lib_dir}" NOTICE VERSION)
    foreach(_dir IN LISTS LIBWEBRTC_HEADER_DIRS)
      list(APPEND _patterns "include/${_dir}")
    endforeach()
    if(_os STREQUAL "linux")
      # Chromium's libc++ the Linux prebuilts are compiled against
      list(APPEND _patterns "include/third_party/libc++/src/include" "include/third_party/libc++abi/src/include")
    endif()

    message(STATUS "Unpacking ${_file} into ${LIBWEBRTC_ROOT}")
    file(REMOVE_RECURSE "${LIBWEBRTC_ROOT}")
    file(ARCHIVE_EXTRACT INPUT "${_archive}" DESTINATION "${LIBWEBRTC_ROOT}" PATTERNS ${_patterns})
    file(REMOVE "${_archive}")
    if(_os STREQUAL "linux")
      message(STATUS "Downloading libc++ headers (llvm-project@${LIBCXX_LLVM_COMMIT}, chromium@${LIBCXX_CHROMIUM_TAG})")
      _fetch_pinned("${CMAKE_CURRENT_LIST_DIR}/libcxx/headers.sha256"
          "https://raw.githubusercontent.com/llvm/llvm-project/${LIBCXX_LLVM_COMMIT}/libcxx/include"
          "${LIBWEBRTC_ROOT}/include/third_party/libc++/src/include")
      _fetch_pinned("${CMAKE_CURRENT_LIST_DIR}/libcxx/config.sha256"
          "https://raw.githubusercontent.com/chromium/chromium/${LIBCXX_CHROMIUM_TAG}/buildtools/third_party/libc++"
          "${LIBWEBRTC_ROOT}/include/buildtools/third_party/libc++")
    endif()

    if(WIN32)
      file(RENAME "${LIBWEBRTC_ROOT}/release" "${LIBWEBRTC_ROOT}/lib")
    elseif(CMAKE_STRIP)
      # Debug info makes up >90% of the archive (700 MB -> 50 MB on macOS)
      message(STATUS "Stripping debug info from libwebrtc")
      execute_process(COMMAND "${CMAKE_STRIP}" -S "${LIBWEBRTC_ROOT}/lib/libwebrtc.a" ERROR_QUIET COMMAND_ERROR_IS_FATAL ANY)
    endif()
    file(WRITE "${_stamp}" "${_stamp_content}")
  endif()
endif()

message(STATUS "Using libwebrtc from ${LIBWEBRTC_ROOT}")

# --- imported target ---------------------------------------------------------

set(_inc "${LIBWEBRTC_ROOT}/include")

add_library(libwebrtc STATIC IMPORTED GLOBAL)
set_target_properties(libwebrtc PROPERTIES
    IMPORTED_LOCATION "${LIBWEBRTC_ROOT}/lib/${CMAKE_STATIC_LIBRARY_PREFIX}webrtc${CMAKE_STATIC_LIBRARY_SUFFIX}"
    INTERFACE_INCLUDE_DIRECTORIES "${_inc};${_inc}/third_party/abseil-cpp;${_inc}/third_party/libyuv/include"
)
# The prebuilts are release builds; debug checks change class layouts.
target_compile_definitions(libwebrtc INTERFACE NDEBUG)

if(WIN32)
  target_compile_definitions(libwebrtc INTERFACE
      WEBRTC_WIN NOMINMAX WIN32_LEAN_AND_MEAN _WINSOCKAPI_ _USE_MATH_DEFINES
  )
  target_link_libraries(libwebrtc INTERFACE
      advapi32 bcrypt crypt32 d3d11 dmoguids dwmapi dxgi gdi32 iphlpapi msdmo ole32 oleaut32
      secur32 shcore strmiids user32 uuid windowscodecs winmm wmcodecdspuuid ws2_32
  )
else()
  target_compile_definitions(libwebrtc INTERFACE WEBRTC_POSIX)
  find_package(Threads REQUIRED)
  target_link_libraries(libwebrtc INTERFACE Threads::Threads)
endif()

if(APPLE)
  target_compile_definitions(libwebrtc INTERFACE WEBRTC_MAC)
  target_link_libraries(libwebrtc INTERFACE
      "-framework AppKit"
      "-framework ApplicationServices"
      "-framework AudioToolbox"
      "-framework AVFoundation"
      "-framework CoreAudio"
      "-framework CoreFoundation"
      "-framework CoreGraphics"
      "-framework CoreMedia"
      "-framework CoreVideo"
      "-framework Foundation"
      "-framework IOSurface"
      "-framework Metal"
      "-framework Security"
      "-framework SystemConfiguration"
  )
elseif(_os STREQUAL "linux")
  if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR
        "libwebrtc for Linux is built against Chromium's libc++, which requires Clang. "
        "Set CXX=clang++ (and CC=clang).")
  endif()
  target_compile_definitions(libwebrtc INTERFACE
      WEBRTC_LINUX
      _LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE
  )
  # Use the bundled libc++ (namespace std::__Cr) instead of the system libstdc++;
  # its implementation is part of libwebrtc.a.
  target_compile_options(libwebrtc INTERFACE
      $<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>
      "SHELL:-isystem ${_inc}/buildtools/third_party/libc++"
      "SHELL:-isystem ${_inc}/third_party/libc++/src/include"
      "SHELL:-isystem ${_inc}/third_party/libc++abi/src/include"
  )
  # BIND_NOW: an incomplete prebuilt must fail on import, not on the first call
  target_link_options(libwebrtc INTERFACE -nostdlib++ "LINKER:--exclude-libs,ALL" "LINKER:-z,now")
  # Declared by a libwebrtc-bin Linux patch, but their definitions are missing from the archive
  target_sources(libwebrtc INTERFACE "${CMAKE_CURRENT_LIST_DIR}/libwebrtc_linux_fixups.cpp")
  target_link_libraries(libwebrtc INTERFACE dl rt m)
endif()
