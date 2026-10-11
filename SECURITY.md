# Security Policy and Deployment Notes

## Project security posture

Tungelligence is a local-first portfolio and educational demonstration. It includes input validation and local-data handling safeguards, but it is **not production-hardened**. Do not expose it to untrusted users or networks without additional controls.

## Safeguards in this repository

- Uploads are restricted to an explicit extension allow-list and a configurable per-file size limit.
- Uploads are staged before changing active files; failed validation/indexing restores previous same-name files where possible.
- Workspace indexes are built in temporary locations and published with rollback across the managed artifact set.
- Pydantic validates application request and response contracts.
- The default host-run scripts bind to `127.0.0.1`.
- Docker Compose publishes the web API to `127.0.0.1:8000`; the Ollama port is not published to the host by default.
- `.gitignore` excludes runtime workspace content, database files, local settings, and generated Python artifacts.
- `.dockerignore` excludes runtime data and local settings from Docker build context; the Dockerfile does not copy `data/` into the image.
- Conversation history and retrieved context are bounded by configuration.
- The default LLM path uses a local Ollama service. Changing `LLM_BASE_URL` to a remote endpoint can transmit prompts and selected document text to that service.

These controls reduce several common accidental-exposure risks. They are not a substitute for a security review, malware scanning, authentication, authorization, or operating-system isolation.

## Important limitations

### No authentication or per-user authorization

The API does not authenticate callers or implement per-user authorization. Workspace IDs are identifiers, not access credentials. Anyone who can reach the service may be able to read, change, or delete its workspace data through the API.

The supplied local scripts and Compose configuration bind published services to loopback by default. Do not override these settings to expose the demo to a LAN or the public internet. A shared deployment requires authentication, authorization, rate limiting, network restrictions, secret management, and an explicit tenant-isolation model.

### Runtime and private data

Workspace content is stored under `data/workspaces/<workspace-id>/`, and the SQLite database defaults to `data/tungelligence.db`. These paths are excluded from source-control and Docker build contexts by the provided ignore files. The safeguards only apply to files not already tracked or included in a prior Git commit/image.

Before each public push, inspect the actual staging list. If a secret or private document has ever been committed, adding an ignore rule does not remove it from Git history. Rotate exposed credentials, remove the sensitive history where appropriate, and invalidate affected artifacts.

Never publish `.env`, credentials, private documents, SQLite databases, workspace directories, user logs, model artifacts, virtual environments, or Python bytecode.

### Document prompt injection and answer reliability

Uploaded documents are untrusted input. Text extracted from them is included in LLM context, so malicious instructions embedded in a document may influence generation. Prompt instructions are not a security boundary. Verify important claims against the displayed source material and avoid using the demo with sensitive or adversarial documents unless this limitation is accepted.

### File-processing limitations

- The extension allow-list is not malware scanning or comprehensive file-signature/content-type validation.
- PDFs must contain extractable text; scanned pages are not OCR-processed.
- DOCX extraction currently reads paragraphs, not table content.
- The confidence score is heuristic, not a calibrated probability of correctness.
- Application-level deletion does not guarantee forensic secure erasure from SSDs, backups, snapshots, browser caches, or external copies.
- Deleting a document removes its source and current derived index data, but prior conversation messages may retain excerpts or answers derived from that document. Delete the relevant conversation/workspace if that history must also be removed.

## Public-release checklist

- [ ] Inspect `git status --short` and `git ls-files` before committing; confirm no runtime data is staged.
- [ ] Confirm `.env` is not tracked and contains no live credentials.
- [ ] Confirm `data/workspaces/`, raw documents, processed chunks, indexes, SQLite files, and logs are ignored.
- [ ] Confirm `.venv/`, `__pycache__/`, and `*.py[cod]` are not tracked.
- [ ] Scan the staged diff for secrets and private content. A pattern scan cannot guarantee that all sensitive information is absent.
- [ ] Do not expose the unauthenticated API or Ollama port to untrusted networks.
- [ ] Run the test suite on the target Python version. Native model inference and Docker image behavior must be tested separately when those backends are installed.
- [ ] Do not describe the current system as production-ready.

## Reporting a vulnerability

Do not publish credentials, private documents, or exploitable details in a public issue. Use GitHub's private vulnerability reporting if enabled for the repository; otherwise contact the maintainer privately before public disclosure.
