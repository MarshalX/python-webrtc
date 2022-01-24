configure_file("${src_loc}/config.h.in" "${src_loc}/config.h")

file(GLOB_RECURSE MODULE_SRC ${src_loc}/*.cpp ${src_loc}/*.h)

pybind11_add_module(${MODULE} ${MODULE_SRC})

set_property(TARGET ${MODULE} PROPERTY CXX_STANDARD 17)

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
    -DUSE_BUILTIN_SW_CODECS
)

if(WIN32)
  set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} /MT /GR-")
  set(CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG} /MTd /GR- -D_HAS_ITERATOR_DEBUGGING=0")
  set(CMAKE_SHARED_LINKER_FLAGS "${CMAKE_SHARED_LINKER_FLAGS} /FORCE:UNRESOLVED")

  target_link_libraries(${MODULE} PRIVATE
      dmoguids.lib
      msdmo.lib
      secur32.lib
      winmm.lib
      wmcodecdspuuid.lib
      ws2_32.lib
  )

  target_compile_definitions(${MODULE} PRIVATE
      -D_WINSOCKAPI_
      -DNOGDI
      -DNOMINMAX
      -DWEBRTC_WIN
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
  )

  if(NOT APPLE)
    target_link_libraries(${MODULE} PRIVATE
        libc++abi
    )
  endif()

  target_compile_options(${MODULE} PRIVATE
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

  if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    target_compile_options(${MODULE} PRIVATE
        -g
#        -fsanitize=address
#        -fno-omit-frame-pointer
    )

    target_compile_definitions(${MODULE} PRIVATE
        -DDEBUG
    )
  endif()

  if(APPLE)
    target_link_libraries(${MODULE} PRIVATE
        "-framework AppKit"
        "-framework AVFoundation"
    )

    if ("$ENV{TARGET_ARCH}" STREQUAL "arm64")
      target_compile_options(${MODULE} PRIVATE
          -arch arm64
      )
      target_link_options(${MODULE} PRIVATE
          -arch arm64
      )
    endif()

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

    target_compile_options(${MODULE} PRIVATE
        -fpermissive
    )

    if ("$ENV{TARGET_ARCH}" STREQUAL "arm" OR "$ENV{TARGET_ARCH}" STREQUAL "arm64")
      set(CMAKE_SYSTEM_NAME Linux)
      set(CMAKE_SYSTEM_PROCESSOR "$ENV{TARGET_ARCH}")
      set(tools $ENV{ARM_TOOLS_PATH})

      set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
      set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
      set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
      set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

      if ("$ENV{TARGET_ARCH}" STREQUAL "arm")
        set(CMAKE_SYSROOT ${libwebrtc_source_dir}/src/build/linux/debian_sid_arm-sysroot)
        target_compile_options(${MODULE} PRIVATE
            -march=armv7-a
            -mfloat-abi=hard
            -mtune=generic-armv7-a
            -mfpu=neon
        )
        set(CMAKE_C_COMPILER ${tools}/bin/arm-linux-gnueabihf-gcc)
        set(CMAKE_CXX_COMPILER ${tools}/bin/arm-linux-gnueabihf-g++)
      else()
        set(CMAKE_SYSROOT ${libwebrtc_source_dir}/src/build/linux/debian_sid_arm64-sysroot)
        set(CMAKE_C_COMPILER ${tools}/bin/aarch64-linux-gnu-gcc)
        set(CMAKE_CXX_COMPILER ${tools}/bin/aarch64-linux-gnu-g++)
      endif()
    else()
      target_compile_options(${MODULE} PRIVATE
          -B${libwebrtc_source_dir}/src/third_party/binutils/Linux_x64/Release/bin
          --sysroot=${libwebrtc_source_dir}/src/build/linux/debian_sid_amd64-sysroot
      )
    endif()
  endif()
endif()
