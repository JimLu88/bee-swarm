"use client";

import { useState } from "react";
import { Icon } from "./Icon";
import { SmartResultRenderer } from "./viz/SmartResultRenderer";
import { InfoFeed, type MediaCard } from "./viz/InfoFeed";
import { TracePanel } from "./viz/TracePanel";
import type { MapPlace } from "./viz/MapPins";
import { avBg, confColor, confBg, initial, EFFORT_LABELS } from "../../lib/scenes";

export type DeptReport = {
  dept?: string;
  consensus?: string;
  conflicts?: string[];
  confidence_score?: number;
  dissent_intensity?: number;
  kb_used?: number;
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
  total_tokens?: number;
  total_cost_yuan?: number;
  elapsed_sec?: number;
  media_cards?: MediaCard[];
  /** v11 方案4 地图钉店: 高德地理编码后的推荐地点坐标 */
  map_places?: MapPlace[];
  /** v12 信源可信度引擎汇总 (前台12场景) */
  source_consensus?: { headline?: string; summary?: string };
};

type Props = {
  summary?: DecisionSummary | null;
  /** v6-S6 重跑某部门 */
  onRerunDept?: (deptId: string) => void;
  rerunningDept?: string | null;
  /** v6-Z 👍👎 反馈 → bandit 学习 (reward: 1=好 / 0=差) */
  onFeedback?: (reward: number) => void;
  /** 重新生成整次决策 */
  onRegenerate?: () => void;
  /** 操作条元信息: 努力程度 1-4 */
  effort?: number;
  /** 部门 id → 中文名 (来自 /api/modes department_labels, 含横切部门); 没有则回退 id */
  labels?: Record<string, string>;
  /** 后端地址 — 传给 InfoFeed 做图片代理 (/api/img) */
  backendUrl?: string;
};

/** 中文标签取「括号前」短名: "内科 (常见病/慢病)" → "内科" */
function shortDeptLabel(name: string): string {
  return name.split(/[\s(（]/)[0] || name;
}

function avg(arr: number[]): number {
  if (arr.length === 0) return 0;
  return arr.reduce((s, v) => s + v, 0) / arr.length;
}

function dissentLabel(v: number): string {
  return v >= 0.7 ? "高" : v >= 0.4 ? "中" : "低";
}

export function ResultPanel({ summary, onRerunDept, rerunningDept, onFeedback, onRegenerate, effort, labels, backendUrl }: Props) {
  const [acOpen, setAcOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [fb, setFb] = useState<null | "up" | "down">(null);
  const [traceOpen, setTraceOpen] = useState(false);

  if (!summary) return null;

  const reports = summary.dept_reports ?? [];
  const confidences = reports.map((r) => Number(r.confidence_score ?? 0));
  const dissents = reports.map((r) => Number(r.dissent_intensity ?? 0));
  const avgConf = avg(confidences);
  const avgDis = avg(dissents);
  const deptCount = reports.length;
  const risks = summary.red_team_risks ?? [];
  const riskCount = risks.length;
  const mediaCards = summary.media_cards ?? [];
  const mapPlaces = summary.map_places ?? [];
  const kbTotal = reports.reduce((s, r) => s + (r.kb_used ?? 0), 0);

  // 「全屏情报站」: 数据写 localStorage 交接 → 新标签页打开 /intel 独立全屏 (视觉更整)
  const openIntel = () => {
    try {
      localStorage.setItem("hsemas:intel", JSON.stringify({
        title: summary.mode_label || summary.task || "情报站",
        mediaCards, mapPlaces, backendUrl: backendUrl || "",
      }));
    } catch { /* 配额满/隐私模式 → 忽略, 仍尝试打开 */ }
    window.open("/intel", "_blank", "noopener");
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(summary.ceo_decision ?? "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch { /* ignore */ }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* 建议正文 — 排版容器 .answer, 正文交给 SmartResultRenderer */}
      {summary.ceo_decision && (
        <div className="answer">
          <SmartResultRenderer text={summary.ceo_decision} />
        </div>
      )}

      {/* KPI 指标条 */}
      {deptCount > 0 && (
        <div className="kpis">
          <div className="kpi tone-accent">
            <Icon name="groups" />
            <span className="kcol"><span className="kv">{deptCount}</span><span className="kl">位顾问参与</span></span>
          </div>
          <div className={`kpi ${avgConf >= 0.75 ? "tone-good" : avgConf >= 0.5 ? "tone-warn" : "tone-bad"}`}>
            <Icon name="handshake" />
            <span className="kcol"><span className="kv">{(avgConf * 100).toFixed(0)}%</span><span className="kl">平均共识度</span></span>
          </div>
          <div className={`kpi ${avgDis >= 0.7 ? "tone-bad" : avgDis >= 0.4 ? "tone-warn" : "tone-good"}`}>
            <Icon name="flash_on" />
            <span className="kcol"><span className="kv">{dissentLabel(avgDis)}</span><span className="kl">意见分歧</span></span>
          </div>
          <div className={`kpi ${riskCount >= 3 ? "tone-bad" : riskCount >= 1 ? "tone-warn" : "tone-good"}`}>
            <Icon name="shield" />
            <span className="kcol"><span className="kv">{riskCount}</span><span className="kl">红队风险</span></span>
          </div>
        </div>
      )}

      {/* 🔍 复盘看板入口 + 面板 (任意有部门发言的决策都能复盘) */}
      {deptCount > 0 && (
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button type="button" onClick={() => setTraceOpen(true)}
            style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "5px 12px", borderRadius: 999, border: "1px solid var(--border)", background: "var(--bg-card)", color: "var(--text-dim)", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
            <Icon name="account_tree" size={15} /> 复盘看板
          </button>
        </div>
      )}
      <TracePanel open={traceOpen} onClose={() => setTraceOpen(false)} summary={summary} labels={labels} backendUrl={backendUrl} />

      {/* 红队风险提示 */}
      {riskCount > 0 && (
        <div className="callout warn">
          <div className="callout-h"><Icon name="gpp_maybe" />红队提醒：这些地方要小心</div>
          {risks.map((r, i) => (
            <div key={i} className="risk">
              <Icon name="chevron_right" />
              <span className="rt">{r}</span>
            </div>
          ))}
        </div>
      )}

      {/* 各顾问发言折叠 */}
      {deptCount > 0 && (
        <div className={`accord${acOpen ? " open" : ""}`}>
          <button type="button" className="accord-head" onClick={() => setAcOpen((v) => !v)}>
            <Icon name="forum" className="lead-i" />
            <span className="t">各顾问具体怎么说</span>
            <span className="c">{deptCount} 份发言{kbTotal > 0 ? ` · 共参考 ${kbTotal} 条专业知识` : ""}</span>
            <Icon name="expand_more" className="chev" />
          </button>
          <div className="accord-body">
            {reports.map((r, i) => {
              const conf = Number(r.confidence_score ?? 0);
              const rawDept = r.dept ?? "?";
              const name = labels?.[rawDept] ? shortDeptLabel(labels[rawDept]) : rawDept;
              return (
                <div key={i} className="dept">
                  <div className="dept-top">
                    <span className="adv-av" style={{ background: avBg(i) }}>{initial(name)}</span>
                    <span className="dept-name">{name}</span>
                    {(r.kb_used ?? 0) > 0 && (
                      <span title="本次该顾问参考的专业知识条数" style={{ fontSize: 11, color: "var(--text-dim)", display: "inline-flex", alignItems: "center", gap: 2, marginLeft: 6 }}>
                        <Icon name="menu_book" size={13} />{r.kb_used}
                      </span>
                    )}
                    <span className="dept-conf">
                      <span className="conf-pill" style={{ background: confBg(conf), color: confColor(conf) }}>
                        {(conf * 100).toFixed(0)}%
                      </span>
                      自信度
                    </span>
                  </div>
                  <div className="dept-say">
                    <SmartResultRenderer text={r.consensus ?? ""} />
                  </div>
                  {r.conflicts && r.conflicts.length > 0 && (
                    <div className="dept-conflict">
                      <b>⚡ 分歧：</b>{r.conflicts.join("；")}
                    </div>
                  )}
                  {onRerunDept && r.dept && (
                    <button
                      type="button"
                      className="dept-rerun"
                      disabled={rerunningDept === r.dept}
                      onClick={() => onRerunDept(r.dept!)}
                      title="只重跑这个部门, 不动其它"
                    >
                      {rerunningDept === r.dept ? "重跑中…" : "重跑此部门"}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 相关图文资料 (爬虫信息流, 有才显示) */}
      {mediaCards.length > 0 && (
        <div className="accord">
          <div className="accord-head" style={{ cursor: "default" }}>
            <Icon name="auto_stories" className="lead-i" />
            <span className="t">相关图文资料</span>
            <span className="c">{mediaCards.length} 条</span>
            <button type="button" onClick={openIntel} title="新标签页打开全屏情报站"
              style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 5, padding: "5px 12px", borderRadius: 999, border: "1px solid var(--accent)", background: "var(--accent-bg)", color: "var(--accent)", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
              <Icon name="travel_explore" size={15} /> 全屏情报站
              <Icon name="open_in_new" size={13} />
            </button>
          </div>
          <div className="accord-body" style={{ display: "flex" }}>
            <InfoFeed deptQuotes={[]} mediaCards={mediaCards} mapPlaces={mapPlaces} backendUrl={backendUrl} consensus={summary.source_consensus} />
          </div>
        </div>
      )}

      {/* 操作条 */}
      <div className="actions">
        <button type="button" className="act" onClick={copy} title={copied ? "已复制" : "复制"} aria-label="复制">
          <Icon name={copied ? "done" : "content_copy"} />
        </button>
        {onRegenerate && (
          <button type="button" className="act" onClick={onRegenerate} title="重新生成" aria-label="重新生成">
            <Icon name="refresh" />
          </button>
        )}
        {onFeedback && (
          <>
            <span className="act-div" />
            <button
              type="button"
              className={`act${fb === "up" ? " on-up" : ""}`}
              disabled={!!fb}
              onClick={() => { if (!fb) { setFb("up"); onFeedback(1); } }}
              title="有帮助" aria-label="有帮助"
            >
              <Icon name="thumb_up" />
            </button>
            <button
              type="button"
              className={`act${fb === "down" ? " on-down" : ""}`}
              disabled={!!fb}
              onClick={() => { if (!fb) { setFb("down"); onFeedback(0); } }}
              title="没帮上" aria-label="没帮上"
            >
              <Icon name="thumb_down" />
            </button>
          </>
        )}
        <span className="act-meta">
          {summary.elapsed_sec != null && <><Icon name="schedule" />{summary.elapsed_sec.toFixed(1)}s</>}
          {effort != null && EFFORT_LABELS[effort] ? <span>· 努力程度 {EFFORT_LABELS[effort]}</span> : null}
        </span>
      </div>
    </div>
  );
}
