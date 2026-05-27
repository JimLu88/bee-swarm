"""
H-SEMAS 桌面启动器：常驻小窗口，一键启动 / 停止 / 重启后端 h-semas.exe。

开发：python scripts/h_semas_launcher.py
发布：与 h-semas.exe 同目录放置 h-semas-launcher.exe，数据仍写入同目录 data/ 。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox, scrolledtext

# Windows: 启动后端时不弹出黑色控制台
if sys.platform == "win32":
    _CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
else:
    _CREATE_NO_WINDOW = 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_server_exe() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "h-semas.exe"
    return _repo_root() / "backend" / "dist" / "h-semas.exe"


def _server_cwd(server_path: Path) -> Path:
    return server_path.resolve().parent


class LauncherApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("H-SEMAS 服务启动器")
        self.root.geometry("520x420")
        self.root.minsize(480, 360)

        self._proc: subprocess.Popen[Any] | None = None
        self._lock = threading.Lock()
        self._poll_after_id: str | None = None

        self._build_ui()
        self._schedule_poll()

    def _build_ui(self) -> None:
        top = tk.Frame(self.root, padx=10, pady=8)
        top.pack(fill=tk.X)

        self.lbl_exe = tk.Label(top, text="", anchor="w", justify=tk.LEFT, wraplength=480)
        self.lbl_exe.pack(fill=tk.X)
        self._refresh_exe_label()

        row1 = tk.Frame(top)
        row1.pack(fill=tk.X, pady=(8, 4))
        tk.Button(row1, text="启动服务器", command=self._on_start, width=14).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(row1, text="停止", command=self._on_stop, width=10).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(row1, text="重启服务器", command=self._on_restart, width=14).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(row1, text="打开网页", command=self._on_open_browser, width=10).pack(side=tk.LEFT)

        row2 = tk.Frame(top)
        row2.pack(fill=tk.X, pady=4)
        self.lbl_status = tk.Label(row2, text="状态：未运行", fg="#37474f", font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(anchor="w")

        hint = (
            "说明：请先在本目录运行过打包脚本生成 h-semas.exe。\n"
            "改代码后点「重启服务器」即可加载新版本；可最小化本窗口常驻任务栏。"
        )
        tk.Label(top, text=hint, justify=tk.LEFT, fg="#546e7a", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

        log_frame = tk.LabelFrame(self.root, text="日志", padx=6, pady=6)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.log = scrolledtext.ScrolledText(log_frame, height=14, state=tk.DISABLED, font=("Consolas", 9))
        self.log.pack(fill=tk.BOTH, expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _refresh_exe_label(self) -> None:
        p = resolve_server_exe()
        exists = p.exists()
        tip = "（文件存在）" if exists else "（未找到：请先运行 scripts/package-b2.ps1 打包）"
        self.lbl_exe.config(
            text=f"后端程序：{p}\n{tip}",
            fg="#2e7d32" if exists else "#c62828",
        )

    def _append_log(self, line: str) -> None:
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, line + "\n")
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _set_status(self, text: str, color: str = "#37474f") -> None:
        self.lbl_status.config(text=text, fg=color)

    def _is_running(self) -> bool:
        with self._lock:
            if self._proc is None:
                return False
            return self._proc.poll() is None

    def _on_start(self) -> None:
        exe = resolve_server_exe()
        if not exe.exists():
            messagebox.showerror("启动失败", f"找不到后端程序：\n{exe}\n\n请先打包：scripts/package-b2.ps1（仓库根目录运行）")
            return
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                messagebox.showinfo("提示", "服务器已在运行中。")
                return
            cwd = _server_cwd(exe)
            cwd.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            # 与 hsemas_entry 一致：默认本机
            env.setdefault("HSEMAS_HOST", "127.0.0.1")
            env.setdefault("HSEMAS_PORT", "8000")
            env.setdefault("HSEMAS_OPEN_BROWSER", "0")  # 由启动器统一「打开网页」
            try:
                self._proc = subprocess.Popen(
                    [str(exe)],
                    cwd=str(cwd),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=_CREATE_NO_WINDOW,
                )
            except Exception as e:
                self._proc = None
                messagebox.showerror("启动失败", str(e))
                return
        self._append_log(f"[{time.strftime('%H:%M:%S')}] 已启动 PID={self._proc.pid}  cwd={cwd}")
        self._set_status(f"状态：运行中 (PID {self._proc.pid})", "#2e7d32")

    def _on_stop(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            self._append_log(f"[{time.strftime('%H:%M:%S')}] 当前没有运行中的进程。")
            self._set_status("状态：未运行", "#37474f")
            return
        self._terminate_process(proc)
        with self._lock:
            self._proc = None
        self._append_log(f"[{time.strftime('%H:%M:%S')}] 已请求停止。")
        self._set_status("状态：未运行", "#37474f")

    def _terminate_process(self, proc: subprocess.Popen[Any]) -> None:
        try:
            if sys.platform == "win32":
                # 结束整棵进程树（uvicorn 子进程）
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    creationflags=_CREATE_NO_WINDOW,
                )
            else:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception as e:
            self._append_log(f"[停止异常] {e!r}")

    def _on_restart(self) -> None:
        self._append_log(f"[{time.strftime('%H:%M:%S')}] —— 重启 ——")
        self._on_stop()
        time.sleep(0.6)
        self._on_start()

    def _on_open_browser(self) -> None:
        host = os.environ.get("HSEMAS_HOST", "127.0.0.1")
        port = os.environ.get("HSEMAS_PORT", "8000")
        if host in ("0.0.0.0", "", "::"):
            host = "127.0.0.1"
        url = f"http://{host}:{port}/"
        try:
            webbrowser.open(url)
            self._append_log(f"[{time.strftime('%H:%M:%S')}] 打开浏览器 {url}")
        except Exception as e:
            messagebox.showwarning("打开浏览器", str(e))

    def _schedule_poll(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            self._set_status(f"状态：运行中 (PID {proc.pid})", "#2e7d32")
        else:
            if proc is not None:
                code = proc.poll()
                if code is not None:
                    self._append_log(f"[{time.strftime('%H:%M:%S')}] 进程已退出，代码={code}")
                    with self._lock:
                        self._proc = None
            self._set_status("状态：未运行", "#37474f")
        self._poll_after_id = self.root.after(1500, self._schedule_poll)

    def _on_close(self) -> None:
        if self._is_running():
            if not messagebox.askokcancel(
                "退出",
                "服务器仍在运行。确定退出启动器？\n（将先停止后端进程）",
            ):
                return
            with self._lock:
                proc = self._proc
            if proc is not None:
                self._terminate_process(proc)
        if self._poll_after_id:
            self.root.after_cancel(self._poll_after_id)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    LauncherApp().run()


if __name__ == "__main__":
    main()
