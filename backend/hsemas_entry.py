from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import uvicorn


def _open_browser_url(host: str, port: int) -> str:
    """Use a loopback URL in the browser even when the server binds on 0.0.0.0 / ::."""
    h = (host or "").strip()
    if h in ("0.0.0.0", "", "::", "[::]"):
        return f"http://127.0.0.1:{port}/"
    if h == "[::1]":
        return f"http://[::1]:{port}/"
    return f"http://{h}:{port}/"


def _app_base_url(host: str, port: int) -> str:
    """Origin for health checks (no trailing slash)."""
    return _open_browser_url(host, port).rstrip("/")


def _wait_for_server(base: str, timeout_s: float = 45.0) -> bool:
    """Poll until /api/health responds so the browser open is not a race."""
    url = f"{base}/api/health"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.25)
    return False


def _launch_browser(url: str) -> bool:
    """
    Open default browser. PyInstaller onefile exes often fail with ``webbrowser.open`` on
    Windows; prefer ShellExecute / ``start``.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            rc = int(ctypes.windll.shell32.ShellExecuteW(None, "open", url, None, None, 1))
            if rc > 32:
                return True
        except Exception:
            pass
        try:
            # Empty quoted title is required when the target is a URL.
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                ["cmd", "/c", "start", "", url],
                shell=False,
                close_fds=True,
                creationflags=creationflags,
            )
            return True
        except Exception:
            pass
    try:
        import webbrowser

        return bool(webbrowser.open(url))
    except Exception:
        return False


def _maybe_open_browser_later(host: str, port: int) -> None:
    flag = (os.getenv("HSEMAS_OPEN_BROWSER") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return

    page_url = _open_browser_url(host, port)
    base = _app_base_url(host, port)

    def _run() -> None:
        ok = _wait_for_server(base)
        if not ok:
            print(
                f"[h-semas] server did not become ready in time; open manually: {page_url}",
                flush=True,
            )
            return
        if not _launch_browser(page_url):
            print(
                f"[h-semas] could not open the default browser; open manually: {page_url}",
                flush=True,
            )

    threading.Thread(target=_run, name="hsemas-open-browser", daemon=True).start()


def main() -> None:
    # Import inside main so PyInstaller hooks pick it up.
    from app.main import app

    host = os.getenv("HSEMAS_HOST", "127.0.0.1")
    port = int(os.getenv("HSEMAS_PORT", "8000"))
    _maybe_open_browser_later(host, port)
    uvicorn.run(app, host=host, port=port, log_level=os.getenv("HSEMAS_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
