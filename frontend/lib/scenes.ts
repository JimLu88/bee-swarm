/**
 * 场景元信息 — mode_id → Material 图标 + 副标 hint (替代 emoji).
 * 与 components/v2/ModePicker 的 BUILTIN_MODES 对应; 这里只补图标/提示.
 * 自定义/extra 场景无映射时回退到 DEFAULT_SCENE_ICON.
 */

export const DEFAULT_SCENE_ICON = "tune";

/** README「场景图标映射」: 13 内置场景的 Material Symbols Rounded 名 */
export const SCENE_ICONS: Record<string, string> = {
  family_doctor: "stethoscope",
  nutrition_fitness: "fitness_center",
  dining_recommendation: "restaurant",
  purchase_decision: "shopping_cart",
  travel_planning: "flight",
  child_education: "child_care",
  legal_consulting: "gavel",
  tax_insurance: "account_balance",
  learning_planning: "school",
  startup_advisory: "rocket_launch",
  stock_trading: "trending_up",
  program_management: "code",
  generic_consulting: "lightbulb",
};

export function sceneIcon(modeId: string): string {
  return SCENE_ICONS[modeId] ?? DEFAULT_SCENE_ICON;
}

/** 顾问头像色板 (按 index 取模) */
export const AV_COLORS = ["#1F66E6", "#8E7BF0", "#1E9E63", "#E0A11A", "#3B73F0", "#5E8DFA", "#14834F"];
export function avBg(i: number): string {
  return AV_COLORS[((i % AV_COLORS.length) + AV_COLORS.length) % AV_COLORS.length];
}

/** 自信度 → 颜色 (≥.8 绿 / ≥.65 琥珀 / 否则红) */
export function confColor(c: number): string {
  return c >= 0.8 ? "var(--success)" : c >= 0.65 ? "var(--warning)" : "var(--danger)";
}
export function confBg(c: number): string {
  return c >= 0.8 ? "var(--success-bg)" : c >= 0.65 ? "var(--warning-bg)" : "var(--danger-bg)";
}

/** 取部门/顾问名首字做头像文字 */
export function initial(name: string): string {
  const t = (name || "").trim();
  return t ? t.slice(0, 1) : "?";
}

/** 努力程度 1-4 → 文案 */
export const EFFORT_LABELS: Record<number, string> = { 1: "简单", 2: "一般", 3: "深入", 4: "全力" };

/** 欢迎页建议卡片 (按场景给 4 条; 无专属则用通用) */
export type Suggestion = { icon: string; text: string };

const SCENE_SUGGESTIONS: Record<string, Suggestion[]> = {
  family_doctor: [
    { icon: "bedtime", text: "最近总是失眠，白天没精神，怎么调整作息？" },
    { icon: "science", text: "体检报告里尿酸偏高 480，要紧吗？要怎么吃？" },
    { icon: "vaccines", text: "孩子反复发烧两天，什么情况必须去医院？" },
    { icon: "accessibility_new", text: "长期久坐腰酸、肩颈僵，有没有靠谱的缓解办法？" },
  ],
};

const GENERIC_SUGGESTIONS: Suggestion[] = [
  { icon: "lightbulb", text: "把我正在纠结的事说清楚，帮我理一个能落地的方案" },
  { icon: "fact_check", text: "帮我把这件事的利弊和风险列出来再做决定" },
  { icon: "checklist", text: "给我一个分步骤的行动清单，从今天能开始做的" },
  { icon: "balance", text: "有几个选项拿不定主意，帮我横向对比一下" },
];

export function sceneSuggestions(modeId: string): Suggestion[] {
  return SCENE_SUGGESTIONS[modeId] ?? GENERIC_SUGGESTIONS;
}
