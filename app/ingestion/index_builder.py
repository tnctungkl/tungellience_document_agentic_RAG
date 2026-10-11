import json
from pathlib import Path

from app.core.exceptions import IngestionError
from app.ingestion.pipeline import IngestionPipeline
from app.validation.schemas import DocumentChunk


def write_chunks_jsonl(chunks: list[DocumentChunk], output_path: Path) -> None:
    """Persist chunks as newline-delimited JSON for reproducible inspection."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(chunk.model_dump_json() + "\n")
            handle.flush()
        temporary.replace(output_path)
    except OSError as exc:
        raise IngestionError("failed to persist processed chunks") from exc


def build_processed_dataset(pipeline: IngestionPipeline, input_dir: Path, output_path: Path) -> int:
    """Process a document directory and persist its validated chunks."""
    chunks = pipeline.process_directory(input_dir)
    write_chunks_jsonl(chunks, output_path)
    return len(chunks)
