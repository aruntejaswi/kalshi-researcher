"""Skill registry. Add new skills by importing and registering them here."""
from __future__ import annotations

from .base import ContextSheet, ResearchSkill
from .general_web import GeneralWebSkill

SKILLS: list[ResearchSkill] = [GeneralWebSkill()]
SKILL_REGISTRY: dict[str, ResearchSkill] = {s.id: s for s in SKILLS}

__all__ = ["ContextSheet", "ResearchSkill", "SKILLS", "SKILL_REGISTRY"]
