"use client";

import { useState, type CSSProperties } from "react";
import { KPICard, KPIRow } from "./viz/KPICard";
import { MiniBarChart, type BarDatum } from "./viz/MiniBarChart";
import { Timeline } from "./viz/Timeline";
import { DecisionFlowDAG } from "./viz/DecisionFlowDAG";
import { SmartResultRenderer } from "./viz/SmartResultRenderer";
import { InfoFeed, type MediaCard } from "./viz/InfoFeed";

export type DeptReport = {
  dept?: string;
  consensus?: string;
  conflicts?: string[];
  confidence_score?: number;
  dissent_intensity?: number;
};

export type DecisionSummary = {
  decision_id?: string;
  task?: string;
  mode_id?: string;
  mode_label?: string;
  created_at?: string;
  dept_reports?: DeptReport[];
  ceo_decision?: string;
  red_team_risks?: string[];
  /** v6-S7 成本可见 */
  total_tokens?: number;
  total_cost_yuan?: number;
  elapsed_sec?: number;
  /** v7 W3 爬虫图文聚合卡 (信息流) */
  media_cards?: MediaCard[];
};

type Props = {
  summary?: DecisionSummary | null;
  /** v6-S6 重跑某部门 */
  onRerunDept?: (deptId: string) => void;
  rerunningDept?: string | null;
  /** v6-Z 👍👎 反馈 → bandit 学习 (reward: 1=好 / 0=差) */
  onFeedback?: (reward: number) => void;
};

const card: CSSProperties = {
  padding: 14,
  borderRadius: 10,
  borderWidth: 1, borderStyle: "solid",
  borderColor: "var(--border)",
  background: "var(--bg-subtle)",
};
const h: CSSProperties = { margin: "0 0 10px 0", fontSize: 14, fontWeight: 700, color: "var(--text)" };

function avg(arr: number[]): number {
  if (arr.length === 0) return 0;
  return arr.reduce((s, v) => s + v, 0) / arr.length;
}

function FeedbackBar({ onFeedback }: { onFeedback: (reward: number) => void }) {
  const [done, setDone] = useState<null | "up" | "down">(null);
  const pill = (active: boolean): CSSProperties => ({
    padding: "5px 14px", fontSize: 13, borderRadius: 20, cursor: done ? "default" : "pointer",
    borderWidth: 1, borderStyle: "solid", borderColor: active ? "var(--accent)" : "var(--border-strong)",
    background: active ? "var(--accent-bg)" : "var(--bg-subtle)", color: "inherit",
  });
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: 8,
      background: "var(--info-bg)", borderWidth: 1, borderStyle: "solid",
      borderColor: "var(--info-bg)", fontSize: 12,
    }}>
      <span style={{ opacity: 0.7 }}>这次的路线/轮数选得怎么样?</span>
      <button type="button" disabled={!!done} style={pill(done === "up")}
        onClick={() => { if (!done) { setDone("up"); onFeedback(1); } }}>👍 好</button>
      <button type="button" disabled={!!done} style={pill(done === "down")}
        onClick={() => { if (!done) { setDone("down"); onFeedback(0); } }}>👎 差</button>
      {done && <span style={{ color: "#86efac" }}>✓ 已记录, CEO 下次会参考 (但仍保留探索)</span>}
    </div>
  );
}

export function ResultPanel({ summary, onRerunDept, rerunningDept, onFeedback }: Props) {
  if (!summary) {
    return (
      <div style={{ ...card, color: "var(--text-dim)", textAlign: "center", padding: "28px 12px" }}>
        🐝 上面写点东西然后点 「开始」, 我让 6 个顾问 AI 一起帮你想
      </div>
    );
  }

  const reports = summary.dept_reports ?? [];
  const confidences = reports.map(r => Number(r.confidence_score ?? 0));
  const dissents = reports.map(r => Number(r.dissent_intensity ?? 0));
  const avgConf = avg(confidences);
  const avgDis = avg(dissents);
  const deptCount = reports.length;
  const riskCount = summary.red_team_risks?.length ?? 0;

  const confBars: BarDatum[] = reports.map(r => ({
    label: r.dept ?? "?",
    value: Number(r.confidence_score ?? 0),
    rightLabel: (r.confidence_score ?? 0).toFixed(2),
  }));

  const dagDepts = reports.map(r => ({
    dept: r.dept ?? "?",
    confidence: r.confidence_score,
    status: (r.confidence_score ?? 1) < 0.5 ? "bad" as const
          : (r.confidence_score ?? 1) < 0.7 ? "warn" as const
          : "ok" as const,
  }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* v6-Z 👍👎 评分 — bandit 学习信号 (这次路线/轮数选得好不好) */}
      {onFeedback && <FeedbackBar onFeedback={onFeedback} />}

      {/* v7 成本不显示; 仅保留耗时 */}
      {summary.elapsed_sec != null && (
        <div style={{
          fontSize: 11, color: "var(--text-faint)", textAlign: "right",
          display: "flex", gap: 10, justifyContent: "flex-end", flexWrap: "wrap",
        }}>
          <span>⏱ {summary.elapsed_sec.toFixed(1)}s</span>
        </div>
      )}

      {deptCount > 0 && (
        <KPIRow>
          <KPICard
            label="平均自信度" icon="🎯"
            value={`${(avgConf * 100).toFixed(0)}%`}
            tone={avgConf >= 0.75 ? "good" : avgConf >= 0.5 ? "neutral" : "bad"}
            hint={`${deptCount} 位顾问`}
          />
          <KPICard
            label="平均分歧度" icon="⚡"
            value={`${(avgDis * 100).toFixed(0)}%`}
            tone={avgDis >= 0.7 ? "bad" : avgDis >= 0.4 ? "warn" : "good"}
            hint={avgDis >= 0.5 ? "意见分歧明显" : "意见相对一致"}
          />
          <KPICard
            label="红队风险" icon="⚠️"
            value={String(riskCount)}
            tone={riskCount >= 3 ? "bad" : riskCount >= 1 ? "warn" : "good"}
            hint={riskCount > 0 ? "见下方风险清单" : "无明显风险"}
          />
          <KPICard
            label="场景" icon="🎬"
            value={summary.mode_label ?? summary.mode_id ?? "—"}
            tone="neutral"
            hint={`ID: ${summary.decision_id?.slice(0, 12) ?? "—"}`}
          />
        </KPIRow>
      )}

      <div style={card}>
        <div style={h}>🎯 我的建议</div>
        {summary.ceo_decision
          ? <SmartResultRenderer text={summary.ceo_decision} />
          : <div style={{ fontSize: 13, color: "var(--text-dim)" }}>(等待中…)</div>
        }
      </div>

      {summary.red_team_risks && summary.red_team_risks.length > 0 && (
        <div style={{
          ...card,
          background: "rgba(255,82,82,0.06)",
          borderColor: "rgba(255,82,82,0.4)",
        }}>
          <div style={{ ...h, color: "#ff8a80" }}>⚠️ 要小心的地方</div>
          <Timeline
            items={summary.red_team_risks.map((r, i) => ({
              title: `风险 ${i + 1}`,
              body: r,
              tone: "bad",
            }))}
          />
        </div>
      )}

      {confBars.length > 0 && (
        <div style={card}>
          <div style={h}>📊 各部门自信度</div>
          <MiniBarChart items={confBars} max={1} />
        </div>
      )}

      {dagDepts.length > 0 && (
        <DecisionFlowDAG task={summary.task} depts={dagDepts} />
      )}

      {/* v7 W3 📎 展开更多: 部门原话 + 爬虫图文聚合 信息流 */}
      {(reports.length > 0 || (summary.media_cards && summary.media_cards.length > 0)) && (
        <div style={card}>
          <details>
            <summary style={{ cursor: "pointer", color: "var(--info)", fontSize: 12, fontWeight: 600 }}>
              📎 展开更多 (信息流: 各部门原话 + 相关图文资料)
            </summary>
            <div style={{ marginTop: 12 }}>
              <InfoFeed
                deptQuotes={reports.map((r) => ({ dept: r.dept ?? "?", consensus: r.consensus, conflicts: r.conflicts }))}
                mediaCards={summary.media_cards ?? []}
              />
            </div>
          </details>
        </div>
      )}

      {reports.length > 0 && (
        <div style={card}>
          <div style={h}>🗣️ 各部门具体怎么说</div>
          <details>
            <summary style={{ cursor: "pointer", color: "var(--info)", fontSize: 12 }}>
              展开看看 {reports.length} 位顾问的原话
            </summary>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}>
              {reports.map((r, i) => (
                <div key={i} style={{
                  padding: "10px 12px", borderRadius: 8,
                  background: "var(--bg-subtle)",
                  borderWidth: 1, borderStyle: "solid",
                  borderColor: "var(--border)",
                }}>
                  <div style={{
                    fontSize: 11, color: "var(--good)", fontWeight: 700,
                    marginBottom: 6, display: "flex", justifyContent: "space-between",
                    alignItems: "center", gap: 8,
                  }}>
                    <span>{r.dept}</span>
                    <span style={{ color: "var(--text-dim)", display: "flex", gap: 8, alignItems: "center" }}>
                      自信 {(r.confidence_score ?? 0).toFixed(2)} ·
                      分歧 {(r.dissent_intensity ?? 0).toFixed(2)}
                      {onRerunDept && r.dept && (
                        <button type="button"
                          disabled={rerunningDept === r.dept}
                          onClick={() => onRerunDept(r.dept!)}
                          title="只重跑这个部门, 不动其它"
                          style={{
                            padding: "2px 8px", fontSize: 10, borderRadius: 3, cursor: "pointer",
                            borderWidth: 1, borderStyle: "solid",
                            borderColor: rerunningDept === r.dept ? "#7f8c8d" : "var(--info)",
                            background: rerunningDept === r.dept ? "rgba(127,140,141,0.10)" : "var(--info-bg)",
                            color: rerunningDept === r.dept ? "#7f8c8d" : "var(--info)",
                          }}>
                          {rerunningDept === r.dept ? "重跑中…" : "🔄 重跑此部门"}
                        </button>
                      )}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text)", lineHeight: 1.55 }}>
                    <SmartResultRenderer text={r.consensus ?? ""} />
                  </div>
                  {r.conflicts && r.conflicts.length > 0 && (
                    <div style={{ marginTop: 8, paddingTop: 8,
                      borderTopWidth: 1, borderTopStyle: "solid",
                      borderTopColor: "var(--bg-hover)",
                    }}>
                      <div style={{ fontSize: 10, color: "#ffb300", fontWeight: 700, marginBottom: 4 }}>
                        ⚡ 部门内冲突
                      </div>
                      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11, color: "var(--text-dim)" }}>
                        {r.conflicts.map((c, k) => <li key={k}>{c}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
