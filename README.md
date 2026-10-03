# Antigravity Conversation Manager

A complete, standalone conversation manager and installable Antigravity plugin for browsing, searching, reading, exporting, and bulk-deleting Antigravity conversations across all your workspaces.

---

## 🔍 Why Does Antigravity "Lose" Past Conversations?

If you opened the Antigravity chat switcher and noticed that **recent conversations disappeared** and only old sessions from a month ago showed up, you encountered an Antigravity internal state synchronization issue:

1. **Where real data actually lives:**
   - Antigravity saves every single chat session in:
     - `~/.gemini/antigravity-ide/conversations/<uuid>.db` (SQLite database with all steps, trajectories, tool calls, and data)
     - `~/.gemini/antigravity-ide/brain/<uuid>/` (contains `.system_generated/logs/transcript.jsonl` with full chat transcripts, prompt history, and user uploads)
   - **Good news:** Your conversations were **never lost**. Every discussion, prompt, and code change is still intact on your drive.
2. **Why the IDE UI stopped showing them:**
   - The Antigravity IDE UI dropdown does *not* scan your disk dynamically. Instead, it reads a cached index stored in `AppData/Roaming/Antigravity IDE/User/globalStorage/state.vscdb` under the key `antigravityUnifiedStateSync.trajectorySummaries`.
   - When this cache freezes, hits an internal limit, or fails to append new sessions, the UI dropdown stays stuck on old entries (e.g. from 1 month ago) while your real sessions keep being created in the background under random UUIDs.
3. **The UUID problem:**
   - When browsing `~/.gemini/antigravity-ide/conversations/` manually, files are named with raw UUIDs like `97b43b16-e8d1-4c7e-be32-bb77a85dee93.db` without titles or dates, making them impossible to identify by eye.

---

## ✨ What This Project Does

This tool resolves the problem completely by providing:

1. **A Standalone Visual Web Dashboard**:
   - Automatically scans and indexes all conversations across all project workspaces.
   - Extracts real **human-readable titles** (from session metadata and initial prompts).
   - Shows formatted dates, relative times ("Yesterday at 1:11 PM", "3 days ago"), workspace tags (e.g. `thelobby`, `sockseek`, `outreach-copilot`), step counts, and disk space used.
   - **Slide-over Transcript Reader**: Click any conversation to read the complete discussion (user messages, assistant responses, collapsible tool executions) outside the Antigravity IDE.
   - **One-Click Markdown Export**: Download or save any chat as clean, readable Markdown.
   - **Bulk Deletion & Space Reclaim**: Select multiple conversations (or use presets like "Older than 30 days" or "Larger than 10 MB") and delete them with one click.
   - **Clean Orphans**: Removes orphaned brain cache directories with no matching database.

2. **An Installable Antigravity Plugin & MCP Server**:
   - Integrates directly into Antigravity via the Model Context Protocol (MCP) and Antigravity Plugin System.
   - Allows agents to answer questions like:
     - *"What did we discuss in our last session on thelobby?"*
     - *"Find conversations where we touched stripe or authentication."*
     - *"Delete past conversations older than 45 days."*

---

## 🚀 Quick Start

### 1. Launch the Visual Web Dashboard
- **Windows:** Double-click `launch-web-ui.bat` or run `python server.py`
- **macOS / Linux:** Run `./launch-web-ui.sh` or `python3 server.py`

This opens `http://127.0.0.1:48100` in your default browser. Zero external dependencies required (uses standard Python 3.8+ on all operating systems).

### 2. Install as an Antigravity Plugin
Run the universal installer on any platform:
```bash
python install.py
# or on macOS/Linux: python3 install.py (or ./install-plugin.sh)
# or on Windows: double-click install-plugin.bat
```

This will automatically:
1. Detect your operating system (Windows, macOS, or Linux).
2. Register the `conversation-manager` MCP server in `~/.gemini/config/mcp_config.json` with your machine's exact Python executable and path.
3. Link the plugin folder to `~/.gemini/config/plugins/conversation-manager`.

Once installed, restart or reopen Antigravity, and all tools and the skill will be active immediately.

---

## 🛠️ MCP Tools Reference

When active in Antigravity, the following tools are available to agents:

| Tool | Description |
| :--- | :--- |
| `convo_list` | Lists conversations with titles, dates, workspace tags, size, and step counts. |
| `convo_search` | Free-text search by title, prompt keyword, workspace, or age. |
| `convo_stats` | Summary metrics: total conversations count, total MB/GB used, workspace list, orphaned data. |
| `convo_read` | Returns the formatted message transcript of a conversation by UUID. |
| `convo_export` | Exports a conversation to a Markdown file. |
| `convo_delete` | Permanently deletes one or more conversations by UUID and reclaims disk space. |
| `convo_clean_orphans` | Removes orphaned brain directories. |
| `convo_sync_ui` | Prunes deleted/dead conversations from the Antigravity UI dropdown cache in `state.vscdb`, or resets the stuck list (`mode='prune'` or `mode='clear'`). |

---

## 📁 Project Structure

```
convo-manager/
├── .gitignore
├── README.md
├── plugin.json                 # Antigravity Plugin manifest
├── mcp_config.json             # Portable MCP server declaration
├── install.py                  # Universal cross-platform installer (Win, Mac, Linux)
├── install-plugin.bat          # 1-click Windows installer
├── install-plugin.sh           # macOS/Linux installer script
├── launch-web-ui.bat           # 1-click Windows launcher
├── launch-web-ui.sh            # macOS/Linux launcher script
├── server.py                   # Standalone Web GUI server & REST API (Python standard lib)
├── engine.py                   # Core conversation scanner, parser, exporter & cleaner
├── mcp_server.py               # JSON-RPC 2.0 MCP server for Antigravity agents
├── skills/
│   └── conversation-manager/
│       └── SKILL.md            # Skill for Antigravity agents
└── web/
    ├── index.html              # Dark-mode dashboard UI
    ├── style.css               # Polished styling
    └── app.js                  # Frontend controller
```
