"""🐝 蜂群系统 看门狗 (Python).

每 5 秒检查一次后端/前端,挂了自动重启。
按 Ctrl+C 优雅关闭。

用法: 双击 启动看门狗.bat
"""
from __future__ import annotations

import os
import sys
import time
import signal
import subprocess
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


# 强制控制台 UTF-8(防中文乱码)
if sys.platform == "win32":
    os.system("chcp 65001 > nul")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


ROOT = Path(r"D:\AI\AI 蜂群系统\h-semas")
LOG_DIR = Path(os.environ["LOCALAPPDATA"]) / "bee-watchdog"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ANSI 颜色(Windows 10+ 默认开)
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_CYAN = "\033[36m"
C_GRAY = "\033[90m"
C_MAGENTA = "\033[35m"
C_RESET = "\033[0m"


class Service:
    def __init__(self, name: str, port: int, cwd: Path, argv: list[str], health_path: str, env_extra: dict[str, str] | None = None):
        self.name = name
        self.port = port
        self.cwd = cwd
        self.argv = argv
        self.health_path = health_path
        self.env_extra = env_extra or {}
        self.proc: subprocess.Popen | None = None
        self.last_start: datetime | None = None
        self.restart_count = -1  # increments to 0 on first start

    def start(self) -> None:
        log_out = LOG_DIR / f"{self.name}.out.log"
        log_err = LOG_DIR / f"{self.name}.err.log"
        # truncate
        log_out.write_text("", encoding="utf-8")
        log_err.write_text("", encoding="utf-8")

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env.update(self.env_extra)

        out_fp = open(log_out, "ab", buffering=0)
        err_fp = open(log_err, "ab", buffering=0)

        # npm/python both need shell=False but npm needs full path on Windows
        self.proc = subprocess.Popen(
            self.argv,
            cwd=str(self.cwd),
            stdout=out_fp,
            stderr=err_fp,
            env=env,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self.last_start = datetime.now()
        self.restart_count += 1

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                # On Windows, kill subprocess tree (npm spawns node etc.)
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True, timeout=10)
                else:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def is_process_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def is_http_alive(self) -> bool:
        url = f"http://127.0.0.1:{self.port}{self.health_path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bee-watchdog"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                return 200 <= resp.status < 500
        except Exception:
            return False

    def age_seconds(self) -> int:
        if not self.last_start:
            return 0
        return int((datetime.now() - self.last_start).total_seconds())


# 找 npm.cmd 全路径(Windows)
def find_npm() -> str:
    candidates = [
        r"C:\Program Files\nodejs\npm.cmd",
        r"C:\Program Files (x86)\nodejs\npm.cmd",
        os.path.join(os.environ.get("APPDATA", ""), "npm", "npm.cmd"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return "npm.cmd"  # hope PATH has it


SERVICES = [
    Service(
        name="后端",
        port=8100,
        cwd=ROOT / "backend",
        argv=["py", "-3.11", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8100"],
        health_path="/api/health",
    ),
    Service(
        name="前端",
        port=4000,
        cwd=ROOT / "frontend",
        argv=[find_npm(), "run", "dev", "--", "-p", "4000"],
        health_path="/",
        env_extra={"PORT": "4000"},
    ),
]


def banner() -> None:
    print(f"{C_CYAN}============================================{C_RESET}")
    print(f"{C_YELLOW}  🐝 蜂群系统 看门狗 (每 5 秒检查一次){C_RESET}")
    print(f"{C_GREEN}  浏览器: http://localhost:4000{C_RESET}")
    print(f"{C_GRAY}  关闭: 按 Ctrl+C{C_RESET}")
    print(f"{C_GRAY}  日志: {LOG_DIR}{C_RESET}")
    print(f"{C_CYAN}============================================{C_RESET}\n")


def status_icon(alive: bool, proc_ok: bool) -> tuple[str, str]:
    if alive:
        return ("✅", C_GREEN)
    if proc_ok:
        return ("⏳ 启动中", C_YELLOW)
    return ("❌ 退出", C_RED)


def main() -> int:
    banner()
    for svc in SERVICES:
        print(f"{C_YELLOW}🚀 启动 {svc.name} ...{C_RESET}")
        svc.start()
    print(f"\n{C_GRAY}首次启动约需 30 秒(Next.js 编译). 请耐心等.{C_RESET}\n")

    tick = 0
    first_ready_announced = False
    try:
        while True:
            tick += 1
            now = datetime.now().strftime("%H:%M:%S")
            parts = []
            all_ok = True
            for svc in SERVICES:
                alive = svc.is_http_alive()
                proc_ok = svc.is_process_alive()
                icon, color = status_icon(alive, proc_ok)
                age = svc.age_seconds()
                parts.append(
                    f"{svc.name}:{color}{icon}{C_RESET}{C_GRAY}(端口{svc.port},运行{age}s,重启{svc.restart_count}){C_RESET}"
                )
                if not alive:
                    all_ok = False
            print(f"{C_GRAY}[第{tick}次 @ {now}]{C_RESET} " + " ".join(parts))

            # restart logic
            # 注意: npm.cmd 启 node 后自己就退, py 启 uvicorn 类似. 所以"进程退" 不等于"服务挂".
            # 真实判定: HTTP 不通 AND 进程也死了 才重启.
            for svc in SERVICES:
                http_alive = svc.is_http_alive()
                proc_alive = svc.is_process_alive()
                if http_alive:
                    continue  # 服务在跑, 不管 Popen 句柄怎样
                if not proc_alive and svc.age_seconds() >= 10:
                    print(f"  {C_MAGENTA}↻ {svc.name} 真死了(HTTP 不通+进程退), 重启...{C_RESET}")
                    svc.stop()
                    svc.start()
                elif not http_alive and svc.age_seconds() >= 75:
                    print(f"  {C_MAGENTA}⚠ {svc.name} 跑了 {svc.age_seconds()}s 还没就绪, 强制重启...{C_RESET}")
                    svc.stop()
                    svc.start()

            if all_ok and not first_ready_announced:
                first_ready_announced = True
                print()
                print(f"{C_GREEN}🎉 两个服务都就绪了, 浏览器开: http://localhost:4000{C_RESET}")
                print()

            time.sleep(5)
    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}🛑 收到 Ctrl+C, 优雅停服务...{C_RESET}")
    finally:
        for svc in SERVICES:
            svc.stop()
        print(f"{C_GREEN}完成. 窗口可以关了.{C_RESET}")
        time.sleep(2)
    return 0


if __name__ == "__main__":
    sys.exit(main())