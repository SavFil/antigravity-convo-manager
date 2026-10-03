---
name: conversation-manager
description: Manage, search, export, read, and bulk-clean Antigravity conversations and trajectories across workspaces. Use when the user asks to find past conversations, inspect transcripts, delete old sessions, or free up disk space from past chats.
---

# Conversation Manager Skill

This skill allows agents to search, inspect, export, and clean Antigravity conversations across all workspaces.

## Available MCP Tools

When the `conversation-manager` plugin is active, the following MCP tools are available:

1. `convo_list`:
   - Returns a structured list of conversations with human-readable titles, dates, workspace tags, size in MB, and step counts.
   - Arguments: `limit` (default 30), `workspace` (optional workspace filter).

2. `convo_search`:
   - Searches across conversation titles, initial prompt text, and workspace names.
   - Arguments: `query` (keywords), `workspace` (filter), `older_than_days` (filter by age).

3. `convo_stats`:
   - Returns total conversations count, total disk space consumed in MB/GB, list of all workspaces, and orphaned data.

4. `convo_read`:
   - Retrieves the full chronological transcript (user prompts, agent responses, tool calls) of a specific conversation UUID.
   - Arguments: `conversation_id`, `max_messages`.

5. `convo_export`:
   - Exports the entire conversation into a clean, formatted Markdown document.
   - Arguments: `conversation_id`, `output_file` (optional path to save).

6. `convo_delete`:
   - Permanently deletes one or more conversation IDs, cleaning up SQLite databases, WAL files, and brain logs/artifacts.
   - Arguments: `conversation_ids` (array of UUIDs).

7. `convo_clean_orphans`:
   - Cleans orphaned brain directories that have no corresponding database.

8. `convo_sync_ui`:
   - Prunes deleted/dead conversations from the Antigravity UI dropdown cache in `state.vscdb`, or resets the stuck list (`mode='prune'` or `mode='clear'`).

## Standalone Web Dashboard

Users can also launch the visual Web UI anytime by running:
```bash
python server.py
# or double-clicking launch-web-ui.bat
```
This opens `http://127.0.0.1:48100` where users can filter, multi-select, read transcripts in a slide-over drawer, and bulk delete.
