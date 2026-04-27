# Michaelisch — Wellenfeld-Experiment

Empirischer Nachweis: Wird die Antwort eines LLM-Agenten *ganzheitlicher*, wenn
der System-Prompt sprachlich vom analytischen Punktraum in den Wellenraum
"umklappt" (Begriffe: *Ableitung, Aufleitung, Wellenfeld, Resonanz,
ganzheitlich*)?

Der vollständige Versuchsplan steht in
[`/root/.claude/plans/ich-habe-entdeckt-wenn-bubbly-clarke.md`](/root/.claude/plans/ich-habe-entdeckt-wenn-bubbly-clarke.md).

## Aufbau

```
prompts/
  de/   S0_null.md … S6_wellenfeld_b.md, S5p_kontrolle.md   (deutsche Stufen)
  en/   S0_null.md … S6_wavefield_b.md, S5p_control.md      (englische Stufen)
  judge_rubric.{de,en}.md
questions/
  A_faktisch.json   (3 Fakten-Fragen mit Goldstandard)
  B_konzeptuell.json (3 konzeptuelle Fragen, kein Gold)
  C_praktisch.json  (3 Beratungsfragen mit Faktorenliste)
runner/
  providers/claude.py   Anthropic-SDK-Adapter mit Prompt-Caching
  loader.py             Stufen + Fragen laden
  run_static.py         Studie 5a (zwischen Sitzungen)
  run_live.py           Studie 5b (innerhalb einer Sitzung, mit Hysterese-Test)
  score.py              M1–M4, M7 lexikalische Metriken
  judge.py              Blinde Cross-Modell-Bewertung (M5, M6)
  stats.py              H1/H2/H3-Tests, Übergangserkennung, κ
results/
  raw/      Rohantworten (JSONL)
  scored/   mit Metriken und Bewertungen angereichert
```

## Versuchsdesign in Kurzform

- **7 Stufen S0…S6** (plus Vokabel-Kontrolle S5'): vom Punktmodus zum
  vollständigen Wellenfeld-Modus, sprachlich abgestuft.
- **9 Fragen** in 3 Kategorien (Fakten / Konzept / Beratung), je in DE und EN.
- **3 Modelle** der Claude-Familie (Haiku 4.5, Sonnet 4.6, Opus 4.7) — testet
  Skaleneffekte innerhalb einer Familie.
- **n = 10 Wiederholungen** pro Zelle in der statischen Studie, **n = 2** in
  der Live-Studie (jede Live-Sitzung = 7 Turns).
- Rund **4 920 Antworten** für die Vollausführung.

## Kosten und Zeit

- API-Kosten geschätzt 50–150 USD für die Vollausführung. **Prompt-Caching auf
  dem System-Prompt** ist aktiviert; jede der 7 (+1) Stufen wird n × 9 × 2
  = 180 Mal pro Modell verwendet, sodass Stufen-Prompts nach dem ersten Aufruf
  als Cache-Read abgerechnet werden (~10 % der Schreibrate).
- Vor der Vollausführung **Pilot fahren**, um Kosten genau hochzurechnen.

## Reproduktion

```bash
# 1. Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...

# 2. Trockenlauf — eine Frage pro Kategorie, ein Modell, alle Stufen, beide Sprachen
python -m runner.run_static \
  --models haiku \
  --n 1 \
  --questions A1 B1 C1 \
  --max-tokens 2048

# 3. Pilot — Haiku auf allen Fragen, n=3
python -m runner.run_static --models haiku --n 3

# 4. Vollausführung statisch
python -m runner.run_static --n 10

# 5. Vollausführung live (Hysterese-Test)
python -m runner.run_live --n 2

# 6. Lexikalische Metriken berechnen
python -m runner.score \
  --input  results/raw/static.jsonl \
  --output results/scored/static.metrics.jsonl
python -m runner.score \
  --input  results/raw/live.jsonl \
  --output results/scored/live.metrics.jsonl

# 7. Blinde Cross-Modell-Bewertung
python -m runner.judge \
  --input  results/scored/static.metrics.jsonl \
  --output results/scored/static.judge.jsonl \
  --passes primary secondary

# 8. Hypothesen-Tests
python -m runner.stats
```

## Hypothesen

- **H1 (Existenz):** Antworten unter S5/S6 sind ganzheitlicher als unter S1
  (M1+M2+M3+M6 signifikant höher; Mann-Whitney, α = 0.01) bei kontrollierter
  Antwortlänge.
- **H2 (Übergang):** Der Wechsel ist **nichtlinear** — eine Strukturbruchanalyse
  über S0…S6 findet einen Sprung an einer bestimmten Stufe.
- **H3 (Begriffswirksamkeit):** S4 (mathematisch) und S5 (metaphorisch)
  unterscheiden sich im Register; S6 (kombiniert) übertrifft beide einzeln in
  M6.
- **H4 (Skalen-/Modellunabhängigkeit):** Der Effekt repliziert sich in
  mindestens 2 von 3 Modellgrößen.

## Sicherheits- und Validitätskontrollen

- **Cross-Judge:** Keine Antwort wird vom selben Modell bewertet, das sie
  erzeugt hat (vermeidet Selbst-Bias). Zweiter Judge-Pass für Inter-Rater-κ.
- **Vokabel-Kontrolle S5':** Gleiches Vokabular-*Volumen* wie S5, aber aus
  juristischer Domäne. Trennt Konzept- von Wortschatz-Effekt.
- **Fakten-Präzision M5:** Auf Kategorie A (Sachfragen) wird geprüft, dass die
  Wellenfeld-Modi keine Fakten verwässern.
- **Antwortlänge M4:** als Kontrollvariable; Effekte auf M1+M2+M3 dürfen nicht
  bloß Längenartefakte sein.
- **Idempotenz:** `run_static.py` und `run_live.py` überspringen bereits
  vorhandene Zellen — Neustarts nach Abbruch sind sicher.
- **Eingefrorene Rubrik:** Die Judge-Rubrik wird vor der Datenerhebung
  versionskontrolliert eingefroren, um p-hacking zu vermeiden.
