"""🐝 蜂群系统 托盘看门狗 (pystray 版).

无控制台窗口, 防误操作关闭。所有功能集中到右键托盘菜单。

用法: 双击 启动看门狗.bat (内部调用 pythonw tray_watchdog.pyw)
依赖: pystray>=0.19, Pillow>=10

核心:
- 默认开机起 后端 8100 + 前端 4000
- 7 剑客其它服务 + Grafana 全栈放菜单, 按需启停
- 5 秒轮询 HTTP /healthz, 挂了自动重启 (可关)
- 图标颜色随状态: 全绿 = OK / 黄 = 部分 / 红 = 有挂
"""
from __future__ import annotations

import os
import sys
import json
import time
import threading
import subprocess
import webbrowser
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from typing import Optional

import pystray
from PIL import Image, ImageDraw

# ============== 路径 / 常量 ==============

ROOT = Path(r"D:\AI\AI 蜂群系统\h-semas")
APPDATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
LOG_DIR = APPDATA / "bee-watchdog"
LOG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = LOG_DIR / "config.json"

POLL_INTERVAL_S = 5          # watchdog restart 判定周期
STATUS_REFRESH_S = 2         # 后台刷新缓存状态的周期 (菜单/图标更新)
HTTP_TIMEOUT_S = 0.5         # 本机健康检查, 0.5s 足够 (之前 3s 是元凶)
STARTUP_GRACE_S = 75
PROC_DEAD_GRACE_S = 10

OBSERV_COMPOSE = Path(r"D:\AI\observability\docker-compose.yml")


def find_npm() -> str:
    for p in (
        r"C:\Program Files\nodejs\npm.cmd",
        r"C:\Program Files (x86)\nodejs\npm.cmd",
        os.path.join(os.environ.get("APPDATA", ""), "npm", "npm.cmd"),
    ):
        if os.path.exists(p):
            return p
    return "npm.cmd"


NPM = find_npm()


# ============== 服务定义 ==============

class Service:
    def __init__(
        self,
        key: str,
        label: str,
        port: int,
        cwd: Path,
        argv: list[str],
        health_path: str,
        env_extra: dict[str, str] | None = None,
        is_core: bool = False,
        startup_grace_s: int = STARTUP_GRACE_S,
    ):
        self.key = key
        self.label = label
        self.port = port
        self.cwd = cwd
        self.argv = argv
        self.health_path = health_path
        self.env_extra = env_extra or {}
        self.is_core = is_core
        self.startup_grace_s = startup_grace_s   # 每服务可独立设 (Next.js 慢, 给 4 分钟)
        self.proc: Optional[subprocess.Popen] = None
        self.last_start: Optional[datetime] = None
        self.restart_count = -1
        self.wanted = is_core
        # 缓存状态 — 后台线程更新, 菜单/图标 lambda 只读, 永不打 HTTP
        self._cached_http_alive = False
        self._cached_proc_alive = False
        self._last_poll_ts: float = 0.0

    def start(self) -> None:
        if not self.cwd.exists():
            self._write_err(f"cwd missing: {self.cwd}")
            return
        log_out = LOG_DIR / f"{self.key}.out.log"
        log_err = LOG_DIR / f"{self.key}.err.log"
        log_out.write_text("", encoding="utf-8")
        log_err.write_text("", encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env.update(self.env_extra)
        try:
            self.proc = subprocess.Popen(
                self.argv,
                cwd=str(self.cwd),
                stdout=open(log_out, "ab", buffering=0),
                stderr=open(log_err, "ab", buffering=0),
                env=env,
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            self.last_start = datetime.now()
            self.restart_count += 1
        except Exception as e:
            self._write_err(f"start failed: {e}")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                        capture_output=True, timeout=10,
                    )
                else:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
            except Exception:
                pass
        self.proc = None
        # 保险:扫光所有还在监听 self.port 的残留进程 (npm→node 孙进程链 taskkill 经常杀不干净)
        self._kill_port_owners()

    def _kill_port_owners(self) -> None:
        """杀光所有 LISTEN 在 self.port 的进程, 杜绝下次重启 EADDRINUSE."""
        if sys.platform != "win32":
            return
        try:
            ps = (
                f"Get-NetTCPConnection -LocalPort {self.port} -State Listen -ErrorAction SilentlyContinue "
                f"| Where-Object {{ $_.OwningProcess -gt 4 }} "
                f"| Select-Object -ExpandProperty OwningProcess -Unique "
                f"| ForEach-Object {{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }}"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass

    def restart(self) -> None:
        self.stop()
        time.sleep(0.5)
        self.start()

    def is_process_alive(self) -> bool:
        """实时进程检查 (本地, 微秒级, 安全)."""
        return self.proc is not None and self.proc.poll() is None

    def _do_http_check(self) -> bool:
        """真打 HTTP — 只由后台 polling 调用, 永远别在 UI 线程调."""
        url = f"http://127.0.0.1:{self.port}{self.health_path}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bee-watchdog"})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
                return 200 <= resp.status < 500
        except Exception:
            return False

    def poll_status(self) -> None:
        """后台线程并发调用, 更新缓存. 主线程菜单 lambda 不准调这个."""
        self._cached_http_alive = self._do_http_check()
        self._cached_proc_alive = self.is_process_alive()
        self._last_poll_ts = time.time()

    def is_http_alive(self) -> bool:
        """读缓存. 主线程菜单 lambda 用. 永不阻塞."""
        return self._cached_http_alive

    def age_s(self) -> int:
        return int((datetime.now() - self.last_start).total_seconds()) if self.last_start else 0

    def status_emoji(self) -> str:
        if not self.wanted:
            return "◯"
        if self.is_http_alive():
            return "✓"
        if self.is_process_alive():
            return "…"
        return "✗"

    def _write_err(self, msg: str) -> None:
        (LOG_DIR / f"{self.key}.err.log").open("a", encoding="utf-8").write(
            f"[{datetime.now().isoformat()}] {msg}\n"
        )


SERVICES: list[Service] = [
    Service(
        key="bee-swarm-backend", label="蜂群后端 8100",
        port=8100, cwd=ROOT / "backend",
        argv=["py", "-3.11", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8100"],
        health_path="/api/health",
        is_core=True,
    ),
    Service(
        key="bee-swarm-frontend", label="前端 4000",
        port=4000, cwd=ROOT / "frontend",
        argv=[NPM, "run", "dev", "--", "-p", "4000"],
        health_path="/",
        env_extra={"PORT": "4000"},
        is_core=True,
        startup_grace_s=240,   # Next.js 删 .next 后首次全量编译能跑到 2-3 分钟
    ),
    Service(
        key="bee-ledger", label="账本 8001",
        port=8001, cwd=Path(r"D:\AI\AI 账本中心\backend"),
        argv=["py", "-3.11", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"],
        health_path="/healthz",
    ),
    Service(
        key="bee-agent-hands", label="代码手脚 8002",
        port=8002, cwd=Path(r"D:\AI\AI 代码手脚\backend"),
        argv=["py", "-3.11", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002"],
        health_path="/healthz",
    ),
    Service(
        key="bee-scraper", label="爬虫 8003",
        port=8003, cwd=Path(r"D:\AI\AI 数据爬虫\backend"),
        argv=["py", "-3.11", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8003"],
        health_path="/healthz",
    ),
    Service(
        key="bee-memory", label="记忆 8004",
        port=8004, cwd=Path(r"D:\AI\AI 记忆中心\backend"),
        argv=["py", "-3.11", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8004"],
        health_path="/healthz",
    ),
    Service(
        key="bee-vision", label="视觉 8006",
        port=8006, cwd=Path(r"D:\AI\AI 视觉中心\backend"),
        argv=["py", "-3.11", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8006"],
        health_path="/healthz",
    ),
    Service(
        key="bee-light-exec", label="轻执行 8007",
        port=8007, cwd=Path(r"D:\AI\AI 轻执行\backend"),
        argv=["py", "-3.11", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8007"],
        health_path="/healthz",
    ),
]


# ============== 配置持久化 ==============

DEFAULT_CFG = {
    "auto_restart": True,
    "autostart_enabled": False,
    "extra_services_enabled": [],
}


def load_cfg() -> dict:
    if CONFIG_PATH.exists():
        try:
            return {**DEFAULT_CFG, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(DEFAULT_CFG)


def save_cfg(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ============== 开机自启 (Windows Startup 文件夹的 .lnk) ==============

STARTUP_LNK = (
    Path(os.environ.get("APPDATA", ""))
    / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "BeeSwarmWatchdog.lnk"
)


def autostart_enable() -> bool:
    bat = ROOT / "启动看门狗.bat"
    if not bat.exists():
        return False
    ps = (
        "$s = New-Object -ComObject WScript.Shell; "
        f"$lnk = $s.CreateShortcut('{STARTUP_LNK}'); "
        f"$lnk.TargetPath = '{bat}'; "
        f"$lnk.WorkingDirectory = '{ROOT}'; "
        "$lnk.WindowStyle = 7; "
        "$lnk.Save()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return STARTUP_LNK.exists()
    except Exception:
        return False


def autostart_disable() -> bool:
    if STARTUP_LNK.exists():
        try:
            STARTUP_LNK.unlink()
            return True
        except Exception:
            return False
    return True


def autostart_is_enabled() -> bool:
    return STARTUP_LNK.exists()


# ============== Grafana 全栈 (docker compose) ==============

class GrafanaStack:
    def is_up(self) -> bool:
        try:
            with urllib.request.urlopen("http://127.0.0.1:3001/api/health", timeout=2) as r:
                return 200 <= r.status < 500
        except Exception:
            return False

    def up(self) -> tuple[bool, str]:
        if not OBSERV_COMPOSE.exists():
            return False, f"compose 文件不存在: {OBSERV_COMPOSE}"
        try:
            r = subprocess.run(
                ["docker", "compose", "-f", str(OBSERV_COMPOSE), "up", "-d"],
                capture_output=True, text=True, timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            ok = r.returncode == 0
            return ok, (r.stdout + "\n" + r.stderr)[-500:]
        except FileNotFoundError:
            return False, "docker 不在 PATH; 先启 Docker Desktop"
        except subprocess.TimeoutExpired:
            return False, "docker compose 超时 (>120s)"

    def down(self) -> tuple[bool, str]:
        try:
            r = subprocess.run(
                ["docker", "compose", "-f", str(OBSERV_COMPOSE), "down"],
                capture_output=True, text=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return r.returncode == 0, (r.stdout + "\n" + r.stderr)[-500:]
        except Exception as e:
            return False, str(e)


GRAFANA = GrafanaStack()


# ============== 看门狗循环 ==============

POLL_EXEC = ThreadPoolExecutor(max_workers=10, thread_name_prefix="bee-poll")


def poll_all_services_concurrent() -> None:
    """并发 ping 全部服务 — 最长 ~HTTP_TIMEOUT_S 秒, 而不是 N×3 秒."""
    futures = [POLL_EXEC.submit(s.poll_status) for s in SERVICES]
    for f in futures:
        try:
            f.result(timeout=HTTP_TIMEOUT_S + 0.3)
        except Exception:
            pass


class Watchdog:
    def __init__(self) -> None:
        self.cfg = load_cfg()
        self.stop_flag = threading.Event()
        for s in SERVICES:
            if not s.is_core and s.key in self.cfg.get("extra_services_enabled", []):
                s.wanted = True

    def loop(self) -> None:
        for s in SERVICES:
            if s.wanted:
                s.start()
        # 首启后立即 poll 一次, 让菜单首次打开就有正确状态
        poll_all_services_concurrent()
        while not self.stop_flag.is_set():
            for s in SERVICES:
                if not s.wanted:
                    if s.is_process_alive():
                        s.stop()
                    continue
                # 用缓存判断, 不打 HTTP (缓存由 ticker 后台线程更新)
                if s._cached_http_alive:
                    continue
                if not self.cfg.get("auto_restart", True):
                    continue
                if not s.is_process_alive() and s.age_s() >= PROC_DEAD_GRACE_S:
                    s.restart()
                elif s.age_s() >= s.startup_grace_s:
                    s.restart()
            self.stop_flag.wait(POLL_INTERVAL_S)

    def shutdown(self) -> None:
        self.stop_flag.set()
        for s in SERVICES:
            s.stop()

    def persist_extra(self) -> None:
        self.cfg["extra_services_enabled"] = [s.key for s in SERVICES if not s.is_core and s.wanted]
        save_cfg(self.cfg)


WD = Watchdog()


# ============== 图标 ==============

def make_icon(state: str) -> Image.Image:
    """state ∈ {'ok', 'partial', 'down'} — 圆形蜂群 logo, 颜色随全局状态."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = {"ok": (76, 175, 80), "partial": (255, 193, 7), "down": (244, 67, 54)}[state]
    d.ellipse((4, 4, size - 4, size - 4), fill=color)
    d.rectangle((22, 24, 42, 28), fill=(33, 33, 33))
    d.rectangle((22, 36, 42, 40), fill=(33, 33, 33))
    return img


def current_state() -> str:
    wanted = [s for s in SERVICES if s.wanted]
    if not wanted:
        return "ok"
    alive = sum(1 for s in wanted if s.is_http_alive())
    if alive == len(wanted):
        return "ok"
    if alive == 0:
        return "down"
    return "partial"


# ============== pystray 菜单 ==============

ICON: Optional[pystray.Icon] = None
_last_icon_state: Optional[str] = None
_last_title: Optional[str] = None


def refresh_icon() -> None:
    """只在状态真变化时才碰 ICON.icon/title — 稳态下零开销, 不触发 Windows 重画."""
    global _last_icon_state, _last_title
    if ICON is None:
        return
    state = current_state()
    if state != _last_icon_state:
        ICON.icon = make_icon(state)
        _last_icon_state = state
    n_ok = sum(1 for s in SERVICES if s.wanted and s._cached_http_alive)
    n_w = sum(1 for s in SERVICES if s.wanted)
    new_title = f"🐝 蜂群看门狗 — {n_ok}/{n_w} 在跑"
    if new_title != _last_title:
        ICON.title = new_title
        _last_title = new_title


def on_open_url(url: str):
    return lambda icon=None, item=None: webbrowser.open(url)


def on_open_logs(icon=None, item=None) -> None:
    subprocess.Popen(["explorer", str(LOG_DIR)], creationflags=subprocess.CREATE_NO_WINDOW)


def on_service_start(svc: Service):
    def handler(icon=None, item=None) -> None:
        svc.wanted = True
        svc.start()
        WD.persist_extra()
        refresh_icon()
    return handler


def on_service_stop(svc: Service):
    def handler(icon=None, item=None) -> None:
        svc.wanted = False
        svc.stop()
        WD.persist_extra()
        refresh_icon()
    return handler


def on_service_restart(svc: Service):
    def handler(icon=None, item=None) -> None:
        svc.restart()
        refresh_icon()
    return handler


def on_open_service_log(svc: Service):
    def handler(icon=None, item=None) -> None:
        out = LOG_DIR / f"{svc.key}.out.log"
        if out.exists():
            os.startfile(str(out))   # type: ignore[attr-defined]
        else:
            os.startfile(str(LOG_DIR))   # type: ignore[attr-defined]
    return handler


def on_start_all_core(icon=None, item=None) -> None:
    for s in SERVICES:
        if s.is_core and not s.is_http_alive():
            s.wanted = True
            s.start()
    refresh_icon()


def on_start_all_services(icon=None, item=None) -> None:
    """启 全部 — 核心 + 七剑客 (不含 Grafana, Docker 那个要单独点)."""
    for s in SERVICES:
        if not s.is_http_alive():
            s.wanted = True
            s.start()
    WD.persist_extra()
    refresh_icon()


def on_stop_all(icon=None, item=None) -> None:
    for s in SERVICES:
        s.wanted = False
        s.stop()
    WD.persist_extra()
    refresh_icon()


def on_grafana_up(icon=None, item=None) -> None:
    ok, msg = GRAFANA.up()
    (LOG_DIR / "grafana.log").write_text(
        f"[{datetime.now().isoformat()}] up ok={ok}\n{msg}\n",
        encoding="utf-8",
    )
    refresh_icon()


def on_grafana_down(icon=None, item=None) -> None:
    ok, msg = GRAFANA.down()
    (LOG_DIR / "grafana.log").open("a", encoding="utf-8").write(
        f"[{datetime.now().isoformat()}] down ok={ok}\n{msg}\n"
    )
    refresh_icon()


def on_toggle_autostart(icon=None, item=None) -> None:
    if autostart_is_enabled():
        autostart_disable()
    else:
        autostart_enable()
    refresh_icon()


def on_toggle_auto_restart(icon=None, item=None) -> None:
    WD.cfg["auto_restart"] = not WD.cfg.get("auto_restart", True)
    save_cfg(WD.cfg)


def on_quit(icon=None, item=None) -> None:
    """点击退出 — pystray 回调线程没消息循环, MessageBox 必须丢新线程才能响应按钮."""
    def confirm_then_quit() -> None:
        try:
            import ctypes
            # MB_YESNO (4) | MB_ICONQUESTION (32) | MB_TOPMOST (0x40000) | MB_TASKMODAL (0x2000)
            FLAGS = 4 | 32 | 0x40000 | 0x2000
            rc = ctypes.windll.user32.MessageBoxW(
                0, "确定要关闭蜂群看门狗吗?\n(所有托管的服务会一起停)", "蜂群看门狗", FLAGS,
            )
            if rc != 6:  # IDYES=6
                return
        except Exception:
            pass
        WD.shutdown()
        if ICON:
            ICON.stop()
    threading.Thread(target=confirm_then_quit, daemon=True, name="quit-confirm").start()


def build_service_submenu(svc: Service) -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem("启动", on_service_start(svc),
                         enabled=lambda i, s=svc: not s.is_http_alive()),
        pystray.MenuItem("停止", on_service_stop(svc),
                         enabled=lambda i, s=svc: s.wanted or s.is_process_alive()),
        pystray.MenuItem("重启", on_service_restart(svc)),
        pystray.MenuItem(f"打开 (http://127.0.0.1:{svc.port})",
                         on_open_url(f"http://127.0.0.1:{svc.port}")),
        pystray.MenuItem("看日志", on_open_service_log(svc)),
    )


def service_label_dynamic(svc: Service):
    return lambda item, s=svc: f"{s.status_emoji()} {s.label}"


def build_menu() -> pystray.Menu:
    core_items = [
        pystray.MenuItem(service_label_dynamic(s), build_service_submenu(s))
        for s in SERVICES if s.is_core
    ]
    extra_items = [
        pystray.MenuItem(service_label_dynamic(s), build_service_submenu(s))
        for s in SERVICES if not s.is_core
    ]

    grafana_submenu = pystray.Menu(
        pystray.MenuItem("启动 (docker compose up)", on_grafana_up),
        pystray.MenuItem("停止 (docker compose down)", on_grafana_down),
        pystray.MenuItem("打开 Grafana (3001)", on_open_url("http://localhost:3001")),
    )

    def header(item):
        n_ok = sum(1 for s in SERVICES if s.wanted and s.is_http_alive())
        n_w = sum(1 for s in SERVICES if s.wanted)
        state = current_state().upper()
        return f"🐝 {state}  {n_ok}/{n_w} 在跑"

    return pystray.Menu(
        pystray.MenuItem(header, None, enabled=False),
        pystray.Menu.SEPARATOR,
        *core_items,
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("七剑客 (按需启)", pystray.Menu(*extra_items)),
        pystray.MenuItem("Grafana 全栈 (Docker)", grafana_submenu),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("一键启动核心", on_start_all_core),
        pystray.MenuItem("一键启动全部 (含七剑客)", on_start_all_services),
        pystray.MenuItem("一键全部停", on_stop_all),
        pystray.MenuItem("打开日志文件夹", on_open_logs),
        pystray.MenuItem("打开蜂群主页 (4000)", on_open_url("http://localhost:4000")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("自动重启", on_toggle_auto_restart,
                         checked=lambda item: WD.cfg.get("auto_restart", True)),
        pystray.MenuItem("开机自启", on_toggle_autostart,
                         checked=lambda item: autostart_is_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出 (需确认)", on_quit),
    )


# ============== 后台周期刷新 ==============

_last_menu_signature: Optional[tuple] = None


def ticker() -> None:
    """后台 2s 轮询 — 并发 ping 全部服务, 刷缓存. 只在状态变化时 update_menu,
    所以稳态下 Windows 不会显示忙碌光标。"""
    global _last_menu_signature
    while not WD.stop_flag.is_set():
        try:
            poll_all_services_concurrent()
            # 计算状态指纹: 改了才刷
            sig = tuple((s.key, s._cached_http_alive, s.wanted) for s in SERVICES)
            if sig != _last_menu_signature:
                _last_menu_signature = sig
                refresh_icon()
                if ICON is not None:
                    try:
                        ICON.update_menu()
                    except Exception:
                        pass
        except Exception:
            pass
        WD.stop_flag.wait(STATUS_REFRESH_S)


# ============== main ==============

def main() -> int:
    global ICON
    threading.Thread(target=WD.loop, daemon=True, name="watchdog-loop").start()
    threading.Thread(target=ticker, daemon=True, name="tray-ticker").start()
    ICON = pystray.Icon(
        "bee-swarm-watchdog",
        icon=make_icon("partial"),
        title="🐝 蜂群看门狗 (启动中)",
        menu=build_menu(),
    )
    ICON.run()
    WD.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
