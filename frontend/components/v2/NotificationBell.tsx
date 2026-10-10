"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";
import { Icon } from "./Icon";

type Notif = {
  id: string;
  ts: number;
  channel: string;
  kind: string;
  body: string;
  delivered: number;
};

type Props = { backendUrl: string };

// 计数小角标 (挂在 .ghost-btn 上, 与顶栏其它图标统一)
const countBadge: CSSProperties = {
  position: "absolute", top: 4, right: 4,
  minWidth: 15, height: 15, padding: "0 4px",
  borderRadius: 99, background: "var(--danger)",
  color: "#fff", fontSize: 9.5, fontWeight: 700, lineHeight: "15px",
  textAlign: "center", boxShadow: "0 0 0 2px var(--bg-app)",
};

const popover: CSSProperties = {
  position: "absolute", top: 40, right: 0, zIndex: 60,
  width: 340, maxHeight: 420, overflow: "auto",
  padding: 8, borderRadius: 16,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-1)",
  background: "var(--bg-surface)", color: "var(--fg-1)",
  boxShadow: "var(--shadow-lg)",
  display: "flex", flexDirection: "column", gap: 6,
};

const notifItem: CSSProperties = {
  padding: "10px 12px", borderRadius: 12,
  background: "var(--bg-surface-2)",
};

// 通知类型 → Material Symbols (替代 emoji, 与全站统一)
const kindIcon: Record<string, string> = {
  idle_24h: "schedule",
  budget_alert: "savings",
  review_due: "rate_review",
  default: "notifications",
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
      <button type="button" className="ghost-btn" onClick={() => setOpen((v) => !v)}
              title="通知中心" aria-label="通知">
        <Icon name="notifications" fill={items.length > 0} />
        {items.length > 0 && <span style={countBadge}>{items.length > 99 ? "99+" : items.length}</span>}
      </button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 55 }} />
          <div style={popover} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 6px" }}>
              <div style={{ fontWeight: 600, fontSize: 14, display: "flex", alignItems: "center", gap: 6 }}>
                <Icon name="notifications" size={18} /> 通知中心
              </div>
              <button type="button" onClick={runChecks}
                      style={{
                        padding: "4px 10px", fontSize: 11.5, borderRadius: 99,
                        borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-1)",
                        background: "var(--bg-surface-2)", color: "var(--fg-2)", cursor: "pointer",
                        display: "inline-flex", alignItems: "center", gap: 4,
                      }}>
                <Icon name="refresh" size={15} /> 跑检查
              </button>
            </div>
            {items.length === 0 && (
              <div style={{ fontSize: 13, color: "var(--fg-3)", padding: "16px 8px", textAlign: "center" }}>
                暂无新通知
              </div>
            )}
            {items.map((n) => (
              <div key={n.id} style={notifItem}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: 8 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
                      <Icon name={kindIcon[n.kind] || kindIcon.default} size={17} style={{ color: "var(--accent)" }} />
                      {n.kind}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 2 }}>
                      {new Date(n.ts * 1000).toLocaleString()} · {n.channel}
                    </div>
                  </div>
                  <button type="button" onClick={() => dismiss(n.id)} title="标记已读"
                          style={{
                            display: "inline-flex", border: "none", background: "transparent",
                            color: "var(--fg-4)", cursor: "pointer", padding: 2, borderRadius: 8,
                          }}>
                    <Icon name="check" size={18} />
                  </button>
                </div>
                <div style={{ fontSize: 12.5, color: "var(--fg-2)", marginTop: 5 }}>{n.body}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
