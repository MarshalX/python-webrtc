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
# the upstream commit of that release (m152.7977@{#0})
set(LIBWEBRTC_COMMIT 6f37672d358475cd17544121a12494da454d85fb)
set(LIBWEBRTC_URL_BASE "https://github.com/crow-misia/libwebrtc-bin/releases/download/${LIBWEBRTC_VERSION}")

set(LIBWEBRTC_SHA256_linux-x64   5ba9bbb3392671d96f8fb300e2a2c1566d76fa4e590e3b4f959fa144da16da5c)
set(LIBWEBRTC_SHA256_linux-arm64 11b84989ee3ca7fb75ff5041bf5aab5fda8934da02d1705891e1adc9c75f1ba4)
set(LIBWEBRTC_SHA256_macos-x64   1d4f4480316e227fa026bb928c31c3fc2fcc0e8c65f85323c314e1be4ac55b14)
set(LIBWEBRTC_SHA256_macos-arm64 3a7d3d7d10de56580d3cbe18910a92c3ab85ae07316e6f745890c7b545c0a9c7)
set(LIBWEBRTC_SHA256_win-x64     41e64b712f3777db0377e8445972051366bc333905b0880a1fc6c4bef1f5b8cf)
set(LIBWEBRTC_SHA256_win-x86     44cb24862b8deb5cbeef697d1e84bdb5a93ec416602aafa5831b6d27131d12e9)

# The Linux prebuilts are compiled against Chromium's libc++ but only ship its *.h
# headers. The extensionless ones are fetched from the matching llvm-project commit
# (see cmake/libcxx/README.md). Its build-generated config comes from the matching Chromium tag.
# The linux-arm64 prebuilt also lacks the compiled libc++ and libc++abi, which are built from the
# llvm-project commits WebRTC pins them (and llvm-libc, which libc++ uses) at.
set(LIBCXX_LLVM_COMMIT 54359956733059b058c071264ad58a6ddbed4976)
set(LIBCXXABI_LLVM_COMMIT 4ffd373e3853ebc00fb339611e215deab682a54c)
set(LLVM_LIBC_COMMIT 2abc19543d802780eadd1450f0aa0c28fed080af)
set(LIBCXX_CHROMIUM_TAG 152.0.7977.0)

# Downloads every "<sha256>  <path>" entry of a manifest from <base_url>/<path> into <dest>/<path>,
# optionally only the paths starting with <prefix>.
function(_fetch_pinned manifest base_url dest)
  if(ARGC GREATER 3)
    file(STRINGS "${manifest}" _lines REGEX "  ${ARGV3}")
  else()
    file(STRINGS "${manifest}" _lines)
  endif()
  foreach(_line IN LISTS _lines)
    string(REGEX MATCH "^([0-9a-f]+)  (.+)$" _ "${_line}")
    set(_sha "${CMAKE_MATCH_1}")
    set(_path "${CMAKE_MATCH_2}")
    # raw.githubusercontent.com fails now and then over hundreds of requests, so retry;
    # no EXPECTED_HASH, it turns a failed attempt into a configure error
    foreach(_attempt RANGE 1 4)
      file(DOWNLOAD "${base_url}/${_path}" "${dest}/${_path}" STATUS _status TLS_VERIFY ON)
      list(GET _status 0 _code)
      if(_code EQUAL 0)
        file(SHA256 "${dest}/${_path}" _actual)
        if(_actual STREQUAL _sha)
          break()
        endif()
        set(_status "SHA256 mismatch: ${_actual}")
      endif()
      if(_attempt EQUAL 4)
        message(FATAL_ERROR "Failed to download ${base_url}/${_path}: ${_status}")
      endif()
      execute_process(COMMAND "${CMAKE_COMMAND}" -E sleep ${_attempt})
    endforeach()
  endforeach()
endfunction()

# Header directories (relative to include/) needed to compile against the public API.
set(LIBWEBRTC_HEADER_DIRS
    api audio call common_audio common_video logging media modules net p2p pc
    rtc_base system_wrappers video
    third_party/abseil-cpp third_party/libyuv
)
if(APPLE)
  # the ObjC SDK, for the VideoToolbox H.264 codecs
  list(APPEND LIBWEBRTC_HEADER_DIRS sdk)
endif()

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
set(_build_libcxx OFF)

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
  if(LIBWEBRTC_PLATFORM STREQUAL "linux-arm64")
    set(_build_libcxx ON)
    file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/libcxx/runtime.sha256" _runtime_hash)
    string(APPEND _stamp_content ";${LIBCXXABI_LLVM_COMMIT};${LLVM_LIBC_COMMIT};${_runtime_hash}")
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
    if(_build_libcxx)
      message(STATUS "Downloading libc++, libc++abi and llvm-libc sources")
      foreach(_dir_commit libcxx/${LIBCXX_LLVM_COMMIT} libcxxabi/${LIBCXXABI_LLVM_COMMIT} libc/${LLVM_LIBC_COMMIT})
        string(REPLACE "/" ";" _dir_commit "${_dir_commit}")
        list(GET _dir_commit 0 _dir)
        list(GET _dir_commit 1 _commit)
        _fetch_pinned("${CMAKE_CURRENT_LIST_DIR}/libcxx/runtime.sha256"
            "https://raw.githubusercontent.com/llvm/llvm-project/${_commit}" "${LIBWEBRTC_ROOT}/llvm" "${_dir}/")
      endforeach()
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
  # the SDK includes its headers relative to these
  set_property(TARGET libwebrtc APPEND PROPERTY INTERFACE_INCLUDE_DIRECTORIES "${_inc}/sdk/objc;${_inc}/sdk/objc/base")
  # ObjC categories the codec glue needs, which no symbol pulls in; -ObjC would also link the SDK's Metal views
  set(_objc_categories
      NSString+StdString.o RTCEncodedImage+Private.o RTCVideoCodecInfo+Private.o RTCVideoEncoderSettings+Private.o)
  set(_objc_dir "${CMAKE_BINARY_DIR}/libwebrtc-objc")
  file(MAKE_DIRECTORY "${_objc_dir}")
  execute_process(
      COMMAND "${CMAKE_AR}" -x "${LIBWEBRTC_ROOT}/lib/libwebrtc.a" ${_objc_categories}
      WORKING_DIRECTORY "${_objc_dir}"
      COMMAND_ERROR_IS_FATAL ANY
  )
  list(TRANSFORM _objc_categories PREPEND "${_objc_dir}/")
  target_link_libraries(libwebrtc INTERFACE ${_objc_categories})
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
      "-framework VideoToolbox"
  )
elseif(_os STREQUAL "linux")
  if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR
        "libwebrtc for Linux is built against Chromium's libc++, which requires Clang. "
        "Set CXX=clang++ (and CC=clang).")
  endif()
  set(_libcxx_defines _LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_EXTENSIVE)
  set(_libcxx_options
      $<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>
      "SHELL:-isystem ${_inc}/buildtools/third_party/libc++"
      "SHELL:-isystem ${_inc}/third_party/libc++/src/include"
      "SHELL:-isystem ${_inc}/third_party/libc++abi/src/include"
  )
  target_compile_definitions(libwebrtc INTERFACE WEBRTC_LINUX ${_libcxx_defines})
  # Use the bundled libc++ (namespace std::__Cr) instead of the system libstdc++;
  # its implementation is part of libwebrtc.a (built below on arm64).
  target_compile_options(libwebrtc INTERFACE ${_libcxx_options})
  # BIND_NOW: an incomplete prebuilt must fail on import, not on the first call
  target_link_options(libwebrtc INTERFACE -nostdlib++ "LINKER:--exclude-libs,ALL" "LINKER:-z,now")
  # Declared by a libwebrtc-bin Linux patch, but their definitions are missing from the archive
  target_sources(libwebrtc INTERFACE "${CMAKE_CURRENT_LIST_DIR}/libwebrtc_linux_fixups.cpp")
  target_link_libraries(libwebrtc INTERFACE dl rt m)

  if(_build_libcxx)
    # Chromium's libc++ and libc++abi, with the flags of its buildtools/third_party/libc++*/BUILD.gn
    set(_llvm "${LIBWEBRTC_ROOT}/llvm")
    file(STRINGS "${CMAKE_CURRENT_LIST_DIR}/libcxx/runtime.sha256" _runtime)
    list(TRANSFORM _runtime REPLACE "^[0-9a-f]+  " "${_llvm}/")
    list(FILTER _runtime INCLUDE REGEX "/libcxx(abi)?/src/.*\\.cpp$")
    set(_libcxxabi_sources ${_runtime})
    list(FILTER _libcxxabi_sources INCLUDE REGEX "/libcxxabi/")
    add_library(chromium_libcxx STATIC ${_runtime})
    set_target_properties(chromium_libcxx PROPERTIES
        CXX_STANDARD 26
        CXX_VISIBILITY_PRESET hidden
        POSITION_INDEPENDENT_CODE ON
        UNITY_BUILD OFF
    )
    target_compile_definitions(chromium_libcxx PRIVATE
        ${_libcxx_defines} NDEBUG _LIBCPP_BUILDING_LIBRARY LIBC_NAMESPACE=__llvm_libc_cr
    )
    target_compile_options(chromium_libcxx PRIVATE ${_libcxx_options} -fstrict-aliasing -w)
    target_include_directories(chromium_libcxx PRIVATE "${_llvm}/libcxx/src" "${_llvm}/libc")
    set_source_files_properties(${_runtime} PROPERTIES COMPILE_DEFINITIONS LIBCXX_BUILDING_LIBCXXABI)
    set_source_files_properties(${_libcxxabi_sources} PROPERTIES COMPILE_DEFINITIONS
        "LIBCXXABI_SILENT_TERMINATE;_LIBCXXABI_USE_FUTEX;_LIBCPP_CONSTINIT=constinit"
    )

    # libwebrtc calls SME ABI routines (__arm_tpidr2_save) that only compiler-rt provides, not libgcc
    execute_process(
        COMMAND "${CMAKE_CXX_COMPILER}" --rtlib=compiler-rt -print-libgcc-file-name
        OUTPUT_VARIABLE _builtins
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    if(NOT EXISTS "${_builtins}")
      message(FATAL_ERROR "Clang's compiler-rt builtins not found (${_builtins}), install compiler-rt")
    endif()
    target_link_libraries(libwebrtc INTERFACE chromium_libcxx "${_builtins}")
  endif()
endif()
