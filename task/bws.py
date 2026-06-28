from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass

from app_cmd.config.BwsConfig import BwsConfig


@dataclass(slots=True)
class Bws:
    config: BwsConfig

    def to_cli_args(self) -> list[str]:
        return ["bws", *self.config.to_cli_args()]

    def start_new_terminal(
        self,
        *,
        log_file_path: str | None = None,
    ) -> subprocess.Popen:
        if getattr(sys, "frozen", False):
            command = [sys.executable]
        else:
            script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            main_py = os.path.join(script_dir, "main.py")

            if os.path.exists(main_py):
                command = [sys.executable, main_py]
            else:
                btb_path = shutil.which("btb")
                if not btb_path:
                    raise RuntimeError("Cannot find main.py or btb command")
                command = [btb_path]

        command.extend(self.to_cli_args())

        env = os.environ.copy()
        env["BTB_PARENT_PID"] = str(os.getpid())
        if log_file_path:
            env["BTB_APP_LOG_NAME"] = os.path.basename(log_file_path)
        else:
            env.setdefault("BTB_APP_LOG_NAME", f"bws-{uuid.uuid4().hex}.log")

        kwargs: dict[str, object] = {}
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE
            )
            env["BTB_HOLD_TERMINAL"] = "1"
            return subprocess.Popen(command, env=env, **kwargs)

        env["BTB_CHILD_PROCESS"] = "1"
        kwargs["start_new_session"] = True
        with open(os.devnull, "r") as devnull_in, open(os.devnull, "a") as devnull_out:
            return subprocess.Popen(
                command,
                env=env,
                stdin=devnull_in,
                stdout=devnull_out,
                stderr=devnull_out,
                **kwargs,
            )


def bws_new_terminal(
    config: BwsConfig,
    log_file_path: str | None = None,
) -> subprocess.Popen:
    return Bws(config=config).start_new_terminal(log_file_path=log_file_path)
