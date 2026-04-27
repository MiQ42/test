"""Load prompt stages and question corpus from disk."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
QUESTIONS = ROOT / "questions"


STAGE_FILENAMES = {
    "de": {
        "S0": "S0_null.md",
        "S1": "S1_punkt.md",
        "S2": "S2_lokal.md",
        "S3": "S3_uebergang_a.md",
        "S4": "S4_uebergang_b.md",
        "S5": "S5_wellenfeld_a.md",
        "S6": "S6_wellenfeld_b.md",
        "S5p": "S5p_kontrolle.md",
    },
    "en": {
        "S0": "S0_null.md",
        "S1": "S1_point.md",
        "S2": "S2_local.md",
        "S3": "S3_transition_a.md",
        "S4": "S4_transition_b.md",
        "S5": "S5_wavefield_a.md",
        "S6": "S6_wavefield_b.md",
        "S5p": "S5p_control.md",
    },
}

STAGES_ORDER = ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]
ALL_STAGES = STAGES_ORDER + ["S5p"]


def load_stage(stage: str, lang: str) -> str:
    path = PROMPTS / lang / STAGE_FILENAMES[lang][stage]
    return path.read_text(encoding="utf-8").strip()


def load_questions() -> list[dict]:
    """Returns a flat list of question dicts with category attached."""
    items = []
    for fname in ("A_faktisch.json", "B_konzeptuell.json", "C_praktisch.json"):
        data = json.loads((QUESTIONS / fname).read_text(encoding="utf-8"))
        for item in data["items"]:
            item = dict(item)
            item["category"] = data["category"]
            items.append(item)
    return items


def load_judge_rubric(lang: str) -> str:
    return (PROMPTS / f"judge_rubric.{lang}.md").read_text(encoding="utf-8").strip()
