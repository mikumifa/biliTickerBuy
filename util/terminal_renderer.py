from __future__ import annotations

from dataclasses import dataclass
import inspect
import re
from typing import Iterable


@dataclass(frozen=True)
class TerminalRenderContext:
    config_name: str
    log_file: str
    platform_name: str


@dataclass
class TerminalViewState:
    stage: str = "初始化"
    countdown: str = "-"
    current_proxy: str = "未初始化"
    cooldown: str = "-"


@dataclass
class LogItem:
    raw_message: str
    display_message: str
    count: int = 1
    kind: str = "normal"
    attempt_start: int | None = None
    attempt_end: int | None = None
    attempt_total: int | None = None
    attempt_body: str | None = None


_ATTEMPT_RE = re.compile(r"^\[(\d+)/(\d+)\]\s*(.*)$")


class BaseTerminalRenderer:
    def __init__(self, context: TerminalRenderContext):
        self.context = context

    def render_header(self) -> None:
        raise NotImplementedError

    def render_message(self, message: str) -> None:
        raise NotImplementedError

    def render_state(self, state) -> None:
        return None

    def close(self) -> None:
        return None


class PlainTerminalRenderer(BaseTerminalRenderer):
    """Stable fallback for terminals where Textual cannot render reliably."""

    def __init__(self, context: TerminalRenderContext):
        super().__init__(context)
        self.state = TerminalViewState()
        self._last_snapshot: tuple[str, str, str, str] | None = None

    def render_header(self) -> None:
        print(
            f"[抢票终端] 配置: {self.context.config_name} | 日志: {self.context.log_file}",
            flush=True,
        )
        self._print_snapshot(force=True)

    def render_message(self, message: str) -> None:
        self._update_state_from_message(message)
        self._print_snapshot()
        print(message, flush=True)

    def render_state(self, state) -> None:
        self.state.stage = getattr(state, "stage", self.state.stage)
        self.state.countdown = getattr(state, "countdown", self.state.countdown)
        self.state.current_proxy = getattr(
            state, "current_proxy", self.state.current_proxy
        )
        cooldown_remaining = getattr(state, "cooldown_remaining", None)
        self.state.cooldown = (
            f"{cooldown_remaining} 秒"
            if isinstance(cooldown_remaining, int) and cooldown_remaining > 0
            else "-"
        )
        self._print_snapshot()

    def _update_state_from_message(self, message: str) -> None:
        if message.startswith("0)"):
            self.state.stage = "等待开票"
        elif message.startswith("1）"):
            self.state.stage = "订单准备"
        elif message.startswith("2）"):
            self.state.stage = "创建订单"
        elif message.startswith("3）"):
            self.state.stage = "抢票成功"

        if message.startswith("距离开始抢票还有:"):
            self.state.countdown = message.split(":", 1)[1].strip()

        if message.startswith("当前代理:"):
            match = re.search(r"^当前代理:\s*(.+)$", message)
            if match:
                self.state.current_proxy = match.group(1).strip()
        elif message.startswith("切换代理到 "):
            match = re.search(r"^切换代理到\s+(.+)$", message)
            if match:
                self.state.current_proxy = match.group(1).strip()
        elif message.startswith("所有代理当前不可用，休息 "):
            match = re.search(r"休息\s+(\d+)\s+秒后再试", message)
            if match:
                self.state.cooldown = f"{match.group(1)} 秒"

    def _print_snapshot(self, *, force: bool = False) -> None:
        snapshot = (
            self.state.stage,
            self.state.countdown,
            self.state.current_proxy,
            self.state.cooldown,
        )
        if not force and snapshot == self._last_snapshot:
            return

        print(
            (
                "[状态] "
                f"阶段: {self.state.stage} | "
                f"倒计时: {self.state.countdown} | "
                f"代理: {self.state.current_proxy} | "
                f"冷却: {self.state.cooldown}"
            ),
            flush=True,
        )
        self._last_snapshot = snapshot


def _parse_attempt(message: str) -> tuple[int, int, str] | None:
    match = _ATTEMPT_RE.match(message)
    if not match:
        return None

    current = int(match.group(1))
    total = int(match.group(2))
    body = match.group(3).strip()
    return current, total, body


def _make_log_item(message: str) -> LogItem:
    parsed = _parse_attempt(message)

    if parsed is None:
        return LogItem(
            raw_message=message,
            display_message=message,
            count=1,
            kind="normal",
        )

    current, total, body = parsed
    return LogItem(
        raw_message=message,
        display_message=message,
        count=1,
        kind="attempt",
        attempt_start=current,
        attempt_end=current,
        attempt_total=total,
        attempt_body=body,
    )


def _can_merge_log_item(item: LogItem, message: str) -> bool:
    if item.kind == "normal":
        return item.raw_message == message

    parsed = _parse_attempt(message)
    if parsed is None:
        return False

    current, total, body = parsed

    if item.attempt_end is None:
        return False

    return (
        item.kind == "attempt"
        and item.attempt_total == total
        and item.attempt_body == body
        and current == item.attempt_end + 1
    )


def _merge_log_item(item: LogItem, message: str) -> None:
    if item.kind == "normal":
        item.count += 1
        return

    parsed = _parse_attempt(message)
    if parsed is None:
        item.count += 1
        return

    current, total, body = parsed

    item.raw_message = message
    item.count += 1
    item.attempt_end = current
    item.attempt_total = total
    item.attempt_body = body

    if item.attempt_start == item.attempt_end:
        item.display_message = f"[{item.attempt_start}/{total}] {body}".rstrip()
    else:
        item.display_message = (
            f"[{item.attempt_start}-{item.attempt_end}/{total}] {body}".rstrip()
        )


class TextualTerminalRenderer(BaseTerminalRenderer):
    def __init__(self, context: TerminalRenderContext):
        super().__init__(context)

        import threading

        from rich.console import Group
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        from textual.app import App, ComposeResult
        from textual.containers import Vertical, VerticalScroll
        from textual.widgets import Static

        self.threading = threading
        self.ready = threading.Event()

        ready = self.ready

        class TicketTerminalApp(App):
            CSS = """
            Screen {
                background: #0f1117;
            }

            #root {
                height: 100%;
                padding: 1 2;
            }

            #status {
                height: 5;
                margin-bottom: 1;
            }

            #log_container {
                height: 1fr;
                border: round #3b4252;
                background: #111827;
            }

            #log {
                height: auto;
                min-height: 100%;
                padding: 0 1;
            }
            """

            BINDINGS = [
                ("q", "quit", "退出"),
                ("ctrl+c", "quit", "退出"),
            ]

            def __init__(self):
                super().__init__()

                self.state = TerminalViewState()
                self.status_widget: Static | None = None
                self.log_container: VerticalScroll | None = None
                self.log_widget: Static | None = None

                self.message_count = 0
                self.log_items: list[LogItem] = []

            def compose(self) -> ComposeResult:
                # 不显示 Header / Footer，所以不会出现标题栏和底部快捷键栏。
                # 退出键位放在顶部状态区里显示。
                with Vertical(id="root"):
                    self.status_widget = Static(id="status")
                    yield self.status_widget

                    with VerticalScroll(id="log_container") as log_container:
                        self.log_container = log_container
                        self.log_widget = Static(id="log")
                        yield self.log_widget

            def on_mount(self) -> None:
                self.title = ""
                self.sub_title = ""

                self.update_status()
                self.update_log()

                ready.set()

            def update_status(self) -> None:
                table = Table.grid(expand=True)
                table.add_column(style="dim", ratio=1)
                table.add_column(style="bold white", ratio=3)

                table.add_row(
                    "倒计时",
                    self.state.countdown,
                )
                table.add_row(
                    "代理状态",
                    self._shorten(self.state.current_proxy, 96),
                )
                table.add_row(
                    "冷却",
                    self.state.cooldown,
                )

                panel = Panel(
                    table,
                    border_style="cyan",
                    padding=(0, 1),
                    expand=True,
                )

                if self.status_widget is not None:
                    self.status_widget.update(panel)

            def update_log(self) -> None:
                if self.log_widget is None:
                    return

                if not self.log_items:
                    self.log_widget.update(Text("等待日志输出...", style="dim"))
                    return

                rendered = [self.render_log_item(item) for item in self.log_items]
                self.log_widget.update(Group(*rendered))
                if self.log_container is not None:
                    self.log_container.scroll_end(animate=False)

            @staticmethod
            def _shorten(text: str, width: int = 60) -> str:
                if not text or text == "-":
                    return "-"
                return text if len(text) <= width else text[: width - 1] + "…"

            def update_state(self, message: str) -> None:
                if message.startswith("0)"):
                    self.state.stage = "等待开票"
                elif message.startswith("1）"):
                    self.state.stage = "订单准备"
                elif message.startswith("2）"):
                    self.state.stage = "创建订单"
                elif message.startswith("3）"):
                    self.state.stage = "抢票成功"

                if message.startswith("距离开始抢票还有:"):
                    self.state.countdown = message.split(":", 1)[1].strip()

                if message.startswith("当前代理:"):
                    match = re.search(r"^当前代理:\s*(.+)$", message)
                    if match:
                        self.state.current_proxy = match.group(1).strip()

                elif message.startswith("切换代理到 "):
                    match = re.search(r"^切换代理到\s+(.+)$", message)
                    if match:
                        self.state.current_proxy = match.group(1).strip()

                elif message.startswith("所有代理当前不可用，休息 "):
                    match = re.search(r"休息\s+(\d+)\s+秒后再试", message)
                    if match:
                        self.state.cooldown = f"{match.group(1)} 秒"

            def sync_state(self, state) -> None:
                self.state.stage = getattr(state, "stage", self.state.stage)
                self.state.countdown = getattr(state, "countdown", self.state.countdown)
                self.state.current_proxy = getattr(
                    state, "current_proxy", self.state.current_proxy
                )
                cooldown_remaining = getattr(state, "cooldown_remaining", None)
                self.state.cooldown = (
                    f"{cooldown_remaining} 秒"
                    if isinstance(cooldown_remaining, int) and cooldown_remaining > 0
                    else "-"
                )
                self.update_status()

            def render_log_message(self, message: str) -> Text:
                text = Text()

                if message.startswith(("0)", "1）", "2）", "3）")):
                    text.append("● ", style="bold cyan")
                    text.append(message, style="bold white")
                    return text

                if message.startswith("距离开始抢票还有"):
                    text.append("⏱ ", style="cyan")
                    text.append(message, style="cyan")
                    return text

                if "412风控" in message:
                    text.append("⚠ ", style="bold yellow")
                    text.append(message, style="bold yellow")
                    return text

                if (
                    message.startswith("当前代理:")
                    or message.startswith("切换代理到 ")
                    or message.startswith("代理冷却:")
                    or message.startswith("代理池状态:")
                    or message.startswith("所有代理当前不可用")
                ):
                    text.append("⇄ ", style="yellow")
                    text.append(message, style="yellow")
                    return text

                if "抢票成功" in message or "请求成功" in message:
                    text.append("✓ ", style="bold green")
                    text.append(message, style="bold green")
                    return text

                if (
                    "接口异常" in message
                    or "请求异常" in message
                    or "程序异常" in message
                ):
                    text.append("✕ ", style="bold red")
                    text.append(message, style="bold red")
                    return text

                if _parse_attempt(message) is not None:
                    if "[900001]" in message or "[900002]" in message:
                        text.append("… ", style="yellow")
                        text.append(message, style="yellow")
                    elif "[100041]" in message or "[100009]" in message:
                        text.append("… ", style="magenta")
                        text.append(message, style="magenta")
                    else:
                        text.append("… ", style="dim")
                        text.append(message, style="white")
                    return text

                text.append("  ", style="dim")
                text.append(message, style="white")
                return text

            def render_log_item(self, item: LogItem) -> Text:
                line = self.render_log_message(item.display_message)

                if item.count > 1:
                    line.append(f"  x{item.count}", style="bold dim")

                return line

            def add_message(self, message: str) -> None:
                self.message_count += 1

                self.update_state(message)
                self.update_status()

                if self.log_items and _can_merge_log_item(self.log_items[-1], message):
                    _merge_log_item(self.log_items[-1], message)
                else:
                    self.log_items.append(_make_log_item(message))

                self.update_log()

        self.app = TicketTerminalApp()
        self.thread = None

    def render_header(self) -> None:
        def run_app() -> None:
            try:
                signature = inspect.signature(self.app.run)
                params = signature.parameters

                run_kwargs = {}

                # Textual 新版本支持 inline 模式。
                # inline=True 可以避免进入全屏 alternate screen；
                # inline_no_clear=True 可以在退出后保留最后的界面输出，方便继续看日志。
                if "inline" in params:
                    run_kwargs["inline"] = True

                if "inline_no_clear" in params:
                    run_kwargs["inline_no_clear"] = True

                self.app.run(**run_kwargs)
            except TypeError:
                self.app.run()

        self.thread = self.threading.Thread(
            target=run_app,
            daemon=True,
        )
        self.thread.start()

        if not self.ready.wait(timeout=5):
            raise RuntimeError("Textual terminal renderer failed to start")

    def render_message(self, message: str) -> None:
        self.app.call_from_thread(self.app.add_message, message)

    def render_state(self, state) -> None:
        self.app.call_from_thread(self.app.sync_state, state)

    def close(self) -> None:
        try:
            self.app.call_from_thread(self.app.exit)
        except Exception:
            pass


def create_terminal_renderer(
    context: TerminalRenderContext,
    *,
    prefer_rich: bool = True,
) -> BaseTerminalRenderer:
    if context.platform_name == "nt":
        try:
            if prefer_rich:
                return TextualTerminalRenderer(context)
        except Exception:
            pass
        return PlainTerminalRenderer(context)

    if prefer_rich:
        try:
            return TextualTerminalRenderer(context)
        except Exception:
            pass

    return PlainTerminalRenderer(context)


def render_message_stream(
    renderer: BaseTerminalRenderer | None,
    messages: Iterable,
    on_message=None,
) -> None:
    if renderer is not None:
        renderer.render_header()

    try:
        for item in messages:
            state = getattr(item, "state", None)
            message = getattr(item, "message", item)

            if renderer is not None and state is not None:
                renderer.render_state(state)

            if message is None:
                continue

            if on_message is not None:
                on_message(message)

            if renderer is not None:
                renderer.render_message(message)

    finally:
        if renderer is not None:
            renderer.close()
