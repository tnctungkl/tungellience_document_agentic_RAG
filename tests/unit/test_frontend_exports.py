from pathlib import Path


def test_save_picker_is_called_before_network_request() -> None:
    js = (Path(__file__).parents[2] / "app" / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    picker_pos = js.index("window.showSaveFilePicker")
    fetch_pos = js.index('fetch("/v1/report"')
    assert picker_pos < fetch_pos


def test_loading_ui_contains_neon_palette() -> None:
    css = (Path(__file__).parents[2] / "app" / "ui" / "static" / "styles.css").read_text(encoding="utf-8")
    for color in ("#ff365f", "#b449ff", "#3f8cff", "#54eaff", "#ffe45b"):
        assert color in css


def test_report_controls_and_print_flow_are_present() -> None:
    root = Path(__file__).parents[2] / "app" / "ui" / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert 'id="export-button"' in html
    assert 'id="print-button"' in html
    assert 'id="new-document-button"' in html
    assert 'function printReport()' in js
    assert 'printWindow.print()' in js
    assert 'showSaveFilePicker' in js


def test_conversation_delete_and_surface_reset_flow_are_present() -> None:
    root = Path(__file__).parents[2] / "app" / "ui" / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert 'id="delete-conversation-modal"' in html
    assert 'data-delete-conversation-id' in js
    assert 'function clearConversationSurface' in js
    assert 'function startNewDocumentFlow' in js
    assert '/v1/workspaces/${state.workspaceId}/conversations/${conversationId}' in js
    assert 'method: "DELETE"' in js


def test_export_print_buttons_are_explicitly_separate_and_refresh_exists() -> None:
    root = Path(__file__).parents[2] / "app" / "ui" / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    css = (root / "styles.css").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")

    assert 'id="export-button"' in html
    assert 'id="print-button"' in html
    assert 'id="refresh-conversation"' in html
    assert '.report-actions { display: flex;' in css
    assert 'gap: 12px' in css
    assert 'flex-direction: row' in css
    assert '.report-button { flex: 1 1 0;' in css
    assert 'function resetCurrentConversation()' in js
    assert '/reset`' in js


def test_conversation_delete_button_is_rendered_with_dedicated_control() -> None:
    js = (Path(__file__).parents[2] / "app" / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'class="conversation-delete"' in js
    assert 'data-delete-conversation-id=' in js


def test_frontend_assets_are_cache_busted_and_legacy_blob_fallback_is_removed() -> None:
    root = Path(__file__).parents[2] / "app" / "ui" / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")

    assert '/ui-static/styles.css?v=1.5.4' in html
    assert '/ui-static/app.js?v=1.5.4' in html
    assert 'function downloadBlob(' not in js
    assert 'function exportReport()' in js
    assert 'function printReport()' in js


def test_document_delete_error_is_not_rendered_as_object_object() -> None:
    js = (Path(__file__).parents[2] / "app" / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'function formatApiError(payload, status)' in js
    assert 'JSON.stringify(detail)' in js
    assert 'throw new Error(formatApiError(payload, response.status))' in js


def test_document_delete_shows_purge_overlay_before_request_and_keeps_it_visible() -> None:
    js = (Path(__file__).parents[2] / "app" / "ui" / "static" / "app.js").read_text(encoding="utf-8")
    show_pos = js.index('showDeleteLoading(documents);')
    request_pos = js.index('`/v1/workspaces/${state.workspaceId}/documents/delete`', show_pos)
    delay_pos = js.index('const minimumLoadingMs = 900;', request_pos)
    assert show_pos < request_pos < delay_pos
