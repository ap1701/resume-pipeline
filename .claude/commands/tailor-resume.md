---
description: Tailor a resume to a job with live web research, a writer and a senior-recruiter review loop. No API key needed.
argument-hint: <resume file> <job description file or URL> "<Company>" "<Job title>" [--latex] [--rounds N]
---

Tailor the user's resume using the three subagents in `.claude/agents/`. Arguments: $ARGUMENTS

If the resume, job description, company or job title is missing from the arguments, ask for it in one message before starting. The resume can be .pdf, .docx, .md or .txt. The job description can be a file, a URL (fetch it) or pasted text. Defaults: 2 review rounds and a target score of 85.

## Steps

1. **Set up.** Create `output/<company>_<role>_<YYYYMMDD-HHMM>/` (lowercase, hyphens). Extract the resume to `00_original_resume.md` and the job description to `00_job_description.md`. For PDF or DOCX files, use `python -c "from resume_pipeline.io_utils import load_text; print(load_text('<path>'))"`. If `pip install -r requirements.txt` hasn't been run yet, run it first.
2. **Research.** Run the `resume-researcher` agent with the company, the role, both file paths and the output folder.
3. **Write, then review, in a loop.** For N = 1 up to the number of rounds:
   - Run `resume-writer`. Pass the original resume, the JD, `02_skills_brief.md`, and the output path `03_resume_vN.md`. From round 2 on, also pass the previous draft and `04_review_v(N-1).md`.
   - Run `senior-recruiter` on `03_resume_vN.md` and have it write `04_review_vN.md`.
   - Stop early if the score is at or above the target and there are no must-fix items and no fabrication flags.
4. **Pick the final draft.** Choose the highest-scoring draft with no fabrication flags and copy it to `resume_final.md`. Then run `python -m resume_pipeline.finalize build output/<run>/resume_final.md` (add `--pdf` if the user passed `--latex` and `pdflatex` is installed).
5. **Report.** Write `REPORT.md` with these sections: the recruiter's verdict and rubric; "Check before you send" (fabrication flags plus the writer's confirmation items); Top skills (with status); Skills to learn; ATS keywords; What changed; and the score for each round.

Reply with:
- the final score and verdict
- the "Check before you send" items
- the top 3 skills to learn
- the output folder path

Never let a skill marked missing, or an invented metric, into `resume_final.md`.
