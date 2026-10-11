from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.workspaces.store import WorkspaceStore


def build_client(tmp_path: Path) -> TestClient:
    store = WorkspaceStore(tmp_path / "app.db", tmp_path / "workspaces")
    return TestClient(create_app(workspace_store=store))


def test_workspace_lifecycle_and_empty_chat_guard(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    response = client.post("/v1/workspaces", json={"name": "Research"})
    assert response.status_code == 201
    workspace = response.json()

    conversations = client.get(f"/v1/workspaces/{workspace['id']}/conversations")
    conversation_id = conversations.json()[0]["id"]

    response = client.post(
        f"/v1/workspaces/{workspace['id']}/conversations/{conversation_id}/query",
        json={"query": "Hello"},
    )
    assert response.status_code == 409
    assert "Upload and index" in response.json()["detail"]


def test_workspace_documents_endpoint_uses_indexing_service(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)

    workspace = client.post("/v1/workspaces", json={"name": "Docs"}).json()

    import app.api.main as main_module
    monkeypatch.setattr(
        main_module,
        "rebuild_workspace_index",
        lambda workspace_id, store, settings: [
            {"id": "1", "file_name": "policy.md", "size_bytes": 12, "chunk_count": 2, "indexed_at": "2026-01-01T00:00:00Z"}
        ],
    )
    response = client.post(
        f"/v1/workspaces/{workspace['id']}/documents",
        files={"files": ("policy.md", b"# Policy\n20 days")},
    )
    assert response.status_code == 200
    assert response.json()[0]["file_name"] == "policy.md"

class RecordingAgent:
    def __init__(self):
        self.calls = []

    def run(self, query, history=None, knowledge_available=True):
        from app.validation.schemas import AgentResponse
        self.calls.append((query, history or []))
        return AgentResponse(answer=f"Answer to: {query}", action="retrieve", query=query, confidence=0.9)


def test_chat_persists_and_reloads_conversation_context(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post("/v1/workspaces", json={"name": "Chat"}).json()
    conversation_id = client.get(f"/v1/workspaces/{workspace['id']}/conversations").json()[0]["id"]

    # Seed one indexed document in the workspace metadata so the API guard allows chat.
    store = client.app.state.workspace_store
    store.replace_documents(workspace["id"], [{"file_name": "policy.md", "size_bytes": 10, "chunk_count": 1}])

    recording_agent = RecordingAgent()
    monkeypatch.setattr("app.api.main.build_workspace_agent", lambda workspace_id, workspace_store: recording_agent)

    first = client.post(
        f"/v1/workspaces/{workspace['id']}/conversations/{conversation_id}/query",
        json={"query": "What is the policy?"},
    )
    assert first.status_code == 200

    second = client.post(
        f"/v1/workspaces/{workspace['id']}/conversations/{conversation_id}/query",
        json={"query": "Can you explain that?"},
    )
    assert second.status_code == 200
    assert len(recording_agent.calls) == 2
    assert recording_agent.calls[1][1][0].content == "What is the policy?"
    assert recording_agent.calls[1][1][1].content == "Answer to: What is the policy?"

    loaded = client.get(f"/v1/workspaces/{workspace['id']}/conversations/{conversation_id}/messages")
    assert len(loaded.json()) == 4


def test_upload_sanitizes_filename_and_rejects_unsupported_files(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post("/v1/workspaces", json={"name": "Upload"}).json()

    import app.api.main as main_module
    monkeypatch.setattr(main_module, "rebuild_workspace_index", lambda workspace_id, store, settings: [])
    response = client.post(
        f"/v1/workspaces/{workspace['id']}/documents",
        files={"files": ("../../safe.md", b"content")},
    )
    assert response.status_code == 200
    assert (tmp_path / "workspaces" / workspace["id"] / "raw" / "safe.md").exists()

    response = client.post(
        f"/v1/workspaces/{workspace['id']}/documents",
        files={"files": ("malware.exe", b"no")},
    )
    assert response.status_code == 415


def test_delete_workspace_endpoint(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    first = client.post('/v1/workspaces', json={'name': 'Delete Me'}).json()
    second = client.post('/v1/workspaces', json={'name': 'Keep Me'}).json()

    response = client.delete(f"/v1/workspaces/{first['id']}")
    assert response.status_code == 204
    assert all(item['id'] != first['id'] for item in client.get('/v1/workspaces').json())
    assert any(item['id'] == second['id'] for item in client.get('/v1/workspaces').json())
    assert client.get(f"/v1/workspaces/{first['id']}").status_code == 404


def test_upload_reports_missing_indexing_backend_without_500(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post('/v1/workspaces', json={'name': 'Backend Error'}).json()

    import app.api.main as main_module
    from app.core.exceptions import EmbeddingError

    def fail_index(*_args, **_kwargs):
        raise EmbeddingError('sentence-transformers is unavailable')

    monkeypatch.setattr(main_module, 'rebuild_workspace_index', fail_index)
    response = client.post(
        f"/v1/workspaces/{workspace['id']}/documents",
        files={'files': ('policy.pdf', b'not-a-real-pdf')},
    )

    assert response.status_code == 503
    assert 'indexing is unavailable' in response.json()['detail']
    assert list((tmp_path / 'workspaces' / workspace['id'] / 'raw').iterdir()) == []


def test_upload_unexpected_failure_is_sanitized(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post('/v1/workspaces', json={'name': 'Unexpected Error'}).json()

    import app.api.main as main_module

    monkeypatch.setattr(main_module, 'rebuild_workspace_index', lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('secret internal path'))) 
    response = client.post(
        f"/v1/workspaces/{workspace['id']}/documents",
        files={'files': ('notes.md', b'content')},
    )

    assert response.status_code == 500
    assert 'secret internal path' not in response.json()['detail']
    assert 'server log' in response.json()['detail']


def test_workspace_processed_dir_is_created(tmp_path):
    from app.workspaces.store import WorkspaceStore
    store = WorkspaceStore(tmp_path / "db.sqlite", tmp_path / "workspaces")
    workspace = store.create_workspace("Processed")
    processed_dir = store.processed_dir(workspace["id"])
    assert processed_dir.exists()
    assert processed_dir.name == "processed"


def test_delete_conversation_endpoint_cascades_messages(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post("/v1/workspaces", json={"name": "Chat Delete"}).json()
    conversation = client.get(f"/v1/workspaces/{workspace['id']}/conversations").json()[0]
    store = client.app.state.workspace_store
    store.replace_documents(workspace["id"], [{"file_name": "policy.md", "size_bytes": 10, "chunk_count": 1}])

    class RecordingAgent:
        def run(self, query, history=None, knowledge_available=True):
            from app.validation.schemas import AgentResponse
            return AgentResponse(answer=f"Answer to: {query}", action="retrieve", query=query, confidence=0.9)

    monkeypatch.setattr("app.api.main.build_workspace_agent", lambda *_args, **_kwargs: RecordingAgent())
    response = client.post(
        f"/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}/query",
        json={"query": "Test"},
    )
    assert response.status_code == 200
    assert client.get(f"/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}/messages").json()

    response = client.delete(f"/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}")
    assert response.status_code == 204
    assert client.get(f"/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}/messages").status_code == 404
    assert all(item["id"] != conversation["id"] for item in client.get(f"/v1/workspaces/{workspace['id']}/conversations").json())


def test_reset_conversation_clears_messages_but_preserves_conversation(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post("/v1/workspaces", json={"name": "Reset"}).json()
    conversation = client.get(f"/v1/workspaces/{workspace['id']}/conversations").json()[0]
    store = client.app.state.workspace_store
    store.replace_documents(workspace["id"], [{"file_name": "policy.md", "size_bytes": 10, "chunk_count": 1}])

    class RecordingAgent:
        def run(self, query, history=None, knowledge_available=True):
            from app.validation.schemas import AgentResponse
            return AgentResponse(answer=f"Answer to: {query}", action="retrieve", query=query, confidence=0.9)

    monkeypatch.setattr("app.api.main.build_workspace_agent", lambda *_args, **_kwargs: RecordingAgent())
    response = client.post(
        f"/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}/query",
        json={"query": "Test"},
    )
    assert response.status_code == 200
    assert len(client.get(f"/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}/messages").json()) == 2

    response = client.post(f"/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}/reset")
    assert response.status_code == 204
    assert client.get(f"/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}").status_code == 405
    conversations = client.get(f"/v1/workspaces/{workspace['id']}/conversations").json()
    assert conversations[0]["id"] == conversation["id"]
    assert client.get(f"/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}/messages").json() == []

def test_delete_selected_documents_removes_files_database_and_rebuilds_index(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post("/v1/workspaces", json={"name": "Document Delete"}).json()
    workspace_id = workspace["id"]
    root = tmp_path / "workspaces" / workspace_id
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "keep.md").write_text("keep this document", encoding="utf-8")
    (raw / "remove.md").write_text("remove this document", encoding="utf-8")

    store = client.app.state.workspace_store
    store.replace_documents(
        workspace_id,
        [
            {"file_name": "keep.md", "size_bytes": 18, "chunk_count": 1},
            {"file_name": "remove.md", "size_bytes": 21, "chunk_count": 1},
        ],
    )
    selected = store.list_documents(workspace_id)
    remove_id = next(item["id"] for item in selected if item["file_name"] == "remove.md")

    import app.api.main as main_module

    def fake_rebuild(workspace_id, store, settings):
        result = [{"id": "new-id", "file_name": "keep.md", "size_bytes": 18, "chunk_count": 1, "indexed_at": "2026-01-01T00:00:00Z"}]
        store.replace_documents(workspace_id, result)
        return store.list_documents(workspace_id)

    monkeypatch.setattr(main_module, "rebuild_workspace_index", fake_rebuild)

    response = client.post(
        f"/v1/workspaces/{workspace_id}/documents/delete",
        json={"document_ids": [remove_id]},
    )

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 1
    assert response.json()["deleted_files"] == ["remove.md"]
    assert not (raw / "remove.md").exists()
    assert (raw / "keep.md").exists()
    assert [item["file_name"] for item in store.list_documents(workspace_id)] == ["keep.md"]
    assert not any(root.glob(".delete-*"))


def test_delete_multiple_documents_clears_entire_workspace_index_when_last_files_are_removed(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post("/v1/workspaces", json={"name": "Delete All Documents"}).json()
    workspace_id = workspace["id"]
    root = tmp_path / "workspaces" / workspace_id
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "a.txt").write_text("alpha", encoding="utf-8")
    (raw / "b.txt").write_text("bravo", encoding="utf-8")

    store = client.app.state.workspace_store
    store.replace_documents(
        workspace_id,
        [
            {"file_name": "a.txt", "size_bytes": 5, "chunk_count": 1},
            {"file_name": "b.txt", "size_bytes": 5, "chunk_count": 1},
        ],
    )
    docs = store.list_documents(workspace_id)

    from app.api import main as main_module
    response = client.post(
        f"/v1/workspaces/{workspace_id}/documents/delete",
        json={"document_ids": [item["id"] for item in docs]},
    )

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 2
    assert store.list_documents(workspace_id) == []
    assert list(raw.iterdir()) == []
    assert not (root / "vector" / "index.faiss").exists()
    assert not (root / "vector" / "index.npy").exists()
    assert not (root / "vector" / "chunks.json").exists()
    assert not (root / "processed" / "chunks.jsonl").exists()


def test_delete_documents_rolls_back_source_files_when_rebuild_fails(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post("/v1/workspaces", json={"name": "Delete Rollback"}).json()
    workspace_id = workspace["id"]
    root = tmp_path / "workspaces" / workspace_id
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "keep.md").write_text("keep", encoding="utf-8")
    (raw / "remove.md").write_text("remove", encoding="utf-8")

    store = client.app.state.workspace_store
    store.replace_documents(
        workspace_id,
        [
            {"file_name": "keep.md", "size_bytes": 4, "chunk_count": 1},
            {"file_name": "remove.md", "size_bytes": 6, "chunk_count": 1},
        ],
    )
    remove_id = next(item["id"] for item in store.list_documents(workspace_id) if item["file_name"] == "remove.md")

    import app.api.main as main_module
    from app.core.exceptions import EmbeddingError
    monkeypatch.setattr(main_module, "rebuild_workspace_index", lambda *_args, **_kwargs: (_ for _ in ()).throw(EmbeddingError("backend unavailable")))

    response = client.post(
        f"/v1/workspaces/{workspace_id}/documents/delete",
        json={"document_ids": [remove_id]},
    )

    assert response.status_code == 503
    assert (raw / "remove.md").exists()
    assert {item["file_name"] for item in store.list_documents(workspace_id)} == {"keep.md", "remove.md"}
    assert not any(root.glob(".delete-*"))



def test_mixed_valid_and_invalid_upload_does_not_change_workspace(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post("/v1/workspaces", json={"name": "Transactional upload"}).json()
    workspace_id = workspace["id"]
    raw = tmp_path / "workspaces" / workspace_id / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    existing = raw / "existing.md"
    existing.write_text("existing content", encoding="utf-8")
    store = client.app.state.workspace_store
    store.replace_documents(workspace_id, [{"file_name": "existing.md", "size_bytes": 16, "chunk_count": 1}])
    previous_id = store.list_documents(workspace_id)[0]["id"]

    import app.api.main as main_module
    monkeypatch.setattr(
        main_module,
        "rebuild_workspace_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("indexing must not start for invalid batch")),
    )

    response = client.post(
        f"/v1/workspaces/{workspace_id}/documents",
        files=[
            ("files", ("new.md", b"new file content", "text/markdown")),
            ("files", ("unsupported.exe", b"not allowed", "application/octet-stream")),
        ],
    )

    assert response.status_code == 415
    assert existing.read_text(encoding="utf-8") == "existing content"
    assert not (raw / "new.md").exists()
    documents = store.list_documents(workspace_id)
    assert len(documents) == 1 and documents[0]["id"] == previous_id
    assert not list((tmp_path / "workspaces" / workspace_id).glob(".upload-*"))


def test_failed_reupload_restores_the_previous_same_name_file(tmp_path: Path, monkeypatch) -> None:
    client = build_client(tmp_path)
    workspace = client.post("/v1/workspaces", json={"name": "Restore old file"}).json()
    workspace_id = workspace["id"]
    raw = tmp_path / "workspaces" / workspace_id / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    original = raw / "policy.md"
    original.write_text("original policy", encoding="utf-8")
    store = client.app.state.workspace_store
    store.replace_documents(workspace_id, [{"file_name": "policy.md", "size_bytes": 15, "chunk_count": 1}])
    old_record = store.list_documents(workspace_id)[0]

    import app.api.main as main_module
    from app.core.exceptions import EmbeddingError

    def fail_index(*_args, **_kwargs):
        raise EmbeddingError("test embedding failure")

    monkeypatch.setattr(main_module, "rebuild_workspace_index", fail_index)
    response = client.post(
        f"/v1/workspaces/{workspace_id}/documents",
        files={"files": ("policy.md", b"replacement policy", "text/markdown")},
    )

    assert response.status_code == 503
    assert original.read_text(encoding="utf-8") == "original policy"
    current_record = store.list_documents(workspace_id)[0]
    assert current_record["id"] == old_record["id"]
    assert current_record["file_name"] == "policy.md"
    assert not list((tmp_path / "workspaces" / workspace_id).glob(".upload-*"))


def test_document_id_remains_stable_across_reindex_metadata_replacement(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "app.db", tmp_path / "workspaces")
    workspace = store.create_workspace("Stable IDs")
    workspace_id = workspace["id"]

    store.replace_documents(workspace_id, [{"file_name": "policy.md", "size_bytes": 10, "chunk_count": 1}])
    first = store.list_documents(workspace_id)[0]
    store.replace_documents(workspace_id, [{"file_name": "policy.md", "size_bytes": 20, "chunk_count": 3}])
    second = store.list_documents(workspace_id)[0]

    assert second["id"] == first["id"]
    assert second["size_bytes"] == 20
    assert second["chunk_count"] == 3
