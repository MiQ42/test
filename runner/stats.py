"""Statistical analysis of the experiment results.

Reads results/scored/static.metrics.jsonl + static.judge.jsonl (joined by
response key) and produces:

  - per-cell summary (mean ± SD of each metric, broken down by model × stage × lang)
  - H1: Mann–Whitney U comparing S5/S6 vs S1 on the holisticness composite
  - H2: structural break detection over S0..S6 (segmented regression / CUSUM)
  - H3: S4 vs S5 comparison on derivative vs wavefield register;
        S6 ≥ max(S4, S5) on M6 holistic score
  - Inter-rater κ between primary and secondary judge passes (when both exist)

Outputs:
  results/scored/summary.csv           cell-level means
  results/scored/h1_h2_h3_results.json  hypothesis test results
  results/scored/transition.csv        per (model, lang) detected break stage
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner.loader import STAGES_ORDER  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCORED = ROOT / "results" / "scored"


# --- Light statistics implementations to avoid scipy dependency for the dry run ---


def mann_whitney_u(a: list[float], b: list[float]) -> tuple[float, float]:
    """Two-sided Mann-Whitney U with normal approximation. Returns (U, p)."""
    if not a or not b:
        return float("nan"), float("nan")
    combined = [(v, "a") for v in a] + [(v, "b") for v in b]
    combined.sort(key=lambda x: x[0])
    ranks: list[float] = [0.0] * len(combined)
    i = 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    rank_sum_a = sum(r for r, (_, g) in zip(ranks, combined) if g == "a")
    n_a = len(a)
    n_b = len(b)
    U_a = rank_sum_a - n_a * (n_a + 1) / 2
    U_b = n_a * n_b - U_a
    U = min(U_a, U_b)
    mean_U = n_a * n_b / 2
    sd_U = math.sqrt(n_a * n_b * (n_a + n_b + 1) / 12)
    if sd_U == 0:
        return U, float("nan")
    z = (U - mean_U) / sd_U
    # two-sided p from standard normal
    p = math.erfc(abs(z) / math.sqrt(2))
    return U, p


def cohen_kappa(rater_a: list[int], rater_b: list[int]) -> float:
    """Cohen's kappa for two raters with the same ordinal scale."""
    if len(rater_a) != len(rater_b) or not rater_a:
        return float("nan")
    cats = sorted(set(rater_a) | set(rater_b))
    n = len(rater_a)
    p_o = sum(1 for x, y in zip(rater_a, rater_b) if x == y) / n
    p_e = 0.0
    for c in cats:
        p_a = sum(1 for x in rater_a if x == c) / n
        p_b = sum(1 for x in rater_b if x == c) / n
        p_e += p_a * p_b
    if p_e == 1.0:
        return float("nan")
    return (p_o - p_e) / (1 - p_e)


def detect_break_point(values_by_stage: dict[str, float]) -> str | None:
    """Detect the stage Sk at which the largest jump from S(k-1) to Sk occurs.

    Simple but informative: returns the stage with the largest positive
    forward difference in the smoothed series. Returns None if values are
    monotonic-flat or the series is too short.
    """
    series = [(s, values_by_stage.get(s)) for s in STAGES_ORDER]
    series = [(s, v) for s, v in series if v is not None]
    if len(series) < 3:
        return None
    diffs = [
        (series[i][0], series[i][1] - series[i - 1][1])
        for i in range(1, len(series))
    ]
    diffs.sort(key=lambda x: x[1], reverse=True)
    if diffs[0][1] <= 0:
        return None
    return diffs[0][0]


# --- Loading ---


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def composite_holistic(rec: dict) -> float | None:
    """Mean of M1+M2+M3 densities (text metrics)."""
    m = rec.get("metrics") or {}
    parts = [
        m.get("cross_ref_density"),
        m.get("derivative_density"),
        m.get("integration_density"),
    ]
    parts = [p for p in parts if p is not None]
    if not parts:
        return None
    return sum(parts) / len(parts)


def m6_score(judge_rec: dict) -> float | None:
    h = judge_rec.get("holistic") if judge_rec else None
    if not h:
        return None
    keys_de = (
        "A_kontextbreite",
        "B_mehrperspektivitaet",
        "C_folgenketten_tiefe",
        "D_integrative_synthese",
    )
    keys_en = (
        "A_context_breadth",
        "B_multi_perspectivity",
        "C_consequence_depth",
        "D_integrative_synthesis",
    )
    keys = keys_de if "A_kontextbreite" in h else keys_en
    vals = [h.get(k) for k in keys]
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return None
    return sum(vals) / len(vals)


# --- Analysis ---


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--metrics",
        type=Path,
        default=SCORED / "static.metrics.jsonl",
    )
    parser.add_argument(
        "--judge",
        type=Path,
        default=SCORED / "static.judge.jsonl",
    )
    parser.add_argument("--out-dir", type=Path, default=SCORED)
    args = parser.parse_args()

    metrics_rows = load_jsonl(args.metrics)
    judge_rows = load_jsonl(args.judge)

    # Index judge rows by (model_size, stage, lang, question_id, repetition, judge_pass)
    judge_index: dict[tuple, dict] = {}
    for jr in judge_rows:
        key = (
            jr["model_size"],
            jr["stage"],
            jr["lang"],
            jr["question_id"],
            jr["repetition"],
            jr["judge_pass"],
        )
        judge_index[key] = jr

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Per-cell summary CSV
    cells: dict[tuple, list[dict]] = defaultdict(list)
    for r in metrics_rows:
        cells[(r["model_size"], r["lang"], r["stage"])].append(r)

    summary_path = args.out_dir / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "model_size",
                "lang",
                "stage",
                "n",
                "mean_word_count",
                "mean_cross_ref_density",
                "mean_derivative_density",
                "mean_integration_density",
                "mean_wavefield_density",
                "mean_composite",
                "mean_m6_holistic_primary",
            ]
        )
        for (model_size, lang, stage), rs in sorted(cells.items()):
            comps = [composite_holistic(r) for r in rs]
            comps = [c for c in comps if c is not None]
            m6_vals = []
            for r in rs:
                k = (
                    r["model_size"],
                    r["stage"],
                    r["lang"],
                    r["question_id"],
                    r["repetition"],
                    "primary",
                )
                jr = judge_index.get(k)
                v = m6_score(jr) if jr else None
                if v is not None:
                    m6_vals.append(v)

            def mean(xs):
                return statistics.fmean(xs) if xs else float("nan")

            w.writerow(
                [
                    model_size,
                    lang,
                    stage,
                    len(rs),
                    mean([r["metrics"]["word_count"] for r in rs]),
                    mean([r["metrics"]["cross_ref_density"] for r in rs]),
                    mean([r["metrics"]["derivative_density"] for r in rs]),
                    mean([r["metrics"]["integration_density"] for r in rs]),
                    mean([r["metrics"]["wavefield_density"] for r in rs]),
                    mean(comps),
                    mean(m6_vals),
                ]
            )
    print(f"summary → {summary_path}", file=sys.stderr)

    # 2) H1: Mann-Whitney on composite, S5 ∪ S6 vs S1 (per model × lang)
    h1_results = []
    for model_size in sorted({r["model_size"] for r in metrics_rows}):
        for lang in sorted({r["lang"] for r in metrics_rows}):
            s1 = [
                composite_holistic(r)
                for r in metrics_rows
                if r["model_size"] == model_size
                and r["lang"] == lang
                and r["stage"] == "S1"
            ]
            s56 = [
                composite_holistic(r)
                for r in metrics_rows
                if r["model_size"] == model_size
                and r["lang"] == lang
                and r["stage"] in ("S5", "S6")
            ]
            s1 = [v for v in s1 if v is not None]
            s56 = [v for v in s56 if v is not None]
            U, p = mann_whitney_u(s1, s56)
            h1_results.append(
                {
                    "model_size": model_size,
                    "lang": lang,
                    "n_S1": len(s1),
                    "n_S5_S6": len(s56),
                    "mean_S1": statistics.fmean(s1) if s1 else None,
                    "mean_S5_S6": statistics.fmean(s56) if s56 else None,
                    "U": U,
                    "p_two_sided": p,
                }
            )

    # 3) H2: detected break stage per model × lang
    transitions = []
    for model_size in sorted({r["model_size"] for r in metrics_rows}):
        for lang in sorted({r["lang"] for r in metrics_rows}):
            stage_means: dict[str, float] = {}
            for stage in STAGES_ORDER:
                vals = [
                    composite_holistic(r)
                    for r in metrics_rows
                    if r["model_size"] == model_size
                    and r["lang"] == lang
                    and r["stage"] == stage
                ]
                vals = [v for v in vals if v is not None]
                if vals:
                    stage_means[stage] = statistics.fmean(vals)
            break_stage = detect_break_point(stage_means)
            transitions.append(
                {
                    "model_size": model_size,
                    "lang": lang,
                    "stage_means": stage_means,
                    "break_stage": break_stage,
                }
            )

    transition_path = args.out_dir / "transition.csv"
    with transition_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model_size", "lang", "break_stage"] + STAGES_ORDER)
        for t in transitions:
            w.writerow(
                [t["model_size"], t["lang"], t["break_stage"]]
                + [t["stage_means"].get(s, "") for s in STAGES_ORDER]
            )
    print(f"transitions → {transition_path}", file=sys.stderr)

    # 4) H3: S4 vs S5 register (derivative vs wavefield) and S6 synergy
    h3_results = []
    for model_size in sorted({r["model_size"] for r in metrics_rows}):
        for lang in sorted({r["lang"] for r in metrics_rows}):
            s4 = [
                r
                for r in metrics_rows
                if r["model_size"] == model_size
                and r["lang"] == lang
                and r["stage"] == "S4"
            ]
            s5 = [
                r
                for r in metrics_rows
                if r["model_size"] == model_size
                and r["lang"] == lang
                and r["stage"] == "S5"
            ]
            s6 = [
                r
                for r in metrics_rows
                if r["model_size"] == model_size
                and r["lang"] == lang
                and r["stage"] == "S6"
            ]
            U_d, p_d = mann_whitney_u(
                [r["metrics"]["derivative_density"] for r in s4],
                [r["metrics"]["derivative_density"] for r in s5],
            )
            U_w, p_w = mann_whitney_u(
                [r["metrics"]["wavefield_density"] for r in s4],
                [r["metrics"]["wavefield_density"] for r in s5],
            )

            def m6_for(rows):
                vals = []
                for r in rows:
                    k = (
                        r["model_size"],
                        r["stage"],
                        r["lang"],
                        r["question_id"],
                        r["repetition"],
                        "primary",
                    )
                    jr = judge_index.get(k)
                    v = m6_score(jr) if jr else None
                    if v is not None:
                        vals.append(v)
                return vals

            m6_s4 = m6_for(s4)
            m6_s5 = m6_for(s5)
            m6_s6 = m6_for(s6)
            h3_results.append(
                {
                    "model_size": model_size,
                    "lang": lang,
                    "derivative_S4_vs_S5": {"U": U_d, "p": p_d},
                    "wavefield_S4_vs_S5": {"U": U_w, "p": p_w},
                    "m6_means": {
                        "S4": statistics.fmean(m6_s4) if m6_s4 else None,
                        "S5": statistics.fmean(m6_s5) if m6_s5 else None,
                        "S6": statistics.fmean(m6_s6) if m6_s6 else None,
                    },
                }
            )

    # 5) Inter-rater kappa where two passes exist
    kappa_results = []
    pairs: dict[tuple, dict[str, int]] = defaultdict(dict)
    for jr in judge_rows:
        key = (
            jr["model_size"],
            jr["stage"],
            jr["lang"],
            jr["question_id"],
            jr["repetition"],
        )
        score = m6_score(jr)
        if score is not None:
            pairs[key][jr["judge_pass"]] = round(score)
    a = []
    b = []
    for v in pairs.values():
        if "primary" in v and "secondary" in v:
            a.append(v["primary"])
            b.append(v["secondary"])
    kappa_results.append({"n": len(a), "kappa": cohen_kappa(a, b)})

    out = {
        "h1_existence_S1_vs_S5_S6": h1_results,
        "h2_transitions": transitions,
        "h3_register": h3_results,
        "inter_rater_kappa": kappa_results,
    }
    out_path = args.out_dir / "h1_h2_h3_results.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"hypothesis tests → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
