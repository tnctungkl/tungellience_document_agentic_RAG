from __future__ import annotations

from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.agent.agent import RAGAgent
from app.api.runtime import build_workspace_agent
from app.core.config import get_settings
from app.core.exceptions import EmbeddingError, GenerationError, RAGApplicationError, VectorStoreError
from app.core.logging import configure_logging
from app.reports.pdf import build_report_pdf
from app.validation.schemas import (
    AgentResponse,
    ChatMessage,
    ConversationCreateRequest,
    ConversationSummary,
    DocumentDeleteRequest,
    DocumentDeleteResponse,
    DocumentSummary,
    QueryRequest,
    QueryResponseEnvelope,
    ReportRequest,
    WorkspaceCreateRequest,
    WorkspaceRenameRequest,
    WorkspaceState,
    WorkspaceSummary,
)
from app.workspaces.indexing import clear_workspace_index, rebuild_workspace_index
from app.workspaces.store import ConversationNotFoundError, WorkspaceNotFoundError, WorkspaceStore


UI_INDEX = Path(__file__).resolve().parents[1] / "ui" / "static" / "index.html"
SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown", ".pdf", ".docx"}


def create_app(agent: RAGAgent | None = None, workspace_store: WorkspaceStore | None = None) -> FastAPI:
    """Build the API application and expose the responsive web UI."""
    settings = get_settings()
    settings.ensure_directories()
    store = workspace_store or WorkspaceStore(settings.workspace_db_path, settings.workspace_data_dir)
    configure_logging(settings.debug)

    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.state.workspace_store = store
    app.state.legacy_agent = agent
    app.mount("/ui-static", StaticFiles(directory=UI_INDEX.parent), name="ui-static")

    @app.get("/", include_in_schema=False)
    def web_app() -> FileResponse:
        # Disable HTML caching so frontend revisions are visible immediately during local development.
        return FileResponse(
            UI_INDEX,
            media_type="text/html",
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": settings.app_version}

    @app.get("/v1/workspaces", response_model=list[WorkspaceSummary])
    def workspaces() -> list[dict]:
        return store.list_workspaces()

    @app.post("/v1/workspaces", response_model=WorkspaceSummary, status_code=201)
    def create_workspace(request: WorkspaceCreateRequest) -> dict:
        workspace = store.create_workspace(request.name)
        state = _workspace_state(store, workspace["id"])
        return state["workspace"]

    @app.patch("/v1/workspaces/{workspace_id}", response_model=WorkspaceSummary)
    def rename_workspace(workspace_id: str, request: WorkspaceRenameRequest) -> dict:
        _require_workspace(store, workspace_id)
        store.rename_workspace(workspace_id, request.name)
        return _workspace_state(store, workspace_id)["workspace"]

    @app.delete("/v1/workspaces/{workspace_id}", status_code=204)
    def delete_workspace(workspace_id: str) -> Response:
        _require_workspace(store, workspace_id)
        store.delete_workspace(workspace_id)
        return Response(status_code=204)

    @app.get("/v1/workspaces/{workspace_id}", response_model=WorkspaceState)
    def workspace_state(workspace_id: str) -> dict:
        try:
            return _workspace_state(store, workspace_id)
        except WorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/workspaces/{workspace_id}/conversations", response_model=list[ConversationSummary])
    def conversations(workspace_id: str) -> list[dict]:
        _require_workspace(store, workspace_id)
        return store.list_conversations(workspace_id)

    @app.post("/v1/workspaces/{workspace_id}/conversations", response_model=ConversationSummary, status_code=201)
    def create_conversation(workspace_id: str, request: ConversationCreateRequest) -> dict:
        return store.create_conversation(workspace_id, request.title)

    @app.delete("/v1/workspaces/{workspace_id}/conversations/{conversation_id}", status_code=204)
    def delete_conversation(workspace_id: str, conversation_id: str) -> Response:
        try:
            store.delete_conversation(workspace_id, conversation_id)
        except ConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post("/v1/workspaces/{workspace_id}/conversations/{conversation_id}/reset", status_code=204)
    def reset_conversation(workspace_id: str, conversation_id: str) -> Response:
        try:
            store.reset_conversation(workspace_id, conversation_id)
        except ConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.get("/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages", response_model=list[ChatMessage])
    def messages(workspace_id: str, conversation_id: str) -> list[dict]:
        try:
            return store.list_messages(workspace_id, conversation_id)
        except ConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/workspaces/{workspace_id}/documents", response_model=list[DocumentSummary])
    async def upload_documents(workspace_id: str, files: list[UploadFile] = File(...)) -> list[dict]:
        """Validate and stage all uploads before changing the active knowledge base.

        Existing files with the same sanitized name are backed up while indexing runs.
        If validation or indexing fails, newly installed files are removed and previous
        versions are restored, so a failed request cannot destroy an older document.
        """
        _require_workspace(store, workspace_id)
        if not files:
            raise HTTPException(status_code=400, detail="select at least one document to upload")
        if len(files) > 20:
            raise HTTPException(status_code=413, detail="a maximum of 20 documents can be uploaded per request")

        raw_dir = store.raw_dir(workspace_id)
        workspace_dir = store._workspace_dir(workspace_id)
        max_bytes = settings.max_document_size_mb * 1024 * 1024
        staging_root = workspace_dir / f".upload-{uuid4().hex}"
        staged_dir = staging_root / "staged"
        backup_dir = staging_root / "backups"
        staged_files: list[tuple[str, Path]] = []
        backups: dict[Path, Path] = {}
        installed: list[Path] = []
        commit_started = False
        staging_root.mkdir(parents=True, exist_ok=False)
        staged_dir.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(parents=True, exist_ok=True)

        def rollback_installed_files() -> None:
            for target in reversed(installed):
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
            for target, backup in reversed(list(backups.items())):
                try:
                    if backup.exists():
                        target.unlink(missing_ok=True)
                        backup.replace(target)
                except OSError:
                    import logging
                    logging.getLogger(__name__).exception("Failed to restore a document upload backup")

        try:
            seen_names: set[str] = set()
            # First validate and write every upload to a staging directory. No active file
            # is touched until the entire request passes validation.
            for index, upload in enumerate(files):
                original_name = upload.filename or ""
                suffix = Path(original_name).suffix.lower()
                if suffix not in SUPPORTED_SUFFIXES:
                    raise HTTPException(status_code=415, detail=f"unsupported file type: {suffix or 'unknown'}")

                filename = store.sanitize_filename(original_name)
                if filename in seen_names:
                    raise HTTPException(status_code=400, detail=f"duplicate filename in upload: {filename}")
                seen_names.add(filename)

                staged_path = staged_dir / f"{index:03d}-{filename}"
                total_bytes = 0
                with staged_path.open("xb") as output:
                    while True:
                        block = await upload.read(1024 * 1024)
                        if not block:
                            break
                        total_bytes += len(block)
                        if total_bytes > max_bytes:
                            raise HTTPException(
                                status_code=413,
                                detail=f"file exceeds {settings.max_document_size_mb} MB limit: {filename}",
                            )
                        output.write(block)

                if total_bytes == 0:
                    raise HTTPException(status_code=422, detail=f"document is empty: {filename}")
                staged_files.append((filename, staged_path))

            # Stage the previous version of any same-name file before installing its replacement.
            commit_started = True
            for index, (filename, staged_path) in enumerate(staged_files):
                target = raw_dir / filename
                if target.is_symlink() or (target.exists() and not target.is_file()):
                    raise HTTPException(status_code=422, detail=f"stored target is not a regular file: {filename}")
                if target.exists():
                    backup_path = backup_dir / f"{index:03d}-{filename}"
                    target.replace(backup_path)
                    backups[target] = backup_path
                staged_path.replace(target)
                installed.append(target)

            documents = rebuild_workspace_index(workspace_id, store, settings)
            return documents
        except HTTPException:
            if commit_started:
                rollback_installed_files()
            raise
        except (EmbeddingError, VectorStoreError) as exc:
            if commit_started:
                rollback_installed_files()
            raise HTTPException(
                status_code=503,
                detail=f"Document indexing is unavailable; the previous workspace state was restored: {exc}",
                headers={"Retry-After": "5"},
            ) from exc
        except RAGApplicationError as exc:
            if commit_started:
                rollback_installed_files()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            if commit_started:
                rollback_installed_files()
            import logging
            logging.getLogger(__name__).exception("Unexpected document indexing failure")
            raise HTTPException(
                status_code=500,
                detail="Document processing failed. The previous uploaded files were restored where possible; check the server log for details.",
            ) from exc
        finally:
            for upload in files:
                await upload.close()
            shutil.rmtree(staging_root, ignore_errors=True)

    @app.post(
        "/v1/workspaces/{workspace_id}/documents/delete",
        response_model=DocumentDeleteResponse,
    )
    def delete_documents(
        workspace_id: str,
        request: DocumentDeleteRequest,
    ) -> dict:
        """Permanently remove selected documents and rebuild the remaining knowledge index."""
        _require_workspace(store, workspace_id)

        selected = store.get_documents_by_ids(
            workspace_id,
            request.document_ids,
        )
        raw_dir = store.raw_dir(workspace_id)
        workspace_dir = store._workspace_dir(workspace_id)
        quarantine_dir = workspace_dir / f".delete-{uuid4().hex}"
        quarantine_dir.mkdir(parents=True, exist_ok=False)
        moved: list[tuple[Path, Path]] = []

        try:
            # Move source files out of the active knowledge directory first.
            # This gives the rebuild a clean view without destroying the files yet.
            for document in selected:
                source = raw_dir / document["file_name"]
                if not source.exists() or source.is_symlink() or not source.is_file():
                    raise RAGApplicationError(
                        f"stored document file is missing or invalid: {document['file_name']}"
                    )
                destination = quarantine_dir / document["file_name"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.replace(destination)
                moved.append((source, destination))

            remaining = [
                item for item in store.list_documents(workspace_id)
                if item["id"] not in {doc["id"] for doc in selected}
            ]

            if remaining:
                rebuilt = rebuild_workspace_index(
                    workspace_id,
                    store,
                    settings,
                )
            else:
                clear_workspace_index(workspace_id, store)
                rebuilt = []

            # The new index/database state is valid; only now destroy the quarantine.
            for _, destination in moved:
                destination.unlink(missing_ok=True)
            quarantine_dir.rmdir()

            return {
                "deleted_count": len(selected),
                "deleted_files": [item["file_name"] for item in selected],
                "documents": rebuilt,
            }
        except (EmbeddingError, VectorStoreError) as exc:
            for source, destination in reversed(moved):
                if destination.exists():
                    destination.replace(source)
            quarantine_dir.rmdir() if quarantine_dir.exists() and not any(quarantine_dir.iterdir()) else None
            raise HTTPException(
                status_code=503,
                detail=f"Document deletion was cancelled because the remaining knowledge index could not be rebuilt: {exc}",
                headers={"Retry-After": "5"},
            ) from exc
        except (RAGApplicationError, OSError) as exc:
            for source, destination in reversed(moved):
                if destination.exists():
                    destination.replace(source)
            if quarantine_dir.exists() and not any(quarantine_dir.iterdir()):
                quarantine_dir.rmdir()
            if isinstance(exc, RAGApplicationError):
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            raise HTTPException(status_code=500, detail="Document deletion failed and was rolled back.") from exc

    @app.post("/v1/workspaces/{workspace_id}/conversations/{conversation_id}/query", response_model=QueryResponseEnvelope)
    def workspace_query(workspace_id: str, conversation_id: str, request: QueryRequest) -> dict:
        _require_workspace(store, workspace_id)
        try:
            store.require_conversation(workspace_id, conversation_id)
        except ConversationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        # Guard before building the agent or calling the LLM so empty workspaces consume zero model tokens.
        if store.document_count(workspace_id) == 0:
            raise HTTPException(status_code=409, detail="Upload and index at least one document before starting a conversation.")

        try:
            history_rows = store.list_messages(
                workspace_id,
                conversation_id,
                limit=settings.conversation_history_messages,
            )
            history = _history_for_prompt(history_rows, settings.max_history_chars)
            workspace_agent = build_workspace_agent(workspace_id, store)
            response = workspace_agent.run(request.query, history=history, knowledge_available=True)
            store.add_turn(workspace_id, conversation_id, request.query.strip(), response.model_dump(mode="json"))
            return {"conversation_id": conversation_id, "response": response}
        except GenerationError as exc:
            raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "5"}) from exc
        except RAGApplicationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v1/query", response_model=AgentResponse, deprecated=True)
    def legacy_query(request: QueryRequest) -> AgentResponse:
        """Keep the original endpoint for backwards compatibility with developer tooling."""
        if app.state.legacy_agent is None:
            raise HTTPException(status_code=410, detail="Use the workspace conversation endpoint for user chat.")
        try:
            return app.state.legacy_agent.run(request.query)
        except GenerationError as exc:
            raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "5"}) from exc
        except RAGApplicationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/v1/report")
    def report(request: ReportRequest) -> Response:
        try:
            if not request.response.answer.strip():
                raise RAGApplicationError("there is no completed answer to export")
            pdf_bytes = build_report_pdf(request.response)
        except RAGApplicationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="tungelligence-report.pdf"', "Cache-Control": "no-store"},
        )

    return app


def _require_workspace(store: WorkspaceStore, workspace_id: str) -> None:
    try:
        store.require_workspace(workspace_id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _workspace_state(store: WorkspaceStore, workspace_id: str) -> dict:
    row = store.require_workspace(workspace_id)
    workspace_rows = [item for item in store.list_workspaces() if item["id"] == workspace_id]
    workspace = workspace_rows[0]
    return {
        "workspace": workspace,
        "conversations": store.list_conversations(workspace_id),
        "documents": store.list_documents(workspace_id),
    }


def _history_for_prompt(rows: list[dict], max_chars: int) -> list[ChatMessage]:
    """Keep recent turns bounded so conversation memory cannot grow without limit."""
    selected: list[ChatMessage] = []
    used = 0
    for row in reversed(rows):
        content = str(row["content"])
        if used + len(content) > max_chars:
            break
        selected.append(ChatMessage(id=row["id"], role=row["role"], content=content, created_at=row["created_at"]))
        used += len(content)
    selected.reverse()
    return selected


app = create_app()
