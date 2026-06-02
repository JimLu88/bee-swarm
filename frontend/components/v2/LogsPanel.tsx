"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type LogItem = {
  ts: number;
  level: string;
  logger: string;
  msg: string;
  service?: string;
  exc?: string;
};

type ServiceBlock = {
  name: string;
  url: string;
  reachable: boolean;
  items: LogItem[];
  stats: { ERROR?: number; WARNING?: number; INFO?: number; size?: number };
  error?: string;
};

type AggregateResp = {
  services: Record<string, ServiceBlock>;
  summary: { total_errors: number; total_warnings: number; service_count: number };
};

type Props = { backendUrl: string };

const btnHeader = (errCount: number, warnCount: number): CSSProperties => ({
  position: "relative",
  padding: "6px 12px",
  borderRadius: 6,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: errCount > 0 ? "#f44336" : warnCount > 0 ? "var(--accent)" : "var(--border)",
  background: errCount > 0
    ? "rgba(244,67,54,0.12)"
    : warnCount > 0
      ? "var(--accent-bg)"
      : "var(--bg-subtle)",
  color: "inherit",
  cursor: "pointer",
  fontSize: 13,
  fontWeight: errCount > 0 ? 600 : 400,
});

const badge: CSSProperties = {
  position: "absolute", top: -6, right: -6,
  minWidth: 18, height: 18, padding: "0 5px",
  borderRadius: 9, background: "#f44336", color: "white",
  fontSize: 10, fontWeight: 700,
  display: "flex", alignItems: "center", justifyContent: "center",
};

const modalBackdrop: CSSProperties = {
  position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
  background: "var(--overlay)", zIndex: 200,
  display: "flex", alignItems: "flex-start", justifyContent: "center",
  paddingTop: 40,
};

const modalBox: CSSProperties = {
  width: "92vw", maxWidth: 1100, maxHeight: "85vh",
  background: "var(--bg)", color: "var(--text)",
  borderRadius: 12,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-strong)",
  display: "flex", flexDirection: "column", overflow: "hidden",
  boxShadow: "var(--shadow-lg)",
};

const tabRow: CSSProperties = {
  display: "flex", gap: 6, padding: 12, flexWrap: "wrap",
  borderBottomWidth: 1, borderBottomStyle: "solid",
  borderBottomColor: "var(--border-strong)",
  background: "var(--bg-elev)",
};

const tab = (active: boolean, reachable: boolean): CSSProperties => ({
  padding: "5px 10px", borderRadius: 6, fontSize: 12, cursor: "pointer",
  borderWidth: 1, borderStyle: "solid",
  borderColor: active ? "var(--accent)" : "var(--border-strong)",
  background: active ? "var(--accent-bg)" : "var(--bg-hover)",
  color: !reachable ? "#ff6b6b" : (active ? "var(--accent)" : "#f0f0f0"),
  fontWeight: active ? 600 : 500,
  display: "flex", alignItems: "center", gap: 6,
});

const dotErr: CSSProperties = {
  display: "inline-block", width: 7, height: 7, borderRadius: "50%",
  background: "#f44336",
};

const dotWarn: CSSProperties = {
  display: "inline-block", width: 7, height: 7, borderRadius: "50%",
  background: "var(--accent)",
};

const lvlPill = (lvl: string): CSSProperties => ({
  padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 700,
  letterSpacing: 0.3,
  background: lvl === "ERROR" ? "#ff5252"
    : lvl === "WARNING" ? "#ffb300"
    : "#66bb6a",
  color: lvl === "WARNING" ? "#1a1a1a" : "#ffffff",
});

const rowItem: CSSProperties = {
  padding: "8px 12px", fontSize: 12, fontFamily: "ui-monospace, Consolas, monospace",
  borderBottomWidth: 1, borderBottomStyle: "solid",
  borderBottomColor: "var(--border)",
  display: "grid", gridTemplateColumns: "110px 78px 1fr",
  gap: 10, alignItems: "start",
  color: "var(--text)",
};

function fmtTime(ts: number): string {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleTimeString("zh-CN", { hour12: false }) + "." +
    String(d.getMilliseconds()).padStart(3, "0");
}

export function LogsPanel({ backendUrl }: Props) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<AggregateResp | null>(null);
  const [activeTab, setActiveTab] = useState<string>("");
  const [levelFilter, setLevelFilter] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const q = new URLSearchParams({ per_service_limit: "150" });
      if (levelFilter) q.set("level", levelFilter);
      const res = await fetchWithTimeout(
        `${backendUrl}/api/logs/aggregate?${q.toString()}`,
        undefined,
        TIMEOUT_MS.default,
      );
      if (!res.ok) {
        setError(`HTTP ${res.status}`);
        setLoading(false);
        return;
      }
      const j = (await res.json()) as AggregateResp;
      setData(j);
      if (!activeTab && j.services) {
        const first = Object.keys(j.services)[0] || "";
        setActiveTab(first);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [backendUrl, levelFilter, activeTab]);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, [load]);

  const errCount = data?.summary.total_errors ?? 0;
  const warnCount = data?.summary.total_warnings ?? 0;

  const services = useMemo(
    () => (data?.services ? Object.values(data.services) : []),
    [data],
  );
  const current = data?.services?.[activeTab];

  return (
    <>
      <button
        type="button"
        style={btnHeader(errCount, warnCount)}
        onClick={() => setOpen(true)}
        title="点击查看所有程序日志 (蜂群 + 7 剑客)"
      >
        📋 日志
        {errCount > 0 && <span style={badge}>{errCount}</span>}
        {errCount === 0 && warnCount > 0 && (
          <span style={{ ...badge, background: "var(--accent)", color: "#111" }}>{warnCount}</span>
        )}
      </button>

      {open && (
        <div style={modalBackdrop} onClick={() => setOpen(false)}>
          <div style={modalBox} onClick={(e) => e.stopPropagation()}>
            <div
              style={{
                padding: 14, borderBottomWidth: 1, borderBottomStyle: "solid",
                borderBottomColor: "var(--border-strong)",
                background: "var(--bg-card)", color: "var(--text)",
                display: "flex", justifyContent: "space-between",
                alignItems: "center", gap: 10,
              }}
            >
              <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>
                📋 全程序日志中心 · {data?.summary.service_count ?? "-"} 个服务
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <select
                  value={levelFilter}
                  onChange={(e) => setLevelFilter(e.target.value)}
                  style={{
                    padding: "4px 8px", fontSize: 12, background: "var(--bg)",
                    color: "var(--text)", borderWidth: 1, borderStyle: "solid",
                    borderColor: "rgba(255,255,255,0.30)", borderRadius: 4,
                  }}
                >
                  <option value="">全部 level</option>
                  <option value="ERROR">仅 ERROR</option>
                  <option value="WARNING">仅 WARNING</option>
                  <option value="INFO">仅 INFO</option>
                </select>
                <button
                  type="button" onClick={load}
                  style={{
                    padding: "4px 12px", fontSize: 12, borderRadius: 4,
                    borderWidth: 1, borderStyle: "solid",
                    borderColor: "rgba(255,255,255,0.30)",
                    background: "var(--bg-card)", color: "var(--text)",
                    cursor: "pointer", fontWeight: 500,
                  }}
                >
                  {loading ? "..." : "↻ 刷新"}
                </button>
                <button
                  type="button" onClick={() => setOpen(false)}
                  style={{
                    padding: "4px 12px", fontSize: 12, borderRadius: 4,
                    borderWidth: 1, borderStyle: "solid",
                    borderColor: "rgba(255,255,255,0.30)",
                    background: "var(--bg-card)", color: "var(--text)",
                    cursor: "pointer", fontWeight: 500,
                  }}
                >
                  ✕ 关闭
                </button>
              </div>
            </div>

            {error && (
              <div style={{ padding: 10, color: "#f44336", fontSize: 12 }}>
                ⚠ {error}
              </div>
            )}

            <div style={tabRow}>
              {services.map((s) => {
                const e = s.stats?.ERROR ?? 0;
                const w = s.stats?.WARNING ?? 0;
                return (
                  <div
                    key={s.name}
                    style={tab(s.name === activeTab, s.reachable)}
                    onClick={() => setActiveTab(s.name)}
                  >
                    {!s.reachable && "🔴"}{s.name}
                    {e > 0 && <span style={dotErr} title={`${e} 错误`} />}
                    {w > 0 && e === 0 && <span style={dotWarn} title={`${w} 警告`} />}
                    {e > 0 && <span style={{ fontSize: 10, color: "#f44336" }}>{e}</span>}
                  </div>
                );
              })}
            </div>

            <div style={{ overflow: "auto", flex: 1, padding: "4px 0" }}>
              {!current && (
                <div style={{ padding: 24, color: "var(--text-dim)", fontSize: 13 }}>
                  选个服务看日志
                </div>
              )}
              {current && current.error && (
                <div style={{ padding: 12, color: "#ff8a80", fontSize: 13, fontWeight: 500 }}>
                  ⚠ 该服务不可达: {current.error}
                </div>
              )}
              {current && current.items.length === 0 && !current.error && (
                <div style={{ padding: 24, color: "var(--text-dim)", fontSize: 13 }}>
                  暂无日志条目 (服务可能刚启动或日志文件还没产生).
                </div>
              )}
              {current && current.items.slice().reverse().map((it, i) => (
                <div key={`${current.name}-${it.ts}-${i}`} style={rowItem}>
                  <div style={{ color: "var(--info)" }}>{fmtTime(it.ts)}</div>
                  <div><span style={lvlPill(it.level)}>{it.level}</span></div>
                  <div style={{ color: "var(--text)", lineHeight: 1.5 }}>
                    <span style={{ color: "#9ccc65", fontWeight: 600 }}>{it.logger}</span>
                    <span style={{ color: "var(--text-faint)" }}> · </span>
                    <span style={{ color: "var(--text)" }}>{it.msg}</span>
                    {it.exc && (
                      <pre
                        style={{
                          marginTop: 6, padding: 8, borderRadius: 4,
                          background: "#2a0f0f", color: "#ff8a80",
                          border: "1px solid #5a1f1f",
                          fontSize: 11, whiteSpace: "pre-wrap",
                          fontFamily: "ui-monospace, Consolas, monospace",
                        }}
                      >
                        {it.exc}
                      </pre>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
