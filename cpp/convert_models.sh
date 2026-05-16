#!/bin/bash
# Convert ONNX models to TensorRT engines for Jetson
# Usage: ./convert_models.sh [models_dir] [output_dir]
#
# Requires: trtexec (included with JetPack)
# Jetson Orin Nano: FP16 optimal, INT8 needs calibration data

set -e

MODELS_DIR="${1:-/opt/lapi/models}"
OUTPUT_DIR="${2:-/opt/lapi/engines}"
PRECISION="${PRECISION:-fp16}"

mkdir -p "$OUTPUT_DIR"

echo "=== LAPI Model Conversion: ONNX → TensorRT ($PRECISION) ==="
echo "    Models dir: $MODELS_DIR"
echo "    Output dir: $OUTPUT_DIR"
echo ""

convert() {
    local name="$1"
    local onnx="$2"
    local extra_args="$3"

    if [ ! -f "$onnx" ]; then
        echo "[SKIP] $name: $onnx not found"
        return
    fi

    local engine="$OUTPUT_DIR/${name}.engine"
    if [ -f "$engine" ]; then
        echo "[SKIP] $name: engine already exists"
        return
    fi

    echo "[CONVERTING] $name..."
    /usr/src/tensorrt/bin/trtexec \
        --onnx="$onnx" \
        --saveEngine="$engine" \
        --${PRECISION} \
        --workspace=1024 \
        $extra_args \
        2>&1 | tail -5

    if [ -f "$engine" ]; then
        local size=$(du -h "$engine" | cut -f1)
        echo "[OK] $name → $engine ($size)"
    else
        echo "[ERROR] $name conversion failed"
        exit 1
    fi
}

# YOLOv8s - Vehicle detection (input: 1x3x640x640)
convert "yolov8s_car" \
    "$MODELS_DIR/yolov8s.onnx" \
    "--inputIOFormats=fp16:chw --outputIOFormats=fp16:chw"

# YOLOv8s-pose - Plate keypoints (input: 1x3x640x640)
convert "yolov8s_plate" \
    "$MODELS_DIR/yolov8s-pose.onnx" \
    "--inputIOFormats=fp16:chw --outputIOFormats=fp16:chw"

# PP-OCRv4 - Text recognition (input: 1x3x48x320)
convert "ppocr_v4" \
    "$MODELS_DIR/ocr_model.onnx" \
    "--inputIOFormats=fp16:chw --outputIOFormats=fp16:chw"

echo ""
echo "=== Conversion complete ==="
echo "Engines:"
ls -lh "$OUTPUT_DIR"/*.engine 2>/dev/null || echo "  (none)"
