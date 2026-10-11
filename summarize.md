# Tungelligence — Engineering Summary

## Project intent

Tungelligence is a local-first, workspace-grounded Agentic RAG demonstration. It is designed to show the engineering work around document ingestion, retrieval, bounded agent routing, local model integration, persistence, evaluation, and a usable browser interface—not merely a thin wrapper around an LLM API.

The repository is intended for learning, technical demonstrations, and portfolio review. It is **not a security-hardened production platform**.

## Main workflow

1. A user creates a workspace and uploads supported documents.
2. Loaders extract text from TXT, Markdown, text-based PDF, and DOCX paragraphs.
3. The pipeline cleans, chunks, validates, and persists document records.
4. Sentence Transformers creates embeddings by default; FAISS stores vectors for similarity search.
5. The query router selects a deterministic text-analysis tool for supported frequency/count operations or sends a document question through retrieval and lexical reranking.
6. The bounded agent selects relevant context and calls Ollama when language-model generation is needed and usable evidence is available.
7. The result, source references, action label, heuristic confidence, and bounded conversation history are presented through the FastAPI-served UI.

## Design highlights

- Explicit Python modules for ingestion, processing, embeddings, vector storage, retrieval, prompting, agent orchestration, API, and reporting.
- SQLite-backed workspace, document metadata, conversation, and message persistence.
- Staged multi-file uploads and rollback-capable publication of derived index artifacts.
- Workspace-specific raw, processed, and vector directories.
- Deterministic analysis tools to avoid LLM generation for supported exact-counting tasks.
- Bounded recent conversation history and context size to limit prompt growth.
- Ollama HTTP integration without a vendor-specific Python SDK.
- Browser-based Export/Print flows and a CLI retained for developer-oriented use.
- Unit and integration tests plus a GitHub Actions workflow with a coverage threshold.

## Default configuration

- **Python:** `>=3.12,<3.14`
- **LLM:** Ollama, `qwen3:8b`
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2`
- **Vector store:** FAISS
- **Reranking:** lightweight lexical relevance scoring
- **Persistence:** SQLite and workspace-local files
- **API/UI:** FastAPI with static HTML, CSS, and JavaScript
- **Report output:** PDF generated with ReportLab

A Hash + NumPy configuration exists for model-download-free smoke tests. It validates application flow but is not a semantic embedding quality mode.

## Important limitations

- This is a controlled local/demo application; authentication, per-user authorization, rate limiting, and production-grade tenant isolation are not implemented.
- PDF ingestion extracts embedded text only; it does not OCR scanned pages.
- DOCX ingestion currently extracts paragraphs but not tables.
- The lexical reranker is not a cross-encoder, and confidence is not a calibrated probability.
- The model only sees bounded workspace context, so large corpora may need a more advanced summarization/retrieval strategy.
- Deleting a document removes its source and derived index records, but historical conversation messages are retained unless the conversation or workspace is deleted too.
- Native FAISS/Sentence Transformers inference, Ollama inference, and Docker build should be smoke-tested in the target environment before a release claim is made.

## Local validation commands

```powershell
.\.venv\Scripts\python.exe -m compileall app tests
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing
```

On macOS/Linux, run the equivalent commands with `python` from the project's virtual environment.

## Public repository note

The repository ignore rules exclude virtual environments, bytecode/cache files, `.env`, SQLite databases, uploaded source documents, and runtime workspace data from Git and Docker build contexts. Before every push, review the actual staged file list (`git status --short` and `git diff --cached --stat`) and scan the staged diff for secrets or private content. Ignore rules cannot remove data that was committed previously.
