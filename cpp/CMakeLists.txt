cmake_minimum_required(VERSION 3.18)
project(lapi_cpp LANGUAGES CXX CUDA)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find packages
find_package(CUDA REQUIRED)
find_package(pybind11 REQUIRED)

# TensorRT (typically at /usr/lib/aarch64-linux-gnu on Jetson)
set(TENSORRT_ROOT "/usr" CACHE PATH "TensorRT installation root")
find_library(NVINFER_LIB nvinfer HINTS ${TENSORRT_ROOT}/lib /usr/lib/aarch64-linux-gnu)
find_library(NVINFER_PLUGIN_LIB nvinfer_plugin HINTS ${TENSORRT_ROOT}/lib /usr/lib/aarch64-linux-gnu)
find_path(TENSORRT_INCLUDE NvInfer.h HINTS ${TENSORRT_ROOT}/include)

if(NOT NVINFER_LIB)
    message(FATAL_ERROR "TensorRT nvinfer library not found")
endif()

# Sources
set(LAPI_SOURCES
    src/inference.cpp
    src/tracker.cpp
    src/pipeline.cpp
)

# Shared library
add_library(lapi_core SHARED ${LAPI_SOURCES})
target_include_directories(lapi_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${TENSORRT_INCLUDE}
    ${CUDA_INCLUDE_DIRS}
)
target_link_libraries(lapi_core
    ${NVINFER_LIB}
    ${NVINFER_PLUGIN_LIB}
    ${CUDA_LIBRARIES}
)

# Python module (pybind11)
pybind11_add_module(lapi_cpp pybind/lapi_cpp.cpp)
target_link_libraries(lapi_cpp PRIVATE lapi_core)
target_include_directories(lapi_cpp PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Install
install(TARGETS lapi_core LIBRARY DESTINATION lib)
install(TARGETS lapi_cpp LIBRARY DESTINATION lib/python)
install(DIRECTORY include/ DESTINATION include/lapi)
