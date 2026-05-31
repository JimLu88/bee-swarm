"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Notif = {
  id: string;
  ts: number;
  channel: string;
  kind: string;
  body: string;
  delivered: number;
};

type Props = { backendUrl: string };

const btnBell: CSSProperties = {
  position: "relative",
  padding: "6px 10px", borderRadius: 6,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  color: "inherit", cursor: "pointer", fontSize: 14,
};

const badge: CSSProperties = {
  position: "absolute", top: -4, right: -4,
  minWidth: 16, height: 16, padding: "0 4px",
  borderRadius: 8, background: "#f44336",
  color: "white", fontSize: 10, fontWeight: 600,
  display: "flex", alignItems: "center", justifyContent: "center",
};

const popover: CSSProperties = {
  position: "absolute", top: 32, right: 0, zIndex: 50,
  width: 340, maxHeight: 400, overflow: "auto",
  padding: 10, borderRadius: 8,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  background: "#1a1a1a",
  display: "flex", flexDirection: "column", gap: 8,
};

const notifItem: CSSProperties = {
  padding: "8px 10px", borderRadius: 6,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--bg-hover)",
  background: "var(--bg-subtle)",
};

const kindEmoji: Record<string, string> = {
  idle_24h: "⏰",
  budget_alert: "💸",
  review_due: "📝",
  default: "🔔",
};

export function NotificationBell({ backendUrl }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notif[]>([]);

  const reload = useCallback(async () => {
    try {
      const res = await fetchWithTimeout(`${backendUrl}/api/proactive/pending?limit=20`,
        undefined, TIMEOUT_MS.default);
      if (res.ok) setItems((await res.json()).items || []);
    } catch {
      setItems([]);
    }
  }, [backendUrl]);

  useEffect(() => {
    reload();
    const t = setInterval(reload, 60_000);
    return () => clearInterval(t);
  }, [reload]);

  const dismiss = useCallback(async (nid: string) => {
    try {
      await fetchWithTimeout(`${backendUrl}/api/proactive/${nid}/delivered`,
        { method: "POST" }, TIMEOUT_MS.default);
      await reload();
    } catch { /* swallow */ }
  }, [backendUrl, reload]);

  const runChecks = useCallback(async () => {
    try {
      await fetchWithTimeout(`${backendUrl}/api/proactive/run-checks`,
        { method: "POST" }, TIMEOUT_MS.default);
      await reload();
    } catch { /* swallow */ }
  }, [backendUrl, reload]);

  return (
    <div style={{ position: "relative" }}>
      <button type="button" onClick={() => setOpen((v) => !v)} style={btnBell} title="v3-K 主动通知">
        🔔
        {items.length > 0 && <span style={badge}>{items.length}</span>}
      </button>
      {open && (
        <div style={popover} onClick={(e) => e.stopPropagation()}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>🔔 通知中心 (v3-K)</div>
            <button type="button" onClick={runChecks}
                    style={{
                      padding: "2px 8px", fontSize: 10, borderRadius: 4,
                      borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
                      background: "var(--bg-subtle)", color: "inherit", cursor: "pointer",
                    }}>跑检查</button>
          </div>
          {items.length === 0 && (
            <div style={{ fontSize: 12, opacity: 0.55 }}>暂无新通知。</div>
          )}
          {items.map((n) => (
            <div key={n.id} style={notifItem}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 6 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>
                    {kindEmoji[n.kind] || kindEmoji.default} {n.kind}
                  </div>
                  <div style={{ fontSize: 11, opacity: 0.55 }}>
                    {new Date(n.ts * 1000).toLocaleString()} · {n.channel}
                  </div>
                </div>
                <button type="button" onClick={() => dismiss(n.id)}
                        style={{
                          padding: "1px 6px", fontSize: 10, borderRadius: 4,
                          borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
                          background: "transparent", color: "inherit", cursor: "pointer",
                        }}>✓</button>
              </div>
              <div style={{ fontSize: 12, marginTop: 4 }}>{n.body}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
