cmake_minimum_required(VERSION 3.18)
project(jetson_lapi CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

# ── OpenCV : fourni par JetPack sur Jetson ────────────────────────────────────
find_package(OpenCV REQUIRED COMPONENTS core imgproc videoio video highgui dnn)

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

add_library(lapi_core STATIC
  src/models/yolo.cpp
  src/models/ocr.cpp
  src/pipeline/core.cpp
  src/pipeline/detect.cpp
  src/pipeline/kalman.cpp
  src/io/reader.cpp
  src/io/writer.cpp
  src/io/viz.cpp
)
target_include_directories(lapi_core PUBLIC src ${ONNXRUNTIME_INCLUDE_DIR})
target_link_libraries(lapi_core PUBLIC ${OpenCV_LIBS} ${ONNXRUNTIME_LIB})

add_executable(lapi src/main.cpp)
target_link_libraries(lapi PRIVATE lapi_core)

# Dump JSON des sorties → tools/compare_oracle.py contre l'oracle Python
add_executable(lapi_oracle src/make_oracle.cpp)
target_link_libraries(lapi_oracle PRIVATE lapi_core)
