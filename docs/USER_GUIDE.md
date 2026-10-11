# Tungelligence User Guide

This guide covers the browser application and the basic local workflow. Tungelligence is a workspace-grounded document assistant: it does not search the public internet, and its factual answers should be based on the documents indexed in the selected workspace.

## 1. Start the application

### Windows PowerShell

From the repository root, using Python 3.12 or 3.13:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
ollama pull qwen3:8b
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Keep the terminal running while you use the app. The first embedding-model use may download model files, and Ollama must have the configured LLM model available for natural-language generation.

The commands use `.venv`'s Python directly; activating the environment is optional. If you prefer activation in PowerShell, follow your organization's execution-policy rules rather than changing machine-wide policy unnecessarily.

## 2. Create a workspace

Create a workspace for a specific topic or project, for example **Product Documentation** or **Security Policies**. Each workspace keeps its own uploaded documents, processed chunks, vector index, and conversations.

Use separate workspaces when the documents should not be mixed together. Workspace separation is a local data-organization feature, not a substitute for authentication or multi-user authorization.

## 3. Upload documents

The current supported extensions are:

- `.txt`
- `.md` and `.markdown`
- `.pdf` with extractable text
- `.docx` paragraphs

The default maximum file size is 25 MB per document. Wait until the loading overlay reports that processing and indexing have completed before asking questions.

**Extraction notes:** scanned/image-only PDFs are not OCR-processed. DOCX tables are not currently extracted. A file that opens normally in a desktop reader may still produce little or no text for this pipeline if its contents are images or unsupported embedded elements.

For a first run, upload `examples/getting_started.txt` from the repository.

## 4. Ask document-grounded questions

Examples of knowledge questions:

- `What is the annual leave entitlement?`
- `Who approves leave requests?`
- `What does the security policy say about password changes?`

The agent searches the selected workspace, reranks candidates, and uses the configured local LLM when it can assemble usable context. Answers can be wrong or incomplete, so inspect the displayed sources when validating an important claim.

## 5. Request broader document work

The composer accepts natural-language requests; you are not limited to example questions. Try:

- `Summarize this document in five bullet points.`
- `Explain the main idea in simple terms.`
- `Compare the responsibilities described in these two documents.`
- `Translate the relevant section into Turkish.`
- `Extract the key requirements and organize them as a checklist.`
- `Draft an email based only on the policy in this workspace.`

The system uses retrieval first and may choose a bounded selection of workspace chunks for broad tasks. Very large workspaces may exceed the available context budget, so do not assume every page or chunk was considered unless the response explicitly supports that conclusion.

## 6. Use deterministic text-analysis tools

Some requests can be answered with ordinary Python calculations instead of an LLM call:

- `What is the most frequent letter in the documents?`
- `Bana en çok geçen harfi söyle.`
- `What is the most frequent word?`
- `How many words are in the documents?`
- `What is the character count?`

These operations analyze the readable text from the selected workspace documents. The character count includes whitespace and punctuation. The word count follows the application's current tokenization pattern; it should not be treated as a linguistic standard for every language.

## 7. Continue a conversation

Conversation history is persisted by conversation. For example:

1. Ask `What is the annual leave entitlement?`
2. Follow up with `Who approves it?`

The application supplies a bounded amount of recent history to help resolve references such as “it” and “that policy”. Older messages may be outside the configured prompt-history limit, even though they remain in stored conversation history.

Use **New conversation** to start a separate thread. Reopening an existing conversation restores its saved messages. The refresh/reset control clears the selected conversation's messages while preserving its conversation record; deleting the conversation is a separate, irreversible action.

## 8. Manage documents and workspace data

The document list allows selected files to be deleted. The app asks for confirmation, shows the selected filenames during the removal process, rebuilds the remaining index, and reports the result.

Deleting an individual document removes its source file, document metadata, processed chunks, and current derived vector index. However, prior conversation messages may still contain answers or excerpts derived from that document. Delete the related conversation (or the whole workspace) if that history must also be removed. This is application-level deletion, not forensic secure erasure from storage media, backups, or other copies.

Deleting a workspace removes that workspace's local directory and stored workspace/conversation records under normal filesystem operation. Make a separate backup first if any information must be retained.

## 9. Export and print a result

The report panel becomes available after the agent produces a completed answer.

- **Export** opens the browser's Save As dialog and writes the generated PDF to the destination you select. It relies on the browser File System Access API and a secure context such as `localhost`; if your browser does not support this API, Export reports an error rather than silently choosing a destination.
- **Print** opens a print-optimized report window and requests the standard browser/operating-system print dialog. Select the intended printer or print-to-PDF destination there. If the browser blocks pop-ups, allow the local app's print window and try again.

The PDF contains the query, answer, action/confidence information, and any citations returned with that response. Confidence is heuristic, not a calibrated probability.

## 10. Local configuration and offline smoke testing

Copy `.env.example` to `.env` before editing values.

The default LLM endpoint is `http://localhost:11434` and the model is `qwen3:8b`. The host-run scripts bind the web application to `127.0.0.1` by default. Check the service and installed model with:

```powershell
ollama list
```

If you need to validate ingestion/indexing without downloading the embedding model or installing FAISS, set these variables in `.env`:

```dotenv
EMBEDDING_PROVIDER=hash
VECTOR_STORE_BACKEND=numpy
EMBEDDING_DIMENSION=128
```

Restart the API after changing configuration. This mode tests the pipeline and basic vector-store flow but does not provide semantic-quality embeddings. The local LLM is still needed for natural-language generation; supported deterministic counting requests can run without LLM generation.

## 11. Troubleshooting

### The API starts, but natural-language questions fail

- Confirm Ollama is running.
- Run `ollama list` and confirm that the configured model is installed.
- Verify `LLM_BASE_URL` in `.env` is `http://localhost:11434` for native execution.
- Review the server terminal for the underlying error.

### The file uploads but indexing fails

- Confirm the extension is supported and the file is within the configured size limit.
- For PDFs, verify that text can be selected/copied from the document; image-only scans are not supported without OCR.
- For DOCX, check whether essential content exists only in tables, which the current loader does not extract.
- Confirm the embedding provider and vector-store backend match the installed dependencies.

### Export is unavailable

Use a current Chromium-based browser such as Chrome or Edge and access the application through `http://127.0.0.1:8000`. Export requires browser support for `showSaveFilePicker`; unlike Print, it does not use an automatic Downloads fallback.

### Port or network concerns

The project is intended for local development. It does not implement authentication or per-user authorization. Do not expose the current API or Ollama service to untrusted networks. See [SECURITY.md](../SECURITY.md) before using Docker or sharing the service.
