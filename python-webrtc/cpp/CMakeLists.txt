configure_file("${src_loc}/config.h.in" "${src_loc}/config.h")

file(GLOB_RECURSE MODULE_SRC ${src_loc}/*.cpp ${src_loc}/*.h)

pybind11_add_module(${MODULE} ${MODULE_SRC})

set_property(TARGET ${MODULE} PROPERTY CXX_STANDARD 14)

target_include_directories(${MODULE} SYSTEM PRIVATE
    ${libwebrtc_source_dir}
    ${libwebrtc_source_dir}/webrtc
    ${libwebrtc_source_dir}/webrtc/third_party/abseil-cpp
    ${libwebrtc_source_dir}/webrtc/third_party/libyuv/include
)

target_include_directories(${MODULE} PRIVATE
    ${CMAKE_SOURCE_DIR}
)

target_link_libraries(${MODULE} PRIVATE
    ${CMAKE_THREAD_LIBS_INIT}
    libpeerconnection
    libwebrtc
)

target_compile_definitions(${MODULE} PRIVATE
    -DNAPI_VERSION=3
    -DUSE_BUILTIN_SW_CODECS
)

if(WIN32)
  target_link_libraries(${MODULE} PRIVATE
      dmoguids.lib
      msdmo.lib
      secur32.lib
      winmm.lib
      wmcodecdspuuid.lib
      ws2_32.lib
  )
else()
  target_include_directories(${MODULE} SYSTEM PRIVATE
      ${libc++_include_dir}
      ${libc++abi_include_dir}
  )

  # NOTE(mroberts): On Linux and macOS, we statically link the same libc++ and
  # libc++abi libraries that libwebrtc builds against.
  target_link_libraries(${MODULE} PRIVATE
      -lc
      -lm
      libc++
      libc++abi
  )

  target_compile_options(${MODULE} PRIVATE
#      -fno-rtti doesnt allowed with pybind11
      -fvisibility=hidden
      -nostdinc++
      -nodefaultlibs
      -Wall
      -Wextra
      -Wno-missing-field-initializers
      -Wno-uninitialized
      -Wno-unused-local-typedefs
      -Wno-unused-variable
      -Wpedantic
  )

  target_compile_definitions(${MODULE} PRIVATE
      -D_LIBCPP_ABI_UNSTABLE
      -DWEBRTC_POSIX=1
  )

  if(APPLE)
    target_link_libraries(${MODULE} PRIVATE
        "-framework AppKit"
        "-framework AVFoundation"
    )

    target_compile_options(${MODULE} PRIVATE
        -Weverything
        -Wno-c++98-compat
        -Wno-c++98-compat-pedantic
        -Wno-documentation
        -Wno-exit-time-destructors
        -Wno-float-conversion
        -Wno-global-constructors
        -Wno-padded
        -Wno-shadow
        -Wno-shadow-field-in-constructor
        -Wno-shorten-64-to-32
        -Wno-sign-conversion
        -Wno-thread-safety-negative
        -Wno-unused-template
        -Wno-weak-vtables
    )

    target_compile_definitions(${MODULE} PRIVATE
        -D_LIBCPP_ABI_UNSTABLE
        -DWEBRTC_MAC
        -DWEBRTC_IOS
    )
  else()
    target_compile_definitions(${MODULE} PRIVATE
        -DWEBRTC_LINUX
    )
  endif()
endif()
