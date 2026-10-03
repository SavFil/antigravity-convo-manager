"""
Antigravity Conversation Manager — Local Web Server
Provides a standalone HTTP server and REST API for the visual conversation dashboard.
Requires zero external dependencies (pure Python 3.12 standard library).
"""

import os
import sys
import json
import socket
import webbrowser
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from engine import ConversationManager

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
cm = ConversationManager()


class ConvoManagerHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def _send_json(self, data: any, status: int = HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, content_type: str = "text/plain; charset=utf-8", status: int = HTTPStatus.OK):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Static Web UI routes
        if path == "/" or path == "/index.html":
            index_file = WEB_DIR / "index.html"
            if index_file.exists():
                return super().do_GET()
            else:
                self._send_text("Web interface files missing in web/ folder.", status=404)
                return

        # API: Get statistics
        if path == "/api/stats":
            stats = cm.get_summary_stats()
            self._send_json(stats)
            return

        # API: List all conversations
        if path == "/api/conversations":
            q = query.get("q", [""])[0].lower()
            ws = query.get("ws", [""])[0].lower()
            sort_by = query.get("sort", ["mtime_desc"])[0]

            convos = cm.scan_conversations()

            if ws:
                convos = [c for c in convos if ws == c["workspace"].lower()]

            if q:
                convos = [
                    c for c in convos
                    if q in c["title"].lower()
                    or q in c["workspace"].lower()
                    or q in c["first_prompt"].lower()
                    or q in c["id"].lower()
                ]

            if sort_by == "mtime_asc":
                convos.sort(key=lambda x: x["mtime"])
            elif sort_by == "size_desc":
                convos.sort(key=lambda x: x["total_bytes"], reverse=True)
            elif sort_by == "steps_desc":
                convos.sort(key=lambda x: x["step_count"], reverse=True)
            elif sort_by == "title_asc":
                convos.sort(key=lambda x: x["title"].lower())
            else:
                convos.sort(key=lambda x: x["mtime"], reverse=True)

            self._send_json({"total": len(convos), "conversations": convos})
            return

        # API: Get conversation transcript
        if path.startswith("/api/conversation/"):
            cid = path.replace("/api/conversation/", "").strip()
            res = cm.get_transcript(cid)
            self._send_json(res)
            return

        # API: Export conversation to Markdown
        if path.startswith("/api/export/"):
            cid = path.replace("/api/export/", "").strip()
            md = cm.export_markdown(cid)
            self._send_text(md, content_type="text/markdown; charset=utf-8")
            return

        # Fallback to static files
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        if path == "/api/delete":
            ids = payload.get("ids", [])
            if not ids or not isinstance(ids, list):
                self._send_json({"error": "No IDs provided"}, status=400)
                return
            res = cm.delete_conversations(ids)
            self._send_json(res)
            return

        if path == "/api/sync-all":
            res = cm.sync_all()
            self._send_json(res)
            return

        if path == "/api/sync-ui":
            mode = payload.get("mode", "prune")
            res = cm.sync_all() if mode == "all" else cm.sync_antigravity_ui(mode=mode)
            self._send_json(res)
            return

        if path == "/api/clean-orphans":
            res = cm.clean_orphaned_brains()
            self._send_json(res)
            return

        self._send_json({"error": "Not Found"}, status=404)


def find_free_port(preferred_port: int = 48100) -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", preferred_port))
            return preferred_port
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


def run_server(port: int = 48100, open_browser: bool = False):
    actual_port = find_free_port(port)
    server_address = ("127.0.0.1", actual_port)
    httpd = HTTPServer(server_address, ConvoManagerHTTPHandler)
    url = f"http://127.0.0.1:{actual_port}"
    print(f"==================================================")
    print(f" Antigravity Conversation Manager")
    print(f" Local Web UI running at: {url}")
    print(f" Press Ctrl+C to stop.")
    print(f"==================================================")

    if open_browser:
        webbrowser.open(url)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        httpd.server_close()


if __name__ == "__main__":
    open_in_browser = "--no-open" not in sys.argv
    port_arg = 48100
    for i, a in enumerate(sys.argv):
        if a == "--port" and i + 1 < len(sys.argv):
            port_arg = int(sys.argv[i + 1])
    run_server(port=port_arg, open_browser=open_in_browser)
