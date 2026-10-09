set(MODULE wrtc)

file(GLOB_RECURSE MODULE_SRC CONFIGURE_DEPENDS src/*.cpp src/*.h)
if(APPLE)
  file(GLOB_RECURSE MODULE_OBJC_SRC CONFIGURE_DEPENDS src/*.mm)
  list(APPEND MODULE_SRC ${MODULE_OBJC_SRC})
  set_source_files_properties(${MODULE_OBJC_SRC} PROPERTIES COMPILE_OPTIONS -fobjc-arc)
endif()
set_source_files_properties("${OPENH264_ENCODER_SRC}" src/codecs/openh264.cpp
    PROPERTIES COMPILE_DEFINITIONS WEBRTC_USE_H264)

pybind11_add_module(${MODULE} ${MODULE_SRC} "${OPENH264_ENCODER_SRC}")

target_include_directories(${MODULE} PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
    "${OPENH264_INCLUDE_DIR}"
)
target_link_libraries(${MODULE} PRIVATE libwebrtc)

if(MSVC)
  target_compile_options(${MODULE} PRIVATE /W3 /utf-8 /Zc:__cplusplus)
else()
  target_compile_options(${MODULE} PRIVATE -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers)
endif()

# Instruments the extension (not the prebuilt libwebrtc), e.g. -DWRTC_SANITIZE=address,undefined with Clang.
# The interpreter isn't instrumented, so the sanitizer runtime has to be preloaded (see .github/scripts/sanitizers.sh).
set(WRTC_SANITIZE "" CACHE STRING "Comma-separated sanitizers to build the extension with")
if(WRTC_SANITIZE)
  # vptr checks need the typeinfo of the C++ runtime, which libwebrtc links in privately
  target_compile_options(${MODULE} PRIVATE
      -fsanitize=${WRTC_SANITIZE} -fno-sanitize=vptr -fno-sanitize-recover=all -fno-omit-frame-pointer)
  target_link_options(${MODULE} PRIVATE -fsanitize=${WRTC_SANITIZE} -fno-sanitize=vptr)
  if(WRTC_SANITIZE MATCHES "address")
    # Atheris preloads its own runtime with libFuzzer (asan_with_fuzzer.so), which must provide the symbols
    if(NOT WRTC_SANITIZE MATCHES "fuzzer")
      target_link_options(${MODULE} PRIVATE -shared-libasan)
    endif()
    # The libc++ inside libwebrtc isn't instrumented (no _LIBCPP_INSTRUMENTED_WITH_ASAN): containers it touches
    # aren't annotated, so annotating them in our code alone reports false container-overflows.
    target_compile_definitions(${MODULE} PRIVATE __SANITIZER_DISABLE_CONTAINER_OVERFLOW__)
  endif()
endif()

option(WRTC_COVERAGE "Build the extension with coverage counters" OFF)
if(WRTC_COVERAGE)
  target_compile_options(${MODULE} PRIVATE -fprofile-instr-generate -fcoverage-mapping)
  target_link_options(${MODULE} PRIVATE -fprofile-instr-generate)
endif()

install(TARGETS ${MODULE} LIBRARY DESTINATION . RUNTIME DESTINATION .)
install(FILES "${PROJECT_SOURCE_DIR}/stubs/wrtc/__init__.pyi" DESTINATION . RENAME wrtc.pyi)
if(DEFINED SKBUILD_METADATA_DIR)
  install(FILES "${LIBWEBRTC_ROOT}/NOTICE" DESTINATION "${SKBUILD_METADATA_DIR}/licenses" RENAME LIBWEBRTC_NOTICE)
endif()
