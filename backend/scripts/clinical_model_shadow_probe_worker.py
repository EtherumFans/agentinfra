"""Isolated stdlib-only worker for a data-only synthetic shadow model."""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _fail() -> int:
    print('{"passed":false,"schema_version":"icoder.synthetic-shadow-probe/v1"}')
    return 2


def main() -> int:
    if len(sys.argv) != 2:
        return _fail()
    try:
        raw = Path(sys.argv[1]).read_bytes()
        model = json.loads(raw.decode("utf-8"))
        if _canonical(model) != raw or set(model) != {
            "features", "labels", "schema_version", "test_vectors"
        }:
            return _fail()
        if model["schema_version"] != "icoder.synthetic-shadow-model/v1":
            return _fail()
        labels = model["labels"]
        features = model["features"]
        vectors = model["test_vectors"]
        if not isinstance(labels, list) or not isinstance(features, dict) or not isinstance(vectors, list):
            return _fail()
        passed = 0
        for vector in vectors:
            scores = {label: 0.0 for label in labels}
            for token in vector["tokens"]:
                for label, weight in features[token].items():
                    numeric = float(weight)
                    if not math.isfinite(numeric):
                        return _fail()
                    scores[label] += numeric
            predicted = min(labels, key=lambda label: (-scores[label], label))
            if predicted != vector["expected"]:
                return _fail()
            passed += 1
        report = {
            "schema_version": "icoder.synthetic-shadow-probe/v1",
            "passed": passed == len(vectors) and passed > 0,
            "test_vector_count": len(vectors),
            "test_vectors_passed": passed,
            "model_sha256": hashlib.sha256(raw).hexdigest(),
            "network_used": False,
            "patient_data_used": False,
            "predictions_emitted": False,
        }
        print(_canonical(report).decode("utf-8"), end="")
        return 0 if report["passed"] else 2
    except Exception:
        return _fail()


if __name__ == "__main__":
    raise SystemExit(main())
