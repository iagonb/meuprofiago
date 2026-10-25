#!/usr/bin/env python3
"""Local-only review UI for editing the COLUNI LaTeX question sources."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "static/simulados/coluni/questions.json"
TEX_DIR = ROOT / "data/coluni/latex-source"
STATUS_FILE = ROOT / ".local/coluni-review-status.json"
UI_DIR = ROOT / "scripts/coluni-reviewer"
HOST = "127.0.0.1"
PORT = 8765
MAX_SOURCE_BYTES = 1_000_000
QUESTION_ID = re.compile(r"^20\d{2}-\d{2}$")


def load_questions() -> list[dict]:
    return json.loads(QUESTIONS.read_text(encoding="utf-8"))


def load_status() -> set[str]:
    if not STATUS_FILE.exists():
        return set()
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        return set(data.get("reviewed", []))
    except (OSError, json.JSONDecodeError, AttributeError):
        return set()


def save_status(reviewed: set[str]) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"reviewed": sorted(reviewed)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(STATUS_FILE)


def question_for(question_id: str) -> dict | None:
    if not QUESTION_ID.fullmatch(question_id):
        return None
    return next((item for item in load_questions() if item["id"] == question_id), None)


def render_latex(source: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".tex", encoding="utf-8") as handle:
        handle.write(source)
        handle.flush()
        result = subprocess.run(
            ["pandoc", handle.name, "-f", "latex", "-t", "html", "--mathjax"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "O Pandoc não conseguiu converter este LaTeX.")

    html = result.stdout
    html = re.sub(
        r'src="(?:\./)?figs/([^" ]+)"',
        lambda match: f'src="/asset/math-figs/{match.group(1).removeprefix("CAP")}"',
        html,
    )
    html = html.replace(
        'src="static/simulados/coluni/',
        'src="/asset/static/simulados/coluni/',
    )
    html = html.replace("<ol>", '<ol class="review-choices">')
    return html


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = "COLUNIReview/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: dict) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_SOURCE_BYTES + 100_000:
            raise ValueError("Tamanho da solicitação inválido.")
        return json.loads(self.rfile.read(length))

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        return not origin or origin in (f"http://{HOST}:{PORT}", f"http://localhost:{PORT}")

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, (UI_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif parsed.path.startswith("/ui/"):
            self._serve_ui(parsed.path.removeprefix("/ui/"))
        elif parsed.path == "/api/questions":
            items = [
                {key: q[key] for key in ("id", "year", "number", "subject", "page", "pdf")}
                for q in load_questions()
            ]
            self._json(200, {"questions": items, "reviewed": sorted(load_status())})
        elif parsed.path.startswith("/api/question/"):
            question_id = unquote(parsed.path.removeprefix("/api/question/"))
            question = question_for(question_id)
            source_path = TEX_DIR / f"{question_id}.tex"
            if not question or not source_path.is_file():
                self._json(404, {"error": "Questão ou fonte LaTeX não encontrada."})
                return
            try:
                preview = render_latex(source_path.read_text(encoding="utf-8"))
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                preview = f"<p class=\"preview-error\">Falha ao gerar prévia: {error}</p>"
            self._json(200, {
                "question": question,
                "source": source_path.read_text(encoding="utf-8"),
                "preview": preview,
                "reviewed": question_id in load_status(),
            })
        elif parsed.path.startswith("/asset/"):
            self._serve_asset(parsed.path.removeprefix("/asset/"))
        else:
            self._json(404, {"error": "Rota não encontrada."})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._same_origin():
            self._json(403, {"error": "Origem não permitida."})
            return
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path.startswith("/api/question/"):
                question_id = unquote(parsed.path.removeprefix("/api/question/"))
                if not question_for(question_id):
                    self._json(404, {"error": "Questão não encontrada."})
                    return
                source = payload.get("source")
                if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
                    self._json(400, {"error": "O conteúdo LaTeX é inválido ou excede 1 MB."})
                    return
                source_path = TEX_DIR / f"{question_id}.tex"
                temporary = source_path.with_suffix(".tex.tmp")
                temporary.write_text(source, encoding="utf-8")
                temporary.replace(source_path)
                self._json(200, {"saved": True})
            elif parsed.path == "/api/preview":
                source = payload.get("source")
                if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
                    self._json(400, {"error": "O conteúdo LaTeX é inválido ou excede 1 MB."})
                    return
                try:
                    self._json(200, {"preview": render_latex(source)})
                except (RuntimeError, subprocess.TimeoutExpired) as error:
                    self._json(422, {"error": str(error)})
            elif parsed.path.startswith("/api/review/"):
                question_id = unquote(parsed.path.removeprefix("/api/review/"))
                if not question_for(question_id):
                    self._json(404, {"error": "Questão não encontrada."})
                    return
                reviewed = bool(payload.get("reviewed"))
                status = load_status()
                if reviewed:
                    status.add(question_id)
                else:
                    status.discard(question_id)
                save_status(status)
                self._json(200, {"reviewed": reviewed})
            elif parsed.path == "/api/regenerate":
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/digitize_coluni_questions.py")],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                self._json(200 if result.returncode == 0 else 500, {
                    "success": result.returncode == 0,
                    "output": (result.stdout + result.stderr).strip(),
                })
            else:
                self._json(404, {"error": "Rota não encontrada."})
        except (ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})
        except subprocess.TimeoutExpired:
            self._json(504, {"error": "A operação excedeu o tempo limite."})

    def _serve_ui(self, filename: str) -> None:
        path = (UI_DIR / filename).resolve()
        if UI_DIR.resolve() not in path.parents or not path.is_file():
            self._json(404, {"error": "Arquivo não encontrado."})
            return
        content_type = "text/css; charset=utf-8" if path.suffix == ".css" else "text/javascript; charset=utf-8"
        self._send(200, path.read_bytes(), content_type)

    def _serve_asset(self, path: str) -> None:
        if path.startswith("static/"):
            target = (ROOT / path).resolve()
            allowed_root = (ROOT / "static").resolve()
        elif path.startswith("math-figs/"):
            filename = Path(path.removeprefix("math-figs/")).name
            target = (ROOT / "Matemática/figs" / filename).resolve()
            if not target.is_file() and filename.startswith("CAP"):
                target = (ROOT / "Matemática/figs" / filename.removeprefix("CAP")).resolve()
            allowed_root = (ROOT / "Matemática/figs").resolve()
        else:
            self._json(404, {"error": "Ativo não encontrado."})
            return
        if allowed_root not in target.parents or not target.is_file():
            self._json(404, {"error": "Ativo não encontrado."})
            return
        mime = "application/pdf" if target.suffix == ".pdf" else "image/png" if target.suffix == ".png" else "application/octet-stream"
        self._send(200, target.read_bytes(), mime)


if __name__ == "__main__":
    print(f"Revisão local do COLUNI: http://{HOST}:{PORT}/")
    print("As alterações salvam em data/coluni/latex-source; o status fica em .local/.")
    ThreadingHTTPServer((HOST, PORT), ReviewHandler).serve_forever()
