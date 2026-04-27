"""Live study (5b): a single conversation per (model, lang, question, rep).

Each conversation walks the prompt ladder S1 → S2 → S3 → S4 → S5 → S6, then
returns to S1 to test for hysteresis. The same question is asked at each step,
but the *system prompt* changes between turns. Every round is recorded as one
JSONL line, with `turn_index` and `stage`.

Note: switching the system prompt across turns invalidates the prompt cache
(prefix change), so live runs cost more per response than static. We use a
smaller n (default 2) for that reason.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.loader import load_questions, load_stage  # noqa: E402
from runner.providers.claude import MODELS, call_with_history  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "raw" / "live.jsonl"

# S1 → S6 ladder, then back to S1 to probe hysteresis.
LIVE_LADDER = ["S1", "S2", "S3", "S4", "S5", "S6", "S1_return"]


def already_done(out_path: Path) -> set[tuple]:
    if not out_path.exists():
        return set()
    done = set()
    for line in out_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        done.add(
            (rec["model_size"], rec["lang"], rec["question_id"], rec["repetition"])
        )
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models", nargs="+", default=["haiku", "sonnet", "opus"], choices=list(MODELS)
    )
    parser.add_argument(
        "--langs", nargs="+", default=["de", "en"], choices=["de", "en"]
    )
    parser.add_argument("--n", type=int, default=2, help="conversations per cell")
    parser.add_argument("--questions", nargs="*", default=None)
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

    total_convs = len(args.models) * len(args.langs) * len(questions) * args.n
    print(
        f"Plan: {total_convs} live conversations × {len(LIVE_LADDER)} turns each. "
        f"Already done: {len(done)}.",
        file=sys.stderr,
    )

    written = 0
    started = time.monotonic()
    with args.out.open("a", encoding="utf-8") as fh:
        for model_size in args.models:
            model_id = MODELS[model_size]
            for lang in args.langs:
                for q in questions:
                    user_msg = q[lang]
                    for rep in range(args.n):
                        key = (model_size, lang, q["id"], rep)
                        if key in done:
                            continue
                        history: list[dict] = []
                        try:
                            for turn_index, stage_label in enumerate(LIVE_LADDER):
                                stage = (
                                    "S1" if stage_label == "S1_return" else stage_label
                                )
                                system_prompt = load_stage(stage, lang)
                                history.append({"role": "user", "content": user_msg})
                                reply = call_with_history(
                                    model=model_id,
                                    system_prompt=system_prompt,
                                    messages=history,
                                    max_tokens=args.max_tokens,
                                    client=client,
                                )
                                history.append(
                                    {"role": "assistant", "content": reply.text}
                                )
                                rec = {
                                    "model_size": model_size,
                                    "model_id": model_id,
                                    "lang": lang,
                                    "question_id": q["id"],
                                    "category": q["category"],
                                    "repetition": rep,
                                    "turn_index": turn_index,
                                    "stage": stage,
                                    "stage_label": stage_label,
                                    "user_message": user_msg,
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
                        except Exception as e:  # noqa: BLE001
                            print(
                                f"ERROR conversation {key}: {type(e).__name__}: {e}",
                                file=sys.stderr,
                            )
                            continue
                        elapsed = time.monotonic() - started
                        print(
                            f"  conversation {key} done; {written} turns written "
                            f"({elapsed:.0f}s elapsed)",
                            file=sys.stderr,
                        )

    print(f"Done. {written} new turns appended to {args.out}.", file=sys.stderr)


if __name__ == "__main__":
    main()
