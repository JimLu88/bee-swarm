"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Icon } from "./Icon";
import type { Difficulty } from "./DifficultySlider";

// 与 backend/scenarios/thinking_frameworks/*.yaml 的 id 对齐
const FRAMEWORKS: { id: string; label: string; emoji: string }[] = [
  { id: "first_principles", label: "第一性原理", emoji: "⚛️" },
  { id: "inversion", label: "逆向思考", emoji: "🔄" },
  { id: "six_hats", label: "六顶帽子", emoji: "🎩" },
  { id: "pre_mortem", label: "预死亡分析", emoji: "💀" },
  { id: "scamper", label: "SCAMPER", emoji: "🧩" },
  { id: "triz", label: "TRIZ 矛盾", emoji: "⚙️" },
  { id: "analogy", label: "类比迁移", emoji: "🪞" },
  { id: "constraint_flip", label: "约束反转", emoji: "🔀" },
];

export type Tier = "A" | "B" | "C";

type Props = {
  value: string;
  onChange: (v: string) => void;
  effort: Difficulty;
  onEffortChange: (e: Difficulty) => void;
  /** 模型档位 A=顶级 / B=中等 / C=经济 */
  tier: Tier;
  onTierChange: (t: Tier) => void;
  onSend: () => void;
  onAttach?: () => void;
  busy?: boolean;
  error?: string | null;
  placeholder?: string;
  /** 待发送的附件预览 (ImageStrip) — 渲染在输入框上方 */
  attachSlot?: ReactNode;
  /** 思维框架: 已选 id 列表 (空=AI自动按任务选); AI 预测的建议; 切换回调 */
  frameworks?: string[];
  aiFrameworks?: string[];
  onToggleFramework?: (id: string) => void;
};

const EFFORTS: { lv: Difficulty; label: string; hint: string }[] = [
  { lv: 1, label: "简单", hint: "CEO 直接答 · 不开部门 · 最快最省" },
  { lv: 2, label: "一般", hint: "关键几位顾问 · 1 轮" },
  { lv: 3, label: "深入", hint: "多位顾问 · 并行讨论 2 轮" },
  { lv: 4, label: "全力", hint: "全部顾问 · 反复讨论 3 轮 · 最贵" },
];

const TIERS: { v: Tier; label: string; hint: string }[] = [
  { v: "C", label: "经济", hint: "最省 · 本地/便宜模型" },
  { v: "B", label: "中等", hint: "便宜云 · 性价比" },
  { v: "A", label: "顶级", hint: "旗舰 · 最强最贵" },
];

export function Composer({
  value, onChange, effort, onEffortChange, tier, onTierChange, onSend, onAttach, busy, error, placeholder, attachSlot,
  frameworks, aiFrameworks, onToggleFramework,
}: Props) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const [fwOpen, setFwOpen] = useState(false);
  const [effOpen, setEffOpen] = useState(false);
  const sel = frameworks ?? [];
  const fwSummary = sel.length === 0
    ? "AI 自动"
    : (FRAMEWORKS.find((f) => f.id === sel[0])?.label ?? sel[0]) + (sel.length > 1 ? ` +${sel.length - 1}` : "");

  const tierLabel = TIERS.find((t) => t.v === tier)?.label ?? "中等";
  const depthLabel = EFFORTS.find((e) => e.lv === effort)?.label ?? "深入";

  // 自适应高度
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 170) + "px";
  }, [value]);

  const ready = value.trim().length > 0 && !busy;

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (ready) onSend();
    }
  };

  const pillBtn = (active: boolean): React.CSSProperties => ({
    display: "flex", alignItems: "center", gap: 8, width: "100%",
    padding: "7px 8px", borderRadius: 8, cursor: "pointer", textAlign: "left",
    border: "none", fontSize: 13,
    background: active ? "var(--accent-bg)" : "transparent",
    color: active ? "var(--accent)" : "var(--text)",
  });

  return (
    <div className="composer">
      {attachSlot}
      <div className="comp-box">
        <div className="comp-top">
          <textarea
            ref={taRef}
            className="comp-input"
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={placeholder ?? "把你的问题写清楚一点，顾问们会更准…"}
          />
        </div>
        <div className="comp-bottom">
          {onAttach && (
            <button type="button" className="comp-ico" onClick={onAttach} title="添加图片 / 文档" aria-label="添加图片或文档">
              <Icon name="add_circle" />
            </button>
          )}

          {/* v10 努力程度 → 下拉: 模型档位 + 讨论深度 (替代原 pill 横条) */}
          <div style={{ position: "relative" }}>
            <button
              type="button"
              onClick={() => { setEffOpen((v) => !v); setFwOpen(false); }}
              title="选模型档位(贵贱) + 讨论深度"
              style={{
                display: "inline-flex", alignItems: "center", gap: 5,
                padding: "5px 12px", borderRadius: 999, fontSize: 12.5, cursor: "pointer",
                borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
                background: "var(--bg-card)", color: "var(--text)", fontWeight: 600,
              }}
            >
              <Icon name="tune" />
              {tierLabel}脑 · {depthLabel}
              <Icon name={effOpen ? "expand_less" : "expand_more"} />
            </button>
            {effOpen && (
              <>
                <div onClick={() => setEffOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
                <div style={{
                  position: "absolute", bottom: "calc(100% + 6px)", left: 0, zIndex: 41,
                  width: 268, padding: 10, borderRadius: 12,
                  background: "var(--bg-card)", boxShadow: "0 8px 28px rgba(0,0,0,0.35)",
                  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
                }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-faint)", padding: "2px 6px 4px" }}>
                    🧠 模型档位（贵贱）
                  </div>
                  {TIERS.map((t) => (
                    <button key={t.v} type="button" onClick={() => onTierChange(t.v)} style={pillBtn(tier === t.v)}>
                      <span style={{ width: 16 }}>{tier === t.v ? "✓" : ""}</span>
                      <span style={{ minWidth: 30, fontWeight: 600 }}>{t.label}</span>
                      <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{t.hint}</span>
                    </button>
                  ))}
                  <div style={{ height: 1, background: "var(--border)", margin: "8px 4px" }} />
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-faint)", padding: "2px 6px 4px" }}>
                    💬 讨论深度
                  </div>
                  {EFFORTS.map((e) => (
                    <button key={e.lv} type="button" onClick={() => onEffortChange(e.lv)} style={pillBtn(effort === e.lv)}>
                      <span style={{ width: 16 }}>{effort === e.lv ? "✓" : ""}</span>
                      <span style={{ minWidth: 30, fontWeight: 600 }}>{e.label}</span>
                      <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{e.hint}</span>
                    </button>
                  ))}
                  <div style={{ fontSize: 10.5, color: "var(--text-faint)", padding: "8px 6px 2px", lineHeight: 1.5 }}>
                    提问后下方会自动生成「路线图」，可单独增减部门再重新会诊。
                  </div>
                </div>
              </>
            )}
          </div>

          {onToggleFramework && (
            <div style={{ position: "relative" }}>
              <button
                type="button"
                onClick={() => { setFwOpen((v) => !v); setEffOpen(false); }}
                title="思维框架 (空=AI自动按任务选, 也可手动指定)"
                style={{
                  display: "inline-flex", alignItems: "center", gap: 4,
                  padding: "5px 10px", borderRadius: 999, fontSize: 12, cursor: "pointer",
                  borderWidth: 1, borderStyle: "solid",
                  borderColor: sel.length ? "var(--accent)" : "var(--border)",
                  background: sel.length ? "var(--accent-bg)" : "var(--bg-card)",
                  color: sel.length ? "var(--accent)" : "var(--text-dim)",
                }}
              >
                🧠 思维·{fwSummary}
                <Icon name={fwOpen ? "expand_less" : "expand_more"} />
              </button>
              {fwOpen && (
                <>
                  <div onClick={() => setFwOpen(false)}
                       style={{ position: "fixed", inset: 0, zIndex: 40 }} />
                  <div style={{
                    position: "absolute", bottom: "calc(100% + 6px)", left: 0, zIndex: 41,
                    width: 230, padding: 8, borderRadius: 10,
                    background: "var(--bg-card)", boxShadow: "0 8px 28px rgba(0,0,0,0.35)",
                    borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
                  }}>
                    <div style={{ fontSize: 11, color: "var(--text-faint)", padding: "2px 6px 6px" }}>
                      留空 = AI 按任务自动选 · 选中=强制使用
                      {aiFrameworks && aiFrameworks.length > 0 && (
                        <div style={{ marginTop: 2, color: "var(--accent)" }}>
                          AI 建议: {aiFrameworks.map((id) => FRAMEWORKS.find((f) => f.id === id)?.label ?? id).join("、")}
                        </div>
                      )}
                    </div>
                    {FRAMEWORKS.map((f) => {
                      const on = sel.includes(f.id);
                      return (
                        <button
                          key={f.id}
                          type="button"
                          onClick={() => onToggleFramework(f.id)}
                          style={{
                            display: "flex", alignItems: "center", gap: 8, width: "100%",
                            padding: "6px 6px", borderRadius: 6, cursor: "pointer", textAlign: "left",
                            border: "none", fontSize: 13,
                            background: on ? "var(--accent-bg)" : "transparent",
                            color: on ? "var(--accent)" : "var(--text)",
                          }}
                        >
                          <span style={{ width: 16 }}>{on ? "✓" : ""}</span>
                          <span>{f.emoji}</span><span>{f.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}
          <button
            type="button"
            className={`send${ready ? " ready" : ""}`}
            onClick={() => ready && onSend()}
            disabled={!ready}
            title={busy ? "顾问们正在讨论…" : "开始"}
            aria-label="发送"
          >
            <Icon name={busy ? "progress_activity" : "arrow_upward"} className={busy ? "spinning" : ""} />
          </button>
        </div>
      </div>
      {error
        ? <div className="comp-err">{error}</div>
        : <div className="comp-hint"><Icon name="bolt" /> 选「{tierLabel}脑·{depthLabel}」· 回车发送，Shift+回车换行</div>}
    </div>
  );
}
