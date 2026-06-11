"""Métriques d'évaluation : matrice de confusion au niveau plaque et caractère."""
from __future__ import annotations


def normalize(text: str) -> str:
    return text.upper().replace(" ", "").strip()


def make_metrics_state() -> dict:
    return {
        # plaques
        "TP": 0, "TN": 0, "FP": 0, "FN": 0,
        # caractères
        "char_TP": 0,   # caractère correct à la bonne position
        "char_FP": 0,   # caractère détecté mais mauvais
        "char_FN": 0,   # caractère attendu mais manquant
        "results": [],
    }


def _char_confusion(gt: str, det: str) -> tuple:
    """Retourne (TP, FP, FN) au niveau caractère."""
    char_TP = sum(1 for i in range(min(len(gt), len(det))) if gt[i] == det[i])
    char_FP = sum(1 for i in range(min(len(gt), len(det))) if gt[i] != det[i])
    char_FN = max(0, len(gt) - len(det))   # caractères manquants
    return char_TP, char_FP, char_FN


def _classify(gt: str, det: str) -> str:
    """Classe une prédiction en TP / TN / FP / FN au niveau plaque."""
    has_gt = gt != ""
    has_det = det != ""
    if has_gt and has_det and gt == det:
        return "TP"
    if not has_gt and not has_det:
        return "TN"
    if has_det and gt != det:
        return "FP"
    return "FN"


def update_metrics(state: dict, ground_truth: str, detected: str) -> dict:
    """Ajoute un résultat aux métriques et affiche la ligne de progression."""
    gt = normalize(ground_truth)
    det = normalize(detected)

    case = _classify(gt, det)
    char_TP, char_FP, char_FN = _char_confusion(gt, det)

    new_state = {
        **state,
        case:      state[case] + 1,
        "char_TP": state["char_TP"] + char_TP,
        "char_FP": state["char_FP"] + char_FP,
        "char_FN": state["char_FN"] + char_FN,
        "results": state["results"] + [{
            "expected": gt, "detected": det, "case": case,
            "char_TP": char_TP, "char_FP": char_FP, "char_FN": char_FN,
        }],
    }

    TP, FP, FN = new_state["TP"], new_state["FP"], new_state["FN"]
    total = TP + FP + FN + new_state["TN"]
    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0

    icon = "OK   " if case == "TP" else case
    print(
        f"  {icon} [{total:5d}]  "
        f"expected={gt:<10}  detected={det:<10}  "
        f"P={precision:.2f}  R={recall:.2f}",
        flush=True,
    )
    return new_state


def print_summary(state: dict) -> None:
    """Affiche le bilan final (plaques et caractères)."""
    TP, TN = state["TP"], state["TN"]
    FP, FN = state["FP"], state["FN"]
    total = TP + TN + FP + FN

    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (TP + TN) / total * 100 if total > 0 else 0

    cTP, cFP, cFN = state["char_TP"], state["char_FP"], state["char_FN"]
    c_precision = cTP / (cTP + cFP) if (cTP + cFP) > 0 else 0
    c_recall = cTP / (cTP + cFN) if (cTP + cFN) > 0 else 0
    c_f1 = (2 * c_precision * c_recall / (c_precision + c_recall)
            if (c_precision + c_recall) > 0 else 0)
    c_accuracy = cTP / (cTP + cFP + cFN) * 100 if (cTP + cFP + cFN) > 0 else 0

    print("\n" + "═" * 55)
    print(f"  RÉSULTAT FINAL")
    print(f"\n  — PLAQUES —")
    print(f"  Total      : {total}")
    print(f"  TP={TP}  TN={TN}  FP={FP}  FN={FN}")
    print(f"  Accuracy   : {accuracy:.1f}%")
    print(f"  Precision  : {precision:.3f}")
    print(f"  Recall     : {recall:.3f}")
    print(f"  F1 score   : {f1:.3f}")
    print(f"\n  — CARACTÈRES —")
    print(f"  TP={cTP}  FP={cFP}  FN={cFN}")
    print(f"  Accuracy   : {c_accuracy:.1f}%")
    print(f"  Precision  : {c_precision:.3f}")
    print(f"  Recall     : {c_recall:.3f}")
    print(f"  F1 score   : {c_f1:.3f}")
    print("═" * 55)
