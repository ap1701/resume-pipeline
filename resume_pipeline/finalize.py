"""Deterministic helpers for the Claude Code workflow (no API key needed).

    python -m resume_pipeline.finalize lint  output/<run>/03_resume_v1.md
    python -m resume_pipeline.finalize build output/<run>/resume_final.md [--paper letter] [--pdf]

`lint` prints AI-tell findings (one per line, nothing if clean).
`build` writes resume_final.docx and resume_final.tex next to the Markdown file.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .humanize import lint
from .io_utils import markdown_to_docx
from .latex import write_latex


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="python -m resume_pipeline.finalize")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_lint = sub.add_parser("lint", help="Print AI-tell findings for a resume Markdown file")
    p_lint.add_argument("markdown")
    p_build = sub.add_parser("build", help="Write .docx and .tex next to a resume Markdown file")
    p_build.add_argument("markdown")
    p_build.add_argument("--paper", choices=["a4", "letter"], default="a4")
    p_build.add_argument("--pdf", action="store_true", help="Also compile the .tex to PDF if pdflatex is installed")
    a = ap.parse_args(argv)

    src = Path(a.markdown)
    md = src.read_text(encoding="utf-8")
    if a.cmd == "lint":
        for finding in lint(md).findings():
            print(finding)
        return
    docx_path = markdown_to_docx(md, src.with_suffix(".docx"))
    tex_path = src.with_suffix(".tex")
    pdf = write_latex(md, tex_path, paper=f"{a.paper}paper", pdf=a.pdf)
    print(f"Word:  {docx_path}\nLaTeX: {tex_path}" + (f"\nPDF:   {pdf}" if pdf else ""))


if __name__ == "__main__":
    main()
