"""LeetCode CSV parsing and aggregation using pandas."""

import io
import logging

import pandas as pd

from app.models.schemas import LeetCodeTopicStats

logger = logging.getLogger(__name__)

# Required columns in the CSV (checked case-insensitively)
REQUIRED_COLUMNS = {"title", "difficulty", "status", "topic"}

# Valid status values for filtering (case-insensitive)
VALID_STATUSES = {"accepted", "solved"}

# Valid difficulty values (case-insensitive)
VALID_DIFFICULTIES = {"easy", "medium", "hard"}


class CSVExtractionError(Exception):
    """Raised when CSV extraction fails due to missing required columns."""

    def __init__(self, message: str, missing_columns: list[str]) -> None:
        super().__init__(message)
        self.missing_columns = missing_columns


class CSVExtractor:
    """Parses LeetCode CSV exports into per-topic difficulty aggregates."""

    def extract(self, file_bytes: bytes) -> list[LeetCodeTopicStats]:
        """Extract and aggregate LeetCode stats from CSV bytes.

        Args:
            file_bytes: Raw CSV file content as bytes.

        Returns:
            List of LeetCodeTopicStats objects with per-topic counts.

        Raises:
            CSVExtractionError: If required columns are missing from the CSV.
        """
        df = pd.read_csv(io.BytesIO(file_bytes))

        # Normalize column headers to lowercase
        df.columns = df.columns.str.lower().str.strip()

        # Validate required columns
        self._validate_columns(df)

        # Filter rows
        df = self._filter_rows(df)

        # Aggregate by (topic, difficulty) and return stats
        return self._aggregate(df)

    def _validate_columns(self, df: pd.DataFrame) -> None:
        """Check that all required columns are present.

        Raises:
            CSVExtractionError: With missing_columns attribute listing
                exactly which required columns are absent.
        """
        present_columns = set(df.columns)
        missing = sorted(REQUIRED_COLUMNS - present_columns)

        if missing:
            raise CSVExtractionError(
                f"CSV is missing required columns: {', '.join(missing)}",
                missing_columns=missing,
            )

    def _filter_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter rows to include only valid solved problems.

        Filters:
        - status must be "Accepted" or "Solved" (case-insensitive)
        - difficulty must be "Easy", "Medium", or "Hard" (case-insensitive)
        - topic must not be empty/null (logs warning for skipped rows)
        """
        # Filter by status (case-insensitive)
        df = df[df["status"].str.lower().str.strip().isin(VALID_STATUSES)]

        # Discard rows with unrecognized difficulty
        df = df[df["difficulty"].str.lower().str.strip().isin(VALID_DIFFICULTIES)]

        # Skip rows with empty/null topic (log warning)
        null_topic_mask = df["topic"].isna() | (df["topic"].str.strip() == "")
        null_topic_count = null_topic_mask.sum()
        if null_topic_count > 0:
            logger.warning(
                "Skipping %d row(s) with empty or null topic", null_topic_count
            )
        df = df[~null_topic_mask]

        return df

    def _aggregate(self, df: pd.DataFrame) -> list[LeetCodeTopicStats]:
        """Group filtered rows by (topic, difficulty) and count.

        Returns a list of LeetCodeTopicStats with easy/medium/hard counts
        per topic. Difficulties with no solved problems get 0.
        """
        if df.empty:
            return []

        # Normalize difficulty for grouping
        df = df.copy()
        df["difficulty"] = df["difficulty"].str.lower().str.strip()
        df["topic"] = df["topic"].str.strip()

        # Group by topic and difficulty, count rows
        grouped = df.groupby(["topic", "difficulty"]).size().reset_index(name="count")

        # Pivot to get easy/medium/hard columns per topic
        pivot = grouped.pivot_table(
            index="topic",
            columns="difficulty",
            values="count",
            fill_value=0,
            aggfunc="sum",
        )

        # Ensure all difficulty columns exist (fill with 0 if missing)
        for diff in VALID_DIFFICULTIES:
            if diff not in pivot.columns:
                pivot[diff] = 0

        # Build list of LeetCodeTopicStats
        results: list[LeetCodeTopicStats] = []
        for topic in pivot.index:
            results.append(
                LeetCodeTopicStats(
                    topic=topic,
                    easy=int(pivot.loc[topic, "easy"]),
                    medium=int(pivot.loc[topic, "medium"]),
                    hard=int(pivot.loc[topic, "hard"]),
                )
            )

        return results
