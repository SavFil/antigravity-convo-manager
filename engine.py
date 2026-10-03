"""
Antigravity Conversation Manager — Core Engine
Scans, indexes, parses, exports, and manages Antigravity conversations.
Works across Windows, macOS, and Linux by dynamically resolving user home paths.
"""

import os
import re
import ssl
import glob
import json
import shutil
import base64
import sqlite3
import datetime
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple



def get_default_paths() -> Dict[str, str]:
    """Dynamically determine default Antigravity data directories."""
    user_home = Path.home()
    app_data = Path(os.environ.get("APPDATA", user_home / "AppData" / "Roaming"))
    
    gemini_base = user_home / ".gemini" / "antigravity-ide"
    convos_dir = gemini_base / "conversations"
    brain_dir = gemini_base / "brain"
    state_db = app_data / "Antigravity IDE" / "User" / "globalStorage" / "state.vscdb"
    
    return {
        "convos_dir": str(convos_dir),
        "brain_dir": str(brain_dir),
        "state_db": str(state_db) if state_db.exists() else "",
        "config_dir": str(user_home / ".gemini" / "config")
    }


class ConversationManager:
    def __init__(self, convos_dir: Optional[str] = None, brain_dir: Optional[str] = None, state_db: Optional[str] = None):
        defaults = get_default_paths()
        self.convos_dir = Path(convos_dir or defaults["convos_dir"])
        self.brain_dir = Path(brain_dir or defaults["brain_dir"])
        self.state_db = Path(state_db or defaults["state_db"]) if (state_db or defaults["state_db"]) else None

    def _extract_title_from_steps(self, cur: sqlite3.Cursor) -> Optional[str]:
        """Extract Antigravity-generated session title from step_payload in steps table."""
        try:
            cur.execute("SELECT step_payload FROM steps WHERE step_type=23 ORDER BY idx ASC")
            rows = cur.fetchall()
            for (p,) in rows:
                if not p:
                    continue
                # Look for Protobuf field 4 (tag 0x22), followed by 1-byte length and ASCII/UTF-8 string
                matches = re.finditer(b'\\x22([\\x04-\\x50])([\\x20-\\x7e]+)', p)
                for m in matches:
                    length = m.group(1)[0]
                    val = m.group(2)[:length]
                    if len(val) == length:
                        s = val.decode("utf-8", errors="ignore").strip()
                        # Validate that it's a realistic human title
                        if (
                            len(s) >= 4 and len(s) <= 80
                            and not s.startswith(("http", "file:", "$", "{", "sessionID", "RESOURCE_", "0,"))
                            and not re.match(r"^[0-9a-f-]{36}$", s)
                            and not re.match(r"^-[0-9]+[A-Za-z]?$", s)
                            and not '"source"' in s
                        ):
                            return s
        except Exception:
            pass
        return None

    def _extract_workspace(self, cur: sqlite3.Cursor) -> Tuple[str, str]:
        """Extract workspace folder and URI from trajectory_metadata_blob."""
        try:
            cur.execute("SELECT data FROM trajectory_metadata_blob WHERE id='main'")
            row = cur.fetchone()
            if row and row[0]:
                raw = row[0]
                matches = re.findall(rb'file:///[a-zA-Z]:[^\x00-\x1f\x7f-\xff\x22\x3c\x3e]+', raw)
                if matches:
                    uri = matches[0].decode("utf-8", errors="ignore")
                    clean_path = uri.replace("file:///", "").replace("%20", " ")
                    folder = clean_path.rstrip("/\\").split("/")[-1].split("\\")[-1]
                    return folder, uri
        except Exception:
            pass
        return "Unknown", ""

    def _extract_first_prompt(self, cid: str) -> Optional[str]:
        """Extract initial user request prompt from transcript.jsonl."""
        log_file = self.brain_dir / cid / ".system_generated" / "logs" / "transcript.jsonl"
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    for _ in range(30):
                        line = f.readline()
                        if not line:
                            break
                        if '"USER_INPUT"' in line:
                            obj = json.loads(line)
                            if obj.get("type") == "USER_INPUT" and obj.get("source") == "USER_EXPLICIT":
                                content = obj.get("content", "")
                                clean = re.sub(r'<[^>]+>', '', content).strip()
                                clean = re.sub(r'\s+', ' ', clean)
                                if clean:
                                    return clean[:300]
            except Exception:
                pass
        return None

    def _get_dir_size(self, path: Path) -> int:
        """Calculate total directory size in bytes."""
        total = 0
        if path.exists() and path.is_dir():
            for root, _, files in os.walk(path):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass
        return total

    def _format_relative_time(self, dt: datetime.datetime) -> str:
        """Return human-readable relative time string."""
        now = datetime.datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        
        if seconds < 60:
            return "Just now"
        elif seconds < 3600:
            m = seconds // 60
            return f"{m}m ago"
        elif seconds < 86400:
            h = seconds // 3600
            return f"{h}h ago"
        elif seconds < 604800:
            d = seconds // 86400
            return f"{d}d ago"
        elif seconds < 2592000:
            w = seconds // 604800
            return f"{w}w ago"
        else:
            mo = seconds // 2592000
            return f"{mo}mo ago"

    def scan_conversations(self) -> List[Dict[str, Any]]:
        """Scan all conversation databases and return structured metadata."""
        if not self.convos_dir.exists():
            return []

        db_files = list(self.convos_dir.glob("*.db"))
        results = []

        for db in db_files:
            cid = db.stem
            try:
                mtime_epoch = db.stat().st_mtime
                ctime_epoch = db.stat().st_ctime
                mtime = datetime.datetime.fromtimestamp(mtime_epoch)
                ctime = datetime.datetime.fromtimestamp(ctime_epoch)
                db_size = db.stat().st_size
            except Exception:
                continue

            # WAL and SHM sizes
            wal_file = self.convos_dir / f"{cid}.db-wal"
            wal_size = wal_file.stat().st_size if wal_file.exists() else 0

            # Brain directory
            brain_path = self.brain_dir / cid
            brain_size = self._get_dir_size(brain_path) if brain_path.exists() else 0
            has_brain = brain_path.exists()

            # Transcript file
            transcript_path = brain_path / ".system_generated" / "logs" / "transcript.jsonl"
            has_transcript = transcript_path.exists()

            title = None
            workspace_name = "Unknown"
            workspace_uri = ""
            step_count = 0

            try:
                conn = sqlite3.connect(f"file:{db.resolve()}?mode=ro", uri=True)
                cur = conn.cursor()
                try:
                    cur.execute("SELECT count(*) FROM steps")
                    step_count = cur.fetchone()[0]
                except Exception:
                    pass

                title = self._extract_title_from_steps(cur)
                workspace_name, workspace_uri = self._extract_workspace(cur)
                conn.close()
            except Exception:
                pass

            first_prompt = self._extract_first_prompt(cid)
            if not title:
                if first_prompt:
                    words = first_prompt.split()
                    title = " ".join(words[:7]) + ("..." if len(words) > 7 else "")
                else:
                    title = f"Conversation {cid[:8]}"

            total_bytes = db_size + wal_size + brain_size

            results.append({
                "id": cid,
                "title": title,
                "workspace": workspace_name,
                "workspace_uri": workspace_uri,
                "mtime": mtime.isoformat(),
                "mtime_display": mtime.strftime("%b %d, %Y %I:%M %p"),
                "relative_time": self._format_relative_time(mtime),
                "ctime": ctime.isoformat(),
                "step_count": step_count,
                "first_prompt": first_prompt or "",
                "db_size_bytes": db_size + wal_size,
                "brain_size_bytes": brain_size,
                "total_bytes": total_bytes,
                "total_mb": round(total_bytes / (1024 * 1024), 2),
                "has_brain": has_brain,
                "has_transcript": has_transcript,
                "db_path": str(db)
            })

        results.sort(key=lambda x: x["mtime"], reverse=True)
        return results

    def get_summary_stats(self, convos: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Compute aggregate statistics across all conversations."""
        if convos is None:
            convos = self.scan_conversations()

        total_bytes = sum(c["total_bytes"] for c in convos)
        workspaces = set(c["workspace"] for c in convos if c["workspace"] != "Unknown")

        # Find orphaned brains (brain dirs with no matching DB)
        db_ids = set(c["id"] for c in convos)
        orphaned_brains = []
        if self.brain_dir.exists():
            for p in self.brain_dir.iterdir():
                if p.is_dir() and p.name not in db_ids and len(p.name) == 36:
                    orphaned_brains.append({
                        "id": p.name,
                        "size_bytes": self._get_dir_size(p),
                        "mtime": datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat()
                    })

        orphaned_bytes = sum(b["size_bytes"] for b in orphaned_brains)

        return {
            "total_conversations": len(convos),
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            "total_size_gb": round(total_bytes / (1024 * 1024 * 1024), 2),
            "workspaces_count": len(workspaces),
            "workspaces_list": sorted(list(workspaces)),
            "orphaned_brains_count": len(orphaned_brains),
            "orphaned_brains_mb": round(orphaned_bytes / (1024 * 1024), 2),
            "latest_activity": convos[0]["mtime_display"] if convos else "None"
        }

    def get_transcript(self, cid: str) -> Dict[str, Any]:
        """Fetch and format the complete transcript for a conversation."""
        log_file = self.brain_dir / cid / ".system_generated" / "logs" / "transcript.jsonl"
        messages = []
        
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                            mtype = obj.get("type")
                            source = obj.get("source")
                            content = obj.get("content", "")
                            tool_calls = obj.get("tool_calls", [])

                            # Clean XML wrapper tags from user prompt
                            if mtype == "USER_INPUT":
                                content = re.sub(r'<USER_REQUEST>\s*', '', content)
                                content = re.sub(r'\s*<\/USER_REQUEST>', '', content).strip()

                            if mtype in ("USER_INPUT", "PLANNER_RESPONSE", "CHECKPOINT"):
                                messages.append({
                                    "step_index": obj.get("step_index"),
                                    "type": mtype,
                                    "source": source,
                                    "content": content,
                                    "tool_calls": tool_calls,
                                    "status": obj.get("status")
                                })
                        except Exception:
                            continue
            except Exception as e:
                return {"id": cid, "error": str(e), "messages": []}

        # If transcript.jsonl wasn't found or was empty, fall back to SQLite steps
        if not messages:
            db_path = self.convos_dir / f"{cid}.db"
            if db_path.exists():
                try:
                    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
                    cur = conn.cursor()
                    cur.execute("SELECT idx, step_type, status, step_payload FROM steps ORDER BY idx ASC")
                    for idx, st, status, payload in cur.fetchall():
                        if payload:
                            strs = [s.decode("utf-8", errors="ignore") for s in re.findall(rb'[\x20-\x7e]{10,}', payload)]
                            if strs:
                                messages.append({
                                    "step_index": idx,
                                    "type": f"STEP_{st}",
                                    "source": "SQLITE",
                                    "content": "\n".join(strs[:3]),
                                    "tool_calls": [],
                                    "status": status
                                })
                    conn.close()
                except Exception:
                    pass

        return {
            "id": cid,
            "messages_count": len(messages),
            "messages": messages
        }

    def export_markdown(self, cid: str) -> str:
        """Generate a complete, beautiful Markdown document of a conversation."""
        convos = {c["id"]: c for c in self.scan_conversations()}
        info = convos.get(cid, {"title": f"Conversation {cid[:8]}", "workspace": "Unknown", "mtime_display": "Unknown"})
        transcript = self.get_transcript(cid)

        md = []
        md.append(f"# {info.get('title')}")
        md.append(f"**Workspace:** `{info.get('workspace')}` | **Date:** {info.get('mtime_display')} | **ID:** `{cid}`\n")
        md.append("---\n")

        for m in transcript.get("messages", []):
            mtype = m.get("type")
            content = m.get("content", "").strip()
            tool_calls = m.get("tool_calls", [])

            if mtype == "USER_INPUT":
                md.append("### User")
                md.append(content)
                md.append("")
            elif mtype == "PLANNER_RESPONSE":
                md.append("### Assistant")
                if content:
                    md.append(content)
                    md.append("")
                if tool_calls:
                    md.append(f"<details><summary><b>Tools Executed ({len(tool_calls)})</b></summary>\n")
                    for tc in tool_calls:
                        name = tc.get("tool_name", tc.get("name", "Tool"))
                        args = json.dumps(tc.get("arguments", tc.get("args", {})), indent=2)
                        md.append(f"**`{name}`**:\n```json\n{args}\n```\n")
                    md.append("</details>\n")
            elif mtype == "CHECKPOINT":
                md.append("> *Conversation checkpoint / compacted context*\n")

        return "\n".join(md)

    def delete_conversations(self, cids: List[str]) -> Dict[str, Any]:
        """Permanently delete specified conversations from disk (DB, WAL, SHM, Brain)."""
        deleted = []
        errors = []
        bytes_freed = 0

        for cid in cids:
            try:
                # 1. Delete SQLite files
                for ext in (".db", ".db-wal", ".db-shm"):
                    p = self.convos_dir / f"{cid}{ext}"
                    if p.exists():
                        try:
                            bytes_freed += p.stat().st_size
                            p.unlink()
                        except Exception as e:
                            errors.append(f"Error removing {p.name}: {str(e)}")

                # 2. Delete Brain directory
                brain_p = self.brain_dir / cid
                if brain_p.exists():
                    try:
                        bytes_freed += self._get_dir_size(brain_p)
                        shutil.rmtree(brain_p, ignore_errors=True)
                    except Exception as e:
                        errors.append(f"Error removing brain/{cid}: {str(e)}")

                deleted.append(cid)
            except Exception as e:
                errors.append(f"Failed deleting {cid}: {str(e)}")

        # Automatically purge deleted conversations from running Antigravity IDE & Language Server
        rpc_stats = {"ext_purged": 0, "ls_purged": 0}
        if deleted:
            try:
                rpc_stats = self.purge_from_running_antigravity(deleted)
            except Exception as e:
                errors.append(f"RPC purge error: {str(e)}")

        # Automatically prune deleted conversations from Antigravity IDE UI state
        pruned_from_ui = 0
        if deleted:
            pruned_from_ui, _ = self._prune_vscdb_entries(deleted)

        return {
            "deleted_count": len(deleted),
            "deleted_ids": deleted,
            "bytes_freed": bytes_freed,
            "mb_freed": round(bytes_freed / (1024 * 1024), 2),
            "pruned_from_ui": pruned_from_ui,
            "rpc_purged": rpc_stats,
            "errors": errors
        }

    def _decode_varint(self, data: bytes, offset: int) -> Tuple[int, int]:
        res = 0
        shift = 0
        while True:
            b = data[offset]
            res |= (b & 0x7f) << shift
            offset += 1
            if not (b & 0x80):
                break
            shift += 7
        return res, offset

    def _encode_varint(self, n: int) -> bytes:
        res = bytearray()
        while True:
            towrite = n & 0x7f
            n >>= 7
            if n:
                res.append(towrite | 0x80)
            else:
                res.append(towrite)
                break
        return bytes(res)

    def _prune_vscdb_entries(self, cids_to_remove: List[str] = None, mode: str = "prune") -> Tuple[int, int]:
        """
        Prunes specified cids and non-existent DBs from Antigravity's trajectorySummaries cache in state.vscdb.
        If mode == 'clear', clears all cached trajectory summaries for a fresh clean slate.
        """
        if not self.state_db or not self.state_db.exists():
            return 0, 0

        cids_set = set(cids_to_remove or [])
        try:
            conn = sqlite3.connect(str(self.state_db), timeout=10.0)
            cur = conn.cursor()
            cur.execute("SELECT value FROM ItemTable WHERE key='antigravityUnifiedStateSync.trajectorySummaries'")
            row = cur.fetchone()
            if not row or not row[0]:
                conn.close()
                return 0, 0

            raw = base64.b64decode(row[0])
            offset = 0
            valid_items = []
            dropped = []

            if mode != "clear":
                while offset < len(raw):
                    tag, offset = self._decode_varint(raw, offset)
                    length, offset = self._decode_varint(raw, offset)
                    item_data = raw[offset:offset + length]
                    offset += length

                    # Parse cid from field 1
                    o2 = 0
                    cid = None
                    while o2 < len(item_data):
                        t2, o2 = self._decode_varint(item_data, o2)
                        f2 = t2 >> 3
                        if f2 == 1:
                            l2, o2 = self._decode_varint(item_data, o2)
                            cid = item_data[o2:o2 + l2].decode("ascii", errors="ignore")
                            break
                        else:
                            w2 = t2 & 0x7
                            if w2 == 2:
                                l2, o2 = self._decode_varint(item_data, o2)
                                o2 += l2
                            else:
                                break

                    # Check if should drop
                    should_drop = False
                    if cid in cids_set:
                        should_drop = True
                    elif mode == "prune":
                        db_file = self.convos_dir / f"{cid}.db"
                        if not db_file.exists():
                            should_drop = True

                    if should_drop:
                        dropped.append(cid)
                    else:
                        valid_items.append(item_data)

            # Reconstruct protobuf
            new_raw = bytearray()
            for item in valid_items:
                new_raw.append(0x0a)
                new_raw.extend(self._encode_varint(len(item)))
                new_raw.extend(item)

            new_b64 = base64.b64encode(new_raw).decode("ascii")
            cur.execute(
                "UPDATE ItemTable SET value=? WHERE key='antigravityUnifiedStateSync.trajectorySummaries'",
                (new_b64,)
            )
            conn.commit()
            cur.execute("PRAGMA wal_checkpoint(FULL);")
            conn.close()
            return len(dropped), len(valid_items)
        except Exception as e:
            print(f"[convo-manager] _prune_vscdb_entries error: {e}")
            return 0, 0

    def discover_active_antigravity_daemons(self) -> Tuple[List[Tuple[int, str]], List[Tuple[int, str]]]:
        """
        Discover running Antigravity Extension Servers (port, csrf) and Language Servers (port, csrf).
        Works dynamically on Windows by inspecting running language server processes and listening ports.
        """
        ext_servers = []
        ls_servers = []

        try:
            wmic_out = subprocess.check_output(
                ['wmic', 'process', 'where', "name like '%language_server%'", 'get', 'ProcessId,CommandLine', '/format:list'],
                text=True, timeout=5
            )

            net_cmd = 'Get-NetTCPConnection -State Listen | Where-Object { $_.OwningProcess -in (Get-Process language_server_windows_x64 -ErrorAction SilentlyContinue).Id } | Select-Object LocalPort, OwningProcess'
            net_out = subprocess.check_output(['powershell', '-Command', net_cmd], text=True, timeout=5)
            ls_ports_by_pid = {}
            for line in net_out.splitlines():
                parts = line.strip().split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    ls_ports_by_pid.setdefault(int(parts[1]), []).append(int(parts[0]))

            for block in wmic_out.split("CommandLine="):
                if not block.strip():
                    continue
                cmdline = block.split("ProcessId=")[0]
                pid_match = re.search(r'ProcessId=(\d+)', block)
                pid = int(pid_match.group(1)) if pid_match else 0

                ext_port_m = re.search(r'--extension_server_port\s+(\d+)', cmdline)
                ext_csrf_m = re.search(r'--extension_server_csrf_token\s+([0-9a-f-]+)', cmdline)
                if ext_port_m and ext_csrf_m:
                    ext_servers.append((int(ext_port_m.group(1)), ext_csrf_m.group(1)))

                ls_csrf_m = re.search(r'--csrf_token\s+([0-9a-f-]+)', cmdline)
                if ls_csrf_m and pid in ls_ports_by_pid:
                    for p in ls_ports_by_pid[pid]:
                        ls_servers.append((p, ls_csrf_m.group(1)))

            ext_servers = list(set(ext_servers))
            ls_servers = list(set(ls_servers))
        except Exception:
            pass

        return ext_servers, ls_servers

    def purge_from_running_antigravity(self, cids: List[str]) -> Dict[str, int]:
        """
        Sends live deletion RPC calls to all active Antigravity Extension Servers and Language Servers.
        This forces the running IDE windows to instantly remove the conversations from their dropdown
        and memory without requiring a full IDE shutdown or reload.
        """
        if not cids:
            return {"ext_purged": 0, "ls_purged": 0}

        ext_servers, ls_servers = self.discover_active_antigravity_daemons()
        ext_purged = 0
        ls_purged = 0
        ctx = ssl._create_unverified_context()

        # 1. Purge from running IDE UI topic cache via Extension Server
        for port, csrf in ext_servers:
            url = f"http://127.0.0.1:{port}/exa.extension_server_pb.ExtensionServerService/PushUnifiedStateSyncUpdate"
            for cid in cids:
                body = {
                    "update": {
                        "topicName": "trajectorySummaries",
                        "appliedUpdate": {
                            "key": cid,
                            "deleted": True
                        }
                    }
                }
                try:
                    req = urllib.request.Request(
                        url,
                        data=json.dumps(body).encode('utf-8'),
                        headers={'Content-Type': 'application/json', 'x-codeium-csrf-token': csrf}
                    )
                    with urllib.request.urlopen(req, timeout=2) as resp:
                        if resp.status == 200:
                            ext_purged += 1
                except Exception:
                    pass

        # 2. Purge from running Language Server & Cloud Code registry
        for port, csrf in ls_servers:
            url = f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/DeleteCascadeTrajectory"
            for cid in cids:
                try:
                    req = urllib.request.Request(
                        url,
                        data=json.dumps({"cascadeId": cid}).encode('utf-8'),
                        headers={'Content-Type': 'application/json', 'x-codeium-csrf-token': csrf}
                    )
                    with urllib.request.urlopen(req, context=ctx, timeout=2) as resp:
                        if resp.status == 200:
                            ls_purged += 1
                except Exception:
                    pass

        return {"ext_purged": ext_purged, "ls_purged": ls_purged}

    def sync_antigravity_ui(self, mode: str = "prune") -> Dict[str, Any]:
        """
        Synchronizes or resets the Antigravity UI past conversations dropdown in both:
        1. Live running Electron UI memory & Language Server processes via RPC.
        2. Persistent SQLite cache in state.vscdb.

        mode='prune': removes deleted/missing conversations from the UI dropdown.
        mode='clear': completely empties the stuck dropdown cache so only fresh sessions appear.
        """
        # Discover all stale IDs from state.vscdb and backup files
        stale_cids = set()
        vscdb_files = []
        if self.state_db and self.state_db.parent.exists():
            vscdb_files = list(self.state_db.parent.glob("state.vscdb*"))

        for vf in vscdb_files:
            try:
                conn = sqlite3.connect(str(vf), timeout=5.0)
                cur = conn.cursor()
                cur.execute("SELECT value FROM ItemTable WHERE key='antigravityUnifiedStateSync.trajectorySummaries'")
                row = cur.fetchone()
                if row and row[0]:
                    raw = base64.b64decode(row[0])
                    matches = re.findall(rb'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', raw)
                    for m in matches:
                        cid = m.decode("ascii", errors="ignore")
                        db_file = self.convos_dir / f"{cid}.db"
                        if not db_file.exists():
                            stale_cids.add(cid)
                conn.close()
            except Exception:
                pass

        # Also purge any active trajectory summaries that have no local database
        ext_servers, ls_servers = self.discover_active_antigravity_daemons()
        ctx = ssl._create_unverified_context()
        for port, csrf in ls_servers:
            try:
                req = urllib.request.Request(
                    f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetAllCascadeTrajectories",
                    data=b'{}',
                    headers={'Content-Type': 'application/json', 'x-codeium-csrf-token': csrf}
                )
                with urllib.request.urlopen(req, context=ctx, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                    summaries = data.get("trajectorySummaries", {})
                    for cid in summaries.keys():
                        db_file = self.convos_dir / f"{cid}.db"
                        if not db_file.exists():
                            stale_cids.add(cid)
            except Exception:
                pass

        # Send live RPC deletion to running daemons
        rpc_stats = self.purge_from_running_antigravity(list(stale_cids))

        # Prune state.vscdb file on disk
        pruned_count, remaining_count = self._prune_vscdb_entries(list(stale_cids), mode=mode)

        return {
            "status": "success",
            "mode": mode,
            "stale_cids_purged": len(stale_cids),
            "pruned_from_disk_db": pruned_count,
            "remaining_in_ui": remaining_count,
            "live_rpc_events": rpc_stats,
            "message": f"Successfully forced past conversations sync ({len(stale_cids)} ghost sessions purged from running IDE RAM, Language Server, and disk cache)."
        }

    def _encode_string_field(self, fnum: int, s: str) -> bytes:
        data = s.encode('utf-8')
        tag = (fnum << 3) | 2
        return self._encode_varint(tag) + self._encode_varint(len(data)) + data

    def _encode_timestamp_field(self, fnum: int, seconds: int) -> bytes:
        ts_data = self._encode_varint((1 << 3) | 0) + self._encode_varint(seconds)
        tag = (fnum << 3) | 2
        return self._encode_varint(tag) + self._encode_varint(len(ts_data)) + ts_data

    def _encode_workspace_field(self, fnum: int, uri: str) -> bytes:
        ws_data = self._encode_string_field(1, uri)
        tag = (fnum << 3) | 2
        return self._encode_varint(tag) + self._encode_varint(len(ws_data)) + ws_data

    def _build_summary_proto(self, title: str, uri: str, timestamp_s: int) -> str:
        """Constructs a valid base64 protobuf CascadeTrajectorySummary message."""
        raw = bytearray()
        raw.extend(self._encode_string_field(1, title))
        raw.extend(self._encode_timestamp_field(3, timestamp_s))
        raw.extend(self._encode_timestamp_field(6, timestamp_s))
        raw.extend(self._encode_workspace_field(8, uri))
        return base64.b64encode(bytes(raw)).decode('ascii')

    def sync_all(self) -> Dict[str, Any]:
        """
        Master all-in-one sync and cleanup operation:
        1. Clean orphaned brain directories.
        2. Purge ghost sessions (stale sessions with no local DB) from running IDE RAM & Language Server.
        3. Inject all valid disk conversations into the running Antigravity IDE UI in real-time.
        4. Persist all valid conversations cleanly into state.vscdb so they stay forever.
        """
        import time

        # 1. Clean orphaned brains
        orphans = self.clean_orphaned_brains()

        # 2. Discover and purge ghost sessions
        stale_cids = set()
        vscdb_files = []
        if self.state_db and self.state_db.parent.exists():
            vscdb_files = list(self.state_db.parent.glob("state.vscdb*"))

        for vf in vscdb_files:
            try:
                conn = sqlite3.connect(str(vf), timeout=5.0)
                cur = conn.cursor()
                cur.execute("SELECT value FROM ItemTable WHERE key='antigravityUnifiedStateSync.trajectorySummaries'")
                row = cur.fetchone()
                if row and row[0]:
                    raw = base64.b64decode(row[0])
                    matches = re.findall(rb'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', raw)
                    for m in matches:
                        cid = m.decode("ascii", errors="ignore")
                        db_file = self.convos_dir / f"{cid}.db"
                        if not db_file.exists():
                            stale_cids.add(cid)
                conn.close()
            except Exception:
                pass

        ext_servers, ls_servers = self.discover_active_antigravity_daemons()
        ctx = ssl._create_unverified_context()
        for port, csrf in ls_servers:
            try:
                req = urllib.request.Request(
                    f"https://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/GetAllCascadeTrajectories",
                    data=b'{}',
                    headers={'Content-Type': 'application/json', 'x-codeium-csrf-token': csrf}
                )
                with urllib.request.urlopen(req, context=ctx, timeout=3) as resp:
                    data = json.loads(resp.read().decode())
                    summaries = data.get("trajectorySummaries", {})
                    for cid in summaries.keys():
                        db_file = self.convos_dir / f"{cid}.db"
                        if not db_file.exists():
                            stale_cids.add(cid)
            except Exception:
                pass

        # Purge ghost sessions live
        if stale_cids:
            self.purge_from_running_antigravity(list(stale_cids))

        # 3. Scan all valid disk conversations and inject them into running IDE UI
        convos = self.scan_conversations()
        synced_count = 0
        valid_data_entries = []

        for c in convos:
            cid = c["id"]
            title = c.get("title", "Conversation")
            uri = c.get("workspace_uri") or "file:///c:/Users/filip/.gemini/antigravity-ide/scratch/thelobby"
            dt = c.get("raw_updated_at")
            ts = int(dt.timestamp()) if dt else int(time.time())
            b64_val = self._build_summary_proto(title, uri, ts)

            # Push live update to running Extension Servers
            for port, csrf in ext_servers:
                body = {
                    "update": {
                        "topicName": "trajectorySummaries",
                        "appliedUpdate": {
                            "key": cid,
                            "newRow": {
                                "value": b64_val
                            }
                        }
                    }
                }
                try:
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{port}/exa.extension_server_pb.ExtensionServerService/PushUnifiedStateSyncUpdate",
                        data=json.dumps(body).encode("utf-8"),
                        headers={"Content-Type": "application/json", "x-codeium-csrf-token": csrf}
                    )
                    with urllib.request.urlopen(req, timeout=2) as r:
                        if r.status == 200:
                            synced_count += 1
                except Exception:
                    pass

            # Prepare binary DataEntry for state.vscdb
            row_bytes = self._encode_string_field(1, b64_val)
            de_bytes = (
                self._encode_string_field(1, cid)
                + self._encode_varint((2 << 3) | 2)
                + self._encode_varint(len(row_bytes))
                + row_bytes
            )
            valid_data_entries.append(de_bytes)

        # 4. Save into state.vscdb
        if self.state_db and self.state_db.exists():
            try:
                new_raw = bytearray()
                for item in valid_data_entries:
                    new_raw.append(0x0a)
                    new_raw.extend(self._encode_varint(len(item)))
                    new_raw.extend(item)

                new_b64 = base64.b64encode(new_raw).decode("ascii")
                conn = sqlite3.connect(str(self.state_db), timeout=10.0)
                cur = conn.cursor()
                cur.execute(
                    "UPDATE ItemTable SET value=? WHERE key='antigravityUnifiedStateSync.trajectorySummaries'",
                    (new_b64,)
                )
                conn.commit()
                cur.execute("PRAGMA wal_checkpoint(FULL);")
                conn.close()
            except Exception as e:
                print(f"[convo-manager] sync_all state.vscdb error: {e}")

        return {
            "status": "success",
            "orphans_removed": orphans["removed_count"],
            "orphans_mb_freed": orphans["mb_freed"],
            "ghosts_purged": len(stale_cids),
            "conversations_synced": len(convos),
            "conversations": [{"id": c["id"], "title": c["title"], "workspace": c["workspace"]} for c in convos],
            "message": f"All-in-one sync complete! Synced {len(convos)} conversations to Antigravity, purged {len(stale_cids)} ghosts, and cleaned {orphans['removed_count']} orphans."
        }

    def clean_orphaned_brains(self) -> Dict[str, Any]:
        """Clean up brain directories that no longer have a matching database."""
        db_ids = set(f.stem for f in self.convos_dir.glob("*.db"))
        removed = []
        bytes_freed = 0

        if self.brain_dir.exists():
            for p in self.brain_dir.iterdir():
                if p.is_dir() and p.name not in db_ids and len(p.name) == 36:
                    try:
                        size = self._get_dir_size(p)
                        shutil.rmtree(p, ignore_errors=True)
                        bytes_freed += size
                        removed.append(p.name)
                    except Exception:
                        pass

        return {
            "removed_count": len(removed),
            "removed_ids": removed,
            "bytes_freed": bytes_freed,
            "mb_freed": round(bytes_freed / (1024 * 1024), 2)
        }



