"""Mesure des temps d'exécution de chaque étape du pipeline (benchmark)."""
from __future__ import annotations

import numpy as np

# Étapes chronométrées par run_pipeline, dans l'ordre d'exécution
PIPELINE_STEPS = ["stabilization", "yolo_inference", "kalman_postproc", "ocr"]

_STEP_DISPLAY_NAMES = {
    "stabilization":   "Stabilisation",
    "yolo_inference":  "Inférence YOLO",
    "kalman_postproc": "Post-traitement",
    "ocr":             "OCR",
}


def make_pipeline_metrics() -> dict:
    """Initialise le dictionnaire de métriques pour le pipeline."""
    return {step: [] for step in PIPELINE_STEPS}


def update_pipeline_metrics(metrics: dict, times: dict) -> dict:
    """Ajoute les mesures de temps d'une frame."""
    for step in PIPELINE_STEPS:
        metrics[step].append(times[step])
    return metrics


def print_pipeline_metrics(metrics: dict) -> None:
    """Affiche les statistiques du pipeline en tableau LaTeX."""
    data = {}
    total_times = []

    for step in PIPELINE_STEPS:
        times_ms = np.array(metrics[step]) * 1000
        data[step] = {"mean": np.mean(times_ms), "stddev": np.std(times_ms)}
        total_times.extend(times_ms)

    total_avg = np.mean(total_times)

    print("\n" + "=" * 70)
    print("\\begin{table}[H]")
    print("\\centering")
    print("\\begin{tabular}{@{}lrrr@{}}")
    print("\\toprule")
    print("\\textbf{Étape} & \\textbf{Temps moyen} & \\textbf{Écart-type} & \\textbf{\\% total} \\\\")
    print("\\midrule")

    for step in PIPELINE_STEPS:
        mean = data[step]["mean"]
        stddev = data[step]["stddev"]
        percent = 100 * mean / total_avg if total_avg > 0 else 0
        print(f"{_STEP_DISPLAY_NAMES[step]:20s} & {mean:6.2f} ms & {stddev:6.2f} ms & {percent:5.1f}\\% \\\\")

    print("\\midrule")
    print(f"{'TOTAL':20s} & {total_avg:6.2f} ms & -- ms & 100.0\\% \\\\")
    print("\\bottomrule")
    print("\\end{tabular}")
    print("\\end{table}")
    print("=" * 70 + "\n")
