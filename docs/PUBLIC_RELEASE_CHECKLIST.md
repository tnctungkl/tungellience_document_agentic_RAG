# Public Release Checklist

Use this checklist immediately before pushing Tungelligence to a public GitHub repository. Ignore files and automated scans reduce risk; they do not prove that a repository contains no sensitive information.

## 1. Confirm the working tree

Run from the repository root:

```bash
git status --short
git ls-files
git diff --cached --stat
```

Review every staged file. The expected repository should contain source code, tests, examples created for the project, documentation, configuration templates, and license files—not machine-specific state.

## 2. Confirm private/runtime files are absent

The checked-in ignore rules exclude `.env`, Python environments and caches, SQLite databases, all runtime files below `data/` (except the three `.gitkeep` placeholders), and workspace folders. Verify this from your own machine:

```bash
git check-ignore -v .env data/tungelligence.db data/workspaces/example/raw/private.pdf .venv/pyvenv.cfg
```

Expected: each example path is reported as ignored. If any path is already tracked, `.gitignore` alone will not remove it from the index. Inspect and untrack the specific file only after confirming it is not needed in the repository. Never force-add runtime data to work around ignore rules.

## 3. Scan for accidental credentials or private content

Before staging, inspect changes and use an available secret scanner (for example, Gitleaks or GitHub secret scanning) against the working tree and staged diff. Also review manually for:

- access tokens, API keys, passwords, private keys, and real connection strings;
- personal information or company/customer documents in examples and tests;
- SQLite databases, uploaded documents, logs, model artifacts, caches, and backups;
- local file paths containing usernames or organization details.

A clean scan is not a guarantee. If a credential was previously committed, revoke/rotate it and follow GitHub guidance for removing sensitive history; deleting the current file is not sufficient.

## 4. Run tests and review limitations

```bash
python -m compileall -q app scripts tests
python -m pytest -q
```

Run a live Ollama + Sentence Transformers + FAISS smoke test and Docker build on a supported target machine before claiming those paths were exercised. The automated test suite deliberately uses test doubles for some external services.

## 5. Keep the demo local-only unless it is hardened

The current application has no authentication or per-user authorization. Keep the host API bound to `127.0.0.1`; do not publish the service or Ollama endpoint to an untrusted network. Do not describe the project as production-ready.

## 6. Check the final source archive

If sharing a ZIP, create it from the clean source tree—not from an installed development folder containing `.venv`, databases, workspace uploads, or caches. List archive contents and inspect the archive size before sharing.
