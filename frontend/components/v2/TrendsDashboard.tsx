"use client";

/** v6-K 趋势仪表盘 — 3 视图自由切换: 气泡聚合 / 卡片瀑布 / 类世界地图. */

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { resolveBackendHttpBase } from "../../lib/backend";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Bubble = {
  topic: string;
  kind: string;
  origin: string;
  url: string;
  score: number;
  ts: number;
  snippet?: string;
  language?: string;
  x?: number;
  y?: number;
};

type AggResp = {
  ts: number;
  live: boolean;
  bubbles: Bubble[];
  cards: Bubble[];
  map_points: Bubble[];
  summary: {
    total: number;
    by_origin: Record<string, number>;
    by_kind: Record<string, number>;
    p17_runs: number;
    p2_papers_total: number;
  };
};

type ViewMode = "bubbles" | "cards" | "map";

const ORIGIN_COLOR: Record<string, string> = {
  HackerNews: "#ff6600",
  GitHubTrending: "#a371f7",
  arxiv: "#b31b1b",
  HuggingFace: "#ffd21e",
};

const wrap: CSSProperties = {
  padding: 20, background: "var(--bg)", color: "var(--text)", minHeight: "100vh",
};

const headerBar: CSSProperties = {
  display: "flex", justifyContent: "space-between", alignItems: "center",
  marginBottom: 16, paddingBottom: 12,
  borderBottomWidth: 1, borderBottomStyle: "solid",
  borderBottomColor: "var(--border)",
};

const viewBtn = (active: boolean): CSSProperties => ({
  padding: "6px 14px", fontSize: 12, borderRadius: 6,
  borderWidth: 1, borderStyle: "solid",
  borderColor: active ? "var(--accent)" : "var(--border-strong)",
  background: active ? "var(--accent-bg)" : "var(--bg-card)",
  color: active ? "var(--accent)" : "#f0f0f0",
  cursor: "pointer", fontWeight: active ? 700 : 500,
});

const kpiBox: CSSProperties = {
  display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 16,
};

const kpiCard: CSSProperties = {
  flex: "1 1 130px", minWidth: 130,
  padding: "8px 12px", borderRadius: 8,
  background: "var(--bg-subtle)",
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
};

export function TrendsDashboard() {
  const backendUrl = resolveBackendHttpBase();
  const [view, setView] = useState<ViewMode>("bubbles");
  const [data, setData] = useState<AggResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const q = new URLSearchParams({ live: String(live) });
      const res = await fetchWithTimeout(
        `${backendUrl}/api/trends/aggregate?${q.toString()}`,
        undefined,
        live ? 60000 : TIMEOUT_MS.default,
      );
      if (!res.ok) {
        setError(`HTTP ${res.status}`);
        return;
      }
      setData(await res.json());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [backendUrl, live]);

  useEffect(() => { load(); }, [load]);

  return (
    <div style={wrap}>
      <div style={headerBar}>
        <div>
          <a href="/" style={{ color: "var(--info)", fontSize: 13, textDecoration: "none" }}>
            ← 返回主页
          </a>
          <div style={{ fontSize: 20, fontWeight: 700, marginTop: 4 }}>
            🌍 全球 AI 趋势仪表盘
          </div>
          <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 2 }}>
            数据来自 p17_trend_monitor + p2_paper_intake + 实时 bee-scraper
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <label style={{
            display: "flex", alignItems: "center", gap: 6, fontSize: 12,
            padding: "4px 10px", borderRadius: 6, background: "var(--bg-card)",
            cursor: "pointer",
          }}>
            <input
              type="checkbox" checked={live}
              onChange={(e) => setLive(e.target.checked)}
            />
            实时抓 (~10s)
          </label>
          <button type="button" onClick={load} style={viewBtn(false)}>
            {loading ? "..." : "↻ 刷新"}
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          padding: 12, marginBottom: 12, borderRadius: 8,
          background: "rgba(255,179,0,0.08)", color: "#ffb300",
          borderWidth: 1, borderStyle: "solid", borderColor: "rgba(255,179,0,0.30)",
        }}>
          ⚠ {error}
        </div>
      )}

      {data && (
        <div style={kpiBox}>
          <div style={kpiCard}>
            <div style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase" }}>抓到</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: "var(--info)" }}>{data.summary.total}</div>
            <div style={{ fontSize: 10, color: "var(--text-dim)" }}>条目</div>
          </div>
          {Object.entries(data.summary.by_origin).map(([k, v]) => (
            <div key={k} style={kpiCard}>
              <div style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase" }}>{k}</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: ORIGIN_COLOR[k] || "#f5f5f5" }}>{v}</div>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button type="button" style={viewBtn(view === "bubbles")} onClick={() => setView("bubbles")}>
          🫧 气泡聚合
        </button>
        <button type="button" style={viewBtn(view === "cards")} onClick={() => setView("cards")}>
          🃏 卡片瀑布
        </button>
        <button type="button" style={viewBtn(view === "map")} onClick={() => setView("map")}>
          🌐 类世界地图
        </button>
      </div>

      {!data && !loading && (
        <div style={{ padding: 40, textAlign: "center", color: "var(--text-dim)" }}>
          没有数据. 勾选 "实时抓" 或先在 CoordinatorPanel 跑一次 p17_trend_monitor.
        </div>
      )}
      {data && view === "bubbles" && <BubblesView items={data.bubbles} />}
      {data && view === "cards" && <CardsView items={data.cards} />}
      {data && view === "map" && <MapView items={data.map_points} />}
    </div>
  );
}

function BubblesView({ items }: { items: Bubble[] }) {
  if (!items || items.length === 0) {
    return <div style={{ color: "var(--text-dim)", padding: 20 }}>暂无气泡</div>;
  }
  const maxScore = Math.max(...items.map(i => i.score), 1);
  return (
    <div style={{
      display: "flex", gap: 10, flexWrap: "wrap",
      padding: 12, borderRadius: 10,
      background: "var(--bg-subtle)",
      borderWidth: 1, borderStyle: "solid", borderColor: "var(--bg-hover)",
    }}>
      {items.map((b, i) => {
        const sz = 50 + (b.score / maxScore) * 90;
        const color = ORIGIN_COLOR[b.origin] || "#888";
        return (
          <a key={i} href={b.url} target="_blank" rel="noreferrer noopener"
             style={{
               width: sz, height: sz, borderRadius: "50%",
               background: `${color}30`,
               borderWidth: 2, borderStyle: "solid", borderColor: color,
               display: "flex", alignItems: "center", justifyContent: "center",
               padding: 6, textDecoration: "none",
               cursor: b.url ? "pointer" : "default",
             }}
             title={`${b.origin} · score=${b.score.toFixed(1)}\n${b.topic}\n${b.snippet || ""}`}>
            <div style={{
              fontSize: Math.max(9, sz / 12), color: "var(--text)", textAlign: "center",
              lineHeight: 1.2, overflow: "hidden", maxHeight: sz - 12,
              wordBreak: "break-word",
            }}>
              {b.topic.slice(0, Math.floor(sz / 6))}
              {b.topic.length > Math.floor(sz / 6) ? "…" : ""}
            </div>
          </a>
        );
      })}
    </div>
  );
}

function CardsView({ items }: { items: Bubble[] }) {
  if (!items || items.length === 0) {
    return <div style={{ color: "var(--text-dim)", padding: 20 }}>暂无卡片</div>;
  }
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
      gap: 12,
    }}>
      {items.map((b, i) => {
        const color = ORIGIN_COLOR[b.origin] || "#888";
        return (
          <a key={i} href={b.url} target="_blank" rel="noreferrer noopener" style={{
            padding: 12, borderRadius: 10, textDecoration: "none",
            background: "var(--bg-subtle)", color: "var(--text)",
            borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
            borderLeftWidth: 4, borderLeftColor: color,
            display: "flex", flexDirection: "column", gap: 6,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{
                fontSize: 10, color, fontWeight: 700, letterSpacing: 0.3,
              }}>{b.origin}</span>
              <span style={{ fontSize: 10, color: "var(--text-faint)" }}>
                score {b.score.toFixed(1)}
              </span>
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", lineHeight: 1.4 }}>
              {b.topic}
            </div>
            {b.snippet && (
              <div style={{ fontSize: 11, color: "var(--text-dim)", lineHeight: 1.5 }}>
                {b.snippet}
              </div>
            )}
            {b.language && (
              <div style={{ fontSize: 10, color: "var(--info)" }}>{b.language}</div>
            )}
          </a>
        );
      })}
    </div>
  );
}

function MapView({ items }: { items: Bubble[] }) {
  if (!items || items.length === 0) {
    return <div style={{ color: "var(--text-dim)", padding: 20 }}>暂无地图点</div>;
  }
  return (
    <div style={{
      padding: 12, borderRadius: 10, background: "var(--bg-subtle)",
      borderWidth: 1, borderStyle: "solid", borderColor: "var(--bg-hover)",
    }}>
      <svg viewBox="0 0 100 60" width="100%" height="500" style={{ display: "block" }}>
        <ellipse cx="20" cy="24" rx="16" ry="11" fill="rgba(255,102,0,0.05)" stroke="rgba(255,102,0,0.30)" strokeWidth="0.2" />
        <text x="20" y="14" textAnchor="middle" fill="#ff6600" fontSize="2.2" fontWeight="700">HackerNews</text>

        <ellipse cx="55" cy="18" rx="16" ry="10" fill="rgba(163,113,247,0.05)" stroke="rgba(163,113,247,0.30)" strokeWidth="0.2" />
        <text x="55" y="6" textAnchor="middle" fill="#a371f7" fontSize="2.2" fontWeight="700">GitHub</text>

        <ellipse cx="80" cy="30" rx="14" ry="12" fill="rgba(179,27,27,0.05)" stroke="rgba(179,27,27,0.30)" strokeWidth="0.2" />
        <text x="80" y="46" textAnchor="middle" fill="#b31b1b" fontSize="2.2" fontWeight="700">arxiv</text>

        <ellipse cx="40" cy="39" rx="14" ry="10" fill="rgba(255,210,30,0.05)" stroke="rgba(255,210,30,0.30)" strokeWidth="0.2" />
        <text x="40" y="55" textAnchor="middle" fill="#ffd21e" fontSize="2.2" fontWeight="700">HuggingFace</text>

        {items.slice(0, 50).map((b, i) => {
          const cx = (b.x ?? 0.5) * 100;
          const cy = (b.y ?? 0.5) * 60;
          const r = Math.max(0.6, Math.min(2.2, Math.log(b.score + 1) * 0.5));
          const color = ORIGIN_COLOR[b.origin] || "#888";
          return (
            <g key={i}>
              <circle cx={cx} cy={cy} r={r} fill={color} opacity="0.85">
                <title>{`${b.origin} | score=${b.score.toFixed(1)}\n${b.topic}`}</title>
              </circle>
            </g>
          );
        })}
      </svg>
      <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-dim)", textAlign: "center" }}>
        鼠标悬停查看话题; 圆点大小 = 热度分数
      </div>
    </div>
  );
}
