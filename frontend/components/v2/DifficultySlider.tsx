"use client";

import type { CSSProperties } from "react";

/**
 * v4-B 4 档分级 + AI 建议高亮
 * - 轻 / 中 / 重 / 极重
 * - difficulty: 1=轻 / 2=中 / 3=重 / 4=极重
 */

export type Difficulty = 1 | 2 | 3 | 4;

export const DIFFICULTY_INFO: Record<Difficulty, { name: string; emoji: string; cost: string; desc: string }> = {
  1: { name: "轻", emoji: "🟢", cost: "¥0.01-0.5", desc: "一句话/翻译/轻办公" },
  2: { name: "中", emoji: "🟡", cost: "¥0.5-5", desc: "多步任务/RAG/2-3 步" },
  3: { name: "重", emoji: "🔴", cost: "¥5-15", desc: "蜂群讨论/写完整功能" },
  4: { name: "极重", emoji: "⚫", cost: "¥15-50", desc: "战略级/5 轮辩论/全员" },
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
  border: "1px solid rgba(255,255,255,0.08)",
  background: "rgba(255,255,255,0.04)",
};

const row: CSSProperties = { display: "flex", gap: 6 };
const tier: CSSProperties = {
  flex: 1,
  padding: "10px 8px",
  borderRadius: 8,
  border: "1px solid rgba(255,255,255,0.12)",
  background: "rgba(0,0,0,0.2)",
  cursor: "pointer",
  textAlign: "center",
  color: "inherit",
  font: "inherit",
};
const tierActive: CSSProperties = { ...tier, borderColor: "#facc15", background: "rgba(250,204,21,0.18)" };
const tierAi: CSSProperties = { ...tier, borderStyle: "dashed", borderColor: "#22d3ee" };

export function DifficultySlider({ value, aiSuggested, aiReason, estimateText, onChange }: Props) {
  return (
    <div style={container}>
      {aiSuggested && (
        <div style={{ fontSize: 12, opacity: 0.85 }}>
          AI 建议 <strong>{DIFFICULTY_INFO[aiSuggested].emoji} {DIFFICULTY_INFO[aiSuggested].name}</strong>
          {aiReason && <span style={{ opacity: 0.6 }}> ({aiReason})</span>}
          {estimateText && <span style={{ marginLeft: 8 }}>· {estimateText}</span>}
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
              <div style={{ fontSize: 10, opacity: 0.6 }}>{info.cost}</div>
              <div style={{ fontSize: 10, opacity: 0.5 }}>{info.desc}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
