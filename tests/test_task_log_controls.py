import signal

import tab.log as task_log
from util import GlobalStatusInstance, TaskLogEntry


def test_is_task_running_treats_posix_zombie_as_stopped(monkeypatch):
    monkeypatch.setattr(task_log.os.path, "exists", lambda _path: False)

    class PsResult:
        stdout = "Z\n"

    monkeypatch.setattr(task_log.subprocess, "run", lambda *args, **kwargs: PsResult())

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("zombie process should be handled before os.kill")

    monkeypatch.setattr(task_log.os, "kill", fail_if_called)

    assert task_log.is_task_running(12345) is False


def test_terminate_task_falls_back_to_process_signal_when_group_denied(monkeypatch):
    running_states = iter([True, False])
    signals_sent = []

    monkeypatch.setattr(task_log, "is_task_running", lambda _pid: next(running_states))
    monkeypatch.setattr(task_log.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        task_log.os,
        "killpg",
        lambda _pgid, _sig: (_ for _ in ()).throw(PermissionError()),
    )
    monkeypatch.setattr(
        task_log.os,
        "kill",
        lambda pid, sig: signals_sent.append((pid, sig)),
    )

    assert task_log.terminate_task(12345) == "已停止任务进程。"
    assert signals_sent == [(12345, signal.SIGTERM)]


def test_terminate_task_returns_message_when_signal_permission_denied(monkeypatch):
    monkeypatch.setattr(task_log, "is_task_running", lambda _pid: True)
    monkeypatch.setattr(task_log.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(
        task_log.os,
        "killpg",
        lambda _pgid, _sig: (_ for _ in ()).throw(PermissionError()),
    )
    monkeypatch.setattr(
        task_log.os,
        "kill",
        lambda _pid, _sig: (_ for _ in ()).throw(PermissionError()),
    )

    assert task_log.terminate_task(12345) == "停止任务进程失败：没有权限。"


def test_stop_all_running_tasks_stops_only_active_pid_entries(monkeypatch, tmp_path):
    log_file = tmp_path / "running.log"
    log_file.write_text("", encoding="utf-8")
    stopped_pids = []
    info_messages = []

    original_task_logs = GlobalStatusInstance.task_logs
    GlobalStatusInstance.task_logs = [
        TaskLogEntry(
            title="running",
            mode="终端",
            log_file=str(log_file),
            created_at=1,
            pid=111,
            status=task_log.TASK_STATUS_RUNNING,
        ),
        TaskLogEntry(
            title="completed",
            mode="终端",
            log_file=str(tmp_path / "completed.log"),
            created_at=1,
            pid=222,
            status=task_log.TASK_STATUS_COMPLETED,
        ),
        TaskLogEntry(
            title="missing-pid",
            mode="终端",
            log_file=str(tmp_path / "missing.log"),
            created_at=1,
            pid=None,
            status=task_log.TASK_STATUS_RUNNING,
        ),
    ]

    try:
        monkeypatch.setattr(task_log, "is_task_running", lambda pid: pid == 111)

        def fake_terminate_task(pid):
            stopped_pids.append(pid)
            return "已停止任务进程。"

        monkeypatch.setattr(task_log, "terminate_task", fake_terminate_task)
        monkeypatch.setattr(
            task_log.gr,
            "Info",
            lambda message: info_messages.append(message),
        )
        monkeypatch.setattr(task_log.gr, "Warning", lambda message: None)

        token, panel_update = task_log.stop_all_running_tasks()

        assert isinstance(token, int)
        assert panel_update["visible"] is True
        assert stopped_pids == [111]
        assert (
            GlobalStatusInstance.get_task_log(111).status
            == task_log.TASK_STATUS_STOPPED
        )
        assert (
            GlobalStatusInstance.get_task_log(222).status
            == task_log.TASK_STATUS_COMPLETED
        )
        assert "BTB_TASK_STOPPED_BY_USER" in log_file.read_text(encoding="utf-8")
        assert info_messages == ["已终止 1 个抢票任务。"]
    finally:
        GlobalStatusInstance.task_logs = original_task_logs
