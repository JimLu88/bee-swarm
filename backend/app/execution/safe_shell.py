from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from shutil import which as shutil_which

from ..settings import settings


def resolve_executable(cmd: str) -> str | None:
    hit = shutil_which(cmd)
    if hit:
        return hit
    stemmed = Path(cmd).stem
    if stemmed.lower() != cmd.lower():
        return shutil_which(stemmed)
    return None

# Unsafe even if mistakenly allow-listed (basename / stem, lowercase, no .exe)
_DENY_EXECUTABLE_STEMS = frozenset(
    {
        "cmd",
        "powershell",
        "pwsh",
        "bash",
        "sh",
        "fish",
        "zsh",
        "wsl",
        "curl",
        "wget",
        "bitsadmin",
        "certutil",
        "regsvr32",
        "msiexec",
        "rundll32",
        "cscript",
        "wscript",
        "explorer",
        "cmdkey",
        "schtasks",
        "at",
        "npx",  # can pull arbitrary code
        "ssh",
        "scp",
        "ftp",
        "telnet",
        # Package / runtime installers — trivial arbitrary code execution paths
        "npm",
        "yarn",
        "pnpm",
        "bun",
        "pip",
        "pip3",
        "pipx",
        "conda",
        "micromamba",
        "gem",
        "composer",
        "dotnet",
    }
)


def _backend_root() -> Path:
    """Directory that contains backend/app/… (usually …/backend)."""
    return Path(__file__).resolve().parents[2]


def _stem(name: str) -> str:
    s = Path(name).name
    lower = s.lower()
    return lower[:-4] if lower.endswith(".exe") else lower


def _parse_allowlist(raw: str) -> frozenset[str]:
    out: set[str] = set()
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        stem = _stem(p)
        if stem and stem not in _DENY_EXECUTABLE_STEMS:
            out.add(stem)
    return frozenset(out)


def sandbox_allowlist() -> frozenset[str]:
    return _parse_allowlist(settings.hsemas_exec_allowlist or "")


def effective_exec_cwd() -> tuple[Path, str | None]:
    """Returns (cwd, error_or_none). Cwd is always anchored under backend root."""
    root = _backend_root()
    hint: str | None = None
    raw = settings.hsemas_exec_cwd
    if raw is None or not raw.strip():
        target = root
    else:
        p = Path(raw.strip())
        target = (p if p.is_absolute() else root / p).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            hint = "exec_cwd_outside_backend_root_fallback"
            target = root
    if not target.is_dir():
        hint = (hint + ";") if hint else ""
        hint = (hint or "") + "exec_cwd_not_a_dir_fallback"
        target = root
    return target, hint


def validate_argv(argv: list[str]) -> tuple[bool, str, str]:
    """(ok, error_code, detail). Executable stem on success."""
    if not argv or not argv[0].strip():
        return False, "empty_argv", ""
    exe = argv[0]
    stem = _stem(exe)

    allow = sandbox_allowlist()
    if stem in _DENY_EXECUTABLE_STEMS:
        return False, "denylisted_binary", stem
    if not allow:
        return False, "allowlist_empty", stem
    if stem not in allow:
        return False, "not_on_allowlist", stem

    if len(argv) > settings.hsemas_exec_max_args:
        return False, "too_many_args", str(len(argv))
    maxlen = settings.hsemas_exec_max_arg_len
    for i, arg in enumerate(argv):
        if not isinstance(arg, str):
            return False, "invalid_arg_type", str(i)
        if "\x00" in arg:
            return False, "embedded_null_byte", str(i)
        if len(arg) > maxlen:
            return False, "arg_too_long", str(i)

    # Restrict dangerous python invocation modes (prefer allow-listed `pytest`, `ruff`, … directly)
    if stem in {"python", "python3"}:
        if "-c" in argv:
            return False, "python_c_forbidden", stem
        if "-m" in argv:
            return False, "python_m_forbidden", stem
        if "--" in argv[:3]:
            return False, "python_interactive_forbidden", stem
    return True, "", stem


async def run_allowlisted(argv: list[str]) -> dict[str, object]:
    """Run argv with asyncio subprocess; cwd under backend/."""
    if not settings.hsemas_sandbox_exec_enabled:
        return {"ok": False, "error": "sandbox_disabled", "detail": "", "returncode": None, "stdout": "", "stderr": ""}

    ok, code, stem = validate_argv(argv)
    if not ok:
        return {"ok": False, "error": code, "detail": stem, "returncode": None, "stdout": "", "stderr": ""}

    cwd, cwd_hint = effective_exec_cwd()
    exe_path = resolve_executable(argv[0])
    if exe_path is None:
        return {
            "ok": False,
            "error": "executable_not_found",
            "detail": argv[0],
            "cwd": str(cwd),
            "returncode": None,
            "stdout": "",
            "stderr": "",
        }

    timeout = float(max(1, min(settings.hsemas_exec_timeout_sec, 600)))
    exe_list = argv.copy()
    exe_list[0] = exe_path
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = await asyncio.create_subprocess_exec(
        *exe_list,
        cwd=str(cwd),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
        creationflags=creationflags,
    )

    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {
            "ok": False,
            "error": "timeout",
            "detail": str(int(timeout)),
            "cwd": str(cwd),
            "returncode": None,
            "stdout": "",
            "stderr": "",
        }

    max_out = settings.hsemas_exec_max_output_chars

    def _dec(b: bytes) -> str:
        return b.decode(errors="replace")[:max_out]

    return {
        "ok": True,
        "executable_stem": stem,
        "cwd": str(cwd),
        "cwd_resolution_note": cwd_hint,
        "returncode": proc.returncode,
        "stdout": _dec(out_b or b""),
        "stderr": _dec(err_b or b""),
    }
