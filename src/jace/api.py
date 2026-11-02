from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from .engine import CognitiveEngine
from .simulator import decide_motion


class JaceHandler(BaseHTTPRequestHandler):
    engine: CognitiveEngine

    def _send(self, status: int, payload: object) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            raise ValueError("request body must be valid JSON")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {"status": "ok", "service": "jace", "reasoner": type(self.engine.reasoner).__name__, "canonical_entries": len(self.engine.canonical.all()), "graph": self.engine.graph.stats()})
            return
        if parsed.path == "/v1/canonical/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            self._send(200, {"entries": [item.to_dict() for item in self.engine.canonical.search(query)]})
            return
        if parsed.path == "/v1/graph/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]
            user_id = params.get("user_id", [""])[0]
            if not query or not user_id:
                self._send(400, {"error": "q and user_id are required"})
                return
            hits = self.engine.graph.retrieve(query, user_id)
            self._send(200, {"hits": [{"node_id": hit.node_id, "node_type": hit.node_type, "title": hit.title, "content": hit.content, "score": hit.score, "depth": hit.depth, "source_id": hit.source_id} for hit in hits]})
            return
        if parsed.path.startswith("/v1/memory/"):
            user_id = unquote(parsed.path.removeprefix("/v1/memory/"))
            if not user_id:
                self._send(400, {"error": "user_id is required"})
                return
            self._send(200, {"memories": [item.to_dict() for item in self.engine.memory.list(user_id)]})
            return
        self._send(404, {"error": "not found"})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/v1/memory/"):
            user_id = unquote(parsed.path.removeprefix("/v1/memory/"))
            if not user_id:
                self._send(400, {"error": "user_id is required"})
                return
            self._send(200, {"deleted": self.engine.forget_user(user_id), "user_id": user_id})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        try:
            body = self._body()
            if self.path == "/v1/think":
                result = self.engine.think(str(body.get("user_id", "")), str(body.get("input", "")))
                payload = result.to_dict()
                if body.get("learn") is True:
                    learned, notes = self.engine.learn_from_conversation(result.user_id, result.input)
                    payload["learned_memory"] = learned.to_dict() if learned else None
                    payload["learning_notes"] = notes
                self._send(200, payload)
                return
            if self.path == "/v1/memory":
                memory, notes = self.engine.remember(str(body.get("user_id", "")), str(body.get("content", "")))
                self._send(201 if memory else 422, {"accepted": memory is not None, "memory": memory.to_dict() if memory else None, "notes": notes})
                return
            if self.path == "/v1/simulate/motion":
                if not isinstance(body.get("observation"), dict):
                    raise ValueError("observation must be an object")
                self._send(200, {"decision": decide_motion(body["observation"]).to_dict()})
                return
            self._send(404, {"error": "not found"})
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception:
            self._send(500, {"error": "internal server error"})

    def log_message(self, format: str, *args) -> None:
        return


def serve(host: str | None = None, port: int | None = None) -> None:
    engine = CognitiveEngine()
    JaceHandler.engine = engine
    server = ThreadingHTTPServer((host or os.getenv("JACE_HOST", "127.0.0.1"), port or int(os.getenv("JACE_PORT", "8787"))), JaceHandler)
    print(f"JACE listening on http://{server.server_address[0]}:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.close()
