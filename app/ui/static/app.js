const state = {
  workspaceId: localStorage.getItem("tungelligence.workspaceId"),
  conversationId: localStorage.getItem("tungelligence.conversationId"),
  workspaces: [],
  workspace: null,
  conversations: [],
  documents: [],
  latestResponse: null,
  busy: false,
};

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.classList.add("visible");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove("visible"), 3400);
}

function setSelection(workspaceId, conversationId = null) {
  state.workspaceId = workspaceId;
  state.conversationId = conversationId;
  if (workspaceId) localStorage.setItem("tungelligence.workspaceId", workspaceId);
  if (conversationId) localStorage.setItem("tungelligence.conversationId", conversationId);
  else localStorage.removeItem("tungelligence.conversationId");
}

function formatApiError(payload, status) {
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map(item => item?.msg || item?.detail || String(item)).filter(Boolean);
    if (messages.length) return messages.join(" | ");
  }
  if (detail && typeof detail === "object") {
    try { return JSON.stringify(detail); } catch { return "The server returned an unreadable error object."; }
  }
  return `Request failed (${status}).`;
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 204) return null;
  const raw = await response.text();
  let payload = null;
  try { payload = raw ? JSON.parse(raw) : null; } catch { payload = null; }
  if (!response.ok) throw new Error(formatApiError(payload, response.status));
  return payload;
}

function renderWorkspaceList() {
  const list = $("#workspace-list");
  list.innerHTML = state.workspaces.length
    ? state.workspaces.map(workspace => `
      <div class="workspace-row ${workspace.id === state.workspaceId ? "active" : ""}">
        <button class="workspace-item" data-workspace-id="${escapeHtml(workspace.id)}" type="button">
          <span class="workspace-symbol">◈</span>
          <span class="workspace-item-body"><strong>${escapeHtml(workspace.name)}</strong><small>${workspace.document_count} docs · ${workspace.conversation_count} chats</small></span>
        </button>
        <button class="workspace-delete" data-delete-workspace-id="${escapeHtml(workspace.id)}" type="button" title="Delete workspace" aria-label="Delete workspace ${escapeHtml(workspace.name)}">×</button>
      </div>`).join("")
    : '<div class="sidebar-empty">No workspaces yet.</div>';
  list.querySelectorAll("[data-workspace-id]").forEach(button => button.addEventListener("click", () => selectWorkspace(button.dataset.workspaceId)));
  list.querySelectorAll("[data-delete-workspace-id]").forEach(button => button.addEventListener("click", (event) => {
    event.stopPropagation();
    openDeleteWorkspaceModal(button.dataset.deleteWorkspaceId);
  }));
}

function renderConversationList() {
  const list = $("#conversation-list");
  list.innerHTML = state.conversations.map(item => `
    <div class="conversation-row ${item.id === state.conversationId ? "active" : ""}">
      <button class="conversation-item" data-conversation-id="${escapeHtml(item.id)}" type="button">
        <span>◦</span><span>${escapeHtml(item.title)}</span>
      </button>
      <button class="conversation-delete" data-delete-conversation-id="${escapeHtml(item.id)}" type="button" title="Delete conversation" aria-label="Delete conversation ${escapeHtml(item.title)}">×</button>
    </div>`).join("");
  list.querySelectorAll("[data-conversation-id]").forEach(button => button.addEventListener("click", () => selectConversation(button.dataset.conversationId)));
  list.querySelectorAll("[data-delete-conversation-id]").forEach(button => button.addEventListener("click", (event) => {
    event.stopPropagation();
    openDeleteConversationModal(button.dataset.deleteConversationId);
  }));
}

function renderDocuments() {
  const strip = $("#document-strip");
  const deleteButton = $("#delete-selected-documents");

  if (!state.documents.length) {
    strip.innerHTML = '<div class="empty-documents"><strong>No indexed documents</strong><span>Add PDF, DOCX, TXT or Markdown files to activate the agent.</span></div>';
    deleteButton.disabled = true;
    return;
  }

  strip.innerHTML = state.documents.map(doc => `
    <article class="document-chip" data-document-id="${escapeHtml(doc.id)}">
      <label class="document-select" title="Select ${escapeHtml(doc.file_name)}">
        <input class="document-checkbox" data-document-id="${escapeHtml(doc.id)}" type="checkbox" aria-label="Select ${escapeHtml(doc.file_name)}">
        <span class="document-checkmark"></span>
      </label>
      <span class="document-icon">▧</span>
      <span class="document-info"><strong title="${escapeHtml(doc.file_name)}">${escapeHtml(doc.file_name)}</strong><small>${doc.chunk_count} chunks</small></span>
      <button class="document-delete" data-document-id="${escapeHtml(doc.id)}" type="button" title="Delete ${escapeHtml(doc.file_name)}" aria-label="Delete ${escapeHtml(doc.file_name)}">×</button>
      <span class="indexed-dot">●</span>
    </article>`).join("");

  strip.querySelectorAll(".document-checkbox").forEach(input => {
    input.addEventListener("change", updateDocumentSelection);
  });
  strip.querySelectorAll("[data-document-id].document-delete").forEach(button => {
    button.addEventListener("click", event => {
      event.stopPropagation();
      const checkbox = strip.querySelector(`.document-checkbox[data-document-id="${CSS.escape(button.dataset.documentId)}"]`);
      if (checkbox) checkbox.checked = true;
      updateDocumentSelection();
      openDeleteDocumentModal();
    });
  });
  updateDocumentSelection();
}

function getSelectedDocumentIds() {
  return [...document.querySelectorAll(".document-checkbox:checked")]
    .map(input => input.dataset.documentId)
    .filter(Boolean);
}

function getSelectedDocuments() {
  const ids = new Set(getSelectedDocumentIds());
  return state.documents.filter(documentItem => ids.has(documentItem.id));
}

function updateDocumentSelection() {
  const selected = getSelectedDocumentIds();
  $("#delete-selected-documents").disabled = !selected.length || state.busy;
}

function renderConversation(messages) {
  const target = $("#conversation");
  if (!messages.length) {
    target.innerHTML = `
      <div class="welcome-card">
        <div class="welcome-icon">✦</div>
        <div class="welcome-kicker">AGENT ONLINE</div>
        <h2>Talk to your knowledge base.</h2>
        <p>Tungelligence can answer questions, explain concepts, summarize, compare documents, translate, extract information, perform deterministic document analysis, and help draft content — while keeping factual answers grounded in your workspace.</p>
        <div class="capability-row">
          <span>Q&amp;A</span><span>Summarize</span><span>Compare</span><span>Extract</span><span>Translate</span><span>Analyze</span>
        </div>
        <div class="suggestion-grid">
          <button class="suggestion-chip" data-query="Summarize the main points of the document." type="button">Summarize</button>
          <button class="suggestion-chip" data-query="What is the document mainly about?" type="button">Explain the topic</button>
          <button class="suggestion-chip" data-query="What is the most frequent letter in the documents?" type="button">Analyze text</button>
          <button class="suggestion-chip" data-query="Extract the most important facts from the document." type="button">Extract facts</button>
        </div>
      </div>`;
    target.querySelectorAll(".suggestion-chip").forEach(button => button.addEventListener("click", () => {
      $("#query").value = button.dataset.query || "";
      $("#query").focus();
    }));
    return;
  }
  target.innerHTML = messages.map(message => `
    <article class="message ${message.role}">
      <div class="message-meta">${message.role === "user" ? "YOU" : "TUNGELLIGENCE AGENT"}</div>
      <div class="message-bubble">${escapeHtml(message.content)}</div>
    </article>`).join("");
  target.scrollTop = target.scrollHeight;
}

function renderResult(response) {
  state.latestResponse = response;
  $("#result-empty").classList.add("hidden");
  $("#result-content").classList.remove("hidden");
  $("#export-button").disabled = false;
  $("#print-button").disabled = false;
  $("#confidence-value").textContent = Number(response.confidence).toFixed(2);
  $("#action-value").textContent = String(response.action).replaceAll("_", " ");
  $("#answer-text").textContent = response.answer;
  const sources = response.citations || [];
  $("#sources-list").innerHTML = sources.length
    ? sources.map(c => `<div class="source-item"><div><strong>${escapeHtml(c.source)}</strong><small>Chunk ${escapeHtml(c.chunk_id)}</small></div><span>${Number(c.score).toFixed(3)}</span></div>`).join("")
    : '<div class="source-item"><div><strong>Workspace-grounded response</strong><small>No individual retrieval citation was required for this result.</small></div></div>';
}

function resetResult() {
  state.latestResponse = null;
  $("#result-empty").classList.remove("hidden");
  $("#result-content").classList.add("hidden");
  $("#export-button").disabled = true;
  $("#print-button").disabled = true;
}

function updateComposer() {
  const ready = Boolean(state.workspaceId && state.documents.length);
  const query = $("#query");
  const button = $("#ask-button");
  const lock = $("#knowledge-lock");
  query.disabled = !ready || state.busy;
  button.disabled = !ready || state.busy;
  query.placeholder = ready ? "Ask, analyze, summarize, compare, translate, or request help with your documents..." : "Upload documents to start chatting...";
  lock.classList.toggle("hidden", ready);
  $("#composer-hint").textContent = state.busy
    ? "Agent is working · retrieving context · reasoning over workspace evidence..."
    : ready
      ? `Workspace-grounded agent · ${state.documents.length} document${state.documents.length === 1 ? "" : "s"} available`
      : "Knowledge base required · no model request will be sent";
}

async function loadWorkspaces() {
  state.workspaces = await api("/v1/workspaces");
  renderWorkspaceList();
  if (!state.workspaces.length) {
    await createWorkspace("My Knowledge Base");
    return;
  }
  if (!state.workspaceId || !state.workspaces.some(item => item.id === state.workspaceId)) setSelection(state.workspaces[0].id);
  await selectWorkspace(state.workspaceId);
}

async function selectWorkspace(workspaceId) {
  clearConversationSurface("Loading conversation...");
  const payload = await api(`/v1/workspaces/${workspaceId}`);
  state.workspace = payload.workspace;
  state.documents = payload.documents;
  state.conversations = payload.conversations;
  const existingConversation = state.conversationId && state.conversations.some(item => item.id === state.conversationId) ? state.conversationId : state.conversations[0]?.id;
  setSelection(workspaceId, existingConversation || null);
  $("#workspace-title").textContent = state.workspace.name;
  $("#document-count-badge").textContent = `${state.documents.length} document${state.documents.length === 1 ? "" : "s"}`;
  $("#rename-workspace-button").disabled = false;
  renderWorkspaceList(); renderConversationList(); renderDocuments(); resetResult(); updateComposer();
  if (state.conversationId) await loadConversation(state.conversationId);
  $("#sidebar").classList.remove("mobile-open");
}

async function createWorkspace(name) {
  const payload = await api("/v1/workspaces", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
  state.workspaces = await api("/v1/workspaces");
  setSelection(payload.id);
  renderWorkspaceList();
  await selectWorkspace(payload.id);
}

async function createConversation() {
  if (!state.workspaceId || state.busy) return;
  const previousConversationId = state.conversationId;
  clearConversationSurface("New conversation");
  try {
    const conversation = await api(`/v1/workspaces/${state.workspaceId}/conversations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: "New conversation" }) });
    state.conversations = await api(`/v1/workspaces/${state.workspaceId}/conversations`);
    setSelection(state.workspaceId, conversation.id);
    renderConversationList();
    $("#conversation-title").textContent = conversation.title;
    renderConversation([]);
    resetResult();
  } catch (error) {
    setSelection(state.workspaceId, previousConversationId);
    if (previousConversationId) await loadConversation(previousConversationId);
    toast(error.message, true);
  }
}

async function selectConversation(conversationId) {
  if (!state.workspaceId || conversationId === state.conversationId) return loadConversation(conversationId);
  setSelection(state.workspaceId, conversationId);
  renderConversationList();
  clearConversationSurface("Loading conversation...");
  await loadConversation(conversationId);
}

function clearConversationSurface(title = "New conversation") {
  state.latestResponse = null;
  resetResult();
  $("#conversation-title").textContent = title;
  renderConversation([]);
  updateComposer();
}

async function loadConversation(conversationId) {
  try {
    const messages = await api(`/v1/workspaces/${state.workspaceId}/conversations/${conversationId}/messages`);
    const item = state.conversations.find(c => c.id === conversationId);
    $("#conversation-title").textContent = item?.title || "Conversation";
    renderConversation(messages);
    const latest = [...messages].reverse().find(m => m.response)?.response;
    if (latest) renderResult(latest);
  } catch (error) { toast(error.message, true); }
}

async function resetCurrentConversation() {
  if (!state.workspaceId || !state.conversationId || state.busy) return;

  const conversationId = state.conversationId;
  try {
    state.busy = true;
    updateComposer();
    await api(
      `/v1/workspaces/${state.workspaceId}/conversations/${conversationId}/reset`,
      { method: "POST" },
    );

    // Keep the conversation itself, but clear its persistent messages and transient UI result.
    clearConversationSurface("New conversation");
    state.conversations = await api(
      `/v1/workspaces/${state.workspaceId}/conversations`,
    );
    renderConversationList();
    toast("Conversation reset. The conversation was kept.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    state.busy = false;
    updateComposer();
  }
}

function startNewDocumentFlow() {
  if (!state.workspaceId || state.busy) return;
  resetResult();
  $("#upload-stage").textContent = "Ready for new document intake...";
  $("#file-input").value = "";
  $("#file-input").click();
}

const uploadStages = [
  "Uploading document payload...",
  "Extracting text and document structure...",
  "Cleaning and segmenting content...",
  "Generating embeddings and building the knowledge index...",
  "Finalizing workspace intelligence...",
];

let uploadStageTimer = null;

function showUploadOverlay(files) {
  $("#file-input").disabled = true;
  $(".upload-button").classList.add("loading");
  $("#upload-loading").classList.remove("hidden");
  $("#upload-file-list").innerHTML = [...files].map(file => `
    <div class="upload-file-row"><span class="file-status">◉</span><strong title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</strong><span>${Math.ceil(file.size / 1024)} KB</span></div>`).join("");
  let stage = 0;
  const updateStage = () => {
    $("#upload-stage").textContent = uploadStages[stage];
    $("#upload-loading-text").textContent = uploadStages[stage];
    stage = Math.min(stage + 1, uploadStages.length - 1);
  };
  updateStage();
  uploadStageTimer = setInterval(updateStage, 1100);
}

function hideUploadOverlay() {
  clearInterval(uploadStageTimer);
  uploadStageTimer = null;
  $("#file-input").disabled = false;
  $(".upload-button").classList.remove("loading");
  $("#upload-loading").classList.add("hidden");
}

async function uploadFiles(files) {
  if (!state.workspaceId || !files.length) return;
  resetResult();
  const form = new FormData();
  [...files].forEach(file => form.append("files", file));
  showUploadOverlay(files);
  try {
    const documents = await api(`/v1/workspaces/${state.workspaceId}/documents`, { method: "POST", body: form });
    state.documents = documents;
    state.workspaces = await api("/v1/workspaces");
    renderWorkspaceList(); renderDocuments();
    $("#document-count-badge").textContent = `${documents.length} document${documents.length === 1 ? "" : "s"}`;
    updateComposer();
    toast(`${documents.length} document${documents.length === 1 ? "" : "s"} indexed successfully.`);
  } catch (error) {
    const suffix = error.message.includes("indexing is unavailable")
      ? " Install the configured embedding/vector dependencies or switch to offline Hash + NumPy mode."
      : "";
    toast(`${error.message}${suffix}`, true);
  } finally {
    $("#file-input").value = "";
    hideUploadOverlay();
  }
}

function appendOptimisticTurn(userText, answer) {
  const target = $("#conversation");
  $(".welcome-card")?.remove();
  target.insertAdjacentHTML("beforeend", `<article class="message user"><div class="message-meta">YOU</div><div class="message-bubble">${escapeHtml(userText)}</div></article><article class="message assistant"><div class="message-meta">TUNGELLIGENCE AGENT</div><div class="message-bubble">${escapeHtml(answer)}</div></article>`);
  target.scrollTop = target.scrollHeight;
}

async function askAgent(query) {
  if (state.busy || !state.workspaceId || !state.conversationId || !query.trim() || !state.documents.length) return;
  state.busy = true;
  updateComposer();
  try {
    const envelope = await api(`/v1/workspaces/${state.workspaceId}/conversations/${state.conversationId}/query`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: query.trim() })
    });
    appendOptimisticTurn(query.trim(), envelope.response.answer);
    renderResult(envelope.response);
    $("#query").value = "";
    state.conversations = await api(`/v1/workspaces/${state.workspaceId}/conversations`);
    renderConversationList();
    const selected = state.conversations.find(item => item.id === state.conversationId);
    if (selected) $("#conversation-title").textContent = selected.title;
  } catch (error) {
    toast(error.message, true);
    if (error.message.toLowerCase().includes("upload and index")) {
      state.documents = []; renderDocuments();
    }
  } finally {
    state.busy = false;
    updateComposer();
  }
}

// Export = Save As. The browser asks the user where to store the generated PDF.
async function exportReport() {
  if (!state.latestResponse?.answer?.trim()) return toast("No completed result is available for export.", true);

  const filename = buildReportFilename();
  try {
    if (!("showSaveFilePicker" in window) || !window.isSecureContext) {
      throw new Error("Your browser does not support the secure Save As dialog used by Export. Use a modern Chromium-based browser or localhost.");
    }

    // Request the destination while the click gesture is active.
    const saveHandle = await window.showSaveFilePicker({
      suggestedName: filename,
      types: [{ description: "PDF report", accept: { "application/pdf": [".pdf"] } }],
    });

    const response = await fetch("/v1/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ response: state.latestResponse }),
    });
    const payload = response.ok ? null : await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.detail || `Report generation failed (${response.status}).`);

    const blob = await response.blob();
    const writable = await saveHandle.createWritable();
    await writable.write(blob);
    await writable.close();
    toast("PDF report exported successfully.");
  } catch (error) {
    if (error?.name !== "AbortError") toast(error.message || "Report export failed.", true);
  }
}

// Print = send the rendered report to the browser print dialog and the user's selected printer.
function printReport() {
  if (!state.latestResponse?.answer?.trim()) return toast("No completed result is available for printing.", true);

  const response = state.latestResponse;
  const printWindow = window.open("", "_blank", "width=1000,height=800");
  if (!printWindow) {
    toast("The print window was blocked by the browser. Allow pop-ups for Tungelligence and try again.", true);
    return;
  }

  const citations = (response.citations || []).map(citation => `
    <tr><td>${escapeHtml(citation.source)}</td><td>${Number(citation.score).toFixed(3)}</td><td>${escapeHtml(citation.chunk_id)}</td></tr>`
  ).join("");

  printWindow.document.write(`<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Tungelligence Report</title>
<style>
  @page { size: A4; margin: 16mm; }
  body { font-family: Arial, sans-serif; color: #18212b; margin: 0; line-height: 1.55; }
  header { border-bottom: 2px solid #1f7896; padding-bottom: 12px; margin-bottom: 18px; }
  h1 { margin: 0; font-size: 24px; } h2 { margin: 4px 0 0; font-size: 13px; color: #536475; font-weight: 500; }
  .meta { display: grid; grid-template-columns: 110px 1fr; gap: 7px 14px; background: #f3f6f9; border: 1px solid #d8e0e8; padding: 12px; }
  .label { font-weight: 700; color: #5d6c7b; } .section { margin-top: 18px; }
  .answer { white-space: pre-wrap; } table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th, td { border: 1px solid #d8e0e8; text-align: left; padding: 7px; font-size: 12px; }
  th { background: #edf2f6; } footer { margin-top: 24px; color: #657687; font-size: 10px; border-top: 1px solid #d8e0e8; padding-top: 8px; }
</style></head><body>
<header><h1>Tungelligence</h1><h2>Agentic RAG Analysis Report</h2></header>
<div class="meta">
<div class="label">Action</div><div>${escapeHtml(response.action)}</div>
<div class="label">Confidence</div><div>${Number(response.confidence).toFixed(2)}</div>
<div class="label">Query</div><div>${escapeHtml(response.query)}</div>
</div>
<section class="section"><div class="label">Answer</div><div class="answer">${escapeHtml(response.answer)}</div></section>
${response.rewritten_query ? `<section class="section"><div class="label">Rewritten Query</div><div>${escapeHtml(response.rewritten_query)}</div></section>` : ""}
<section class="section"><div class="label">Sources</div>${citations ? `<table><thead><tr><th>Source</th><th>Score</th><th>Chunk</th></tr></thead><tbody>${citations}</tbody></table>` : "<p>No citations were returned.</p>"}</section>
<footer>Tungelligence Agentic RAG · Printed from the application</footer>
</body></html>`);
  printWindow.document.close();
  printWindow.focus();
  let printed = false;
  const triggerPrint = () => {
    if (printed || printWindow.closed) return;
    printed = true;
    printWindow.print();
  };
  printWindow.addEventListener("load", triggerPrint, { once: true });
  setTimeout(triggerPrint, 450);
  printWindow.addEventListener("afterprint", () => printWindow.close(), { once: true });
}


function buildReportFilename() {
  const source = state.workspace?.name || "workspace";
  const safeName = source
    .normalize("NFKD")
    .replace(/[^a-zA-Z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase() || "workspace";
  return `tungelligence-${safeName}-report.pdf`;
}

async function renameWorkspace() {
  if (!state.workspaceId) return;
  const name = window.prompt("Workspace name", state.workspace?.name || "");
  if (!name?.trim()) return;
  try { await api(`/v1/workspaces/${state.workspaceId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) }); await loadWorkspaces(); toast("Workspace renamed."); }
  catch (error) { toast(error.message, true); }
}

let pendingDeleteWorkspaceId = null;
function openDeleteWorkspaceModal(workspaceId) {
  pendingDeleteWorkspaceId = workspaceId;
  const workspace = state.workspaces.find(item => item.id === workspaceId);
  if (!workspace) return;
  $("#delete-workspace-title").textContent = `Delete “${workspace.name}”?`;
  $("#delete-workspace-modal").classList.remove("hidden");
}
function closeDeleteWorkspaceModal() { pendingDeleteWorkspaceId = null; $("#delete-workspace-modal").classList.add("hidden"); }

async function deleteWorkspace() {
  const workspaceId = pendingDeleteWorkspaceId;
  if (!workspaceId) return;
  const deletedWorkspace = state.workspaces.find(item => item.id === workspaceId);
  try {
    $("#delete-confirm").disabled = true;
    await api(`/v1/workspaces/${workspaceId}`, { method: "DELETE" });
    closeDeleteWorkspaceModal();
    state.workspaces = await api("/v1/workspaces");
    localStorage.removeItem("tungelligence.conversationId");
    if (!state.workspaces.length) {
      state.workspaceId = null; state.conversationId = null; localStorage.removeItem("tungelligence.workspaceId");
      state.workspace = null; state.documents = []; state.conversations = [];
      $("#workspace-title").textContent = "No workspace selected"; $("#document-count-badge").textContent = "0 documents"; $("#rename-workspace-button").disabled = true;
      renderWorkspaceList(); renderConversationList(); renderDocuments(); resetResult(); updateComposer();
    } else {
      const nextId = state.workspaces.some(item => item.id === state.workspaceId) ? state.workspaceId : state.workspaces[0].id;
      setSelection(nextId); renderWorkspaceList(); await selectWorkspace(nextId);
    }
    toast(`Workspace “${deletedWorkspace?.name || ""}” deleted.`);
  } catch (error) { toast(error.message, true); }
  finally { $("#delete-confirm").disabled = false; }
}

let pendingDeleteConversationId = null;
function openDeleteConversationModal(conversationId) {
  pendingDeleteConversationId = conversationId;
  const conversation = state.conversations.find(item => item.id === conversationId);
  if (!conversation) return;
  $("#delete-conversation-title").textContent = `Delete “${conversation.title}”?`;
  $("#delete-conversation-modal").classList.remove("hidden");
}
function closeDeleteConversationModal() {
  pendingDeleteConversationId = null;
  $("#delete-conversation-modal").classList.add("hidden");
}

async function deleteConversation() {
  const conversationId = pendingDeleteConversationId;
  if (!conversationId || !state.workspaceId) return;

  try {
    $("#conversation-delete-confirm").disabled = true;
    await api(
      `/v1/workspaces/${state.workspaceId}/conversations/${conversationId}`,
      { method: "DELETE" },
    );
    closeDeleteConversationModal();

    state.conversations = await api(
      `/v1/workspaces/${state.workspaceId}/conversations`,
    );

    if (state.conversationId === conversationId) {
      const next = state.conversations[0] || await api(
        `/v1/workspaces/${state.workspaceId}/conversations`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: "New conversation" }),
        },
      );

      state.conversations = state.conversations.length
        ? state.conversations
        : [next];
      setSelection(state.workspaceId, next.id);
      clearConversationSurface(next.title || "New conversation");
    }

    renderConversationList();
    state.workspaces = await api("/v1/workspaces");
    renderWorkspaceList();
    toast("Conversation deleted.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    $("#conversation-delete-confirm").disabled = false;
  }
}

let pendingDeleteDocumentIds = [];

function openDeleteDocumentModal() {
  const documents = getSelectedDocuments();
  if (!documents.length || state.busy) return;

  pendingDeleteDocumentIds = documents.map(item => item.id);
  $("#delete-document-title").textContent = documents.length === 1
    ? `Delete “${documents[0].file_name}”?`
    : `Delete ${documents.length} selected documents?`;
  $("#selected-delete-list").innerHTML = documents
    .map(item => `<div class="selected-delete-item"><span>▧</span><strong>${escapeHtml(item.file_name)}</strong></div>`)
    .join("");
  $("#delete-document-modal").classList.remove("hidden");
}

function closeDeleteDocumentModal() {
  pendingDeleteDocumentIds = [];
  $("#delete-document-modal").classList.add("hidden");
}

function showDeleteLoading(documents) {
  $("#file-input").disabled = true;
  $("#delete-selected-documents").disabled = true;
  $("#delete-file-list").innerHTML = documents
    .map(item => `<div class="upload-file-row delete-file-row"><span class="file-status">◉</span><strong title="${escapeHtml(item.file_name)}">${escapeHtml(item.file_name)}</strong><span>SELECTED</span></div>`)
    .join("");
  $("#delete-loading").classList.remove("hidden");

  let stage = 0;
  const stages = [
    "Removing selected document records...",
    "Purging source files from storage...",
    "Removing processed chunks and embeddings...",
    "Rebuilding the remaining knowledge index...",
    "Finalizing permanent deletion...",
  ];
  const update = () => {
    const value = stages[Math.min(stage, stages.length - 1)];
    $("#delete-stage").textContent = value;
    $("#delete-loading-text").textContent = value;
    stage += 1;
  };
  update();
  state.deleteStageTimer = setInterval(update, 900);
}

function hideDeleteLoading() {
  clearInterval(state.deleteStageTimer);
  state.deleteStageTimer = null;
  $("#file-input").disabled = false;
  $("#delete-loading").classList.add("hidden");
}

async function deleteSelectedDocuments() {
  if (!state.workspaceId || state.busy || !pendingDeleteDocumentIds.length) return;

  const requestDocumentIds = [...pendingDeleteDocumentIds];
  const documents = requestDocumentIds
    .map(id => state.documents.find(item => item.id === id))
    .filter(Boolean);
  if (!documents.length) {
    closeDeleteDocumentModal();
    return;
  }

  const startedAt = performance.now();

  try {
    state.busy = true;
    closeDeleteDocumentModal();
    showDeleteLoading(documents);

    const result = await api(
      `/v1/workspaces/${state.workspaceId}/documents/delete`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: requestDocumentIds }),
      },
    );

    // Keep the purge overlay visible long enough for the user to see what happened.
    const elapsed = performance.now() - startedAt;
    const minimumLoadingMs = 900;
    if (elapsed < minimumLoadingMs) {
      await new Promise(resolve => setTimeout(resolve, minimumLoadingMs - elapsed));
    }

    state.documents = result.documents || [];
    state.workspaces = await api("/v1/workspaces");
    renderWorkspaceList();
    renderDocuments();
    $("#document-count-badge").textContent = `${state.documents.length} document${state.documents.length === 1 ? "" : "s"}`;

    // A deletion invalidates the displayed answer because its evidence may have been removed.
    clearConversationSurface("New conversation");
    renderConversation([]);
    updateComposer();

    $("#delete-success-copy").textContent =
      `${result.deleted_count} ${result.deleted_count === 1 ? "file has" : "files have"} been successfully deleted. The selected documents and all stored knowledge derived from them have been removed.`;
    $("#delete-success-modal").classList.remove("hidden");
  } catch (error) {
    toast(error instanceof Error ? error.message : String(error), true);
    try {
      await selectWorkspace(state.workspaceId);
    } catch (refreshError) {
      toast(refreshError instanceof Error ? refreshError.message : String(refreshError), true);
    }
  } finally {
    pendingDeleteDocumentIds = [];
    state.busy = false;
    hideDeleteLoading();
    updateDocumentSelection();
    updateComposer();
  }
}

function openWorkspaceModal() { $("#workspace-modal").classList.remove("hidden"); $("#workspace-name").value = ""; $("#workspace-name").focus(); }
function closeWorkspaceModal() { $("#workspace-modal").classList.add("hidden"); }

$("#query-form").addEventListener("submit", event => { event.preventDefault(); askAgent($("#query").value); });
$("#file-input").addEventListener("change", event => uploadFiles(event.target.files));
$("#new-workspace-button").addEventListener("click", openWorkspaceModal);
$("#modal-cancel").addEventListener("click", closeWorkspaceModal);
$("#modal-submit").addEventListener("click", async () => { const name = $("#workspace-name").value; if (!name.trim()) return; try { await createWorkspace(name); closeWorkspaceModal(); } catch (error) { toast(error.message, true); } });
$("#new-conversation-button").addEventListener("click", createConversation);
$("#clear-conversation").addEventListener("click", createConversation);
$("#new-document-button").addEventListener("click", startNewDocumentFlow);
$("#delete-selected-documents").addEventListener("click", openDeleteDocumentModal);
$("#document-delete-cancel").addEventListener("click", closeDeleteDocumentModal);
$("#document-delete-confirm").addEventListener("click", deleteSelectedDocuments);
$("#delete-success-continue").addEventListener("click", () => $("#delete-success-modal").classList.add("hidden"));
$("#export-button").addEventListener("click", exportReport);
$("#print-button").addEventListener("click", printReport);
$("#refresh-conversation").addEventListener("click", resetCurrentConversation);
$("#rename-workspace-button").addEventListener("click", renameWorkspace);
$("#delete-cancel").addEventListener("click", closeDeleteWorkspaceModal);
$("#delete-confirm").addEventListener("click", deleteWorkspace);
$("#conversation-delete-cancel").addEventListener("click", closeDeleteConversationModal);
$("#conversation-delete-confirm").addEventListener("click", deleteConversation);
$("#mobile-menu").addEventListener("click", () => $("#sidebar").classList.toggle("mobile-open"));
$("#workspace-name").addEventListener("keydown", event => { if (event.key === "Enter") $("#modal-submit").click(); });

async function healthCheck() {
  try { const response = await fetch("/health", { cache: "no-store" }); if (!response.ok) throw new Error(); $("#health-dot").classList.add("ok"); $("#health-label").textContent = "Runtime online"; }
  catch { $("#health-dot").classList.add("error"); $("#health-label").textContent = "Runtime unavailable"; }
}

Promise.all([healthCheck(), loadWorkspaces()]).catch(error => toast(error.message, true));
