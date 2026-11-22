"""Deterministic 'AI tell' linter.

A cheap, model-free check run on every draft. Its findings go to both the
recruiter (as evidence) and the writer (as must-address items), so the
human-voice requirement doesn't depend only on model judgment.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List

BUZZWORDS = [
    "spearheaded", "leveraged", "leveraging", "utilized", "utilizing", "orchestrated",
    "synergy", "synergies", "dynamic", "results-driven", "passionate", "cutting-edge",
    "seamless", "seamlessly", "robust", "innovative", "transformative", "proven track record",
    "fast-paced", "a testament to", "delve", "showcase", "showcasing", "foster", "fostering",
    "pivotal", "meticulous", "meticulously", "adept", "game-changer", "best-in-class",
    "world-class", "detail-oriented", "go-getter", "thought leader", "holistic",
    "strategic thinker", "self-starter", "team player", "drove synergies", "empower",
    "revolutionized", "harnessed", "navigated the complexities",
]

_word = re.compile(r"[A-Za-z][A-Za-z\-']+")


@dataclass
class LintReport:
    buzzwords: List[str] = field(default_factory=list)
    em_dashes: int = 0
    repeated_openers: List[str] = field(default_factory=list)
    trailing_ing_bullets: int = 0
    formulaic_ratio: float = 0.0
    bullet_count: int = 0

    def findings(self) -> List[str]:
        out: List[str] = []
        if self.buzzwords:
            out.append("Buzzwords/AI-tell vocabulary: " + ", ".join(sorted(set(self.buzzwords))))
        if self.em_dashes:
            out.append(f"{self.em_dashes} em dash(es); rephrase with commas, periods or parentheses")
        if self.repeated_openers:
            out.append("Bullets repeatedly start with the same verb: " + ", ".join(self.repeated_openers))
        if self.bullet_count and self.trailing_ing_bullets / self.bullet_count > 0.25:
            out.append(f"{self.trailing_ing_bullets}/{self.bullet_count} bullets end with a ', ...ing' clause")
        if self.formulaic_ratio > 0.6:
            out.append(f"{self.formulaic_ratio:.0%} of bullets follow 'Verb ..., resulting in/leading to N%'; vary structure")
        return out


def lint(markdown: str) -> LintReport:
    rep = LintReport()
    low = markdown.lower()
    for b in BUZZWORDS:
        if re.search(r"\b" + re.escape(b) + r"\b", low):
            rep.buzzwords.append(b)
    rep.em_dashes = markdown.count("—")

    bullets = [ln.strip()[2:].strip() for ln in markdown.splitlines() if ln.strip().startswith(("- ", "* "))]
    rep.bullet_count = len(bullets)
    if not bullets:
        return rep

    openers = Counter()
    for b in bullets:
        m = _word.match(b)
        if m:
            openers[m.group(0).lower()] += 1
    rep.repeated_openers = [w for w, n in openers.most_common() if n >= 3]

    rep.trailing_ing_bullets = sum(1 for b in bullets if re.search(r",\s+\w+ing\b[^,]*\.?$", b))
    formulaic = sum(
        1 for b in bullets
        if re.search(r"\b(resulting in|leading to|driving|which (led|resulted) to)\b.*\d+\s*%", b, re.I)
    )
    rep.formulaic_ratio = formulaic / len(bullets)
    return rep
