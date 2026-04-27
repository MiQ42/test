"""Blind LLM-as-judge scoring (M6 holistic rubric, M5 factual coverage).

Cross-judge rule: a response is never judged by the model that produced it.
The default mapping is:

    answer model    ->   judge model
    haiku           ->   sonnet
    sonnet          ->   opus
    opus            ->   sonnet

A second-pass judge (used for inter-rater reliability) shifts everyone one
step further. This keeps any single model from being both author and judge,
without requiring more than three models.

Reads scored/static.metrics.jsonl (or live.metrics.jsonl), produces
scored/<study>.judge.jsonl with one row per (response, judge_model, pass).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.loader import load_judge_rubric, load_questions  # noqa: E402
from runner.providers.claude import MODELS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCORED = ROOT / "results" / "scored"


PRIMARY_JUDGE = {"haiku": "sonnet", "sonnet": "opus", "opus": "sonnet"}
SECONDARY_JUDGE = {"haiku": "opus", "sonnet": "haiku", "opus": "haiku"}


# --- Prompts ---

HOLISTIC_USER_TEMPLATE = {
    "de": (
        "Frage:\n{question}\n\nAntwort (zu bewerten):\n{answer}\n\n"
        "Bewerte gemäß Rubrik und antworte nur mit dem JSON-Objekt."
    ),
    "en": (
        "Question:\n{question}\n\nAnswer (to be rated):\n{answer}\n\n"
        "Rate per the rubric and reply only with the JSON object."
    ),
}

FACTUAL_SYSTEM = {
    "de": (
        "Du bewertest, wie viele zentrale Sachfakten aus einer Liste die Antwort "
        "korrekt abdeckt. Zähle nur Fakten, die die Antwort tatsächlich nennt — "
        "nicht ähnliche oder verwandte. Antworte nur als JSON wie:\n"
        '{"covered": <int>, "total": <int>, "missing": [<string>, ...]}'
    ),
    "en": (
        "You judge how many key facts from a list an answer correctly covers. "
        "Count only facts that the answer actually states — not similar or "
        "related ones. Reply only as JSON like:\n"
        '{"covered": <int>, "total": <int>, "missing": [<string>, ...]}'
    ),
}

FACTUAL_USER_TEMPLATE = {
    "de": (
        "Goldstandard-Fakten:\n{gold}\n\nAntwort:\n{answer}\n\n"
        "Wie viele dieser Fakten deckt die Antwort? Antworte nur als JSON."
    ),
    "en": (
        "Gold-standard facts:\n{gold}\n\nAnswer:\n{answer}\n\n"
        "How many of these facts does the answer cover? Reply only as JSON."
    ),
}


# --- JSON extraction (tolerates markdown fences) ---

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> dict | None:
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# --- Judging primitives ---

def _question_lookup() -> dict:
    return {q["id"]: q for q in load_questions()}


def judge_holistic(
    *,
    judge_model_id: str,
    rubric: str,
    question_text: str,
    answer_text: str,
    lang: str,
    client: anthropic.Anthropic,
) -> dict | None:
    user = HOLISTIC_USER_TEMPLATE[lang].format(
        question=question_text, answer=answer_text
    )
    resp = client.messages.create(
        model=judge_model_id,
        max_tokens=512,
        thinking={"type": "disabled"},
        system=[
            {
                "type": "text",
                "text": rubric,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return extract_json(text)


def judge_factual(
    *,
    judge_model_id: str,
    gold: list[str],
    question_text: str,
    answer_text: str,
    lang: str,
    client: anthropic.Anthropic,
) -> dict | None:
    if not gold:
        return None
    user = FACTUAL_USER_TEMPLATE[lang].format(
        gold="\n".join(f"- {g}" for g in gold), answer=answer_text
    )
    resp = client.messages.create(
        model=judge_model_id,
        max_tokens=512,
        thinking={"type": "disabled"},
        system=FACTUAL_SYSTEM[lang],
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return extract_json(text)


# --- CLI ---

def already_done(path: Path) -> set[tuple]:
    if not path.exists():
        return set()
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        seen.add(
            (
                rec["model_size"],
                rec["stage"],
                rec["lang"],
                rec["question_id"],
                rec["repetition"],
                rec["judge_pass"],
            )
        )
    return seen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path, required=True, help="metrics-augmented JSONL"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--passes",
        nargs="+",
        default=["primary"],
        choices=["primary", "secondary"],
        help="which judge mappings to run",
    )
    parser.add_argument(
        "--factual-categories",
        nargs="+",
        default=["A_faktisch", "C_praktisch"],
        help="categories that have a gold list and should get M5 scoring",
    )
    args = parser.parse_args()

    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(2)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic()
    questions = _question_lookup()
    rubrics = {lang: load_judge_rubric(lang) for lang in ("de", "en")}
    done = already_done(args.output)

    started = time.monotonic()
    written = 0
    with args.output.open("a", encoding="utf-8") as fh:
        for line in args.input.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            for judge_pass in args.passes:
                mapping = PRIMARY_JUDGE if judge_pass == "primary" else SECONDARY_JUDGE
                judge_size = mapping[rec["model_size"]]
                judge_model_id = MODELS[judge_size]
                key = (
                    rec["model_size"],
                    rec["stage"],
                    rec["lang"],
                    rec["question_id"],
                    rec["repetition"],
                    judge_pass,
                )
                if key in done:
                    continue
                q = questions[rec["question_id"]]
                holistic = judge_holistic(
                    judge_model_id=judge_model_id,
                    rubric=rubrics[rec["lang"]],
                    question_text=q[rec["lang"]],
                    answer_text=rec["answer"],
                    lang=rec["lang"],
                    client=client,
                )
                factual = None
                if rec["category"] in args.factual_categories:
                    gold_key = f"gold_{rec['lang']}"
                    factual = judge_factual(
                        judge_model_id=judge_model_id,
                        gold=q.get(gold_key, []),
                        question_text=q[rec["lang"]],
                        answer_text=rec["answer"],
                        lang=rec["lang"],
                        client=client,
                    )
                out = {
                    **{
                        k: rec[k]
                        for k in (
                            "model_size",
                            "model_id",
                            "stage",
                            "lang",
                            "question_id",
                            "category",
                            "repetition",
                        )
                    },
                    "judge_pass": judge_pass,
                    "judge_model_size": judge_size,
                    "judge_model_id": judge_model_id,
                    "holistic": holistic,
                    "factual": factual,
                }
                fh.write(json.dumps(out, ensure_ascii=False) + "\n")
                fh.flush()
                written += 1
                if written % 25 == 0:
                    elapsed = time.monotonic() - started
                    print(
                        f"  {written} judgements written ({elapsed:.0f}s)",
                        file=sys.stderr,
                    )

    print(f"Done. {written} judgements appended to {args.output}.", file=sys.stderr)


if __name__ == "__main__":
    main()
