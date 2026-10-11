from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.core.exceptions import IngestionError
from app.validation.schemas import DocumentChunk


_TOKEN_PATTERN = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)


@dataclass(frozen=True)
class ContextItem:
    """A grounded text fragment selected from the workspace knowledge base."""

    chunk: DocumentChunk
    score: float


class WorkspaceContextTool:
    """Select grounded workspace context for broad document reasoning tasks."""

    def __init__(self, processed_dir: Path, max_context_chars: int = 28000) -> None:
        self.processed_dir = processed_dir
        self.max_context_chars = max_context_chars
        self.chunk_file = processed_dir / "chunks.jsonl"

    def load_chunks(self) -> list[DocumentChunk]:
        """Load persisted chunks without re-parsing the original documents."""
        if not self.chunk_file.exists():
            raise IngestionError("workspace index does not contain processed chunks")

        chunks: list[DocumentChunk] = []
        try:
            with self.chunk_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        chunks.append(DocumentChunk.model_validate_json(line))
        except (OSError, ValueError) as exc:
            raise IngestionError("workspace processed chunk file is invalid") from exc

        if not chunks:
            raise IngestionError("workspace contains no processed chunks")
        return chunks

    def select(self, query: str) -> tuple[list[ContextItem], bool]:
        """Select the most useful persisted chunks within a bounded context budget."""
        chunks = self.load_chunks()
        query_terms = {term.casefold() for term in _TOKEN_PATTERN.findall(query) if len(term) > 1}

        scored: list[ContextItem] = []
        for chunk in chunks:
            text = chunk.text.casefold()
            overlap = sum(text.count(term) for term in query_terms)
            scored.append(ContextItem(chunk=chunk, score=float(overlap)))

        scored.sort(key=lambda item: (-item.score, item.chunk.metadata.get("file_name", ""), item.chunk.chunk_index))

        selected: list[ContextItem] = []
        used_chars = 0
        seen_documents: set[UUID] = set()

        # Prefer a little coverage from every source before spending the rest of the budget on high-overlap chunks.
        for item in scored:
            if item.chunk.document_id in seen_documents:
                continue
            if used_chars + len(item.chunk.text) > self.max_context_chars:
                continue
            selected.append(item)
            seen_documents.add(item.chunk.document_id)
            used_chars += len(item.chunk.text)

        for item in scored:
            if item in selected:
                continue
            if used_chars + len(item.chunk.text) > self.max_context_chars:
                continue
            selected.append(item)
            used_chars += len(item.chunk.text)

        # The context is exhaustive only if every persisted chunk fit in the configured budget.
        complete = len(selected) == len(chunks)
        selected.sort(key=lambda item: (item.chunk.metadata.get("file_name", ""), item.chunk.chunk_index))
        return selected, complete
