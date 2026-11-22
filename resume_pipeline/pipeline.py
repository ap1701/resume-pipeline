"""Orchestrator: research -> strategy -> (write -> lint -> review)* -> outputs."""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .agents import recruiter_agent, research_agent, strategist_agent, writer_agent
from .humanize import lint
from .io_utils import markdown_to_docx
from .latex import write_latex
from .llm import LLM
from .models import RecruiterReview, ResearchBrief, TailoredResume

log = logging.getLogger("resume_pipeline")


@dataclass
class PipelineConfig:
    company: str
    role: str
    jd: str
    resume: str
    out_dir: Path
    target_score: int = 85
    max_rounds: int = 3
    location: Optional[str] = None
    extra_instructions: str = ""
    research_report: Optional[str] = None  # reuse a previous run's research
    latex: bool = False          # also write resume_final.tex (+ PDF if pdflatex is installed)
    latex_paper: str = "a4paper"  # or "letterpaper"


@dataclass
class Round:
    n: int
    draft: TailoredResume
    review: RecruiterReview
    lint_findings: List[str]

    @property
    def passed(self) -> bool:
        return not self.review.fabrication_flags and not self.review.must_fix

    def rank(self) -> tuple:
        # Any fabrication disqualifies a draft; then prefer a higher recruiter score.
        return (not self.review.fabrication_flags, self.review.overall_score, -len(self.review.must_fix))


@dataclass
class PipelineResult:
    brief: ResearchBrief
    research_report: str
    rounds: List[Round] = field(default_factory=list)
    best: Optional[Round] = None
    out_dir: Optional[Path] = None


_LABELS = {
    "jd_alignment": "JD alignment", "keyword_coverage": "Keyword coverage",
    "impact_and_specificity": "Impact and specificity", "readability_and_format": "Readability and format",
    "human_voice": "Human voice", "truthfulness": "Truthfulness",
}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "x"


def run(cfg: PipelineConfig, llm: Optional[LLM] = None) -> PipelineResult:
    llm = llm or LLM()
    out = cfg.out_dir / f"{_slug(cfg.company)}_{_slug(cfg.role)}_{dt.datetime.now():%Y%m%d-%H%M}"
    out.mkdir(parents=True, exist_ok=True)
    ctx = dict(company=cfg.company, role=cfg.role, jd=cfg.jd, resume=cfg.resume)

    # 1. Research agent (web) --------------------------------------------------
    if cfg.research_report:
        log.info("[1/4] Using research report you supplied")
        report = cfg.research_report
    else:
        log.info("[1/4] Research agent: company hiring history and today's market…")
        report = research_agent(llm, location=cfg.location, **ctx)
    (out / "01_research_report.md").write_text(report)

    # 2. Strategist: structured skills brief + gap analysis --------------------
    log.info("[2/4] Strategist: skill recommendations and gap analysis…")
    brief = strategist_agent(llm, research_report=report, **ctx)
    (out / "02_skills_brief.json").write_text(brief.model_dump_json(indent=2))
    result = PipelineResult(brief=brief, research_report=report, out_dir=out)

    # 3+4. Writer <-> senior recruiter loop ------------------------------------
    draft: Optional[TailoredResume] = None
    review: Optional[RecruiterReview] = None
    lint_rep = None
    for n in range(1, cfg.max_rounds + 1):
        log.info("[3/4] Writer: draft %d…", n)
        draft = writer_agent(llm, brief=brief, previous=draft, review=review, lint_report=lint_rep,
                             extra_instructions=cfg.extra_instructions, **ctx)
        lint_rep = lint(draft.resume_markdown)
        log.info("[4/4] Senior recruiter: reviewing draft %d…", n)
        review = recruiter_agent(llm, brief=brief, draft=draft, lint_report=lint_rep, **ctx)

        rnd = Round(n=n, draft=draft, review=review, lint_findings=lint_rep.findings())
        result.rounds.append(rnd)
        (out / f"03_resume_v{n}.md").write_text(draft.resume_markdown)
        (out / f"04_review_v{n}.json").write_text(json.dumps({
            "review": review.model_dump(), "style_check": rnd.lint_findings,
            "change_log": [c.model_dump() for c in draft.change_log],
            "needs_candidate_confirmation": draft.needs_candidate_confirmation,
        }, indent=2))
        log.info("      score=%d verdict=%s must_fix=%d fabrication_flags=%d",
                 review.overall_score, review.verdict, len(review.must_fix), len(review.fabrication_flags))

        if review.overall_score >= cfg.target_score and rnd.passed:
            log.info("      Target reached.")
            break

    best = max(result.rounds, key=Round.rank)
    result.best = best
    (out / "resume_final.md").write_text(best.draft.resume_markdown)
    markdown_to_docx(best.draft.resume_markdown, out / "resume_final.docx")
    if cfg.latex:
        pdf = write_latex(best.draft.resume_markdown, out / "resume_final.tex", paper=cfg.latex_paper, pdf=True)
        log.info("LaTeX: resume_final.tex%s", " + resume_final.pdf" if pdf else " (no pdflatex found; open it in Overleaf)")
    (out / "REPORT.md").write_text(render_report(cfg, result))
    log.info("Done. Best draft: v%d (score %d). Output: %s", best.n, best.review.overall_score, out)
    return result


def render_report(cfg: PipelineConfig, r: PipelineResult) -> str:
    b, best = r.brief, r.best
    assert best is not None
    rv = best.review
    L: List[str] = [
        f"# Application pack: {cfg.role} at {cfg.company}",
        f"_Generated {dt.date.today():%B %d, %Y}. Final resume is draft v{best.n} of {len(r.rounds)}._",
        "",
        "## Recruiter verdict",
        f"**{rv.overall_score}/100, {rv.verdict.upper()}**. {rv.six_second_impression}",
        "",
        "| Rubric | Score |", "|---|---|",
        *[f"| {_LABELS.get(k, k)} | {v}/10 |" for k, v in rv.scores.model_dump().items()],
        "",
        "Score by round: " + " → ".join(f"v{x.n}: {x.review.overall_score}" for x in r.rounds),
        "",
    ]
    if rv.fabrication_flags:
        L += ["### ⚠️ Claims to remove or verify", *[f"- {f}" for f in rv.fabrication_flags], ""]
    if best.draft.needs_candidate_confirmation:
        L += ["### Check these before you send", *[f"- {x}" for x in best.draft.needs_candidate_confirmation], ""]
    if rv.must_fix or rv.nice_to_fix:
        L += ["### Remaining recruiter notes",
              *[f"- **{i.location}**: {i.problem} → _{i.suggested_fix}_" for i in rv.must_fix + rv.nice_to_fix], ""]

    L += ["## Company and market research", b.company_snapshot, "",
          "### Hiring signals", *[f"- **{h.signal}**: {h.evidence}" + (f" ([source]({h.source_url}))" if h.source_url else "")
                                  for h in b.hiring_signals], "",
          "### Market today", *[f"- {t}" for t in b.market_trends], "",
          "### Positioning strategy", b.positioning_strategy, "",
          "## Recommended skills",
          "| Skill | Priority | Driven by | You | Why |", "|---|---|---|---|---|",
          *[f"| {s.skill} | {s.priority.replace('_', ' ')} | {', '.join(d.replace('_', ' ') for d in s.driven_by)} "
            f"| {s.candidate_status} | {s.why} |" for s in b.skills], "",
          "### Skills to build", *[f"- {s}" for s in b.skills_to_learn], "",
          "### ATS keywords", ", ".join(b.ats_keywords), "",
          "## What changed in your resume",
          *[f"- **{c.section}**: {c.reason}" for c in best.draft.change_log], "",
          "Full research with sources: `01_research_report.md`."]
    return "\n".join(L) + "\n"
