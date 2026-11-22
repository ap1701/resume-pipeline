"""Offline end-to-end test.

Uses the real Anthropic SDK with an httpx MockTransport that replies with
canned SSE streams, so request construction, streaming, pause_turn handling
and structured-output parsing are all exercised without network or API key.
"""

import json
import sys
from pathlib import Path

import anthropic
import httpx2 as httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resume_pipeline.humanize import lint  # noqa: E402
from resume_pipeline.llm import LLM  # noqa: E402
from resume_pipeline.pipeline import PipelineConfig, run  # noqa: E402

EX = Path(__file__).resolve().parents[1] / "examples"


def sse(text: str, stop_reason: str = "end_turn") -> bytes:
    ev = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 0}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                           "usage": {"output_tokens": 50}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in ev).encode()


BRIEF = {
    "company_snapshot": "Acme builds logistics software.",
    "hiring_signals": [{"signal": "Growing data platform team", "evidence": "5 postings since Aug", "source_url": "https://example.com"}],
    "market_trends": ["dbt and streaming are table stakes"],
    "skills": [
        {"skill": "Airflow", "priority": "must_have", "driven_by": ["job_description"], "why": "core",
         "candidate_status": "demonstrated", "how_to_surface": "ETL bullet"},
        {"skill": "Kafka", "priority": "strong_plus", "driven_by": ["company_hiring_history", "market_trend"], "why": "streaming",
         "candidate_status": "missing", "how_to_surface": ""},
    ],
    "ats_keywords": ["data pipelines", "Airflow"],
    "culture_and_values_language": ["ownership"],
    "skills_to_learn": ["Kafka: build a small CDC project"],
    "positioning_strategy": "Lead with pipeline reliability.",
}


def draft(v: int) -> dict:
    return {
        "resume_markdown": f"# Jane Doe\njane@example.com\n## Experience\n### Data Engineer | Foo | 2020-Now\n- Built Airflow pipelines v{v}\n",
        "change_log": [{"section": "Experience", "before": "Wrote ETL", "after": "Built Airflow pipelines", "reason": "JD keyword"}],
        "keywords_worked_in": ["Airflow"],
        "needs_candidate_confirmation": [],
    }


def review(score: int, must_fix: bool) -> dict:
    issue = {"location": "Experience b1", "problem": "vague", "suggested_fix": "name the system"}
    return {
        "six_second_impression": "Solid data engineer.",
        "scores": {k: 8 for k in ["jd_alignment", "keyword_coverage", "impact_and_specificity",
                                  "readability_and_format", "human_voice", "truthfulness"]},
        "overall_score": score, "verdict": "shortlist" if score >= 85 else "maybe",
        "strengths": ["clear"], "must_fix": [issue] if must_fix else [], "nice_to_fix": [],
        "missing_keywords": [], "ai_tells": [], "fabrication_flags": [],
    }


def make_llm(captured: list) -> LLM:
    replies = iter([
        sse("partial research", "pause_turn"),            # research pauses once
        sse("# Research\nAcme is hiring."),                 # research resumes and finishes
        sse(json.dumps(BRIEF)),                             # strategist
        sse(json.dumps(draft(1))), sse(json.dumps(review(72, True))),
        sse(json.dumps(draft(2))), sse(json.dumps(review(88, False))),
    ])

    def handler(req: httpx.Request) -> httpx.Response:
        captured.append(json.loads(req.content))
        return httpx.Response(200, content=next(replies), headers={"content-type": "text/event-stream"})

    client = anthropic.Anthropic(api_key="test", base_url="http://mock",
                                 http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return LLM(client=client)


def test_end_to_end(tmp_path):
    captured: list = []
    cfg = PipelineConfig(company="Acme", role="Data Engineer", jd=(EX / "job_description.txt").read_text(),
                         resume=(EX / "resume.md").read_text(), out_dir=tmp_path, max_rounds=3,
                         latex=True)
    res = run(cfg, make_llm(captured))

    # loop stopped once the recruiter cleared the draft
    assert [r.review.overall_score for r in res.rounds] == [72, 88]
    assert res.best.n == 2
    for f in ["01_research_report.md", "02_skills_brief.json", "resume_final.docx", "resume_final.tex",
              "REPORT.md", "04_review_v1.json"]:
        assert (res.out_dir / f).exists(), f

    # request shapes
    research = captured[0]
    assert {t["type"] for t in research["tools"]} == {"web_search_20260209", "web_fetch_20260209"}
    assert research["fallbacks"] == "default" and research["model"] == "claude-opus-5-5"
    assert captured[1]["messages"][-1]["role"] == "assistant"  # pause_turn resumed with paused turn
    strat = captured[2]
    assert strat["output_config"]["effort"] == "high"
    assert strat["output_config"]["format"]["type"] == "json_schema"
    # revision round carries recruiter feedback to the writer
    assert "senior_recruiter_feedback" in captured[5]["messages"][0]["content"]


def test_lint_flags_ai_tells():
    rep = lint("- Spearheaded a robust platform — leveraging synergy, resulting in 40% growth\n"
               "- Spearheaded X, ensuring quality\n- Spearheaded Y, driving 20% uplift\n")
    f = " ".join(rep.findings())
    assert "spearheaded" in f and "em dash" in f and "same verb" in f
