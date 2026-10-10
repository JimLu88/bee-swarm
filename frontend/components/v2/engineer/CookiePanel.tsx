"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../../lib/http";
import { resolveBackendHttpBase } from "../../../lib/backend";

/** 与 PC 媒体爬虫 _cookie_meta 对应 */
type CookieMeta = {
  platform: string; label: string; has_cookie: boolean; length: number; updated: string;
};

const card: CSSProperties = {
  padding: 14, borderRadius: 10, borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  background: "var(--bg-subtle)", display: "flex", flexDirection: "column", gap: 10,
};
const rowBox: CSSProperties = {
  padding: "9px 11px", borderRadius: 8, borderWidth: 1, borderStyle: "solid",
  borderColor: "var(--bg-hover)", background: "var(--bg-subtle)",
  display: "flex", flexDirection: "column", gap: 8,
};
const label: CSSProperties = { fontSize: 13, fontWeight: 600 };
const hint: CSSProperties = { fontSize: 10, opacity: 0.55 };
const input: CSSProperties = {
  fontSize: 12, padding: "6px 8px", borderRadius: 4, borderWidth: 1, borderStyle: "solid",
  borderColor: "var(--border)", background: "var(--bg)", color: "inherit",
  width: "100%", boxSizing: "border-box", resize: "vertical", fontFamily: "monospace",
};
const btn = (v: "default" | "primary"): CSSProperties => ({
  padding: "4px 12px", fontSize: 11, borderRadius: 4, borderWidth: 1, borderStyle: "solid",
  borderColor: v === "primary" ? "var(--accent)" : "var(--border)",
  background: v === "primary" ? "var(--accent-bg)" : "var(--bg-subtle)",
  color: "inherit", cursor: "pointer",
});

export function CookiePanel({ backendUrl }: { backendUrl?: string }) {
  const base = backendUrl || resolveBackendHttpBase();
  const [online, setOnline] = useState<boolean | null>(null);
  const [items, setItems] = useState<CookieMeta[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetchWithTimeout(`${base}/api/cookies/list`, undefined, TIMEOUT_MS.default);
      const j = await r.json();
      setOnline(!!j.online);
      if (j.online) setItems(j.platforms || []);
    } catch (e) { setErr((e as Error).message); }
  }, [base]);

  useEffect(() => { load(); }, [load]);

  const openEdit = useCallback(async (platform: string) => {
    if (editing === platform) { setEditing(null); return; }
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await fetchWithTimeout(`${base}/api/cookies/get/${platform}`, undefined, TIMEOUT_MS.default);
      const j = await r.json();
      if (!j.online) { setErr(j.error || "PC 媒体爬虫未连接"); return; }
      setDraft(j.cookie || "");
      setEditing(platform);
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }, [base, editing]);

  const save = useCallback(async (platform: string) => {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await fetchWithTimeout(`${base}/api/cookies/set`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ platform, cookie: draft }) },
        TIMEOUT_MS.default);
      const j = await r.json();
      if (!j.online) { setErr(j.error || "PC 媒体爬虫未连接"); return; }
      setMsg(`已保存 ${platform}`);
      setTimeout(() => setMsg(null), 1800);
      setEditing(null);
      load();
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }, [base, draft, load]);

  return (
    <div style={card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>🍪 爬虫 Cookie 管理</div>
        <div style={{ fontSize: 11, opacity: 0.75 }}>
          {online === null ? "…" : online ? "✅ 媒体爬虫在线" : "⚪ PC 媒体爬虫未连接"}
        </div>
      </div>

      <div style={hint}>
        改完即生效, 下次抓取用新 cookie。数据源是 PC 的 <code>cookies\\*.txt</code> 单一文件,
        和 PC 自带页 (<code>http://192.168.31.91:8009/</code>) 改的是同一份。
      </div>

      {online === false && (
        <div style={{ fontSize: 11, lineHeight: 1.6, padding: 8, borderRadius: 6, background: "var(--info-bg)" }}>
          PC 媒体爬虫 (8009) 未连接。可在 🚀 服务 tab 一键启动"媒体爬虫", 或确认 NAS 的
          <code> BEE_MEDIA_URL=http://192.168.31.91:8009</code>。连上后此处即可编辑。
        </div>
      )}

      {items.map((it) => (
        <div key={it.platform} style={rowBox}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
            <div>
              <div style={label}>{it.label} <span style={hint}>{it.platform}</span></div>
              <div style={hint}>
                {it.has_cookie
                  ? <span style={{ color: "#4caf50" }}>✅ 已设置 · {it.length} 字 · {it.updated}</span>
                  : <span style={{ color: "#9e9e9e" }}>⚪ 未设置</span>}
              </div>
            </div>
            <button type="button" disabled={busy} onClick={() => openEdit(it.platform)} style={btn("default")}>
              {editing === it.platform ? "收起" : "编辑"}
            </button>
          </div>
          {editing === it.platform && (
            <>
              <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={5}
                        placeholder={`粘贴 ${it.label} 的 cookie 串 (浏览器 F12 → Network → 复制 Cookie 请求头)`}
                        style={input} />
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <button type="button" disabled={busy} onClick={() => save(it.platform)} style={btn("primary")}>保存</button>
                <button type="button" disabled={busy} onClick={() => setEditing(null)} style={btn("default")}>取消</button>
                {msg && <span style={{ fontSize: 12, color: "#4caf50" }}>{msg}</span>}
              </div>
            </>
          )}
        </div>
      ))}

      {err && <span style={{ fontSize: 12, color: "#f44336" }}>⚠ {err}</span>}
      <div style={{ ...hint, marginTop: 2 }}>
        💡 抖音 cookie 几天就失效、价值低, 一般不填。主力小红书/知乎。其它项目要用本爬虫也改这里。
      </div>
    </div>
  );
}
