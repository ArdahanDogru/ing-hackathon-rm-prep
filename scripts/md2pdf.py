"""Render the deliverables (docs/teslim/*.md) to PDF: Markdown -> HTML (with
Mermaid diagrams) -> headless Chrome "print to PDF".

Usage (from prototype/):
    python scripts/md2pdf.py                      # all docs/teslim/*.md -> docs/teslim/pdf/
    python scripts/md2pdf.py docs/teslim/01-problem-tanimi.md

Needs the `markdown` package (not a project dependency; e.g.
`pip install --target <dir> markdown` and PYTHONPATH=<dir>) and Google Chrome.
Mermaid is loaded from its CDN while Chrome renders the page.
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "teslim"
OUT = SRC / "pdf"
CHROME = Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe")
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
body { font-family: Inter, "Segoe UI", Arial, sans-serif; color: #1D2440; font-size: 10.5pt; line-height: 1.5; }
h1 { font-size: 20pt; border-bottom: 3px solid #FF6200; padding-bottom: 6px; margin: 0 0 12px; }
h2 { font-size: 14pt; margin: 20px 0 8px; color: #1D2440; }
h3 { font-size: 12pt; margin: 16px 0 6px; }
blockquote { margin: 0 0 14px; padding: 8px 12px; background: #F5F7FA; border-left: 3px solid #4676BF; color: #475467; font-size: 9.5pt; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 14px; font-size: 9pt; page-break-inside: auto; }
th, td { border: 1px solid #D0D5DD; padding: 4px 6px; vertical-align: top; text-align: left; }
th { background: #F2F4F7; }
tr { page-break-inside: avoid; }
code { font-family: Consolas, monospace; font-size: 8.8pt; background: #F2F4F7; padding: 0 3px; border-radius: 3px; word-break: break-all; }
pre { background: #F5F7FA; padding: 8px; font-size: 8.5pt; white-space: pre-wrap; }
.mermaid { text-align: center; margin: 10px 0; page-break-inside: avoid; }
.footer { margin-top: 24px; font-size: 8pt; color: #98A2B3; border-top: 1px solid #E4E7EC; padding-top: 6px; }
"""

# A file with this mark gets a smaller font and margins (deliverable 2 must fit one page).
COMPACT_MARK = "<!-- pdf: compact -->"
COMPACT_CSS = """
@page { margin: 12mm 13mm 12mm 13mm; }
body { font-size: 9.6pt; line-height: 1.38; }
h1 { font-size: 17pt; margin: 0 0 8px; }
h2 { font-size: 12pt; margin: 12px 0 5px; }
blockquote { margin: 0 0 8px; padding: 5px 10px; font-size: 8.6pt; }
table { margin: 5px 0 8px; font-size: 8.6pt; }
th, td { padding: 3px 5px; }
ul, ol { margin: 4px 0; }
.footer { margin-top: 10px; }
"""

FENCE = re.compile(r"```mermaid\n(.*?)```", re.S)


def to_html(md_text: str, title: str) -> str:
    diagrams: list[str] = []

    def keep(m: re.Match) -> str:
        diagrams.append(m.group(1))
        return f"\n\nMERMAID_{len(diagrams) - 1}\n\n"

    body = markdown.markdown(FENCE.sub(keep, md_text), extensions=["tables", "fenced_code", "sane_lists"])
    for i, code in enumerate(diagrams):
        body = body.replace(f"<p>MERMAID_{i}</p>", f'<pre class="mermaid">{html.escape(code)}</pre>')
    return f"""<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{CSS}{COMPACT_CSS if COMPACT_MARK in md_text else ""}</style><script src="{MERMAID}"></script></head><body>{body}
<div class="footer">ING Agentic AI Hackathon · RM görüşme hazırlığı · {html.escape(title)}</div>
<script>mermaid.initialize({{startOnLoad: true, theme: "neutral", flowchart: {{useMaxWidth: true}}}});</script>
</body></html>"""


def render(md_path: Path) -> Path:
    OUT.mkdir(exist_ok=True)
    text = md_path.read_text(encoding="utf-8")
    title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), md_path.stem)
    pdf = OUT / f"{md_path.stem}.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / f"{md_path.stem}.html"
        page.write_text(to_html(text, title), encoding="utf-8")
        subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=15000", f"--user-data-dir={Path(tmp) / 'chrome'}",
                        f"--print-to-pdf={pdf}", page.as_uri()], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return pdf


def main(argv: list[str]) -> int:
    files = [Path(a).resolve() for a in argv] or sorted(SRC.glob("*.md"))
    for f in files:
        print(render(f))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
