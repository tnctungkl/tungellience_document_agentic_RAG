from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.core.exceptions import IngestionError
from app.ingestion.loaders import LoaderRegistry
from app.processing.cleaner import clean_text


@dataclass(frozen=True)
class AnalysisResult:
    """Deterministic document-analysis result that does not require an LLM."""

    operation: str
    answer: str
    sources: tuple[str, ...]


class DocumentAnalysisTool:
    """Answer deterministic document questions without invoking the language model."""

    _LETTER_PATTERNS = (
        re.compile(r"\bmost\s+(?:frequent|common)\s+letters?\b", re.IGNORECASE),
        re.compile(r"\bwhich\s+letter\s+(?:appears?|occurs?)\s+most\b", re.IGNORECASE),
        re.compile(r"\bwhat\s+letter\s+(?:appears?|occurs?)\s+most\b", re.IGNORECASE),
        re.compile(r"\bmost\s+used\s+letter\b", re.IGNORECASE),
    )
    _TURKISH_LETTER_PATTERNS = (
        re.compile(r"en\s+(?:çok|sık)\s+(?:geçen|kullanılan)\s+harf", re.IGNORECASE),
        re.compile(r"en\s+fazla\s+(?:geçen|kullanılan)\s+harf", re.IGNORECASE),
        re.compile(r"hangi\s+harf\s+(?:en\s+çok|en\s+sık)\s+geç", re.IGNORECASE),
    )
    _WORD_PATTERNS = (
        re.compile(r"\bmost\s+(?:frequent|common|used)\s+words?\b", re.IGNORECASE),
        re.compile(r"\bwhich\s+word\s+(?:appears?|occurs?)\s+most\b", re.IGNORECASE),
    )
    _TURKISH_WORD_PATTERNS = (
        re.compile(r"en\s+(?:çok|sık)\s+(?:geçen|kullanılan)\s+kelime", re.IGNORECASE),
        re.compile(r"en\s+fazla\s+(?:geçen|kullanılan)\s+kelime", re.IGNORECASE),
    )
    _WORD_COUNT_PATTERNS = (
        re.compile(r"\bhow\s+many\s+words\b", re.IGNORECASE),
        re.compile(r"\bword\s+count\b", re.IGNORECASE),
    )
    _TURKISH_WORD_COUNT_PATTERNS = (
        re.compile(r"kaç\s+kelime", re.IGNORECASE),
        re.compile(r"kelime\s+sayısı", re.IGNORECASE),
    )
    _CHAR_COUNT_PATTERNS = (
        re.compile(r"\bhow\s+many\s+characters\b", re.IGNORECASE),
        re.compile(r"\bcharacter\s+count\b", re.IGNORECASE),
    )
    _TURKISH_CHAR_COUNT_PATTERNS = (
        re.compile(r"kaç\s+(?:karakter|harf)", re.IGNORECASE),
        re.compile(r"karakter\s+sayısı", re.IGNORECASE),
    )

    def __init__(self, raw_dir: Path, max_size_mb: int = 25) -> None:
        self.raw_dir = raw_dir
        self.registry = LoaderRegistry(max_size_mb)

    @classmethod
    def supports(cls, query: str) -> bool:
        """Return whether the query can be answered deterministically."""
        patterns = (
            *cls._LETTER_PATTERNS,
            *cls._TURKISH_LETTER_PATTERNS,
            *cls._WORD_PATTERNS,
            *cls._TURKISH_WORD_PATTERNS,
            *cls._WORD_COUNT_PATTERNS,
            *cls._TURKISH_WORD_COUNT_PATTERNS,
            *cls._CHAR_COUNT_PATTERNS,
            *cls._TURKISH_CHAR_COUNT_PATTERNS,
        )
        return any(pattern.search(query.strip()) for pattern in patterns)

    def analyze(self, query: str) -> AnalysisResult | None:
        """Execute a supported analysis request against the workspace documents."""
        operation = self._detect_operation(query)
        if operation is None:
            return None

        corpus_parts: list[str] = []
        sources: list[str] = []
        for path in sorted(self.raw_dir.iterdir()):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in {".txt", ".md", ".markdown", ".pdf", ".docx"}:
                document = self.registry.load(path)
                content = clean_text(document.content)
                if content:
                    corpus_parts.append(content)
                    sources.append(path.name)

        if not corpus_parts:
            raise IngestionError("no readable documents are available for analysis")

        text = "\n\n".join(corpus_parts)
        answer = self._build_answer(operation, text, len(sources))
        return AnalysisResult(operation=operation, answer=answer, sources=tuple(sources))

    @classmethod
    def _detect_operation(cls, query: str) -> str | None:
        normalized = query.strip()
        if any(pattern.search(normalized) for pattern in (*cls._LETTER_PATTERNS, *cls._TURKISH_LETTER_PATTERNS)):
            return "most_frequent_letter"
        if any(pattern.search(normalized) for pattern in (*cls._WORD_PATTERNS, *cls._TURKISH_WORD_PATTERNS)):
            return "most_frequent_word"
        if any(pattern.search(normalized) for pattern in (*cls._WORD_COUNT_PATTERNS, *cls._TURKISH_WORD_COUNT_PATTERNS)):
            return "word_count"
        if any(pattern.search(normalized) for pattern in (*cls._CHAR_COUNT_PATTERNS, *cls._TURKISH_CHAR_COUNT_PATTERNS)):
            return "character_count"
        return None

    @staticmethod
    def _build_answer(operation: str, text: str, document_count: int) -> str:
        if operation == "most_frequent_letter":
            letters = [char.casefold() for char in text if char.isalpha()]
            counts = Counter(letters)
            if not counts:
                return "No alphabetic characters were found in the indexed documents."
            highest = max(counts.values())
            winners = sorted(letter for letter, count in counts.items() if count == highest)
            letters_text = ", ".join(winners)
            return f"The most frequent letter is {letters_text}, appearing {highest} times across {document_count} document(s)."

        if operation == "most_frequent_word":
            words = re.findall(r"[\wÀ-ÖØ-öø-ÿ]+", text.casefold(), flags=re.UNICODE)
            counts = Counter(word for word in words if word)
            if not counts:
                return "No words were found in the indexed documents."
            highest = max(counts.values())
            winners = sorted(word for word, count in counts.items() if count == highest)
            words_text = ", ".join(winners)
            return f"The most frequent word is {words_text}, appearing {highest} times across {document_count} document(s)."

        if operation == "word_count":
            count = len(re.findall(r"[\wÀ-ÖØ-öø-ÿ]+", text, flags=re.UNICODE))
            return f"The indexed documents contain {count} words across {document_count} document(s)."

        if operation == "character_count":
            count = len(text)
            return f"The indexed documents contain {count} characters, including whitespace and punctuation, across {document_count} document(s)."

        raise ValueError(f"unsupported analysis operation: {operation}")
