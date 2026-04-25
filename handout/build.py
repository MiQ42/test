#!/usr/bin/env python3
"""Build the PDF handout from synthesis + prompt."""

import sys
from pathlib import Path
from weasyprint import HTML, CSS

ROOT = Path(__file__).parent
BUILD = ROOT / "build"

def read(p):
    return Path(p).read_text(encoding="utf-8")

def md_to_paragraphs(text, drop_first_heading=False):
    """Tiny markdown-ish renderer: paragraphs, **bold**, *italic*, ## H2, # H1."""
    import re
    out = []
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    first_h_dropped = False
    for b in blocks:
        if b.startswith("# ") and not first_h_dropped and drop_first_heading:
            first_h_dropped = True
            continue
        if b.startswith("### "):
            out.append(f"<h3>{b[4:].strip()}</h3>")
        elif b.startswith("## "):
            out.append(f"<h2>{b[3:].strip()}</h2>")
        elif b.startswith("# "):
            out.append(f"<h1>{b[2:].strip()}</h1>")
        elif b.startswith("---"):
            out.append('<hr class="break">')
        else:
            inner = b.replace("\n", " ")
            inner = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", inner)
            inner = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", inner)
            inner = re.sub(r"`([^`]+?)`", r"<code>\1</code>", inner)
            out.append(f"<p>{inner}</p>")
    return "\n".join(out)


WAVELET_SVG = """
<svg class="wavelet" viewBox="0 0 600 60" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">
  <path d="M 0 30
           Q 30 30 60 30
           C 90 30 105 8 120 30
           C 135 52 165 4 195 30
           C 225 56 255 4 285 30
           C 315 52 345 12 375 30
           C 405 44 435 22 465 30
           Q 510 30 540 30
           Q 575 30 600 30"
        fill="none" stroke="#555" stroke-width="0.6"/>
</svg>
"""

CSS_TEXT = r"""
@page {
  size: A4;
  margin: 22mm 18mm 22mm 22mm;
  @bottom-right {
    content: counter(page);
    font-family: "Bitstream Charter", serif;
    font-size: 8.5pt;
    color: #888;
  }
  @bottom-left {
    content: "Invarianten · Triangulation · Apr 2026";
    font-family: "Bitstream Charter", serif;
    font-size: 8pt;
    color: #aaa;
    font-style: italic;
  }
}

@page :first {
  margin: 30mm 18mm 30mm 22mm;
  @bottom-left { content: ""; }
  @bottom-right { content: ""; }
}

html { font-size: 10.5pt; }

body {
  font-family: "Bitstream Charter", "Charter", Georgia, serif;
  color: #1a1a1a;
  line-height: 1.55;
  hyphens: auto;
  text-align: justify;
  font-feature-settings: "kern", "liga", "onum";
}

h1, h2, h3 {
  font-family: "Bitstream Charter", serif;
  font-weight: normal;
  letter-spacing: 0.01em;
}

h1 {
  font-size: 22pt;
  font-weight: bold;
  margin: 0 0 6pt 0;
  line-height: 1.15;
}

h2 {
  font-size: 13pt;
  font-style: italic;
  color: #333;
  margin: 18pt 0 6pt 0;
  page-break-after: avoid;
}

h3 {
  font-size: 11pt;
  font-weight: bold;
  margin: 12pt 0 3pt 0;
  page-break-after: avoid;
}

p {
  margin: 0 0 6pt 0;
  text-indent: 0;
  orphans: 3;
  widows: 3;
}

p + p { text-indent: 1.4em; }
h1 + p, h2 + p, h3 + p, hr + p { text-indent: 0; }

em { font-style: italic; }
strong { font-weight: bold; }

code {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 0.88em;
  color: #444;
}

hr.break {
  border: none;
  height: 8pt;
  margin: 10pt 0;
  background: none;
  position: relative;
}
hr.break::after {
  content: "✶";
  display: block;
  text-align: center;
  color: #888;
  font-size: 8pt;
  letter-spacing: 0.5em;
}

/* WAVELET MOTIF */
.wavelet {
  display: block;
  width: 100%;
  height: 18pt;
  margin: 4pt 0 14pt 0;
  opacity: 0.7;
}

.wavelet-mini {
  width: 60pt;
  height: 12pt;
  display: inline-block;
  vertical-align: middle;
  opacity: 0.55;
}

/* COVER */
.cover {
  page-break-after: always;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.cover .top {
  font-family: "Bitstream Charter", serif;
  font-size: 9pt;
  color: #888;
  letter-spacing: 0.15em;
  text-transform: uppercase;
}

.cover .title-block {
  margin-top: 14mm;
}

.cover .title {
  font-size: 30pt;
  line-height: 1.05;
  font-weight: bold;
  margin: 0 0 8pt 0;
  max-width: 80%;
}

.cover .subtitle {
  font-size: 13pt;
  font-style: italic;
  color: #444;
  max-width: 70%;
  line-height: 1.35;
  margin: 0;
}

.cover .colophon {
  font-size: 9pt;
  color: #666;
  font-style: italic;
  border-top: 0.4pt solid #aaa;
  padding-top: 6pt;
  max-width: 60%;
  line-height: 1.4;
}

.cover .meta {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 7.5pt;
  color: #888;
  letter-spacing: 0.05em;
  margin-top: 4pt;
}

/* SECTIONS */
section {
  page-break-before: always;
}

section.no-break-before {
  page-break-before: auto;
}

.section-tag {
  font-family: "Bitstream Charter", serif;
  font-size: 8pt;
  color: #888;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  margin: 0 0 4pt 0;
}

/* PROMPT BLOCK */
.prompt-block {
  font-family: "Bitstream Charter", serif;
  font-size: 9.8pt;
  line-height: 1.5;
  color: #2a2a2a;
  background: #f6f4ee;
  padding: 14pt 18pt 12pt 18pt;
  border-left: 1pt solid #aaa;
  margin: 8pt 0;
  text-align: left;
  hyphens: auto;
}

.prompt-block p {
  margin: 0 0 5pt 0;
  text-indent: 0;
}

.prompt-block p + p { text-indent: 1.2em; }

/* MARGINALIA / SIDENOTES — these are the "wavelet tails" */
.marg {
  float: right;
  clear: right;
  width: 32mm;
  margin-right: -38mm;
  margin-top: 0;
  margin-bottom: 6pt;
  font-family: "Bitstream Charter", serif;
  font-size: 8pt;
  font-style: italic;
  line-height: 1.35;
  color: #777;
  text-align: left;
  text-indent: 0;
  hyphens: auto;
}

.marg .term {
  font-style: normal;
  font-family: "WenQuanYi Zen Hei", "Bitstream Charter", serif;
  color: #555;
  letter-spacing: 0.05em;
}

.marg .math {
  font-family: "DejaVu Sans Mono", monospace;
  font-style: normal;
  font-size: 7.5pt;
  color: #555;
  display: block;
  margin-top: 2pt;
}

/* SYNTHESIS HEADINGS */
.synthesis h1 {
  font-size: 18pt;
  margin-top: 0;
}

/* CODA */
.coda {
  font-size: 9.5pt;
  color: #2a2a2a;
}

.coda h1 {
  font-size: 14pt;
}

/* TABLE OF AGENTS */
.agents-table {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 8pt;
  color: #555;
  line-height: 1.7;
  margin-top: 6pt;
}

/* small drop cap on first paragraph of synthesis */
.synthesis > p.lead::first-letter {
  font-size: 26pt;
  float: left;
  line-height: 0.95;
  padding: 2pt 4pt 0 0;
  font-weight: bold;
  color: #222;
}
"""


def render(synthesis_html, prompt_html, agents_meta, erkenntnis_html):
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Invarianten des Lebendigen — Triangulation</title>
<style>{CSS_TEXT}</style>
</head>
<body>

<!-- COVER -->
<div class="cover">
  <div>
    <div class="top">Triangulation · 15 Stimmen · Eine Synthese</div>
    {WAVELET_SVG}
    <div class="title-block">
      <h1 class="title">Invarianten des Lebendigen</h1>
      <p class="subtitle">Was bleibt, wenn man fünfzehn voneinander unabhängige Antworten<br>auf dieselbe Frage übereinanderlegt.</p>
    </div>
  </div>
  <div>
    {WAVELET_SVG}
    <div class="colophon">
      Ein Handout zum Weitergeben. Ausgangspunkt war ein Versuch:
      eine Frage nicht an ein Modell, sondern an drei Modelle in je fünf
      Ausführungen zu stellen — Haiku, Sonnet, Opus — und zu sehen, wo die
      fünfzehn Antworten konvergieren und wo sie auseinanderdriften.
      Die Konvergenz misst nicht die Wahrheit. Sie misst den Anteil der
      Sache am Denken.
      <div class="meta">n = 15 · Modelle: claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-7 · Synthese: opus</div>
    </div>
  </div>
</div>

<!-- INTRO / ERKENNTNIS -->
<section class="intro">
  <p class="section-tag">Worum es geht</p>
  {erkenntnis_html}
</section>

<!-- THE PROMPT -->
<section class="prompt-section">
  <p class="section-tag">Der Prompt</p>
  <h1 style="font-size:18pt;margin-top:0;">Die Frage, die fünfzehn mal gestellt wurde</h1>
  <p style="font-size:9.5pt;color:#555;margin-bottom:10pt;font-style:italic;">
    Identisch an alle fünfzehn Instanzen verschickt. Keine Anleitung zu Themen,
    keine Vorgabe von Traditionen über die unten genannten hinaus, kein Beispiel.
  </p>
  <div class="prompt-block">
    {prompt_html}
  </div>
</section>

<!-- SYNTHESIS -->
<section class="synthesis">
  <p class="section-tag">Die verdichtete Antwort</p>
  {synthesis_html}
</section>

<!-- CODA -->
<section class="coda">
  <p class="section-tag">Methodische Notiz</p>
  <h1>Wie das hier zustande kam</h1>

  <p>Fünfzehn Anfragen, identischer Prompt, drei verschiedene Modelle in je fünf Instanzen. Jede Instanz hat ihre Antwort selbständig formuliert, ohne Kenntnis der anderen vierzehn. Eine sechzehnte Instanz (Opus) hat die fünfzehn gelesen und nach Schnittmengen, Reduktionsverdacht und Cringe-Grenzen-Verletzungen geordnet.</p>

  <p>Die Konvergenz ist real und sie ist überprüfbar — die fünfzehn Einzelantworten liegen als Quelldateien neben diesem PDF. Sie beweist nichts über die Natur des Lebendigen. Sie ist eine schwache, aber nicht-triviale Evidenz dafür, dass bestimmte Strukturen weniger Variation in den Beschreibungen zulassen als andere; und das bestimmen vermutlich Randbedingungen der Sache, nicht Vorlieben einer Tradition.</p>

  <div class="agents-table">{agents_meta}</div>

  <p style="margin-top:12pt;font-size:9pt;color:#666;font-style:italic;">
    Quellen, ungeschnitten, in einer einzigen Datei nebeneinander gestellt:
    <code>handout/answers/answer_*.md</code>. Wer die Triangulation selbst nachzeichnen will, beginnt dort.
  </p>

  {WAVELET_SVG}
</section>

</body>
</html>
"""


def main():
    synth_path = ROOT / "synthesis.md"
    erkenntnis_path = ROOT / "erkenntnis.md"
    prompt_path = ROOT / "prompt.md"

    synthesis_html = md_to_paragraphs(read(synth_path), drop_first_heading=False)
    erkenntnis_html = md_to_paragraphs(read(erkenntnis_path), drop_first_heading=False)
    prompt_html = md_to_paragraphs(read(prompt_path))

    answers = sorted((ROOT / "answers").glob("answer_*.md"))
    rows = []
    for a in answers:
        size = a.stat().st_size
        name = a.stem.replace("answer_", "")
        rows.append(f"  {name:<14} · {size:>6} bytes")
    agents_meta = "<br>".join(rows)

    out_html = BUILD / "handout.html"
    out_pdf = ROOT / "Invarianten_des_Lebendigen.pdf"

    html_text = render(synthesis_html, prompt_html, agents_meta, erkenntnis_html)
    out_html.write_text(html_text, encoding="utf-8")

    HTML(string=html_text, base_url=str(ROOT)).write_pdf(str(out_pdf))
    print(f"Wrote {out_pdf} ({out_pdf.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
