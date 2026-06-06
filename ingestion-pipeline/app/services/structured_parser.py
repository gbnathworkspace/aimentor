"""Structured parser for transforming extracted content into typed facts in MongoDB.

Handles:
- LeetCode topic stats → Skill Graph upserts
- Resume sections → Core Profile extraction
- Zod-style validation before writes
- MongoDB transaction wrapping for atomicity
"""

from __future__ import annotations

import logging
import re

from app.config.database import get_mongo_client, get_skill_graph_collection, get_users_collection
from app.models.schemas import LeetCodeTopicStats, ResumeSection
from app.models.validators import ValidationError, validate_core_profile, validate_skill_graph_signals

logger = logging.getLogger(__name__)


class StructuredParser:
    """Transform extracted content into typed facts and write to MongoDB.

    Processes LeetCode stats into Skill Graph upsert documents and
    resume sections into Core Profile fields, validating all data
    before persisting within a MongoDB transaction.
    """

    async def process(
        self,
        leetcode_stats: list[LeetCodeTopicStats] | None,
        resume_sections: list[ResumeSection] | None,
        user_id: str,
        job_id: str,
    ) -> None:
        """Process extracted content into structured MongoDB writes.

        Args:
            leetcode_stats: Aggregated LeetCode topic stats (from CSV extraction).
            resume_sections: Resume sections routed to the structured path.
            user_id: The user who owns this data.
            job_id: The ingestion job identifier for traceability.

        Raises:
            ValidationError: If any data fails Zod-style schema validation.
        """
        # Build upsert documents from LeetCode stats
        skill_graph_upserts = self._build_skill_graph_upserts(leetcode_stats)

        # Extract profile data from resume sections
        profile_data = self._extract_profile_data(resume_sections)

        # Validation gate: validate all data before any writes
        if profile_data:
            validate_core_profile(profile_data)

        for upsert in skill_graph_upserts:
            validate_skill_graph_signals(upsert["signals"])

        # Write within a MongoDB transaction
        await self._write_within_transaction(
            user_id=user_id,
            skill_graph_upserts=skill_graph_upserts,
            profile_data=profile_data,
        )

        logger.info(
            "Structured parser completed for job %s: %d skill graph upserts, profile=%s",
            job_id,
            len(skill_graph_upserts),
            bool(profile_data),
        )

    def _build_skill_graph_upserts(
        self, leetcode_stats: list[LeetCodeTopicStats] | None
    ) -> list[dict]:
        """Transform LeetCode topic stats into Skill Graph upsert documents.

        For each topic stat, creates a document with:
        { "topic": ..., "signals": { "leetcode_solved": { "easy": ..., "medium": ..., "hard": ... } } }

        Args:
            leetcode_stats: List of per-topic difficulty aggregates.

        Returns:
            List of upsert documents ready for Skill Graph collection.
        """
        if not leetcode_stats:
            return []

        upserts: list[dict] = []
        for stat in leetcode_stats:
            upserts.append(
                {
                    "topic": stat.topic,
                    "signals": {
                        "leetcode_solved": {
                            "easy": stat.easy,
                            "medium": stat.medium,
                            "hard": stat.hard,
                        }
                    },
                }
            )
        return upserts

    def _extract_profile_data(
        self, resume_sections: list[ResumeSection] | None
    ) -> dict | None:
        """Extract Core Profile fields from resume sections.

        Extracts:
        - current_role: from work_experience (first sub_entry or first line)
        - years_of_experience: from work_experience (year range calculation)
        - education: from education section (first sub_entry or first significant line)
        - skills: from skills section (split on commas, pipes, or newlines)

        Sets null for unrecognizable fields and logs a warning.

        Args:
            resume_sections: Resume sections routed to the structured path.

        Returns:
            Dictionary of profile fields, or None if no resume sections provided.
        """
        if not resume_sections:
            return None

        profile: dict = {
            "current_role": None,
            "years_of_experience": None,
            "education": None,
            "skills": [],
        }

        for section in resume_sections:
            section_name = section.section.lower().strip()

            if section_name == "work_experience":
                profile["current_role"] = self._extract_current_role(section)
                profile["years_of_experience"] = self._extract_years_of_experience(section)
            elif section_name == "education":
                profile["education"] = self._extract_education(section)
            elif section_name == "skills":
                profile["skills"] = self._extract_skills(section)

        return profile

    def _extract_current_role(self, section: ResumeSection) -> str | None:
        """Extract the current role from a work experience section.

        Uses the first sub_entry if available, otherwise the first non-empty line.

        Args:
            section: The work_experience ResumeSection.

        Returns:
            The current role string, or None if unrecognizable.
        """
        # Try sub_entries first (these are job titles / positions)
        if section.sub_entries:
            role = section.sub_entries[0].strip()
            if role:
                return role

        # Fall back to first non-empty line of text
        lines = [line.strip() for line in section.text.split("\n") if line.strip()]
        if lines:
            return lines[0]

        logger.warning("Could not extract current_role from work_experience section.")
        return None

    def _extract_years_of_experience(self, section: ResumeSection) -> int | None:
        """Extract years of experience from a work experience section.

        Looks for year ranges (e.g., "2018-2023", "2018 - Present") and
        calculates the span from the earliest year to the latest year or current year.

        Args:
            section: The work_experience ResumeSection.

        Returns:
            Integer years of experience, or None if no year ranges found.
        """
        text = section.text

        # Match year ranges like "2018-2023", "2018 - Present", "2018 – 2023"
        year_pattern = r"((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2}|[Pp]resent|[Cc]urrent)"
        matches = re.findall(year_pattern, text)

        if not matches:
            logger.warning(
                "Could not extract years_of_experience from work_experience section."
            )
            return None

        import datetime

        current_year = datetime.datetime.now(datetime.UTC).year

        earliest_start = current_year
        latest_end = 0

        for start_str, end_str in matches:
            start_year = int(start_str)
            if end_str.lower() in ("present", "current"):
                end_year = current_year
            else:
                end_year = int(end_str)

            earliest_start = min(earliest_start, start_year)
            latest_end = max(latest_end, end_year)

        if latest_end >= earliest_start:
            return latest_end - earliest_start

        logger.warning(
            "Could not calculate years_of_experience from year ranges."
        )
        return None

    def _extract_education(self, section: ResumeSection) -> str | None:
        """Extract education info from an education section.

        Uses the first sub_entry if available, otherwise the first significant line.

        Args:
            section: The education ResumeSection.

        Returns:
            Education string, or None if unrecognizable.
        """
        if section.sub_entries:
            edu = section.sub_entries[0].strip()
            if edu:
                return edu

        # Fall back to first significant non-empty line (at least 5 chars)
        lines = [line.strip() for line in section.text.split("\n") if line.strip()]
        for line in lines:
            if len(line) >= 5:
                return line

        logger.warning("Could not extract education from education section.")
        return None

    def _extract_skills(self, section: ResumeSection) -> list[str]:
        """Extract skills list from a skills section.

        Splits text on commas, pipes, or newlines to get individual skill tags.

        Args:
            section: The skills ResumeSection.

        Returns:
            List of skill strings (may be empty).
        """
        text = section.text.strip()
        if not text:
            return []

        # Split on commas, pipes, or newlines
        raw_skills = re.split(r"[,|\n]+", text)

        # Clean up: strip whitespace, filter empty strings
        skills = [skill.strip() for skill in raw_skills if skill.strip()]

        if not skills:
            logger.warning("Could not extract skills from skills section.")

        return skills

    async def _write_within_transaction(
        self,
        user_id: str,
        skill_graph_upserts: list[dict],
        profile_data: dict | None,
    ) -> None:
        """Execute all structured writes within a MongoDB transaction.

        Upserts skill graph documents and updates the user profile atomically.
        On any error, aborts the transaction and re-raises.

        Args:
            user_id: The user who owns this data.
            skill_graph_upserts: List of skill graph upsert documents.
            profile_data: Core Profile fields to write, or None.
        """
        client = get_mongo_client()
        async with await client.start_session() as session:
            async with session.start_transaction():
                try:
                    # Upsert skill graph documents
                    if skill_graph_upserts:
                        skill_graph_collection = get_skill_graph_collection()
                        for upsert in skill_graph_upserts:
                            await skill_graph_collection.update_one(
                                {"user_id": user_id, "topic": upsert["topic"]},
                                {"$set": upsert["signals"]},
                                upsert=True,
                                session=session,
                            )

                    # Update user profile
                    if profile_data:
                        users_collection = get_users_collection()
                        await users_collection.update_one(
                            {"user_id": user_id},
                            {"$set": profile_data},
                            upsert=True,
                            session=session,
                        )
                except Exception:
                    # Transaction automatically aborts on exception with context manager
                    logger.error(
                        "MongoDB transaction failed for user %s, aborting.",
                        user_id,
                    )
                    raise
