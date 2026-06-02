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

/** v4-C / v6-A: 场景卡片 - 13 个内置场景, 鼠标悬停看更详细的说明.
 *  排序: 高频日常 (前 6) + 专业咨询 (后 6) + 通用 (最后 1).
 */
export const BUILTIN_MODES: ModeOption[] = [
  // 高频日常
  { mode_id: "family_doctor", label: "家庭医生", emoji: "🩺", hint: "看症状/营养建议/用药提醒" },
  { mode_id: "nutrition_fitness", label: "营养健身", emoji: "💪", hint: "减脂/增肌/慢病管理/装备" },
  { mode_id: "dining_recommendation", label: "餐饮推荐", emoji: "🍽️", hint: "本地探店/商务宴请/性价比" },
  { mode_id: "gift_selection", label: "送礼参谋", emoji: "🎁", hint: "送谁/什么场合/预算/避雷不踩坑" },
  { mode_id: "purchase_decision", label: "采购决策", emoji: "🛒", hint: "车/电子大件/家电/横向对比" },
  { mode_id: "travel_planning", label: "旅行计划", emoji: "✈️", hint: "签证/机票/安全/文化" },
  { mode_id: "child_education", label: "儿童教育", emoji: "👶", hint: "升学/心理/特长/家庭沟通" },
  // 专业咨询
  { mode_id: "legal_consulting", label: "法律咨询", emoji: "⚖️", hint: "合同/劳动/继承/知识产权" },
  { mode_id: "tax_insurance", label: "税务保险", emoji: "💰", hint: "个税/养老/保险/遗产规划" },
  { mode_id: "learning_planning", label: "学习规划", emoji: "📚", hint: "考研/留学/考证/语言考试" },
  { mode_id: "startup_advisory", label: "创业咨询", emoji: "🚀", hint: "商业模式/融资/团队/技术架构" },
  { mode_id: "stock_trading", label: "股票交易", emoji: "📈", hint: "盯盘/财报/资金/技术面" },
  { mode_id: "program_management", label: "程序管理", emoji: "💻", hint: "做软件/写代码/搞架构" },
  // 兜底
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
  // 拆开三属性, 避免简写 border 与单独 borderColor/borderStyle 互相覆盖触发 React 警告
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--bg-hover)",
  background: "var(--bg-subtle)",
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
  borderColor: "var(--accent)",
  background: "var(--accent-bg)",
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
