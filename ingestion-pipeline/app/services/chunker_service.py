"""Section-aware text chunking service for the ingestion pipeline.

Splits narrative text into chunks suitable for embedding, respecting section
boundaries, token limits, and sentence-level overlap.
"""

from __future__ import annotations

import logging
import re

from app.models.schemas import Chunk, ChunkMetadata, ResumeSection

logger = logging.getLogger(__name__)


class ChunkerService:
    """Splits resume/session text into section-aware chunks for embedding.

    Each chunk respects the 512-token maximum and preserves section context.
    When a section exceeds the limit, it is split at sentence boundaries with
    a 50-token overlap between consecutive chunks.
    """

    MAX_CHUNK_TOKENS = 512
    OVERLAP_TOKENS = 50

    # Regex to split on sentence boundaries: . ? or ! followed by whitespace
    _SENTENCE_SPLIT_RE = re.compile(r"(?<=[.?!])\s+")

    def chunk(
        self,
        sections: list[ResumeSection],
        user_id: str,
        source: str,
        job_id: str | None = None,
    ) -> list[Chunk]:
        """Produce embedding-ready chunks from a list of resume sections.

        Args:
            sections: Parsed resume sections (may be empty or contain only
                      'unstructured' entries).
            user_id: Owner of the content.
            source: Origin label — 'resume' or 'session'.
            job_id: Optional ingestion job identifier.

        Returns:
            Ordered list of Chunk objects with metadata attached.
        """
        # Edge case: no sections or only unstructured content
        if not sections or all(
            s.section.lower().strip() in ("unstructured", "") for s in sections
        ):
            return self._chunk_unstructured(sections, user_id, source, job_id)

        chunks: list[Chunk] = []
        for section in sections:
            section_chunks = self._chunk_section(section, user_id, source, job_id)
            chunks.extend(section_chunks)
        return chunks

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _chunk_unstructured(
        self,
        sections: list[ResumeSection],
        user_id: str,
        source: str,
        job_id: str | None,
    ) -> list[Chunk]:
        """Handle the edge case where no recognized headings were detected.

        Treats all text as a single unnamed section and applies standard
        splitting rules.
        """
        combined_text = " ".join(s.text for s in sections if s.text.strip())
        if not combined_text.strip():
            return []

        texts = self._split_text(combined_text)
        return [
            Chunk(
                text=t,
                metadata=ChunkMetadata(
                    user_id=user_id,
                    source=source,
                    section="unnamed",
                    chunk_index=idx,
                    topic=None,
                    job_id=job_id,
                ),
            )
            for idx, t in enumerate(texts)
        ]

    def _chunk_section(
        self,
        section: ResumeSection,
        user_id: str,
        source: str,
        job_id: str | None,
    ) -> list[Chunk]:
        """Chunk a single section, keeping sub-entries intact when possible."""
        section_name = section.section.strip()
        chunk_index = 0
        chunks: list[Chunk] = []

        # If the section has sub-entries, treat each as a potential chunk
        entries = section.sub_entries if section.sub_entries else [section.text]

        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue

            token_count = self._count_tokens(entry)

            if token_count <= self.MAX_CHUNK_TOKENS:
                # Entry fits in a single chunk
                chunks.append(
                    Chunk(
                        text=entry,
                        metadata=ChunkMetadata(
                            user_id=user_id,
                            source=source,
                            section=section_name,
                            chunk_index=chunk_index,
                            topic=self._map_topic(section_name),
                            job_id=job_id,
                        ),
                    )
                )
                chunk_index += 1
            else:
                # Entry exceeds limit — split with overlap
                split_texts = self._split_with_overlap(entry)
                for text_part in split_texts:
                    chunks.append(
                        Chunk(
                            text=text_part,
                            metadata=ChunkMetadata(
                                user_id=user_id,
                                source=source,
                                section=section_name,
                                chunk_index=chunk_index,
                                topic=self._map_topic(section_name),
                                job_id=job_id,
                            ),
                        )
                    )
                    chunk_index += 1

        # If no entries produced chunks, fall back to section text
        if not chunks and section.text.strip():
            texts = self._split_text(section.text)
            for idx, t in enumerate(texts):
                chunks.append(
                    Chunk(
                        text=t,
                        metadata=ChunkMetadata(
                            user_id=user_id,
                            source=source,
                            section=section_name,
                            chunk_index=idx,
                            topic=self._map_topic(section_name),
                            job_id=job_id,
                        ),
                    )
                )

        return chunks

    def _split_text(self, text: str) -> list[str]:
        """Split text respecting token limit — convenience wrapper."""
        if self._count_tokens(text) <= self.MAX_CHUNK_TOKENS:
            return [text]
        return self._split_with_overlap(text)

    def _count_tokens(self, text: str) -> int:
        """Approximate token count using whitespace splitting.

        Each whitespace-delimited word is treated as ~1 token.
        """
        return len(text.split())

    def _split_with_overlap(self, text: str) -> list[str]:
        """Split text at sentence boundaries with overlap between chunks.

        Algorithm:
          1. Split text into sentences.
          2. Accumulate sentences until the token count approaches MAX_CHUNK_TOKENS.
          3. When starting a new chunk, include the last ~OVERLAP_TOKENS tokens
             from the previous chunk as overlap.
          4. If a single sentence exceeds the limit, force-split it on word
             boundaries so every chunk respects the token cap.

        Returns:
            List of chunk text strings, each ≤ MAX_CHUNK_TOKENS tokens.
        """
        sentences = self._split_sentences(text)

        if not sentences:
            return [text] if text.strip() else []

        chunks: list[str] = []
        current_sentences: list[str] = []
        current_token_count = 0

        for sentence in sentences:
            sentence_tokens = self._count_tokens(sentence)

            # If a single sentence exceeds the max, force-split on word boundaries
            if sentence_tokens > self.MAX_CHUNK_TOKENS and not current_sentences:
                word_chunks = self._force_split_words(sentence)
                chunks.extend(word_chunks)
                continue

            if current_token_count + sentence_tokens > self.MAX_CHUNK_TOKENS:
                # Flush current chunk
                if current_sentences:
                    chunks.append(" ".join(current_sentences))

                # Build overlap from end of previous chunk
                overlap_sentences = self._get_overlap_sentences(current_sentences)
                current_sentences = overlap_sentences
                current_token_count = self._count_tokens(" ".join(current_sentences))

            # If adding this sentence still exceeds limit (e.g. overlap + sentence),
            # force-split
            if current_token_count + sentence_tokens > self.MAX_CHUNK_TOKENS:
                if current_sentences:
                    chunks.append(" ".join(current_sentences))
                    current_sentences = []
                    current_token_count = 0

                if sentence_tokens > self.MAX_CHUNK_TOKENS:
                    word_chunks = self._force_split_words(sentence)
                    chunks.extend(word_chunks)
                    continue

            current_sentences.append(sentence)
            current_token_count += sentence_tokens

        # Flush remaining sentences
        if current_sentences:
            chunks.append(" ".join(current_sentences))

        return chunks if chunks else [text]

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences at `. `, `? `, `! ` boundaries."""
        parts = self._SENTENCE_SPLIT_RE.split(text)
        return [p.strip() for p in parts if p.strip()]

    def _force_split_words(self, text: str) -> list[str]:
        """Force-split text on word boundaries when no sentence breaks exist.

        Used as a fallback when a single sentence exceeds MAX_CHUNK_TOKENS.
        Produces chunks of up to MAX_CHUNK_TOKENS words with OVERLAP_TOKENS
        overlap between consecutive chunks.
        """
        words = text.split()
        chunks: list[str] = []
        start = 0

        while start < len(words):
            end = min(start + self.MAX_CHUNK_TOKENS, len(words))
            chunk_text = " ".join(words[start:end])
            chunks.append(chunk_text)

            if end >= len(words):
                break

            # Next chunk starts with overlap
            start = end - self.OVERLAP_TOKENS

        return chunks

    def _get_overlap_sentences(self, sentences: list[str]) -> list[str]:
        """Select sentences from the end of a chunk to form overlap (~50 tokens)."""
        overlap: list[str] = []
        token_count = 0

        for sentence in reversed(sentences):
            sent_tokens = self._count_tokens(sentence)
            if token_count + sent_tokens > self.OVERLAP_TOKENS and overlap:
                break
            overlap.insert(0, sentence)
            token_count += sent_tokens

        return overlap

    @staticmethod
    def _map_topic(section_name: str) -> str | None:
        """Map section name to a topic tag for filtered retrieval.

        Currently returns None for standard resume sections — the topic
        is typically derived from deeper content analysis rather than the
        section heading itself.
        """
        # Standard resume sections don't map to a specific topic
        known_sections = {
            "work_experience",
            "skills",
            "projects",
            "education",
        }
        if section_name.lower().strip() in known_sections:
            return None
        return None
