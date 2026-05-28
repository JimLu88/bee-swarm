"""v3-K 主动交互 — 从被动响应升级为主动问 / 提醒.

触发示例:
- 24h 无活动 → "今天还需要做点什么?"
- 账本快触顶 → 主动告警
- v3-F 复习项到期 → 主动召唤
- 演化协调器周报 → 主动推送

通道: 系统托盘 / 邮件 / Telegram bot / PWA push
"""
from __future__ import annotations

import sqlite3, time, uuid, os, json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DB_PATH = DATA_DIR / "proactive_log.sqlite"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAIN_DB = DATA_DIR / "decision_memory.sqlite"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY, ts INTEGER NOT NULL,
            channel TEXT NOT NULL, kind TEXT NOT NULL,
            body TEXT, delivered INTEGER DEFAULT 0
        )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_notif_ts ON notifications(ts)")
    c.row_factory = sqlite3.Row
    return c


def _last_user_activity_ts() -> int:
    if not MAIN_DB.exists():
        return 0
    try:
        mc = sqlite3.connect(str(MAIN_DB))
        row = mc.execute("SELECT MAX(ts) FROM decisions").fetchone()
        mc.close()
        return int(row[0]) if row and row[0] else 0
    except sqlite3.OperationalError:
        return 0


def _enqueue(channel: str, kind: str, body: str) -> str:
    nid = "n-" + uuid.uuid4().hex[:10]
    now = int(time.time())
    with _conn() as c:
        c.execute("INSERT INTO notifications (id,ts,channel,kind,body) VALUES (?,?,?,?,?)",
                  (nid, now, channel, kind, body))
    return nid


def check_idle_24h(channels: list[str] | None = None) -> list[str]:
    last = _last_user_activity_ts()
    if last == 0 or time.time() - last < 86400:
        return []
    chs = channels or ["tray"]
    body = "已经 24h 没动了,今天有想做的事情吗?可以问我天气、看账本余额、或起一个轻办公任务。"
    return [_enqueue(ch, "idle_24h", body) for ch in chs]


def check_budget_alert(threshold: float = 0.8, channels: list[str] | None = None) -> list[str]:
    chs = channels or ["tray"]
    try:
        import urllib.request, urllib.error
        token = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")
        req = urllib.request.Request("http://127.0.0.1:8001/ledger/status",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read())
        used = data.get("month_used_yuan", 0)
        cap = data.get("month_cap_yuan", 800)
        if cap == 0:
            return []
        ratio = used / cap
        if ratio < threshold:
            return []
        body = f"本月已花 ¥{used:.2f} / ¥{cap} ({ratio*100:.0f}%)。"
        if ratio >= 1.0:
            body += " 已触顶,蜂群已自动降级到便宜模型。"
        elif ratio >= threshold:
            body += " 接近上限,考虑暂时关掉重型任务。"
        return [_enqueue(ch, "budget_alert", body) for ch in chs]
    except Exception:
        return []


def check_review_due(channels: list[str] | None = None) -> list[str]:
    chs = channels or ["tray"]
    try:
        import urllib.request
        token = os.environ.get("BEE_BEARER_TOKEN", "dev-token-change-me")
        req = urllib.request.Request("http://127.0.0.1:8004/memory/review/stats",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read())
        due = data.get("due_now", 0)
        if due == 0:
            return []
        body = f"v3-F 复习闸:有 {due} 项到期了,要现在复习吗?"
        return [_enqueue(ch, "review_due", body) for ch in chs]
    except Exception:
        return []


def run_all_checks() -> dict:
    return {
        "idle_24h": check_idle_24h(),
        "budget_alert": check_budget_alert(),
        "review_due": check_review_due(),
    }


def pending(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM notifications WHERE delivered=0 ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_delivered(nid: str) -> bool:
    with _conn() as c:
        n = c.execute("UPDATE notifications SET delivered=1 WHERE id=?", (nid,)).rowcount
    return n > 0
