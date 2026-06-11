cmake_minimum_required(VERSION 3.18)
project(jetson_lapi CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# ── OpenCV : fourni par JetPack sur Jetson ────────────────────────────────────
find_package(OpenCV REQUIRED COMPONENTS core imgproc videoio video highgui)

# ── ONNX Runtime : pas de find_package officiel partout, on pointe la racine ──
# -DONNXRUNTIME_ROOT_DIR=/path/to/onnxruntime  (contient include/ et lib/)
set(ONNXRUNTIME_ROOT_DIR "" CACHE PATH "Racine de l'installation ONNX Runtime C++")

find_path(ONNXRUNTIME_INCLUDE_DIR
  NAMES onnxruntime_cxx_api.h
  HINTS "${ONNXRUNTIME_ROOT_DIR}/include"
        "${ONNXRUNTIME_ROOT_DIR}/include/onnxruntime"
        "${ONNXRUNTIME_ROOT_DIR}/include/onnxruntime/core/session"
        /usr/local/include/onnxruntime /usr/include/onnxruntime)
find_library(ONNXRUNTIME_LIB
  NAMES onnxruntime
  HINTS "${ONNXRUNTIME_ROOT_DIR}/lib" /usr/local/lib)

if(NOT ONNXRUNTIME_INCLUDE_DIR OR NOT ONNXRUNTIME_LIB)
  message(FATAL_ERROR "ONNX Runtime introuvable — passer -DONNXRUNTIME_ROOT_DIR=...")
endif()

add_executable(lapi
  src/main.cpp
  src/models/yolo.cpp
  src/models/ocr.cpp
  src/pipeline/core.cpp
  src/pipeline/detect.cpp
  src/pipeline/kalman.cpp
  src/io/reader.cpp
  src/io/writer.cpp
  src/io/viz.cpp
)

target_include_directories(lapi PRIVATE src ${ONNXRUNTIME_INCLUDE_DIR})
target_link_libraries(lapi PRIVATE ${OpenCV_LIBS} ${ONNXRUNTIME_LIB})
