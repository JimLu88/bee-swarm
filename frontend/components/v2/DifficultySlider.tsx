"use client";

import type { CSSProperties } from "react";

/**
 * v4-B 4 档分级 + AI 建议高亮
 * - 轻 / 中 / 重 / 极重
 * - difficulty: 1=轻 / 2=中 / 3=重 / 4=极重
 */

export type Difficulty = 1 | 2 | 3 | 4;

export const DIFFICULTY_INFO: Record<Difficulty, { name: string; emoji: string; cost: string; desc: string }> = {
  1: { name: "简单", emoji: "🟢", cost: "约几分钱", desc: "翻译、一句话回答、做个表格" },
  2: { name: "一般", emoji: "🟡", cost: "约 1 元以内", desc: "整理资料、写邮件、做 PPT 大纲" },
  3: { name: "深入", emoji: "🔴", cost: "约 5-15 元", desc: "出方案、写代码、做完整 PPT" },
  4: { name: "全力", emoji: "⚫", cost: "约 15-50 元", desc: "战略规划、长报告、大决策" },
};

type Props = {
  value: Difficulty;
  aiSuggested?: Difficulty;
  aiReason?: string;
  estimateText?: string;
  onChange: (v: Difficulty) => void;
};

const container: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid var(--bg-hover)",
  background: "var(--bg-subtle)",
};

const row: CSSProperties = { display: "flex", gap: 6 };
const tier: CSSProperties = {
  flex: 1,
  padding: "10px 8px",
  borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--bg-subtle)",
  cursor: "pointer",
  textAlign: "center",
  color: "inherit",
  fontFamily: "inherit",
};
const tierActive: CSSProperties = { ...tier, borderColor: "var(--accent)", background: "var(--accent-bg)" };
const tierAi: CSSProperties = { ...tier, borderStyle: "dashed", borderColor: "#22d3ee" };

export function DifficultySlider({ value, aiSuggested, aiReason, onChange }: Props) {
  return (
    <div style={container}>
      {aiSuggested && (
        <div style={{ fontSize: 12, opacity: 0.85 }}>
          AI 建议 <strong>{DIFFICULTY_INFO[aiSuggested].emoji} {DIFFICULTY_INFO[aiSuggested].name}</strong>
          {aiReason && <span style={{ opacity: 0.6 }}> ({aiReason})</span>}
        </div>
      )}
      <div style={row}>
        {([1, 2, 3, 4] as Difficulty[]).map((d) => {
          const info = DIFFICULTY_INFO[d];
          const isSelected = value === d;
          const isAi = aiSuggested === d && !isSelected;
          return (
            <button
              key={d}
              type="button"
              onClick={() => onChange(d)}
              style={isSelected ? tierActive : isAi ? tierAi : tier}
            >
              <div style={{ fontSize: 18 }}>{info.emoji}</div>
              <div style={{ fontWeight: 600 }}>{info.name}</div>
              <div style={{ fontSize: 10, opacity: 0.5 }}>{info.desc}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
