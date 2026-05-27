"use client";

import type { CSSProperties } from "react";

/**
 * v4-C 5+1 场景大卡片(首屏顶部,一键切 mode_id)
 * - 5 内置 + "自定义场景..." 跳到 extra YAML 列表
 */

export type ModeOption = {
  mode_id: string;
  label: string;
  emoji: string;
  hint: string;
};

export const BUILTIN_MODES: ModeOption[] = [
  { mode_id: "program_management", label: "程序管理", emoji: "💻", hint: "架构/逻辑/UI/数据库" },
  { mode_id: "family_doctor", label: "家庭医生", emoji: "🩺", hint: "症状/营养/用药/心理" },
  { mode_id: "stock_trading", label: "股票交易", emoji: "📈", hint: "宏观/财报/技术/主力" },
  { mode_id: "travel_planning", label: "旅行计划", emoji: "✈️", hint: "签证/性价比/安全/禁忌" },
  { mode_id: "generic_consulting", label: "通用咨询", emoji: "💡", hint: "百搭场景" },
];

type Props = {
  selected: string;
  onSelect: (mode_id: string) => void;
  onOpenCustom: () => void;
};

const baseCard: CSSProperties = {
  padding: "14px 18px",
  borderRadius: 12,
  border: "1px solid rgba(255,255,255,0.08)",
  background: "rgba(255,255,255,0.04)",
  cursor: "pointer",
  minWidth: 130,
  display: "flex",
  flexDirection: "column",
  gap: 4,
  transition: "all 0.15s",
  color: "inherit",
  font: "inherit",
};

const selectedCard: CSSProperties = {
  ...baseCard,
  borderColor: "#facc15",
  background: "rgba(250, 204, 21, 0.12)",
  boxShadow: "0 0 0 1px #facc15 inset",
};

export function ModePicker({ selected, onSelect, onOpenCustom }: Props) {
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", padding: "8px 0" }}>
      {BUILTIN_MODES.map((m) => (
        <button
          key={m.mode_id}
          type="button"
          onClick={() => onSelect(m.mode_id)}
          style={selected === m.mode_id ? selectedCard : baseCard}
          aria-pressed={selected === m.mode_id}
        >
          <div style={{ fontSize: 22 }}>{m.emoji}</div>
          <div style={{ fontWeight: 600 }}>{m.label}</div>
          <div style={{ fontSize: 11, opacity: 0.6 }}>{m.hint}</div>
        </button>
      ))}
      <button
        type="button"
        onClick={onOpenCustom}
        style={{ ...baseCard, borderStyle: "dashed", opacity: 0.7 }}
      >
        <div style={{ fontSize: 22 }}>＋</div>
        <div style={{ fontWeight: 600 }}>自定义场景</div>
        <div style={{ fontSize: 11, opacity: 0.6 }}>从 YAML 加载</div>
      </button>
    </div>
  );
}
