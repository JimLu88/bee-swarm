"use client";

import type { CSSProperties } from "react";

export type DeptHeat = {
  dept: string;
  label?: string;
  heat: number; // 0-1
  callCount?: number;
  model?: string;
  status?: "idle" | "running" | "done";
  opinion?: string;
};

const overlay: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.6)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 100,
  padding: 24,
};

const modal: CSSProperties = {
  background: "#1a1a1f",
  borderRadius: 12,
  padding: 20,
  width: "min(720px, 96vw)",
  maxHeight: "92vh",
  overflowY: "auto",
  border: "1px solid rgba(255,255,255,0.1)",
};

const section: CSSProperties = {
  padding: 12,
  borderRadius: 8,
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.06)",
};

function HeatBar({ heat }: { heat: number }) {
  const pct = Math.max(0, Math.min(1, heat)) * 100;
  return (
    <div style={{ background: "rgba(0,0,0,0.4)", borderRadius: 4, height: 8, overflow: "hidden" }}>
      <div
        style={{
          width: pct + "%",
          height: "100%",
          background: heat > 0.7 ? "#ef4444" : heat > 0.4 ? "#facc15" : "#22c55e",
          transition: "width 0.4s",
        }}
      />
    </div>
  );
}

export function SwarmDashboardModal({
  open,
  onClose,
  heats,
  progressPct,
  etaSec,
  flowText,
}: {
  open: boolean;
  onClose: () => void;
  heats: DeptHeat[];
  progressPct?: number;
  etaSec?: number;
  flowText?: string;
}) {
  if (!open) return null;
  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h2 style={{ margin: 0, fontSize: 18 }}>🐝 AI 顾问们在干什么 (实时)</h2>
          <button
            type="button"
            onClick={onClose}
            style={{ background: "transparent", border: "none", color: "inherit", cursor: "pointer", fontSize: 18 }}
          >
            ✕
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={section}>
            <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>━━━ 哪几位 AI 顾问在忙 ━━━</div>
            {heats.length === 0 ? (
              <div style={{ opacity: 0.5, fontSize: 12 }}>(还没开始任务)</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {heats.map((h) => (
                  <div key={h.dept} style={{ display: "grid", gridTemplateColumns: "120px 1fr 80px", gap: 8, alignItems: "center", fontSize: 12 }}>
                    <div>{h.label ?? h.dept}</div>
                    <HeatBar heat={h.heat} />
                    <div style={{ opacity: 0.6, fontSize: 11 }}>{h.model ?? ""} {h.callCount ? `(${h.callCount})` : ""}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={section}>
            <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>━━━ 顾问们的实时想法 ━━━</div>
            {heats.filter((h) => h.opinion).length === 0 ? (
              <div style={{ opacity: 0.5, fontSize: 12 }}>(等顾问开始说话)</div>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
                {heats.filter((h) => h.opinion).map((h) => (
                  <li key={h.dept}>
                    <strong>{h.label ?? h.dept}:</strong> {h.opinion}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {flowText && (
            <div style={section}>
              <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>━━━ 整体流程 ━━━</div>
              <pre style={{ margin: 0, fontSize: 11, whiteSpace: "pre-wrap" }}>{flowText}</pre>
            </div>
          )}

          {progressPct !== undefined && (
            <div style={section}>
              <div style={{ marginBottom: 6, fontSize: 12 }}>
                总进度: {progressPct}% {etaSec ? `· 大约还有 ${etaSec} 秒` : ""}
              </div>
              <HeatBar heat={progressPct / 100} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
