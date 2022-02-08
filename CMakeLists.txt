cmake_minimum_required(VERSION 3.14)
cmake_policy(SET CMP0076 NEW)

include(ExternalProject)

project(python_webrtc
    LANGUAGES C CXX
    DESCRIPTION "a Python Extension that provides bindings to WebRTC"
    HOMEPAGE_URL "https://github.com/MarshalX/python-webrtc"
    VERSION "0.0.0.5"
)

include(ExternalProject)
find_package(Git REQUIRED)
find_package(Threads REQUIRED)

get_filename_component(third_party_loc "third_party" REALPATH)
get_filename_component(project_loc "python-webrtc/cpp/" REALPATH)
get_filename_component(src_loc "${project_loc}/src" REALPATH)


# depot tools
# ref about fix on M1 macs with git commits: https://bugs.chromium.org/p/chromium/issues/detail?id=1102967
if (APPLE)
  set(DEPOT_GIT_TAG cb340f5b7bbdcaba0fad346b08db91538619a531)
else()
  set(DEPOT_GIT_TAG 9b5dd7ab8a98140a1b73b9dea29245605137cd09) # glibc 2.18, supports python 3 < 3.8
endif()

if (WIN32)
  set(DEPOT_GIT_TAG 2fddb95698211db1373ebe2b16091a54eac51c9c)
endif()

ExternalProject_Add(
    project_depot_tools

    GIT_REPOSITORY    https://chromium.googlesource.com/chromium/tools/depot_tools.git
    GIT_TAG           ${DEPOT_GIT_TAG}

    PREFIX            ${third_party_loc}/depot_tools/prefix
    TMP_DIR           ${third_party_loc}/depot_tools/tmp
    STAMP_DIR         ${third_party_loc}/depot_tools/stamp
    DOWNLOAD_DIR      ${third_party_loc}/depot_tools/download
    SOURCE_DIR        ${third_party_loc}/depot_tools/src
    BINARY_DIR        ${third_party_loc}/depot_tools/build

    CONFIGURE_COMMAND ""
    BUILD_COMMAND     ""
    INSTALL_COMMAND   ""
)

ExternalProject_Get_Property(project_depot_tools SOURCE_DIR)
set(depot_tools_install_dir ${SOURCE_DIR})


# libc++
set(libwebrtc_binary_dir ${third_party_loc}/libwebrtc/build/${CMAKE_BUILD_TYPE})
set(libwebrtc_src_dir ${third_party_loc}/libwebrtc/download/src)

add_library(libc++ OBJECT IMPORTED)
add_dependencies(libc++ libwebrtc)

set(libc++_objects
    algorithm.o
    any.o
    atomic.o
    barrier.o
    bind.o
    charconv.o
    chrono.o
    condition_variable.o
    condition_variable_destructor.o
    debug.o
    exception.o
    functional.o
    future.o
    hash.o
    ios.instantiations.o
    ios.o
    iostream.o
    locale.o
    memory.o
    mutex.o
    mutex_destructor.o
    new.o
    optional.o
    random.o
    random_shuffle.o
    regex.o
    shared_mutex.o
    stdexcept.o
    string.o
    strstream.o
    system_error.o
    thread.o
    typeinfo.o
    utility.o
    valarray.o
    variant.o
    vector.o
)
list(TRANSFORM libc++_objects PREPEND ${libwebrtc_binary_dir}/obj/buildtools/third_party/libc++/libc++/)

set_property(TARGET libc++ APPEND PROPERTY IMPORTED_CONFIGURATIONS DEBUG)
set_target_properties(libc++ PROPERTIES IMPORTED_OBJECTS_DEBUG "${libc++_objects}" IMPORTED_OBJECTS "${libc++_objects}")

# libc++abi
add_library(libc++abi OBJECT IMPORTED)
add_dependencies(libc++abi libwebrtc)

set(libc++abi_objects
    abort_message.o
    cxa_aux_runtime.o
    cxa_default_handlers.o
    cxa_demangle.o
    cxa_exception.o
    cxa_exception_storage.o
    cxa_guard.o
    cxa_handlers.o
    cxa_personality.o
#    cxa_unexpected.o TODO doublecheck
    cxa_vector.o
    cxa_virtual.o
    fallback_malloc.o
    private_typeinfo.o
    stdlib_exception.o
    stdlib_stdexcept.o
    stdlib_typeinfo.o
)
list(TRANSFORM libc++abi_objects PREPEND ${libwebrtc_binary_dir}/obj/buildtools/third_party/libc++abi/libc++abi/)

set_property(TARGET libc++abi APPEND PROPERTY IMPORTED_CONFIGURATIONS DEBUG)
set_target_properties(libc++abi PROPERTIES IMPORTED_OBJECTS_DEBUG "${libc++abi_objects}" IMPORTED_OBJECTS "${libc++abi_objects}")


# libwebrtc
set(WEBRTC_REVISION branch-heads/4515) # m92

list(APPEND GN_GEN_ARGS
    use_rtti=true
    rtc_build_examples=false
    rtc_use_x11=false
    rtc_enable_protobuf=false
    rtc_include_pulse_audio=false
    rtc_include_tests=false
)
if ("$ENV{TARGET_ARCH}" STREQUAL "arm")
  list(APPEND GN_GEN_ARGS
      target_os="linux"
      target_cpu="arm"
      rtc_build_tools=true
      treat_warnings_as_errors=false
      fatal_linker_warnings=false
  )
elseif ("$ENV{TARGET_ARCH}" STREQUAL "arm64")
  if(NOT APPLE)
    list(APPEND GN_GEN_ARGS
        target_os="linux"
    )
  endif()
  list(APPEND GN_GEN_ARGS
      target_cpu="arm64"
      rtc_build_tools=true
      treat_warnings_as_errors=false
      fatal_linker_warnings=false
  )
else()
  list(APPEND GN_GEN_ARGS
      use_glib=false
      rtc_build_tools=false
  )

  if ("$ENV{TARGET_ARCH}" STREQUAL "ia32")
    list(APPEND GN_GEN_ARGS
        target_arch=ia32
    )
  endif()
endif()

if (WIN32)
  list(APPEND GN_GEN_ARGS is_clang=false)
endif()

if (CMAKE_BUILD_TYPE STREQUAL "Debug")
  list(APPEND GN_GEN_ARGS is_debug=true)
else()
  list(APPEND GN_GEN_ARGS is_debug=false)
endif()

string(REPLACE ";" " " GN_GEN_ARGS "${GN_GEN_ARGS}")

if(WIN32)
  set(suffix bat)
  set(PLATFORM windows)
else()
  set(suffix sh)
  if(APPLE)
    set(PLATFORM darwin)
  else()
    set(PLATFORM linux)
  endif()
endif()

if (WIN32)
  set(byproducts
      ${libwebrtc_binary_dir}/obj/webrtc.lib
      ${libwebrtc_binary_dir}/obj/pc/peerconnection.lib
  )
else()
  set(byproducts
      ${libc++_objects}
      ${libwebrtc_binary_dir}/obj/libwebrtc.a
      ${libwebrtc_binary_dir}/obj/pc/libpeerconnection.a
  )
  if (NOT APPLE)
      list(APPEND byproducts ${libc++abi_objects})
  endif()
endif()

ExternalProject_Add(
    project_libwebrtc

    PREFIX            ${third_party_loc}/libwebrtc/prefix
    TMP_DIR           ${third_party_loc}/libwebrtc/tmp
    STAMP_DIR         ${third_party_loc}/libwebrtc/stamp
    DOWNLOAD_DIR      ${third_party_loc}/libwebrtc/download
    SOURCE_DIR        ${third_party_loc}/libwebrtc/download/src
    BINARY_DIR        ${third_party_loc}/libwebrtc/build/${CMAKE_BUILD_TYPE}

    BUILD_BYPRODUCTS  ${byproducts}

    DOWNLOAD_COMMAND  ${CMAKE_COMMAND} -E env DEPOT_TOOLS=${depot_tools_install_dir} PLATFORM=${PLATFORM} WEBRTC_REVISION=${WEBRTC_REVISION} ${CMAKE_SOURCE_DIR}/scripts/download-webrtc.${suffix}
    CONFIGURE_COMMAND ${CMAKE_COMMAND} -E env BINARY_DIR=<BINARY_DIR> DEPOT_TOOLS=${depot_tools_install_dir} GN_GEN_ARGS=${GN_GEN_ARGS} SOURCE_DIR=<SOURCE_DIR> ${CMAKE_SOURCE_DIR}/scripts/configure-webrtc.${suffix}
    BUILD_COMMAND     ${CMAKE_COMMAND} -E env CMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE} DEPOT_TOOLS=${depot_tools_install_dir} ${CMAKE_SOURCE_DIR}/scripts/build-webrtc.${suffix}
    INSTALL_COMMAND   ""
)

add_dependencies(project_libwebrtc project_depot_tools)

ExternalProject_Get_Property(project_libwebrtc DOWNLOAD_DIR)
set(libwebrtc_source_dir "${DOWNLOAD_DIR}")

ExternalProject_Get_Property(project_libwebrtc BINARY_DIR)
set(libwebrtc_binary_dir "${BINARY_DIR}")

add_library(libwebrtc STATIC IMPORTED)
add_dependencies(libwebrtc project_libwebrtc)

if(WIN32)
  set_property(TARGET libwebrtc PROPERTY IMPORTED_LOCATION "${libwebrtc_binary_dir}/obj/webrtc.lib")
else()
  set_property(TARGET libwebrtc PROPERTY IMPORTED_LOCATION "${libwebrtc_binary_dir}/obj/libwebrtc.a")
endif()

add_library(libpeerconnection STATIC IMPORTED)
add_dependencies(libpeerconnection project_libwebrtc)

if(WIN32)
  set_property(TARGET libpeerconnection PROPERTY IMPORTED_LOCATION "${libwebrtc_binary_dir}/obj/pc/peerconnection.lib")
else()
  set_property(TARGET libpeerconnection PROPERTY IMPORTED_LOCATION "${libwebrtc_binary_dir}/obj/pc/libpeerconnection.a")
endif()

set(libc++_include_dir "${libwebrtc_source_dir}/src/buildtools/third_party/libc++/trunk/include")
set(libc++abi_include_dir "${libwebrtc_source_dir}/src/buildtools/third_party/libc++abi/trunk/include")

# pybind11
add_subdirectory(${third_party_loc}/pybind11)

# python binding
set(MODULE wrtc)
add_subdirectory(${project_loc})
