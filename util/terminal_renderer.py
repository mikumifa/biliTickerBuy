from __future__ import annotations

from dataclasses import dataclass
import inspect
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


def _extract_message_meta(item) -> tuple[str, str, int | None, int | None]:
    message = getattr(item, "message", item)
    kind = getattr(item, "kind", "normal")
    state = getattr(item, "state", None)
    attempt_current = getattr(state, "attempt_current", None)
    attempt_total = getattr(state, "attempt_total", None)
    return str(message), str(kind), attempt_current, attempt_total


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

    def render_message(self, item) -> None:
        message = getattr(item, "message", item)
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


def _make_log_item(item) -> LogItem:
    message, kind, attempt_current, attempt_total = _extract_message_meta(item)

    if kind != "attempt" or attempt_current is None or attempt_total is None:
        return LogItem(
            raw_message=message,
            display_message=message,
            count=1,
            kind="normal",
        )

    return LogItem(
        raw_message=message,
        display_message=message,
        count=1,
        kind="attempt",
        attempt_start=attempt_current,
        attempt_end=attempt_current,
        attempt_total=attempt_total,
        attempt_body=message,
    )


def _can_merge_log_item(item: LogItem, next_item) -> bool:
    message, kind, attempt_current, attempt_total = _extract_message_meta(next_item)
    if item.kind == "normal":
        return item.raw_message == message

    if kind != "attempt" or attempt_current is None or attempt_total is None:
        return False

    if item.attempt_end is None:
        return False

    return (
        item.kind == "attempt"
        and item.attempt_total == attempt_total
        and item.attempt_body == message
        and attempt_current == item.attempt_end + 1
    )


def _merge_log_item(item: LogItem, next_item) -> None:
    message, kind, attempt_current, attempt_total = _extract_message_meta(next_item)
    if item.kind == "normal":
        item.count += 1
        return

    if kind != "attempt" or attempt_current is None or attempt_total is None:
        item.count += 1
        return

    item.raw_message = message
    item.count += 1
    item.attempt_end = attempt_current
    item.attempt_total = attempt_total
    item.attempt_body = message

    if item.attempt_start == item.attempt_end:
        item.display_message = (
            f"[{item.attempt_start}/{attempt_total}] {message}".rstrip()
        )
    else:
        item.display_message = f"[{item.attempt_start}-{item.attempt_end}/{attempt_total}] {message}".rstrip()


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

            def render_log_message(self, message: str, item: LogItem) -> Text:
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
                    or message.startswith("目前已配置代理")
                    or message.startswith("切换代理到 ")
                    or message.startswith("代理冷却:")
                    or message.startswith("代理池状态:")
                    or message.startswith("所有代理当前不可用")
                ):
                    text.append("⇄ ", style="yellow")
                    text.append(message, style="yellow")
                    return text

                if "抢票成功" in message or "创建订单成功" in message:
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

                if item.kind == "attempt":
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
                line = self.render_log_message(item.display_message, item)

                if item.count > 1:
                    line.append(f"  x{item.count}", style="bold dim")

                return line

            def add_message(self, event) -> None:
                self.message_count += 1

                if self.log_items and _can_merge_log_item(self.log_items[-1], event):
                    _merge_log_item(self.log_items[-1], event)
                else:
                    self.log_items.append(_make_log_item(event))

                self.update_log()

        self.app = TicketTerminalApp()
        self.thread = None

    def _dump_final_snapshot(self) -> None:
        state = self.app.state
        print(
            f"[抢票终端] 配置: {self.context.config_name} | 日志: {self.context.log_file}",
            flush=True,
        )
        print(
            (
                "[状态] "
                f"阶段: {state.stage} | "
                f"倒计时: {state.countdown} | "
                f"代理: {state.current_proxy} | "
                f"冷却: {state.cooldown}"
            ),
            flush=True,
        )
        if not self.app.log_items:
            print("等待日志输出...", flush=True)
            return
        for item in self.app.log_items:
            print(item.display_message, flush=True)

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

    def render_message(self, item) -> None:
        self.app.call_from_thread(self.app.add_message, item)

    def render_state(self, state) -> None:
        self.app.call_from_thread(self.app.sync_state, state)

    def close(self) -> None:
        try:
            self.app.call_from_thread(self.app.exit)
        except Exception:
            pass
        try:
            if self.thread is not None:
                self.thread.join(timeout=2)
        except Exception:
            pass
        self._dump_final_snapshot()


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
                renderer.render_message(item)

    finally:
        if renderer is not None:
            renderer.close()
