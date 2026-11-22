"""Command-line entry point.

    python -m resume_pipeline --resume me.pdf --jd jd.txt --company "Acme" --role "Senior Data Engineer"
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .io_utils import load_text
from .llm import DEFAULT_MODEL, LLM, AgentError
from .pipeline import PipelineConfig, run


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="resume_pipeline", description="Tailor a resume to a job with research, writer and recruiter agents.")
    ap.add_argument("--resume", required=True, help="Path to your resume (.pdf, .docx, .md, .txt)")
    ap.add_argument("--jd", required=True, help="Job description: a file path, a URL, or pasted text")
    ap.add_argument("--company", required=True)
    ap.add_argument("--role", required=True, help="Job title as posted")
    ap.add_argument("--location", help="City, used to localise market research (optional)")
    ap.add_argument("--notes", default="", help="Your own preferences, e.g. 'keep it one page, emphasise ML work'")
    ap.add_argument("--research", help="Reuse a saved research report (.md) instead of re-researching")
    ap.add_argument("--target-score", type=int, default=85, help="Stop once the recruiter scores this or higher (default 85)")
    ap.add_argument("--max-rounds", type=int, default=3, help="Max writer/recruiter rounds (default 3)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--out", default="output", help="Output directory (default ./output)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(message)s")
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    cfg = PipelineConfig(
        company=a.company, role=a.role,
        jd=load_text(a.jd), resume=load_text(a.resume),
        out_dir=Path(a.out), target_score=a.target_score, max_rounds=a.max_rounds,
        location=a.location, extra_instructions=a.notes,
        research_report=Path(a.research).read_text() if a.research else None,
    )
    if len(cfg.resume) < 200:
        sys.exit("Resume text looks empty. If it's a scanned PDF, export it as .docx or .txt first.")

    llm = LLM(model=a.model)
    try:
        result = run(cfg, llm)
    except AgentError as e:
        sys.exit(f"Pipeline stopped: {e}")
    u = llm.usage
    print(f"\nFinal resume: {result.out_dir / 'resume_final.docx'}")
    print(f"Report:       {result.out_dir / 'REPORT.md'}")
    print(f"API calls: {u.calls}, input tokens: {u.input_tokens:,} (cached {u.cache_read_tokens:,}), output tokens: {u.output_tokens:,}")


if __name__ == "__main__":
    main()
