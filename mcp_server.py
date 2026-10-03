"""
Antigravity Conversation Manager — MCP Server
Exposes conversation search, transcript reading, bulk deletion, and disk cleanup tools
via the Model Context Protocol (JSON-RPC 2.0 over stdio).
"""

import sys
import json
import traceback
from typing import Any, Dict, List
from engine import ConversationManager

# Force UTF-8 for stdin/stdout on Windows
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

cm = ConversationManager()

TOOLS = [
    {
        "name": "convo_list",
        "description": "List all Antigravity conversations with their human titles, dates, workspace names, message counts, and disk usage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of conversations to return (default: 30)."
                },
                "workspace": {
                    "type": "string",
                    "description": "Optional filter by workspace name (e.g. 'thelobby', 'sockseek')."
                }
            }
        }
    },
    {
        "name": "convo_search",
        "description": "Search past conversations by keyword, prompt content, or workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to match in title, prompt text, or workspace."
                },
                "workspace": {
                    "type": "string",
                    "description": "Filter results by workspace folder name."
                },
                "older_than_days": {
                    "type": "integer",
                    "description": "Filter conversations older than N days."
                }
            }
        }
    },
    {
        "name": "convo_stats",
        "description": "Get summary metrics: total conversations, disk space used, workspace breakdown, and orphaned data.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "convo_read",
        "description": "Read the full transcript (user prompts, agent responses, tool calls) of a specific conversation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "The UUID of the conversation to inspect."
                },
                "max_messages": {
                    "type": "integer",
                    "description": "Max messages to return (default: 50)."
                }
            },
            "required": ["conversation_id"]
        }
    },
    {
        "name": "convo_export",
        "description": "Export a conversation to a formatted Markdown document for reading offline or archiving.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "The UUID of the conversation to export."
                },
                "output_file": {
                    "type": "string",
                    "description": "Optional file path to save the markdown document."
                }
            },
            "required": ["conversation_id"]
        }
    },
    {
        "name": "convo_delete",
        "description": "Permanently delete one or more conversations (cleans .db, .db-wal, and brain directories) to reclaim disk space.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of conversation UUIDs to permanently delete."
                }
            },
            "required": ["conversation_ids"]
        }
    },
    {
        "name": "convo_clean_orphans",
        "description": "Clean up orphaned brain directories that have no corresponding database file.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


def handle_tool_call(name: str, args: Dict[str, Any]) -> Any:
    if name == "convo_list":
        limit = args.get("limit", 30)
        ws_filter = args.get("workspace")
        convos = cm.scan_conversations()
        if ws_filter:
            convos = [c for c in convos if ws_filter.lower() in c["workspace"].lower()]
        
        trimmed = []
        for c in convos[:limit]:
            trimmed.append({
                "id": c["id"],
                "title": c["title"],
                "workspace": c["workspace"],
                "date": c["mtime_display"],
                "relative": c["relative_time"],
                "size_mb": c["total_mb"],
                "steps": c["step_count"],
                "preview": c["first_prompt"][:100]
            })
        return {
            "total_matching": len(convos),
            "showing": len(trimmed),
            "conversations": trimmed
        }

    elif name == "convo_search":
        query = args.get("query", "").lower()
        ws_filter = args.get("workspace", "").lower()
        older_than_days = args.get("older_than_days")

        convos = cm.scan_conversations()
        matched = []
        
        import datetime
        now = datetime.datetime.now()

        for c in convos:
            if ws_filter and ws_filter not in c["workspace"].lower():
                continue
            if older_than_days is not None:
                mtime = datetime.datetime.fromisoformat(c["mtime"])
                if (now - mtime).days < older_than_days:
                    continue
            if query:
                text_to_search = f"{c['title']} {c['workspace']} {c['first_prompt']} {c['id']}".lower()
                if query not in text_to_search:
                    continue
            matched.append({
                "id": c["id"],
                "title": c["title"],
                "workspace": c["workspace"],
                "date": c["mtime_display"],
                "relative": c["relative_time"],
                "size_mb": c["total_mb"],
                "steps": c["step_count"],
                "preview": c["first_prompt"][:120]
            })

        return {
            "query": query,
            "total_matches": len(matched),
            "matches": matched[:40]
        }

    elif name == "convo_stats":
        return cm.get_summary_stats()

    elif name == "convo_read":
        cid = args["conversation_id"]
        max_msgs = args.get("max_messages", 50)
        res = cm.get_transcript(cid)
        messages = res.get("messages", [])
        return {
            "id": cid,
            "total_messages": len(messages),
            "messages": messages[:max_msgs]
        }

    elif name == "convo_export":
        cid = args["conversation_id"]
        out_file = args.get("output_file")
        md_content = cm.export_markdown(cid)
        if out_file:
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(md_content)
            return {"status": "saved", "path": out_file, "chars": len(md_content)}
        return {"id": cid, "markdown": md_content}

    elif name == "convo_delete":
        cids = args.get("conversation_ids", [])
        return cm.delete_conversations(cids)

    elif name == "convo_clean_orphans":
        return cm.clean_orphaned_brains()

    else:
        raise ValueError(f"Unknown tool: {name}")


def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")

        try:
            if method == "initialize":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "antigravity-convo-manager",
                            "version": "1.0.0"
                        }
                    }
                }
            elif method == "tools/list":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": TOOLS
                    }
                }
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                output = handle_tool_call(tool_name, tool_args)
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(output, indent=2, ensure_ascii=False)
                            }
                        ]
                    }
                }
            else:
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {}
                }
        except Exception as e:
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32000,
                    "message": str(e),
                    "data": traceback.format_exc()
                }
            }

        sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
