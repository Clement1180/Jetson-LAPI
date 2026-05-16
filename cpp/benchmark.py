#!/usr/bin/env python3
"""
Benchmark: C++/TensorRT vs Python/ONNX pipeline.
Run on Jetson after building the C++ module and converting models.

Usage:
    python benchmark.py --image test.jpg --iterations 100
    python benchmark.py --video test.mp4 --max-frames 300
"""

import argparse
import sys
import time

import numpy as np

sys.path.insert(0, "..")


def benchmark_cpp(frame, iterations):
    """Benchmark C++/TensorRT pipeline."""
    try:
        import lapi_cpp
    except ImportError:
        print("[C++] Module not available, skipping")
        return None

    config = lapi_cpp.PipelineConfig()
    config.car_engine_path = "/opt/lapi/engines/yolov8s_car.engine"
    config.plate_engine_path = "/opt/lapi/engines/yolov8s_plate.engine"
    config.ocr_engine_path = "/opt/lapi/engines/ppocr_v4.engine"
    config.ocr_dict_path = "/opt/lapi/models/en_dict.txt"

    pipeline = lapi_cpp.Pipeline()
    if not pipeline.init(config):
        print("[C++] Init failed")
        return None

    # Warmup
    for _ in range(10):
        pipeline.process_frame(frame)

    # Benchmark
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        tracks = pipeline.process_frame(frame)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)

    return times


def benchmark_python(frame, iterations):
    """Benchmark Python/ONNX pipeline."""
    try:
        from python.src.core import init_inference_engines
        from python.src.pipeline import create_lapi_pipeline
    except ImportError:
        print("[Python] Import failed, trying relative")
        sys.path.insert(0, "../python")
        from src.core import init_inference_engines
        from src.pipeline import create_lapi_pipeline

    run_car, run_plate, run_ocr = init_inference_engines(
        "/opt/lapi/models/yolov8s.onnx",
        "/opt/lapi/models/yolov8s-pose.onnx",
        "/opt/lapi/models/ocr_model.onnx",
        "/opt/lapi/models/en_dict.txt",
    )
    pipeline = create_lapi_pipeline(run_car, run_plate, run_ocr)

    # Warmup
    for _ in range(10):
        pipeline(frame)

    # Benchmark
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        tracks = pipeline(frame)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000)

    return times


def print_stats(name, times):
    if times is None:
        print(f"  {name}: N/A")
        return
    arr = np.array(times)
    print(f"  {name}:")
    print(f"    Mean:   {arr.mean():.2f} ms")
    print(f"    Median: {np.median(arr):.2f} ms")
    print(f"    P95:    {np.percentile(arr, 95):.2f} ms")
    print(f"    P99:    {np.percentile(arr, 99):.2f} ms")
    print(f"    Min:    {arr.min():.2f} ms")
    print(f"    Max:    {arr.max():.2f} ms")
    print(f"    FPS:    {1000.0 / arr.mean():.1f}")


def main():
    parser = argparse.ArgumentParser(description="LAPI Pipeline Benchmark")
    parser.add_argument("--image", type=str, help="Test image path")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--cpp-only", action="store_true")
    parser.add_argument("--python-only", action="store_true")
    args = parser.parse_args()

    if args.image:
        import cv2
        frame = cv2.imread(args.image)
        if frame is None:
            print(f"Cannot read: {args.image}")
            sys.exit(1)
    else:
        frame = np.random.randint(0, 255, (args.height, args.width, 3), dtype=np.uint8)
        print(f"Using random frame {args.width}x{args.height}")

    print(f"\n=== LAPI Pipeline Benchmark ===")
    print(f"    Frame: {frame.shape[1]}x{frame.shape[0]}")
    print(f"    Iterations: {args.iterations}")
    print()

    cpp_times = None
    py_times = None

    if not args.python_only:
        cpp_times = benchmark_cpp(frame, args.iterations)

    if not args.cpp_only:
        py_times = benchmark_python(frame, args.iterations)

    print("\n=== Results ===")
    print_stats("C++/TensorRT", cpp_times)
    print_stats("Python/ONNX", py_times)

    if cpp_times and py_times:
        speedup = np.mean(py_times) / np.mean(cpp_times)
        print(f"\n  Speedup: {speedup:.1f}x")


if __name__ == "__main__":
    main()
