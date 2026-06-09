"""Build the iCoDer 201 fixture from ccl2026_train_gold.json.

Samples 201 cases from the CCL 2026 train set (1800 cases) using
random.Random(42) for reproducibility. Each sampled case is tagged
``source: "icoder_201_subset"`` and the wrapper records the seed so
that re-runs are byte-equal.

Output: tests/fixtures/icoder_201.json

The fixture is consumed by scripts/e2e_medcoder_validation.py via
``load_gold_cases`` (which handles the ``{"gold_cases": [...]}`` wrap)
and ``extract_gold_codes`` (which reads the flat CCL fields).

Usage:
  python scripts/build_icoder_201_fixture.py
  python scripts/build_icoder_201_fixture.py --input tests/fixtures/other.json --out /tmp/other_201.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

DEFAULT_INPUT = _BACKEND_ROOT / "tests" / "fixtures" / "ccl2026_train_gold.json"
DEFAULT_OUTPUT = _BACKEND_ROOT / "tests" / "fixtures" / "icoder_201.json"
DEFAULT_SAMPLE_SIZE = 201
DEFAULT_SEED = 42


def build_fixture(
    input_path: Path,
    output_path: Path,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Sample ``sample_size`` cases from ``input_path`` and write the iCoDer 201 fixture.

    Idempotent: re-running with the same args produces a byte-equal
    output because the sampling uses a deterministic RNG.
    """
    with open(input_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
    if not isinstance(cases, list):
        raise ValueError(f"Expected a JSON list in {input_path}, got {type(cases).__name__}")
    if len(cases) < sample_size:
        raise ValueError(
            f"Source has only {len(cases)} cases, can't sample {sample_size}"
        )

    rng = random.Random(seed)
    sampled = rng.sample(cases, sample_size)

    # Tag each case for provenance — downstream tooling can detect
    # this subset by checking ``case["source"] == "icoder_201_subset"``.
    for c in sampled:
        c["source"] = "icoder_201_subset"

    fixture = {
        "source": "icoder_201_subset",
        "sampled_at_seed": seed,
        "sampled_from": input_path.name,
        "n_cases": len(sampled),
        "gold_cases": sampled,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)

    return fixture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Source JSON list of cases.")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT, help="Output fixture path.")
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    fixture = build_fixture(args.input, args.output, args.sample_size, args.seed)
    print(f"Built iCoDer 201 fixture: {len(fixture['gold_cases'])} cases")
    print(f"  source:     {fixture['source']}")
    print(f"  seed:       {fixture['sampled_at_seed']}")
    print(f"  sampled_from: {fixture['sampled_from']}")
    print(f"  output:     {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
