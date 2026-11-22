"""LaTeX output: escaping, structure, and (if pdflatex is installed) a real compile."""

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resume_pipeline.latex import inline, markdown_to_latex, write_latex  # noqa: E402

EX = Path(__file__).resolve().parents[1] / "examples"

TRICKY = """# José Núñez-O'Brien
Bengaluru · jose_n@example.co.in · [LinkedIn](https://linkedin.com/in/jose-n)

## Experience
### Senior Engineer | Foo & Bar Pvt. Ltd. | 2019 – 2022
- Rewrote the {billing} service in C#; cut cost ~30% ($1.2M/yr), 100% uptime_target met.
- Used `code`, ^caret and back\\slash safely.
### Intern | Acme
- Short bullet.

## Skills
**Languages:** Python, C++
"""


def test_escaping():
    out = inline("C# & R&D: 100% of $5 for a_b {x} ~y ^z")
    for frag in [r"C\#", r"R\&D", r"100\%", r"\$5", r"a\_b", r"\{x\}", r"\textasciitilde{}y", r"\textasciicircum{}z"]:
        assert frag in out


def test_links_and_formatting():
    out = inline("**Bold** and *it* [site](https://x.dev/a_b) mail me@x.io")
    assert r"\textbf{Bold}" in out and r"\textit{it}" in out
    assert r"\href{https://x.dev/a_b}{site}" in out
    assert r"\href{mailto:me@x.io}" in out


def test_structure():
    tex = markdown_to_latex(TRICKY, paper="letterpaper")
    assert r"\usepackage[letterpaper" in tex
    assert tex.count(r"\begin{center}") == tex.count(r"\end{center}") == 1
    assert tex.count(r"\begin{itemize}") == tex.count(r"\end{itemize}") == 2
    assert r"\resumeentry{Senior Engineer}{Foo \& Bar Pvt. Ltd.}{2019 \textendash{} 2022}" in tex
    assert r"\resumeentry{Intern}{Acme}{}" in tex          # company under title, not in the date slot
    assert r"\section*{Skills}" in tex


@pytest.mark.skipif(not shutil.which("pdflatex"), reason="pdflatex not installed")
@pytest.mark.parametrize("md", [TRICKY, (EX / "resume.md").read_text()])
def test_compiles_and_text_is_extractable(tmp_path, md):
    from pypdf import PdfReader
    pdf = write_latex(md, tmp_path / "r.tex", pdf=True)
    assert pdf and pdf.exists()
    text = PdfReader(str(pdf)).pages[0].extract_text()
    assert "Experience" in text
    if "Airflow" in md:
        assert "Airflow" in text  # fi/fl ligatures disabled for ATS parsing
