#!/usr/bin/env python3
"""Modelo falso compatible con OpenAI (chat/completions, con streaming) para pruebas E2E sin costo.

Sigue un guion JSON: una lista de pasos, cada uno {"tool": nombre, "args": {...}} o {"text": "..."}. El paso que
responde es el número de mensajes 'assistant' ya presentes en la request, así que cada turno avanza uno.
Las requests sin tools (títulos, resúmenes) reciben un texto corto.

Uso: python3 tools/fake-llm/server.py --port 18080 --script guion.json [--log requests.jsonl]
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

SCRIPT: list[dict[str, Any]] = []
LOG: Path | None = None


def next_step(body: dict[str, Any]) -> dict[str, Any]:
    if not body.get("tools"):
        return {"text": "probe"}
    done = sum(1 for m in body.get("messages", []) if m.get("role") == "assistant")
    return SCRIPT[done] if done < len(SCRIPT) else {"text": "DONE"}


def chunk(delta: dict[str, Any], finish: str | None = None, usage: bool = False) -> bytes:
    payload: dict[str, Any] = {"id": "fake", "object": "chat.completion.chunk", "created": int(time.time()),
                               "model": "scripted", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage:
        payload["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    return f"data: {json.dumps(payload)}\n\n".encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_: Any) -> None:
        pass

    def do_GET(self) -> None:  # /v1/models
        self._json({"object": "list", "data": [{"id": "scripted", "object": "model", "owned_by": "fake"}]})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        step = next_step(body)
        if LOG:
            with LOG.open("a", encoding="utf-8") as fh:
                text = json.dumps(body.get("messages", []), ensure_ascii=False)
                fh.write(json.dumps({"tools": [t.get("function", {}).get("name") for t in body.get("tools", [])],
                                     "messages": len(body.get("messages", [])), "step": step,
                                     "handoff_mentions": text.count("[session-handoff]")}) + "\n")
        call = None
        if "tool" in step:
            call = {"index": 0, "id": f"call_{int(time.time() * 1000)}", "type": "function",
                    "function": {"name": step["tool"], "arguments": json.dumps(step.get("args", {}))}}
        if not body.get("stream"):
            message: dict[str, Any] = {"role": "assistant", "content": step.get("text")}
            if call:
                message["tool_calls"] = [{k: v for k, v in call.items() if k != "index"}]
            self._json({"id": "fake", "object": "chat.completion", "created": int(time.time()), "model": "scripted",
                        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if call else "stop"}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if call:
            self.wfile.write(chunk({"role": "assistant", "tool_calls": [call]}))
            self.wfile.write(chunk({}, "tool_calls", usage=True))
        else:
            self.wfile.write(chunk({"role": "assistant", "content": step.get("text", "")}))
            self.wfile.write(chunk({}, "stop", usage=True))
        self.wfile.write(b"data: [DONE]\n\n")

    def _json(self, data: dict[str, Any]) -> None:
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> None:
    global SCRIPT, LOG
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--script", required=True)
    parser.add_argument("--log")
    args = parser.parse_args()
    SCRIPT = json.loads(Path(args.script).read_text(encoding="utf-8"))
    LOG = Path(args.log) if args.log else None
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
