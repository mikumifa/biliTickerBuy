from __future__ import annotations

import gradio as gr

import tab.config as config_tab


class _FakeConfigDB:
    """In-memory stand-in for util.ConfigDB used by the settings tab."""

    def __init__(self):
        self.store: dict = {}

    def insert(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def get_as_int(self, key, default):
        raw = self.store.get(key)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    def get_as_bool(self, key, default):
        value = self.store.get(key)
        if value is None:
            return default
        return bool(value)


def _build_tab(monkeypatch):
    """Construct the settings tab with a fake ConfigDB and return its handlers.

    Returns a mapping of callback function name -> callable so tests can drive
    the notifier advanced-parameter callbacks (which are closures inside
    go_settings_tab and not otherwise importable).
    """
    fake = _FakeConfigDB()
    monkeypatch.setattr(config_tab, "ConfigDB", fake)

    with gr.Blocks():
        header_ui = gr.Markdown("header")
        config_tab.go_settings_tab(header_ui)
        handlers = {}
        # Access the enclosing Blocks context to read registered handlers.
        blocks = gr.context.get_blocks_context()

    fns = getattr(blocks, "fns", {})
    for block_fn in fns.values():
        fn = getattr(block_fn, "fn", None)
        if fn is not None and getattr(fn, "__name__", "") not in handlers:
            handlers[fn.__name__] = fn
    return fake, handlers


def test_config_tab_imports():
    # Basic sanity: the module imports and exposes the entry point.
    assert hasattr(config_tab, "go_settings_tab")


def test_notify_advanced_callbacks_write_correct_db_keys(monkeypatch):
    fake, handlers = _build_tab(monkeypatch)

    for name in (
        "inner_input_notify_connect_timeout",
        "inner_input_notify_read_timeout",
        "inner_input_notify_retries",
        "inner_input_notify_backoff",
    ):
        assert name in handlers, f"missing callback: {name}"

    handlers["inner_input_notify_connect_timeout"](7)
    handlers["inner_input_notify_read_timeout"](15)
    handlers["inner_input_notify_retries"](5)
    handlers["inner_input_notify_backoff"](1.5)

    assert fake.store["notifyConnectTimeout"] == 7.0
    assert fake.store["notifyReadTimeout"] == 15.0
    assert fake.store["notifyRetries"] == 5
    assert fake.store["notifyBackoff"] == 1.5


def test_notify_advanced_callbacks_reject_invalid_values(monkeypatch):
    fake, handlers = _build_tab(monkeypatch)

    # Invalid / empty input must not write a broken value; it falls back to the
    # dataclass default (5.0 / 10.0 / 3 / 0.5).
    handlers["inner_input_notify_connect_timeout"]("not-a-number")
    handlers["inner_input_notify_read_timeout"](None)
    handlers["inner_input_notify_retries"]("")
    handlers["inner_input_notify_backoff"]("abc")

    assert fake.store["notifyConnectTimeout"] == 5.0
    assert fake.store["notifyReadTimeout"] == 10.0
    assert fake.store["notifyRetries"] == 3
    assert fake.store["notifyBackoff"] == 0.5
