"""The four agents. Each is a focused Claude call with its own system prompt."""

from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from . import prompts
from .humanize import LintReport
from .llm import LLM
from .models import RecruiterReview, ResearchBrief, TailoredResume


def _block(tag: str, body: str) -> str:
    return f"<{tag}>\n{body.strip()}\n</{tag}>"


def _context(*, company: str, role: str, jd: str, resume: str) -> str:
    # Stable prefix shared across calls so prompt caching can kick in.
    return "\n\n".join([
        f"Target company: {company}\nTarget role: {role}",
        _block("job_description", jd),
        _block("original_resume", resume),
    ])


# -------------------------------------------------------------- 1. research --

def research_agent(llm: LLM, *, company: str, role: str, jd: str, resume: str,
                   location: Optional[str] = None, max_searches: int = 12) -> str:
    """Web-researches the company's hiring history + today's market. Returns a Markdown report."""
    search_tool: dict = {"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}
    if location:
        search_tool["user_location"] = {"type": "approximate", "city": location}
    tools = [search_tool, {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8}]
    user = _context(company=company, role=role, jd=jd, resume=resume) + (
        "\n\nResearch this company and role and write the report. The resume is included only so "
        "you know the candidate's background; don't rewrite it."
    )
    return llm.run_with_tools(
        agent="researcher",
        system=prompts.RESEARCHER.format(today=dt.date.today().isoformat()),
        user=user, tools=tools, effort="high",
    )


# ------------------------------------------------------- 2. skills strategist --

def strategist_agent(llm: LLM, *, company: str, role: str, jd: str, resume: str,
                     research_report: str) -> ResearchBrief:
    """Turns the research into a structured skills brief + gap analysis against the resume."""
    user = _context(company=company, role=role, jd=jd, resume=resume) + "\n\n" + _block(
        "research_report", research_report
    )
    return llm.structured(agent="strategist", system=prompts.STRATEGIST, user=user,
                          schema=ResearchBrief, effort="high")


# ---------------------------------------------------------------- 3. writer --

def writer_agent(llm: LLM, *, company: str, role: str, jd: str, resume: str, brief: ResearchBrief,
                 previous: Optional[TailoredResume] = None, review: Optional[RecruiterReview] = None,
                 lint_report: Optional[LintReport] = None,
                 extra_instructions: str = "") -> TailoredResume:
    parts = [
        _context(company=company, role=role, jd=jd, resume=resume),
        _block("research_brief", brief.model_dump_json(indent=2)),
    ]
    if extra_instructions:
        parts.append(_block("candidate_preferences", extra_instructions))
    if previous and review:
        parts.append(_block("your_previous_draft", previous.resume_markdown))
        parts.append(_block("senior_recruiter_feedback", review.model_dump_json(indent=2)))
        if lint_report and lint_report.findings():
            parts.append(_block("automated_style_check", "\n".join(lint_report.findings())))
        parts.append("Revise your previous draft to address the feedback. Return the full revised resume.")
    else:
        parts.append("Write the tailored resume.")
    return llm.structured(agent="writer", system=prompts.WRITER, user="\n\n".join(parts),
                          schema=TailoredResume, effort="high")


# ------------------------------------------------------------- 4. recruiter --

def recruiter_agent(llm: LLM, *, company: str, role: str, jd: str, resume: str, brief: ResearchBrief,
                    draft: TailoredResume, lint_report: LintReport) -> RecruiterReview:
    parts = [
        _context(company=company, role=role, jd=jd, resume=resume),
        _block("research_brief", json.dumps({
            "skills": [s.model_dump() for s in brief.skills],
            "ats_keywords": brief.ats_keywords,
            "hiring_signals": [h.signal for h in brief.hiring_signals],
        }, indent=2)),
        _block("tailored_resume", draft.resume_markdown),
    ]
    if lint_report.findings():
        parts.append(_block("automated_style_check", "\n".join(lint_report.findings())))
    parts.append("Review the tailored resume.")
    return llm.structured(agent="recruiter", system=prompts.RECRUITER, user="\n\n".join(parts),
                          schema=RecruiterReview, effort="high")
