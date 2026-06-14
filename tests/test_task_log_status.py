from pathlib import Path

from tab import log as log_tab
from util import GlobalStatusInstance


def test_sync_task_statuses_marks_user_closed_task_as_stopped(tmp_path: Path):
    log_file = tmp_path / "task.log"
    log_file.write_text("BTB_TASK_STOPPED_BY_USER\n", encoding="utf-8")

    GlobalStatusInstance.task_logs = []
    GlobalStatusInstance.register_task_log(
        title="demo",
        mode="终端",
        log_file=str(log_file),
        pid=12345,
    )

    original_is_task_running = log_tab.is_task_running
    try:
        log_tab.is_task_running = lambda _pid: False
        entries = log_tab.sync_task_statuses()
    finally:
        log_tab.is_task_running = original_is_task_running
        GlobalStatusInstance.task_logs = []

    assert len(entries) == 1
    assert entries[0].status == log_tab.TASK_STATUS_STOPPED
