"""Apply text metrics (M1–M4, M7) to a raw JSONL of responses.

Reads results/raw/<study>.jsonl, writes results/scored/<study>.metrics.jsonl
with the original record plus a `metrics` field. Idempotent: re-running with
the same input/output simply re-derives the metrics deterministically.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner import metrics  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.input.open(encoding="utf-8") as src, args.output.open(
        "w", encoding="utf-8"
    ) as dst:
        for line in src:
            if not line.strip():
                continue
            rec = json.loads(line)
            m = metrics.compute(rec.get("answer", ""), rec.get("lang"))
            rec["metrics"] = asdict(m)
            dst.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1

    print(f"{written} rows scored → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
