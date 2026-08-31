"""Build/evaluate a prediction packet through the unified 26-Agent platform."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.offline_evaluation import (  # noqa: E402
    DEFAULT_PACKS,
    DEFAULT_SUITE,
    build_reference_prediction_packet,
    evaluate_prediction_packet,
    validate_offline_report,
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packs-dir", type=Path, default=DEFAULT_PACKS)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--write-reference-packet", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.predictions and args.write_reference_packet:
        parser.error("choose predictions or write-reference-packet, not both")
    if args.predictions:
        packet = json.loads(args.predictions.read_text(encoding="utf-8"))
    else:
        packet = build_reference_prediction_packet(
            packs_dir=args.packs_dir.resolve(), suite_path=args.suite.resolve(),
        )
        if args.write_reference_packet:
            _write(args.write_reference_packet.resolve(), packet)
    report = evaluate_prediction_packet(
        packet, packs_dir=args.packs_dir.resolve(), suite_path=args.suite.resolve(),
    )
    validate_offline_report(report)
    _write(args.output.resolve(), report)
    print(
        f"offline evaluation: agents={report['agent_count']} "
        f"cases={report['case_count']} passed={report['passed_case_count']}"
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
