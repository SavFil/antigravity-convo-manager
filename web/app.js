// Antigravity Conversation Manager — Frontend Controller

(function () {
  let allConversations = [];
  let currentSelection = new Set();
  let currentDrawerConvoId = null;
  let debounceTimer = null;

  // DOM Elements
  const statTotal = document.getElementById("stat-total");
  const statSize = document.getElementById("stat-size");
  const statSizeDetail = document.getElementById("stat-size-detail");
  const statWorkspaces = document.getElementById("stat-workspaces");
  const statLatest = document.getElementById("stat-latest");
  const orphanCountSpan = document.getElementById("orphan-count");

  const inputSearch = document.getElementById("input-search");
  const btnClearSearch = document.getElementById("btn-clear-search");
  const selectWorkspace = document.getElementById("select-workspace");
  const selectSort = document.getElementById("select-sort");

  const convoListContainer = document.getElementById("convo-list");
  const emptyState = document.getElementById("empty-state");
  const counterShowing = document.getElementById("counter-showing");
  const checkboxMaster = document.getElementById("checkbox-master");

  const batchBar = document.getElementById("batch-bar");
  const batchCount = document.getElementById("batch-count");
  const batchSize = document.getElementById("batch-size");
  const btnBatchDeselect = document.getElementById("btn-batch-deselect");
  const btnBatchDelete = document.getElementById("btn-batch-delete");

  const drawer = document.getElementById("transcript-drawer");
  const drawerBackdrop = document.getElementById("drawer-backdrop");
  const drawerTitle = document.getElementById("drawer-title");
  const drawerWorkspace = document.getElementById("drawer-workspace");
  const drawerDate = document.getElementById("drawer-date");
  const drawerId = document.getElementById("drawer-id");
  const drawerMessages = document.getElementById("drawer-messages");
  const btnCloseDrawer = document.getElementById("btn-close-drawer");
  const btnExportMd = document.getElementById("btn-export-md");
  const btnDeleteSingle = document.getElementById("btn-delete-single");

  const modalBackdrop = document.getElementById("modal-backdrop");
  const modalTitle = document.getElementById("modal-title");
  const modalMessage = document.getElementById("modal-message");
  const btnModalCancel = document.getElementById("btn-modal-cancel");
  const btnModalConfirm = document.getElementById("btn-modal-confirm");
  let onModalConfirm = null;

  const btnSyncAll = document.getElementById("btn-sync-all");
  const btnSyncAllText = document.getElementById("btn-sync-all-text");
  const toast = document.getElementById("toast");

  // Show Toast
  function showToast(msg, duration = 3500) {
    toast.textContent = msg;
    toast.classList.remove("hidden");
    setTimeout(() => {
      toast.classList.add("hidden");
    }, duration);
  }

  // Load Global Stats
  async function loadStats() {
    try {
      const res = await fetch("/api/stats");
      const data = await res.json();
      statTotal.textContent = data.total_conversations || 0;
      statSize.textContent = `${data.total_size_mb || 0} MB`;
      if (data.total_size_gb >= 1) {
        statSize.textContent = `${data.total_size_gb} GB`;
      }
      statSizeDetail.textContent = `${data.total_size_mb || 0} MB total disk space`;
      statWorkspaces.textContent = data.workspaces_count || 0;
      statLatest.textContent = `Latest: ${data.latest_activity || "None"}`;
      orphanCountSpan.textContent = data.orphaned_brains_count || 0;

      // Populate workspace dropdown if empty
      const currentVal = selectWorkspace.value;
      selectWorkspace.innerHTML = '<option value="">All Workspaces</option>';
      if (data.workspaces_list) {
        data.workspaces_list.forEach(ws => {
          const opt = document.createElement("option");
          opt.value = ws;
          opt.textContent = ws;
          if (ws === currentVal) opt.selected = true;
          selectWorkspace.appendChild(opt);
        });
      }
    } catch (e) {
      console.error("Failed to load stats:", e);
    }
  }

  // Load Conversations with Active Filters
  async function loadConversations() {
    const q = inputSearch.value.trim();
    const ws = selectWorkspace.value;
    const sort = selectSort.value;

    btnClearSearch.classList.toggle("hidden", !q);

    try {
      const url = `/api/conversations?q=${encodeURIComponent(q)}&ws=${encodeURIComponent(ws)}&sort=${sort}`;
      const res = await fetch(url);
      const data = await res.json();
      allConversations = data.conversations || [];
      renderConversations();
    } catch (e) {
      console.error("Failed to load conversations:", e);
      counterShowing.textContent = "Failed to load conversations.";
    }
  }

  // Render Conversation List
  function renderConversations() {
    convoListContainer.innerHTML = "";

    if (allConversations.length === 0) {
      emptyState.classList.remove("hidden");
      counterShowing.textContent = "0 conversations";
      checkboxMaster.checked = false;
      updateBatchBar();
      return;
    }

    emptyState.classList.add("hidden");
    counterShowing.textContent = `Showing ${allConversations.length} conversations`;

    // Check master checkbox state
    const allVisibleSelected = allConversations.length > 0 && allConversations.every(c => currentSelection.has(c.id));
    checkboxMaster.checked = allVisibleSelected;

    allConversations.forEach(convo => {
      const isSelected = currentSelection.has(convo.id);
      const card = document.createElement("div");
      card.className = `convo-card ${isSelected ? "selected" : ""}`;
      card.dataset.id = convo.id;

      card.innerHTML = `
        <input type="checkbox" class="convo-checkbox" data-id="${convo.id}" ${isSelected ? "checked" : ""}>
        <div class="convo-main">
          <div class="convo-meta-row">
            <span class="workspace-tag">${escapeHtml(convo.workspace)}</span>
            <span class="convo-date">
              <span class="convo-date-rel">${convo.relative_time}</span> • ${convo.mtime_display}
            </span>
          </div>
          <div class="convo-title" title="${escapeHtml(convo.title)}">${escapeHtml(convo.title)}</div>
          <div class="convo-prompt-snippet" title="${escapeHtml(convo.first_prompt)}">
            ${convo.first_prompt ? escapeHtml(convo.first_prompt) : '<em style="color:var(--text-dim)">No prompt preview available</em>'}
          </div>
        </div>
        <div class="convo-side">
          <span class="pill pill-size">${convo.total_mb} MB</span>
          <span class="pill">${convo.step_count} steps</span>
          <div class="convo-actions">
            <button class="btn-card-action btn-card-export" title="Export as Markdown" data-id="${convo.id}">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7 10 12 15 17 10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </button>
            <button class="btn-card-action btn-card-delete" title="Delete conversation" data-id="${convo.id}">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
            </button>
          </div>
        </div>
      `;

      // Click card to open drawer
      card.addEventListener("click", (e) => {
        if (e.target.closest(".convo-checkbox") || e.target.closest(".convo-actions")) {
          return;
        }
        openTranscriptDrawer(convo.id);
      });

      // Individual checkbox
      const chk = card.querySelector(".convo-checkbox");
      chk.addEventListener("change", (e) => {
        e.stopPropagation();
        toggleSelect(convo.id, chk.checked);
      });

      // Card action buttons
      const btnExport = card.querySelector(".btn-card-export");
      btnExport.addEventListener("click", (e) => {
        e.stopPropagation();
        exportConversation(convo.id, convo.title);
      });

      const btnDelete = card.querySelector(".btn-card-delete");
      btnDelete.addEventListener("click", (e) => {
        e.stopPropagation();
        confirmDeleteSingle(convo.id, convo.title, convo.total_mb);
      });

      convoListContainer.appendChild(card);
    });

    updateBatchBar();
  }

  // Toggle Selection
  function toggleSelect(id, checked) {
    if (checked) {
      currentSelection.add(id);
    } else {
      currentSelection.delete(id);
    }
    const card = document.querySelector(`.convo-card[data-id="${id}"]`);
    if (card) {
      card.classList.toggle("selected", checked);
      const chk = card.querySelector(".convo-checkbox");
      if (chk) chk.checked = checked;
    }
    const allVisibleSelected = allConversations.length > 0 && allConversations.every(c => currentSelection.has(c.id));
    checkboxMaster.checked = allVisibleSelected;
    updateBatchBar();
  }

  // Update Batch Bar
  function updateBatchBar() {
    const count = currentSelection.size;
    if (count > 0) {
      let totalBytes = 0;
      allConversations.forEach(c => {
        if (currentSelection.has(c.id)) {
          totalBytes += c.total_bytes;
        }
      });
      const mb = (totalBytes / (1024 * 1024)).toFixed(2);
      batchCount.textContent = count;
      batchSize.textContent = `${mb} MB`;
      batchBar.classList.remove("hidden");
    } else {
      batchBar.classList.add("hidden");
    }
  }

  // Master Checkbox
  checkboxMaster.addEventListener("change", () => {
    const checked = checkboxMaster.checked;
    allConversations.forEach(c => {
      if (checked) currentSelection.add(c.id);
      else currentSelection.delete(c.id);
    });
    renderConversations();
  });

  // Presets Handlers
  document.querySelectorAll(".chip-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const preset = btn.dataset.preset;
      const now = new Date();

      if (preset === "all") {
        allConversations.forEach(c => currentSelection.add(c.id));
      } else if (preset === "clear") {
        currentSelection.clear();
      } else if (preset === "older-30") {
        allConversations.forEach(c => {
          const diffDays = (now - new Date(c.mtime)) / (1000 * 60 * 60 * 24);
          if (diffDays >= 30) currentSelection.add(c.id);
        });
      } else if (preset === "older-60") {
        allConversations.forEach(c => {
          const diffDays = (now - new Date(c.mtime)) / (1000 * 60 * 60 * 24);
          if (diffDays >= 60) currentSelection.add(c.id);
        });
      } else if (preset === "large-10") {
        allConversations.forEach(c => {
          if (c.total_mb >= 10.0) currentSelection.add(c.id);
        });
      }

      renderConversations();
    });
  });

  // Batch Deselect
  btnBatchDeselect.addEventListener("click", () => {
    currentSelection.clear();
    renderConversations();
  });

  // Batch Delete
  btnBatchDelete.addEventListener("click", () => {
    const count = currentSelection.size;
    if (count === 0) return;

    let totalBytes = 0;
    allConversations.forEach(c => {
      if (currentSelection.has(c.id)) totalBytes += c.total_bytes;
    });
    const mb = (totalBytes / (1024 * 1024)).toFixed(2);

    openConfirmModal(
      `Delete ${count} Conversations?`,
      `Are you sure you want to permanently delete these ${count} conversations? This will free approximately ${mb} MB of disk space. This action cannot be undone.`,
      async () => {
        const ids = Array.from(currentSelection);
        try {
          const res = await fetch("/api/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids })
          });
          const result = await res.json();
          showToast(`Deleted ${result.deleted_count} conversations. Freed ${result.mb_freed} MB.`);
          currentSelection.clear();
          await loadStats();
          await loadConversations();
        } catch (e) {
          showToast("Failed to delete conversations.", 4000);
        }
      }
    );
  });

  // Single Delete Confirmation
  function confirmDeleteSingle(id, title, mb) {
    openConfirmModal(
      "Delete Conversation?",
      `Are you sure you want to permanently delete "${title}" (${mb} MB)? This cannot be undone.`,
      async () => {
        try {
          const res = await fetch("/api/delete", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids: [id] })
          });
          const result = await res.json();
          showToast(`Conversation deleted. Freed ${result.mb_freed} MB.`);
          currentSelection.delete(id);
          if (currentDrawerConvoId === id) closeTranscriptDrawer();
          await loadStats();
          await loadConversations();
        } catch (e) {
          showToast("Failed to delete conversation.", 4000);
        }
      }
    );
  }

  // Open Confirmation Modal
  function openConfirmModal(title, msg, onConfirm) {
    modalTitle.textContent = title;
    modalMessage.textContent = msg;
    onModalConfirm = onConfirm;
    modalBackdrop.classList.remove("hidden");
  }

  btnModalCancel.addEventListener("click", () => {
    modalBackdrop.classList.add("hidden");
    onModalConfirm = null;
  });

  btnModalConfirm.addEventListener("click", () => {
    modalBackdrop.classList.add("hidden");
    if (onModalConfirm) {
      onModalConfirm();
      onModalConfirm = null;
    }
  });

  // Open Transcript Drawer
  async function openTranscriptDrawer(cid) {
    currentDrawerConvoId = cid;
    const convo = allConversations.find(c => c.id === cid);

    drawerTitle.textContent = convo ? convo.title : "Conversation Transcript";
    drawerWorkspace.textContent = convo ? convo.workspace : "Workspace";
    drawerDate.textContent = convo ? convo.mtime_display : "";
    drawerId.textContent = cid;
    drawerMessages.innerHTML = '<div style="color:var(--text-muted);text-align:center;padding:40px;">Loading transcript...</div>';

    drawer.classList.remove("hidden");
    drawerBackdrop.classList.remove("hidden");

    try {
      const res = await fetch(`/api/conversation/${cid}`);
      const data = await res.json();
      renderTranscriptMessages(data.messages || []);
    } catch (e) {
      drawerMessages.innerHTML = '<div style="color:var(--accent-danger);padding:20px;">Failed to load transcript.</div>';
    }
  }

  function renderTranscriptMessages(messages) {
    drawerMessages.innerHTML = "";
    if (messages.length === 0) {
      drawerMessages.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:40px;">No messages recorded in this conversation.</div>';
      return;
    }

    messages.forEach(m => {
      const msgDiv = document.createElement("div");
      const isUser = m.type === "USER_INPUT";
      const isAssistant = m.type === "PLANNER_RESPONSE";
      const isCheckpoint = m.type === "CHECKPOINT";

      msgDiv.className = `chat-msg ${isUser ? "chat-user" : isAssistant ? "chat-assistant" : "chat-system"}`;

      if (isCheckpoint) {
        msgDiv.innerHTML = `
          <div style="font-size:0.775rem; color:var(--text-dim); text-align:center; padding: 6px; font-style: italic;">
            Conversation Checkpoint / Compacted Context
          </div>
        `;
      } else {
        const author = isUser ? "User" : "Antigravity Assistant";
        let toolHtml = "";

        if (m.tool_calls && m.tool_calls.length > 0) {
          toolHtml = `
            <details class="tool-calls-box">
              <summary>Tools Executed (${m.tool_calls.length})</summary>
              ${m.tool_calls.map(tc => {
                const name = tc.tool_name || tc.name || "Tool";
                const args = JSON.stringify(tc.arguments || tc.args || {}, null, 2);
                return `
                  <div class="tool-call-item">
                    <div class="tool-name">${escapeHtml(name)}</div>
                    <pre class="tool-args">${escapeHtml(args)}</pre>
                  </div>
                `;
              }).join("")}
            </details>
          `;
        }

        msgDiv.innerHTML = `
          <div class="chat-author">${author}</div>
          <div class="chat-bubble">${escapeHtml(m.content || "")} ${toolHtml}</div>
        `;
      }

      drawerMessages.appendChild(msgDiv);
    });
  }

  function closeTranscriptDrawer() {
    drawer.classList.add("hidden");
    drawerBackdrop.classList.add("hidden");
    currentDrawerConvoId = null;
  }

  btnCloseDrawer.addEventListener("click", closeTranscriptDrawer);
  drawerBackdrop.addEventListener("click", closeTranscriptDrawer);

  // Export Markdown from Drawer
  btnExportMd.addEventListener("click", () => {
    if (currentDrawerConvoId) {
      const convo = allConversations.find(c => c.id === currentDrawerConvoId);
      exportConversation(currentDrawerConvoId, convo ? convo.title : "conversation");
    }
  });

  // Delete Single from Drawer
  btnDeleteSingle.addEventListener("click", () => {
    if (currentDrawerConvoId) {
      const convo = allConversations.find(c => c.id === currentDrawerConvoId);
      confirmDeleteSingle(currentDrawerConvoId, convo ? convo.title : "this conversation", convo ? convo.total_mb : 0);
    }
  });

  // Export Conversation Helper
  function exportConversation(cid, title) {
    const safeTitle = (title || "conversation").replace(/[^a-zA-Z0-9_-]/g, "_").substring(0, 40);
    const link = document.createElement("a");
    link.href = `/api/export/${cid}`;
    link.download = `${safeTitle}_${cid.substring(0, 8)}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast("Exporting conversation markdown...");
  }

  // Unified All-in-One Master Sync & Clean
  if (btnSyncAll) {
    btnSyncAll.addEventListener("click", async () => {
      btnSyncAll.disabled = true;
      if (btnSyncAllText) btnSyncAllText.textContent = "Syncing & Cleaning...";
      showToast("Running all-in-one sync & cleanup...", 3000);

      try {
        const res = await fetch("/api/sync-all", { method: "POST" });
        const data = await res.json();
        const msg = data.message || "All-in-one sync complete!";
        showToast(msg, 5000);

        // Instantly reload UI stats and list
        await loadStats();
        await loadConversations();
      } catch (e) {
        showToast("Error during sync & cleanup: " + e.message, 4500);
      } finally {
        btnSyncAll.disabled = false;
        if (btnSyncAllText) btnSyncAllText.textContent = "Sync & Clean All";
      }
    });
  }

  // Search & Filter Events
  inputSearch.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(loadConversations, 250);
  });

  btnClearSearch.addEventListener("click", () => {
    inputSearch.value = "";
    loadConversations();
  });

  selectWorkspace.addEventListener("change", loadConversations);
  selectSort.addEventListener("change", loadConversations);

  // Escape HTML utility
  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Keyboard Shortcuts (Esc closes drawer or modal)
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (!modalBackdrop.classList.contains("hidden")) {
        modalBackdrop.classList.add("hidden");
        onModalConfirm = null;
      } else if (!drawer.classList.contains("hidden")) {
        closeTranscriptDrawer();
      }
    }
  });

  // Initial Load
  loadStats();
  loadConversations();
})();
