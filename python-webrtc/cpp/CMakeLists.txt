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

install(TARGETS ${MODULE} LIBRARY DESTINATION . RUNTIME DESTINATION .)
install(FILES "${PROJECT_SOURCE_DIR}/stubs/wrtc/__init__.pyi" DESTINATION . RENAME wrtc.pyi)
if(DEFINED SKBUILD_METADATA_DIR)
  install(FILES "${LIBWEBRTC_ROOT}/NOTICE" DESTINATION "${SKBUILD_METADATA_DIR}/licenses" RENAME LIBWEBRTC_NOTICE)
endif()
