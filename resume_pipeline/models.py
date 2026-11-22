"""Structured outputs exchanged between the agents.

Every agent except the web researcher returns one of these Pydantic models via
Claude structured outputs, so the orchestrator never has to scrape free text.
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- research ---

class HiringSignal(BaseModel):
    signal: str = Field(description="What the company's hiring activity shows, e.g. 'Opened 6 data-platform roles since August'.")
    evidence: str = Field(description="Concrete evidence behind the signal (posting titles, dates, blog posts, news).")
    source_url: str = Field(description="URL the evidence came from, or '' if it came from the job description.")


class SkillRecommendation(BaseModel):
    skill: str
    priority: Literal["must_have", "strong_plus", "nice_to_have"]
    driven_by: List[Literal["job_description", "company_hiring_history", "market_trend"]] = Field(
        description="Which inputs made this skill matter."
    )
    why: str = Field(description="One or two sentences on why this skill matters for THIS role at THIS company right now.")
    candidate_status: Literal["demonstrated", "implied", "missing"] = Field(
        description="demonstrated = clearly in the resume; implied = adjacent experience exists but isn't stated; missing = no evidence at all."
    )
    how_to_surface: str = Field(
        description="If demonstrated/implied: which existing resume experience to reword to show it. If missing: '' (never invent it)."
    )


class ResearchBrief(BaseModel):
    company_snapshot: str = Field(description="3-5 sentences: what the company does, stage/size, current direction.")
    hiring_signals: List[HiringSignal]
    market_trends: List[str] = Field(description="What the market for this role looks like today: in-demand skills, tooling shifts, seniority expectations.")
    skills: List[SkillRecommendation] = Field(description="Ranked most important first.")
    ats_keywords: List[str] = Field(description="Exact phrases an ATS or recruiter will search for, using the JD's own wording.")
    culture_and_values_language: List[str] = Field(description="Words/themes the company uses about itself that the resume can echo naturally.")
    skills_to_learn: List[str] = Field(description="Missing skills worth building before/while applying, each with a concrete suggestion (course, project, cert).")
    positioning_strategy: str = Field(description="One paragraph: how this candidate should position themselves for this role.")


# ------------------------------------------------------------------ writer ---

class ResumeChange(BaseModel):
    section: str
    before: str = Field(description="Original text ('' if newly added from existing facts elsewhere in the resume).")
    after: str
    reason: str = Field(description="Which JD requirement / research finding / recruiter note this change serves.")


class TailoredResume(BaseModel):
    resume_markdown: str = Field(
        description="The complete tailored resume in Markdown: '# Name', contact line, '## Section' headings, '- ' bullets, '### Role | Company | Dates' lines."
    )
    change_log: List[ResumeChange]
    keywords_worked_in: List[str]
    needs_candidate_confirmation: List[str] = Field(
        description="Anything you inferred that the candidate must verify before sending (e.g. a rounded metric, a tool implied but not named)."
    )


# --------------------------------------------------------------- recruiter ---

class RubricScores(BaseModel):
    jd_alignment: int = Field(description="0-10. Does the resume read like it was written for this role?")
    keyword_coverage: int = Field(description="0-10. Are the must-have terms present, in natural context?")
    impact_and_specificity: int = Field(description="0-10. Concrete outcomes, scope, numbers, named systems.")
    readability_and_format: int = Field(description="0-10. Skimmable in 6 seconds, consistent, right length.")
    human_voice: int = Field(description="0-10. 10 = reads like a sharp human wrote it; 0 = obvious AI boilerplate.")
    truthfulness: int = Field(description="0-10. 10 = every claim traceable to the original resume.")


class ReviewIssue(BaseModel):
    location: str = Field(description="Section and bullet/line the issue is in.")
    problem: str
    suggested_fix: str


class RecruiterReview(BaseModel):
    six_second_impression: str = Field(description="What a recruiter takes away from a 6-second skim.")
    scores: RubricScores
    overall_score: int = Field(description="0-100 holistic score for this role (not an average).")
    verdict: Literal["shortlist", "maybe", "reject"]
    strengths: List[str]
    must_fix: List[ReviewIssue] = Field(description="Issues that would cost an interview. Empty if none.")
    nice_to_fix: List[ReviewIssue]
    missing_keywords: List[str]
    ai_tells: List[str] = Field(description="Exact phrases that read as AI-generated or template-y.")
    fabrication_flags: List[str] = Field(
        description="Claims in the tailored resume that are NOT supported by the original resume. Quote them."
    )
