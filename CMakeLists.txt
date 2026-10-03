cmake_minimum_required(VERSION 3.26)

if(NOT DEFINED SKBUILD_PROJECT_VERSION)
  set(SKBUILD_PROJECT_VERSION 0.0.0)
  set(SKBUILD_PROJECT_VERSION_FULL 0.0.0.dev0)
endif()

project(python_webrtc
    LANGUAGES C CXX
    DESCRIPTION "a Python extension that provides bindings to WebRTC"
    HOMEPAGE_URL "https://github.com/MarshalX/python-webrtc"
    VERSION ${SKBUILD_PROJECT_VERSION}
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(APPLE)
  # glue to libwebrtc's ObjC VideoToolbox codecs
  enable_language(OBJCXX)
  set(CMAKE_OBJCXX_STANDARD 20)
endif()
# for clang-tidy (make tidy) and editors
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
if(MSVC)
  # libwebrtc is linked against the static release CRT
  set(CMAKE_MSVC_RUNTIME_LIBRARY MultiThreaded)
endif()

include(cmake/libwebrtc.cmake)

find_package(Python 3.9 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(pybind11 CONFIG REQUIRED)

include(cmake/openh264.cmake)

add_subdirectory(python-webrtc/cpp)
