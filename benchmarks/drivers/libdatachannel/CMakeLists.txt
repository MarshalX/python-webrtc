#
#  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
#
#  Use of this source code is governed by a BSD-style license
#  that can be found in the LICENSE.md file in the root of the project.
#
# The driver of libdatachannel for the benchmarks, built against the pinned checkout in vendor/ (see runner.py).

cmake_minimum_required(VERSION 3.16)
project(libdatachannel_driver CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# data channels only: no media, no WebSocket, a static library
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(NO_MEDIA ON CACHE BOOL "" FORCE)
set(NO_WEBSOCKET ON CACHE BOOL "" FORCE)
set(NO_EXAMPLES ON CACHE BOOL "" FORCE)
set(NO_TESTS ON CACHE BOOL "" FORCE)
# like python-webrtc with WRTC_ALLOW_LOOPBACK=1: libjuice gathers loopback candidates too
set(ENABLE_LOCALHOST_ADDRESS ON CACHE BOOL "" FORCE)
set(JSON_BuildTests OFF CACHE BOOL "" FORCE)

add_subdirectory(vendor EXCLUDE_FROM_ALL)
add_subdirectory(vendor/deps/json EXCLUDE_FROM_ALL)

add_executable(libdatachannel-driver main.cpp channel.cpp)
target_link_libraries(libdatachannel-driver PRIVATE LibDataChannel::LibDataChannelStatic nlohmann_json::nlohmann_json)
# bin/ for multi-config generators (Visual Studio, Xcode) too
set_target_properties(libdatachannel-driver PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/bin
    RUNTIME_OUTPUT_DIRECTORY_RELEASE ${CMAKE_CURRENT_SOURCE_DIR}/bin)
