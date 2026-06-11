"""Compare la sortie C++ (lapi_oracle) à l'oracle Python (src/make_oracle.py).

Tolérances : box exacte, polygone ±2 px (cast int après Kalman, écarts BLAS
possibles), score ±0.001 (arrondi 3 décimales), texte exact. Les masques
ne sont comparés que par leur forme (le sha256 n'existe que côté Python).

Usage : python tools/compare_oracle.py oracle/oracle_40frames.json cpp_oracle.json
"""
import json
import sys

POLYGON_TOL = 2.0
SCORE_TOL = 0.001


def compare(ref_path: str, got_path: str) -> int:
    ref = json.load(open(ref_path, encoding="utf-8"))
    got = json.load(open(got_path, encoding="utf-8"))
    errors = []

    if ref["n_frames"] != got["n_frames"]:
        errors.append(f"n_frames : {ref['n_frames']} != {got['n_frames']}")

    for fr_ref, fr_got in zip(ref["frames"], got["frames"]):
        f = fr_ref["frame"]
        dr, dg = fr_ref["detections"], fr_got["detections"]
        if len(dr) != len(dg):
            errors.append(f"frame {f} : {len(dr)} détections ref vs {len(dg)}")
            continue
        for i, (a, b) in enumerate(zip(dr, dg)):
            where = f"frame {f} det {i}"
            if a["class"] != b["class"]:
                errors.append(f"{where} : class {a['class']} != {b['class']}")
            if abs(a["score"] - b["score"]) > SCORE_TOL:
                errors.append(f"{where} : score {a['score']} != {b['score']}")
            if a["box"] != b["box"]:
                errors.append(f"{where} : box {a['box']} != {b['box']}")
            if a["text"] != b["text"]:
                errors.append(f"{where} : text {a['text']!r} != {b['text']!r}")
            if a.get("mask_shape") != b.get("mask_shape"):
                errors.append(f"{where} : mask_shape {a.get('mask_shape')} != {b.get('mask_shape')}")
            for j, (pa, pb) in enumerate(zip(a["polygon"], b["polygon"])):
                if abs(pa[0] - pb[0]) > POLYGON_TOL or abs(pa[1] - pb[1]) > POLYGON_TOL:
                    errors.append(f"{where} : polygon[{j}] {pa} != {pb}")

    if errors:
        print(f"ÉCHEC — {len(errors)} écart(s) :")
        for e in errors[:50]:
            print(" ", e)
        if len(errors) > 50:
            print(f"  ... et {len(errors) - 50} de plus")
        return 1
    print(f"OK — {ref['n_frames']} frames identiques (tolérances : "
          f"polygone ±{POLYGON_TOL} px, score ±{SCORE_TOL})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(compare(sys.argv[1], sys.argv[2]))
