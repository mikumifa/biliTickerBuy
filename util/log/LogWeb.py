from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import time
from urllib.parse import quote

from fastapi import HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from util import LOG_DIR
from util.Constant import _LOG_STREAM_ROUTE, _LOG_VIEW_ROUTE

MAX_INITIAL_LOG_BYTES = 512 * 1024


def build_log_view_url(path: str) -> str:
    log_name = os.path.basename(path)
    return f"{_LOG_VIEW_ROUTE}?name={quote(log_name, safe='')}"


def _resolve_log_path(raw_path: str | None = None, log_name: str | None = None) -> Path:
    log_root = Path(LOG_DIR).resolve()

    if log_name:
        safe_name = os.path.basename(log_name.strip())
        if not safe_name:
            raise HTTPException(status_code=400, detail="missing log name")
        target = (log_root / safe_name).resolve()
    elif raw_path:
        target = Path(raw_path).resolve()
        try:
            target.relative_to(log_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=403, detail="log path is outside log dir"
            ) from exc
    else:
        raise HTTPException(status_code=400, detail="missing log identifier")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="log file not found")

    return target


def _read_log_text(path: Path, *, max_bytes: int | None = None) -> str:
    with open(path, "rb") as handle:
        if max_bytes is not None:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size > max_bytes:
                handle.seek(size - max_bytes)
                data = handle.read()
                text = data.decode("utf-8", errors="replace")
                return (
                    f"[日志较大，已只显示末尾 {max_bytes // 1024}KB]\n"
                    f"{text}"
                )
            handle.seek(0)
        return handle.read().decode("utf-8", errors="replace")


def attach_log_routes(app) -> None:
    if getattr(app.state, "btb_log_routes_ready", False):
        return

    @app.get(_LOG_VIEW_ROUTE, response_class=HTMLResponse)
    def view_log(
        request: Request,
        path: str | None = Query(default=None),
        name: str | None = Query(default=None),
    ) -> HTMLResponse:
        log_path = _resolve_log_path(raw_path=path, log_name=name)
        initial_text = escape(
            _read_log_text(log_path, max_bytes=MAX_INITIAL_LOG_BYTES)
        )
        title = escape(log_path.name)
        stream_url = f"{_LOG_STREAM_ROUTE}?name={quote(log_path.name, safe='')}"
        body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1220;
      --panel: #111827;
      --border: #334155;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #22c55e;
      --mono: "JetBrains Mono", Consolas, monospace;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 "Noto Sans SC", system-ui, sans-serif;
    }}
    .shell {{
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: 100vh;
    }}
    .bar {{
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
      background: rgba(17, 24, 39, 0.95);
      position: sticky;
      top: 0;
    }}
    .title {{
      font-weight: 700;
    }}
    .path {{
      margin-top: 4px;
      color: var(--muted);
      word-break: break-all;
      font-size: 12px;
    }}
    .status {{
      margin-top: 6px;
      color: var(--accent);
      font-size: 12px;
    }}
    pre {{
      margin: 0;
      padding: 16px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      font: 13px/1.5 var(--mono);
      background: var(--panel);
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="bar">
      <div class="title">实时日志</div>
      <div class="path">{escape(str(log_path))}</div>
      <div class="status" id="status">已连接，等待新日志...</div>
    </div>
    <pre id="log">{initial_text}</pre>
  </div>
  <script>
    const logEl = document.getElementById("log");
    const statusEl = document.getElementById("status");
    const stream = new EventSource({json.dumps(stream_url)});
    function stickToBottom() {{
      const gap = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight;
      return gap < 80;
    }}
    stream.addEventListener("append", (event) => {{
      const shouldScroll = stickToBottom();
      logEl.textContent += event.data;
      if (shouldScroll) {{
        logEl.scrollTop = logEl.scrollHeight;
      }}
      statusEl.textContent = "已连接，日志实时更新中";
    }});
    stream.addEventListener("reset", (event) => {{
      logEl.textContent = event.data;
      logEl.scrollTop = logEl.scrollHeight;
      statusEl.textContent = "日志已重置，已重新加载";
    }});
    stream.onerror = () => {{
      statusEl.textContent = "连接中断，正在尝试重连...";
    }};
  </script>
</body>
</html>"""
        return HTMLResponse(body)

    @app.get(_LOG_STREAM_ROUTE)
    def stream_log(
        path: str | None = Query(default=None),
        name: str | None = Query(default=None),
    ) -> StreamingResponse:
        log_path = _resolve_log_path(raw_path=path, log_name=name)

        def generate():
            position = log_path.stat().st_size
            last_ping = 0.0
            while True:
                try:
                    current_size = log_path.stat().st_size
                    if current_size < position:
                        content = _read_log_text(
                            log_path,
                            max_bytes=MAX_INITIAL_LOG_BYTES,
                        )
                        position = current_size
                        yield _sse("reset", content)
                    elif current_size > position:
                        with open(
                            log_path, "r", encoding="utf-8", errors="replace"
                        ) as handle:
                            handle.seek(position)
                            chunk = handle.read()
                        position = current_size
                        if chunk:
                            yield _sse("append", chunk)

                    now = time.time()
                    if now - last_ping >= 10:
                        last_ping = now
                        yield ": ping\n\n"
                    time.sleep(1)
                except FileNotFoundError:
                    yield _sse("append", "\n[日志文件已不存在]\n")
                    return

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    app.state.btb_log_routes_ready = True


def build_log_stream_url(path: str) -> str:
    log_name = os.path.basename(path)
    return f"{_LOG_STREAM_ROUTE}?name={quote(log_name, safe='')}"


def _sse(event: str, data: str) -> str:
    safe_data = data.replace("\r\n", "\n").replace("\r", "\n")
    return f"event: {event}\ndata: {safe_data.replace(chr(10), chr(10) + 'data: ')}\n\n"
