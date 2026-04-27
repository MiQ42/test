"""Static study (5a): each (model, stage, language) combination is a fresh
single-turn agent that answers all questions independently.

Output: one JSONL line per response in results/raw/static.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import anthropic

# Allow running as a script from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.loader import (  # noqa: E402
    ALL_STAGES,
    STAGES_ORDER,
    load_questions,
    load_stage,
)
from runner.providers.claude import MODELS, call_static  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "raw" / "static.jsonl"


def already_done(out_path: Path) -> set[tuple]:
    if not out_path.exists():
        return set()
    done = set()
    for line in out_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        done.add(
            (
                rec["model_size"],
                rec["stage"],
                rec["lang"],
                rec["question_id"],
                rec["repetition"],
            )
        )
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        default=["haiku", "sonnet", "opus"],
        choices=list(MODELS),
    )
    parser.add_argument(
        "--stages",
        nargs="+",
        default=ALL_STAGES,
        choices=ALL_STAGES,
    )
    parser.add_argument(
        "--langs", nargs="+", default=["de", "en"], choices=["de", "en"]
    )
    parser.add_argument("--n", type=int, default=10, help="repetitions per cell")
    parser.add_argument(
        "--questions", nargs="*", default=None, help="restrict to question ids"
    )
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    questions = load_questions()
    if args.questions:
        questions = [q for q in questions if q["id"] in set(args.questions)]
    if not questions:
        print("No questions selected.", file=sys.stderr)
        sys.exit(1)

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(2)

    client = anthropic.Anthropic()
    done = already_done(args.out)
    total = (
        len(args.models) * len(args.stages) * len(args.langs) * len(questions) * args.n
    )
    print(
        f"Plan: {total} responses ({len(args.models)} models × {len(args.stages)} stages "
        f"× {len(args.langs)} langs × {len(questions)} questions × {args.n} reps). "
        f"Already done: {len(done)}.",
        file=sys.stderr,
    )

    # Outer loops ordered to maximise prompt-cache hits: same (model, stage,
    # lang) → same cached system prompt → cheap reads on repetitions 2..n.
    written = 0
    started = time.monotonic()
    with args.out.open("a", encoding="utf-8") as fh:
        for model_size in args.models:
            model_id = MODELS[model_size]
            for stage in args.stages:
                for lang in args.langs:
                    system_prompt = load_stage(stage, lang)
                    for q in questions:
                        prompt_text = q[lang]
                        for rep in range(args.n):
                            key = (model_size, stage, lang, q["id"], rep)
                            if key in done:
                                continue
                            try:
                                reply = call_static(
                                    model=model_id,
                                    system_prompt=system_prompt,
                                    user_message=prompt_text,
                                    max_tokens=args.max_tokens,
                                    client=client,
                                )
                            except Exception as e:  # noqa: BLE001
                                print(
                                    f"ERROR {key}: {type(e).__name__}: {e}",
                                    file=sys.stderr,
                                )
                                continue
                            rec = {
                                "model_size": model_size,
                                "model_id": model_id,
                                "stage": stage,
                                "lang": lang,
                                "question_id": q["id"],
                                "category": q["category"],
                                "repetition": rep,
                                "user_message": prompt_text,
                                "answer": reply.text,
                                "stop_reason": reply.stop_reason,
                                "input_tokens": reply.input_tokens,
                                "output_tokens": reply.output_tokens,
                                "cache_creation_tokens": reply.cache_creation_tokens,
                                "cache_read_tokens": reply.cache_read_tokens,
                                "latency_s": reply.latency_s,
                            }
                            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            fh.flush()
                            written += 1
                            if written % 25 == 0:
                                elapsed = time.monotonic() - started
                                print(
                                    f"  {written} responses written "
                                    f"({elapsed:.0f}s elapsed)",
                                    file=sys.stderr,
                                )

    print(f"Done. {written} new responses appended to {args.out}.", file=sys.stderr)


def stage_order_index(stage: str) -> int:
    """Helper for downstream sort: S0..S6 then S5p."""
    if stage in STAGES_ORDER:
        return STAGES_ORDER.index(stage)
    return len(STAGES_ORDER)


if __name__ == "__main__":
    main()
