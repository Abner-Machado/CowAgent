"""
Skills module for agent system.

This module provides the framework for loading, managing, and executing skills.
Skills are markdown files with frontmatter that provide specialized instructions
for specific tasks.
"""

from agent.skills.types import (
    Skill,
    SkillEntry,
    SkillMetadata,
    SkillInstallSpec,
    LoadSkillsResult,
)
from agent.skills.loader import SkillLoader
from agent.skills.manager import SkillManager, build_skill_manager
from agent.skills.service import SkillService
from agent.skills.formatter import format_skills_for_prompt

__all__ = [
    "Skill",
    "SkillEntry",
    "SkillMetadata",
    "SkillInstallSpec",
    "LoadSkillsResult",
    "SkillLoader",
    "SkillManager",
    "build_skill_manager",
    "SkillService",
    "format_skills_for_prompt",
]
