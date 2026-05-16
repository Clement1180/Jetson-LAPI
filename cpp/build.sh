#!/bin/bash
# Build the LAPI C++ pipeline on Jetson
# Prerequisites: JetPack 5.x/6.x, pybind11, cmake >= 3.18
#
# Install deps:
#   sudo apt install cmake python3-pybind11 pybind11-dev
#   pip install pybind11

set -e

BUILD_DIR="${1:-build}"
INSTALL_DIR="${2:-/opt/lapi}"

echo "=== Building LAPI C++ Pipeline ==="
echo "    Build: $BUILD_DIR"
echo "    Install: $INSTALL_DIR"

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR" \
    -Dpybind11_DIR="$(python3 -m pybind11 --cmakedir)"

make -j$(nproc)

echo ""
echo "=== Build successful ==="
echo "Library: $(pwd)/liblapi_core.so"
echo "Python:  $(pwd)/lapi_cpp*.so"
echo ""
echo "To install: sudo make install"
echo "To use in Python:"
echo "  import sys; sys.path.insert(0, '$(pwd)')"
echo "  import lapi_cpp"
