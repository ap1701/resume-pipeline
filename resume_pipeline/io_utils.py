"""Load resumes / job descriptions and render the final resume to .docx."""

from __future__ import annotations

import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


# ------------------------------------------------------------------ loading --

def load_text(path_or_text: str) -> str:
    """Accept a file path (.pdf/.docx/.txt/.md), a URL, or raw text."""
    s = path_or_text.strip()
    if s.startswith(("http://", "https://")):
        return _fetch_url(s)
    p = Path(s).expanduser()
    if len(s) < 1024 and p.exists():
        suffix = p.suffix.lower()
        if suffix == ".pdf":
            from pypdf import PdfReader
            return "\n".join((page.extract_text() or "") for page in PdfReader(str(p)).pages).strip()
        if suffix == ".docx":
            import docx
            d = docx.Document(str(p))
            lines = [para.text for para in d.paragraphs]
            for table in d.tables:
                for row in table.rows:
                    lines.append(" | ".join(c.text for c in row.cells))
            return "\n".join(lines).strip()
        return p.read_text(encoding="utf-8", errors="replace").strip()
    return s


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "div", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (resume-pipeline)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        ctype = r.headers.get("content-type", "")
        body = r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    if "html" not in ctype:
        return body
    ex = _TextExtractor()
    ex.feed(body)
    text = re.sub(r"[ \t]+", " ", "".join(ex.parts))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


# ---------------------------------------------------------------- rendering --

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _add_runs(paragraph, text: str) -> None:
    pos = 0
    for m in _BOLD.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos:m.start()])
        paragraph.add_run(m.group(1)).bold = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def markdown_to_docx(markdown: str, out_path: Path) -> Path:
    """Render the writer's simple Markdown into a clean, ATS-friendly .docx."""
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, Inches

    d = docx.Document()
    for section in d.sections:
        section.top_margin = section.bottom_margin = Inches(0.6)
        section.left_margin = section.right_margin = Inches(0.7)
    normal = d.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(2)

    first_heading_done = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip() in ("---", "***"):
            continue
        s = line.strip()
        if s.startswith("# "):
            p = d.add_paragraph()
            r = p.add_run(s[2:].strip())
            r.bold, r.font.size = True, Pt(18)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            first_heading_done = True
        elif s.startswith("## "):
            p = d.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            r = p.add_run(s[3:].strip().upper())
            r.bold, r.font.size = True, Pt(11.5)
        elif s.startswith("### "):
            p = d.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            r = p.add_run(_BOLD.sub(r"\1", s[4:].strip()))
            r.bold = True
        elif s.startswith(("- ", "* ")):
            p = d.add_paragraph(style="List Bullet")
            _add_runs(p, s[2:].strip())
        else:
            p = d.add_paragraph()
            _add_runs(p, s)
            if first_heading_done and len(d.paragraphs) <= 3:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER  # contact line under the name
    d.save(str(out_path))
    return out_path
