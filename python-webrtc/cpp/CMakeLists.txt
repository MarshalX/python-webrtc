set(MODULE wrtc)

configure_file(src/config.h.in "${CMAKE_CURRENT_BINARY_DIR}/generated/config.h")

file(GLOB_RECURSE MODULE_SRC CONFIGURE_DEPENDS src/*.cpp src/*.h)

pybind11_add_module(${MODULE} ${MODULE_SRC})

target_include_directories(${MODULE} PRIVATE
    "${CMAKE_CURRENT_BINARY_DIR}/generated"
    "${CMAKE_CURRENT_SOURCE_DIR}/src"
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

install(TARGETS ${MODULE} LIBRARY DESTINATION . RUNTIME DESTINATION .)
install(FILES "${PROJECT_SOURCE_DIR}/stubs/wrtc/__init__.pyi" DESTINATION . RENAME wrtc.pyi)
if(DEFINED SKBUILD_METADATA_DIR)
  install(FILES "${LIBWEBRTC_ROOT}/NOTICE" DESTINATION "${SKBUILD_METADATA_DIR}/licenses" RENAME LIBWEBRTC_NOTICE)
endif()
