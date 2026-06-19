import signal

import tab.log as task_log


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
