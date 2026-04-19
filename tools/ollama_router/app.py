"""
Ollama transparent proxy with a synthetic model "auto" that routes to theory vs code models.

Point Open WebUI Ollama base URL at this service. Choose model "auto" to enable routing.
Upstream should be real Ollama (e.g. http://host.docker.internal:11435 when using socat on Mac Docker).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

UPSTREAM = os.environ.get("OLLAMA_UPSTREAM", "http://127.0.0.1:11434").rstrip("/")
AUTO_ALIASES = frozenset(
    x.strip().lower()
    for x in os.environ.get(
        "ROUTER_AUTO_ALIASES",
        "auto,router,smart-route,auto-route",
    ).split(",")
    if x.strip()
)
MODEL_CODE = os.environ.get("ROUTER_MODEL_CODE", "qwen3-coder:30b")
MODEL_THEORY = os.environ.get("ROUTER_MODEL_THEORY", "qwen3-coder-next:latest")
CODE_RE = re.compile(
    r"```|"
    r"\bdef\s+\w+\s*\(|"
    r"\bclass\s+\w+\s*[:\(]|"
    r"\b(import|from)\s+\w+\s+|"
    r"\b(function|const|let|var|public\s+static|fn\s+)\s+\w+|"
    r"=>|"
    r"\b(stack\s*trace|traceback|syntaxerror|refactor|unit\s*test|pytest|git\s+diff)\b|"
    r"\.(py|js|ts|tsx|go|rs|java|cpp|c|h)\b|"
    r"\b(API|endpoint|middleware|dockerfile|kubernetes)\b",
    re.IGNORECASE | re.DOTALL,
)

app = FastAPI(title="Ollama router", version="1.0.0")

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [ollama-router] %(message)s",
)
log = logging.getLogger("ollama_router")

CONTEXT_PREFIX = (
    "Project context (injected by ollama-router from the user's repo mount). "
    "Use it as ground truth for paths, names, and code. Do not refuse to use this text.\n\n"
)


def _safe_join(root: str, rel: str) -> str | None:
    root = os.path.realpath(root)
    if ".." in rel.split(os.sep):
        return None
    fp = os.path.realpath(os.path.join(root, rel.lstrip(os.sep)))
    if not fp.startswith(root + os.sep) and fp != root:
        return None
    return fp if os.path.isfile(fp) else None


def _tree_skip_dirs() -> set[str]:
    raw = os.environ.get(
        "ROUTER_CONTEXT_SKIP_DIRS",
        ".git,node_modules,__pycache__,.venv,venv,dist,build,.idea,.tox,.mypy_cache,htmlcov",
    )
    return {x.strip() for x in raw.split(",") if x.strip()}


def _tree_skip_extensions() -> set[str]:
    raw = os.environ.get(
        "ROUTER_CONTEXT_SKIP_EXT",
        ".png,.jpg,.jpeg,.gif,.webp,.ico,.pyc,.pyo,.so,.dylib,.dll,.bin,.exe,.zip,.tar,.gz,.7z,.pdf",
    )
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def build_tree_listing(root: str) -> str:
    """One path per line, relative to repo root; bounded by depth and file count."""
    if os.environ.get("ROUTER_CONTEXT_TREE", "1").lower() not in ("1", "true", "yes"):
        return ""
    root = os.path.realpath(root)
    max_depth = int(os.environ.get("ROUTER_CONTEXT_TREE_MAX_DEPTH", "5"))
    max_files = int(os.environ.get("ROUTER_CONTEXT_TREE_MAX_FILES", "800"))
    skip_dirs = _tree_skip_dirs()
    skip_ext = _tree_skip_extensions()
    lines: list[str] = []
    n = 0
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        rel_dir = os.path.relpath(dirpath, root)
        depth = 0 if rel_dir in (".", "") else rel_dir.count(os.sep) + 1
        if depth > max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in skip_dirs and (not d.startswith(".") or d == ".github")
        )
        for fn in sorted(filenames):
            if n >= max_files:
                lines.append("… [tree truncated: ROUTER_CONTEXT_TREE_MAX_FILES]")
                return "\n".join(lines)
            _base, ext = os.path.splitext(fn)
            if ext.lower() in skip_ext:
                continue
            rel_file = fn if rel_dir in (".", "") else f"{rel_dir.replace(os.sep, '/')}/{fn}"
            lines.append(rel_file)
            n += 1
    return "\n".join(lines)


def build_context_block() -> str:
    """Repo snapshot: optional tree + file contents under ROUTER_CONTEXT_ROOT (e.g. /project)."""
    if os.environ.get("ROUTER_CONTEXT_ENABLED", "1").lower() not in ("1", "true", "yes"):
        return ""
    root = os.environ.get("ROUTER_CONTEXT_ROOT", "").strip()
    if not root or not os.path.isdir(root):
        return ""
    max_total = int(os.environ.get("ROUTER_CONTEXT_MAX_CHARS", "28000"))
    per_file = int(os.environ.get("ROUTER_CONTEXT_MAX_PER_FILE", "12000"))
    parts: list[str] = []
    used = 0

    tree_txt = build_tree_listing(root)
    if tree_txt:
        chunk = "### Repository layout (relative paths; not file contents)\n```\n" + tree_txt + "\n```\n"
        if used + len(chunk) > max_total:
            chunk = chunk[: max(0, max_total - used)] + "\n… [truncated]\n"
        parts.append(chunk)
        used += len(chunk)

    raw_list = os.environ.get(
        "ROUTER_CONTEXT_FILES",
        "README.md,README,AGENTS.md",
    )
    rels = [x.strip() for x in raw_list.split(",") if x.strip()]
    for rel in rels:
        fp = _safe_join(root, rel)
        if not fp:
            continue
        try:
            with open(fp, encoding="utf-8", errors="replace") as f:
                text = f.read(per_file + 1)
            if len(text) > per_file:
                text = text[:per_file] + "\n… [truncated per file]\n"
        except OSError:
            continue
        chunk = f"### File: {rel}\n```\n{text}\n```\n"
        if used + len(chunk) > max_total:
            chunk = chunk[: max(0, max_total - used)] + "\n… [truncated total]\n"
            parts.append(chunk)
            break
        parts.append(chunk)
        used += len(chunk)
    if not parts:
        return ""
    return "\n".join(parts)


def inject_project_context(data: dict[str, Any], api_path: str) -> tuple[dict[str, Any], int]:
    """Prepend system message with repo files for chat APIs; prepend to prompt for generate."""
    block = build_context_block()
    if not block:
        return data, 0
    n = len(block)
    if api_path in ("/api/chat", "/v1/chat/completions") and "messages" in data:
        msgs = data.get("messages")
        if isinstance(msgs, list) and msgs:
            sys_content = CONTEXT_PREFIX + block
            if isinstance(msgs[0], dict) and msgs[0].get("role") == "system":
                prev = str(msgs[0].get("content", ""))
                msgs[0] = {**msgs[0], "content": sys_content + "\n" + prev}
            else:
                data = {**data, "messages": [{"role": "system", "content": sys_content}, *msgs]}
    elif api_path == "/api/generate" and "prompt" in data:
        data = {
            **data,
            "prompt": CONTEXT_PREFIX + block + "\n---\n" + str(data.get("prompt", "")),
        }
    log.info("injected project context: %d chars", n)
    return data, n


def _extract_text_from_messages(messages: Any) -> str:
    if not messages:
        return ""
    for m in reversed(messages):
        if not isinstance(m, dict) or m.get("role") != "user":
            continue
        c = m.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            chunks: list[str] = []
            for block in c:
                if isinstance(block, dict) and block.get("type") == "text":
                    chunks.append(str(block.get("text", "")))
                elif isinstance(block, str):
                    chunks.append(block)
            return "\n".join(chunks)
    return ""


def classify(text: str) -> str:
    t = (text or "").strip()
    if len(t) < 2:
        return MODEL_THEORY
    if CODE_RE.search(t):
        return MODEL_CODE
    return MODEL_THEORY


def resolve_model(requested: str | None, body: dict[str, Any]) -> str:
    req = (requested or "").strip().lower()
    if req in AUTO_ALIASES:
        if "messages" in body:
            return classify(_extract_text_from_messages(body.get("messages")))
        if "prompt" in body:
            return classify(str(body.get("prompt", "")))
    return (requested or "").strip()


def _hop_by_hop(request: Request) -> dict[str, str]:
    skip = {"host", "connection", "content-length", "transfer-encoding", "keep-alive"}
    return {k: v for k, v in request.headers.items() if k.lower() not in skip}


def _response_headers_from_upstream(resp: httpx.Response, extra: dict[str, str] | None) -> dict[str, str]:
    """Forward Ollama headers; drop hop-by-hop. Do not forward Content-Length for streamed bodies."""
    skip = {"connection", "keep-alive", "content-length", "transfer-encoding", "content-encoding"}
    out = {k: v for k, v in resp.headers.items() if k.lower() not in skip}
    if extra:
        out.update(extra)
    return out


async def _stream_upstream(
    method: str,
    url: str,
    body: bytes,
    headers: dict[str, str],
    extra_headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """Stream from Ollama with upstream status + headers so browsers don't get transfer-length errors."""
    timeout = httpx.Timeout(600.0, connect=60.0)
    client = httpx.AsyncClient(timeout=timeout)
    try:
        req = client.build_request(method, url, content=body, headers=headers)
        resp = await client.send(req, stream=True)
    except Exception:
        await client.aclose()
        raise

    media = (resp.headers.get("content-type") or "application/octet-stream").split(";")[0].strip()
    out_h = _response_headers_from_upstream(resp, extra_headers)

    async def gen() -> AsyncIterator[bytes]:
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            try:
                await resp.aclose()
            finally:
                await client.aclose()

    return StreamingResponse(
        gen(),
        status_code=resp.status_code,
        media_type=media,
        headers=out_h,
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "upstream": UPSTREAM}


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy(full_path: str, request: Request) -> Response:
    path = "/" + full_path if full_path else "/"
    url = f"{UPSTREAM}{path}"
    if request.query_params:
        url = f"{url}?{request.query_params}"

    headers = _hop_by_hop(request)

    if request.method == "GET" and path == "/api/tags":
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=30.0)) as client:
            r = await client.get(url, headers=headers)
        if r.status_code != 200:
            return Response(content=r.content, status_code=r.status_code)
        try:
            payload = r.json()
        except json.JSONDecodeError:
            return Response(content=r.content, status_code=r.status_code)
        models = payload.get("models") or []
        if not any(
            isinstance(m, dict) and (m.get("name") == "auto" or m.get("model") == "auto") for m in models
        ):
            models = [
                {
                    "name": "auto",
                    "model": "auto",
                    "modified_at": "1970-01-01T00:00:00Z",
                    "size": 0,
                    "digest": "router",
                    "details": {
                        "parent_model": "",
                        "format": "router",
                        "family": "router",
                        "families": ["router"],
                        "parameter_size": "0B",
                        "quantization_level": "ROUTER",
                    },
                }
            ] + list(models)
        payload["models"] = models
        return JSONResponse(content=payload)

    if request.method in ("POST", "PUT", "PATCH"):
        raw = await request.body()
        ct = request.headers.get("content-type", "")
        stream_json = False
        out_body = raw

        router_meta: dict[str, str] = {}
        looks_json = bool(raw) and raw.lstrip()[:1] in (b"{", b"[")
        if raw and ("application/json" in ct or looks_json):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    data, ctx_chars = inject_project_context(data, path)
                    if ctx_chars > 0:
                        router_meta["X-Router-Context-Chars"] = str(ctx_chars)
                    if "model" in data:
                        requested = str(data.get("model", "")).strip()
                        new_model = resolve_model(requested, data)
                        if new_model:
                            data["model"] = new_model
                        if requested.lower() in AUTO_ALIASES:
                            final = str(data.get("model", ""))
                            bucket = "code" if final == MODEL_CODE else "theory"
                            router_meta.update(
                                {
                                    "X-Router-Requested": requested,
                                    "X-Router-Resolved-Model": final,
                                    "X-Router-Bucket": bucket,
                                }
                            )
                            log.info("auto route: %r -> %r (%s)", requested, final, bucket)
                    out_body = json.dumps(data).encode("utf-8")
                    stream_json = bool(data.get("stream"))
            except (json.JSONDecodeError, TypeError):
                pass

        headers = _hop_by_hop(request)
        headers["content-length"] = str(len(out_body))

        if stream_json and request.method == "POST":
            return await _stream_upstream(request.method, url, out_body, headers, router_meta)

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            r = await client.request(request.method, url, content=out_body, headers=headers)
        out_h = dict(r.headers)
        for k, v in router_meta.items():
            out_h[k] = v
        return Response(content=r.content, status_code=r.status_code, headers=out_h)

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
        r = await client.request(request.method, url, headers=headers)
    return Response(content=r.content, status_code=r.status_code, headers=dict(r.headers))
