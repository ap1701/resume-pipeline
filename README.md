# Resume Tailoring Pipeline

This tool rewrites your resume for one specific job. It uses three agents:

- a **researcher** that looks up the company and the market,
- a **writer** that tailors the resume,
- a **senior recruiter** that judges the result.

The writer and the recruiter take turns until the recruiter would forward the resume to a hiring manager.

```
 resume + JD + company + role
            │
            ▼
 ┌──────────────────────┐   web search + web fetch (live, today's date)
 │ 1. Research agent    │── company careers page & recent postings, eng blog,
 └──────────┬───────────┘   funding/layoff news, market demand for the role
            ▼  01_research_report.md (with sources)
 ┌──────────────────────┐
 │ 2. Skills strategist │── ranks skills (JD / hiring history / market) and
 └──────────┬───────────┘   marks each one demonstrated / implied / missing
            ▼  02_skills_brief.json
 ┌──────────────────────┐        ┌──────────────────────────┐
 │ 3. Writer agent      │──────▶ │ style linter (no LLM):   │
 │    (tailors resume)  │        │ buzzwords, em dashes,    │
 └──────────▲───────────┘        │ repeated verbs, formulas │
            │ feedback           └────────────┬─────────────┘
 ┌──────────┴───────────┐                     │
 │ 4. Senior recruiter  │◀────────────────────┘
 │  score /100, rubric, │  loop until score ≥ target, with no fabrication
 │  fabrication check   │  and no must-fix issues (max N rounds)
 └──────────┬───────────┘
            ▼
 resume_final.docx · resume_final.md · REPORT.md · every draft and review
```

## How it keeps the resume honest and human

- **No fabrication.** The writer can only reword, reorder and cut what is already in your resume. Skills the strategist marks as `missing` go into a "skills to build" list and never into the resume. The recruiter checks every claim against your original resume and quotes anything it can't trace. A draft with any fabrication flag can't be chosen as the final version.
- **No obvious AI voice.** The writer works under explicit style rules: specific nouns, varied bullet structures, no stock buzzwords, no em dashes, and as much of your own phrasing as possible. A deterministic linter checks every draft for buzzwords, repeated opening verbs and formulaic "resulting in X%" bullets. Its findings go to both the recruiter and the writer.
- **Numbers aren't invented.** If a bullet would be stronger with a metric you didn't give, the writer adds a question to "Check these before you send" in `REPORT.md` instead of making one up.

## Setup

```bash
cd resume-pipeline
```

```bash
pip install -r requirements.txt
```

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

You need a Claude API key from https://platform.claude.com. Web search must be enabled for your organization in the Console. All agents use `claude-opus-5-5` by default. Server-side refusal fallback is turned on, so if a request is declined it is automatically retried on a fallback model.

## Run it

```bash
python -m resume_pipeline \
  --resume ~/Documents/my_resume.pdf \
  --jd https://careers.acme.com/jobs/1234 \
  --company "Acme Logistics" \
  --role "Senior Data Engineer" \
  --location "Bengaluru" \
  --notes "Keep it to one page. I want to move toward streaming work."
```

To try it with the bundled sample:

```bash
python -m resume_pipeline --resume examples/resume.md --jd examples/job_description.txt --company "Acme Logistics" --role "Senior Data Engineer"
```

| Flag | Meaning |
|---|---|
| `--resume` | `.pdf`, `.docx`, `.md` or `.txt` |
| `--jd` | A file, a URL, or pasted text |
| `--location` | Localizes the market research (optional) |
| `--notes` | Your own preferences for the writer |
| `--research old_run/01_research_report.md` | Reuse earlier research, for example when applying to a second role at the same company |
| `--target-score 85` | The recruiter score at which the loop stops |
| `--max-rounds 3` | The maximum number of writer/recruiter rounds |
| `--latex` | Also produce `resume_final.tex`, plus `resume_final.pdf` if `pdflatex` is installed |
| `--paper a4\|letter` | Paper size for the LaTeX output (default `a4`) |
| `--model` | Override the model |

Output goes to `output/<company>_<role>_<timestamp>/`:

| File | What it is |
|---|---|
| `resume_final.docx` / `.md` | The best draft (no fabrication flags, highest score) |
| `REPORT.md` | Recruiter verdict, rubric, items for you to verify, research summary, skill recommendations, ATS keywords, change log |
| `01_research_report.md` | The full research with source URLs |
| `02_skills_brief.json` | Structured skill and gap analysis |
| `03_resume_vN.md`, `04_review_vN.json` | Every draft and every recruiter review |

With `--latex` you also get `resume_final.tex`, plus `resume_final.pdf` when `pdflatex` is installed.

**Always read `REPORT.md` → "Check these before you send" before you submit.**

## LaTeX output (optional)

There are two ways to get LaTeX code for your resume.

**1. As part of a run.** Add `--latex`:

```bash
python -m resume_pipeline --resume my_resume.pdf --jd jd.txt --company "Acme" --role "Data Engineer" --latex
```

**2. From any resume Markdown file**, for example a final resume from an earlier run, or one you edited by hand:

```bash
python -m resume_pipeline.latex output/<run>/resume_final.md
```

```bash
python -m resume_pipeline.latex output/<run>/resume_final.md -o jane_doe.tex --pdf --paper letter
```

Both write a standalone `.tex` file that compiles with `pdflatex`. You can also upload it to [Overleaf](https://www.overleaf.com) (New Project → Upload Project) and edit it there.

- **Deterministic conversion.** The `.tex` is converted by code, with no extra Claude call, so it always matches the final resume word for word.
- **Special characters are escaped:** `C#`, `R&D`, `100%`, `$`, `_`, `{}`, accents, smart quotes and dashes.
- **Links work.** Emails, URLs and `[text](url)` links become clickable.
- **ATS-friendly PDF.** It uses a single column with no tables or icons. Unicode mapping is on, and "fi"/"fl" ligatures are off, so tracking systems read "Airflow" rather than "Airow".
- **Easy to restyle.** Change the accent color (`accent`), margins, or the `\resumeentry` macro at the top of the file.
- **Optional local PDF.** To build PDFs on your machine you need TeX Live. On Debian or Ubuntu that's `texlive-latex-base`, `texlive-latex-recommended`, `texlive-latex-extra` and `lmodern`. On macOS it's MacTeX. Without it you still get the `.tex` file.

## Tests

```bash
python -m pytest -q tests
```

The tests run the whole pipeline offline. They use the real Anthropic SDK against a mocked HTTP transport, so they need no API key.

## Code map

| File | Role |
|---|---|
| `resume_pipeline/agents.py` | The four agents, each a focused Claude call |
| `resume_pipeline/prompts.py` | System prompts; tune the writer's voice or the recruiter's strictness here |
| `resume_pipeline/models.py` | Pydantic schemas for the structured outputs passed between agents |
| `resume_pipeline/pipeline.py` | The orchestrator, the review loop, the outputs |
| `resume_pipeline/humanize.py` | The AI-tell linter; add phrases to `BUZZWORDS` |
| `resume_pipeline/llm.py` | SDK wrapper: streaming, `pause_turn` resume, refusal handling, prompt caching |
| `resume_pipeline/io_utils.py` | PDF/DOCX/URL loading and DOCX rendering |
| `resume_pipeline/latex.py` | Markdown → LaTeX converter and optional PDF build |
