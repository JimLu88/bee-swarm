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

/** v4-C: 场景卡片 - 每个有 title + hint, 鼠标悬停看更详细的说明 */
export const BUILTIN_MODES: ModeOption[] = [
  { mode_id: "program_management", label: "程序管理", emoji: "💻", hint: "做软件/写代码/搞架构" },
  { mode_id: "family_doctor", label: "家庭医生", emoji: "🩺", hint: "看症状/营养建议/用药提醒" },
  { mode_id: "stock_trading", label: "股票交易", emoji: "📈", hint: "盯盘/财报/资金/技术面" },
  { mode_id: "travel_planning", label: "旅行计划", emoji: "✈️", hint: "签证/机票/安全/文化" },
  { mode_id: "generic_consulting", label: "通用咨询", emoji: "💡", hint: "啥都能聊,不限定领域" },
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
  fontFamily: "inherit",
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
        <div style={{ fontSize: 11, opacity: 0.6 }}>YAML 配置自己加</div>
      </button>
    </div>
  );
}
