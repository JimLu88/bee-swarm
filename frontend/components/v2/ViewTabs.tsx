"use client";

import type { CSSProperties, ReactNode } from "react";

export type ViewMode = "user" | "advanced" | "engineer";

const VIEWS: { id: ViewMode; label: string; emoji: string }[] = [
  { id: "user", label: "日常", emoji: "🌱" },
  { id: "advanced", label: "进阶", emoji: "⚙️" },
  { id: "engineer", label: "技术", emoji: "🔧" },
];

const tabRow: CSSProperties = {
  display: "flex",
  gap: 4,
  padding: 4,
  borderRadius: 8,
  background: "var(--bg-subtle)",
  width: "fit-content",
};

const tab: CSSProperties = {
  padding: "5px 12px",
  borderRadius: 6,
  border: "none",
  background: "transparent",
  cursor: "pointer",
  color: "inherit",
  fontFamily: "inherit",
  fontSize: 12,
  opacity: 0.7,
};

const tabActive: CSSProperties = { ...tab, background: "var(--border)", opacity: 1, fontWeight: 600 };

export function ViewTabs({
  value,
  onChange,
  children,
}: {
  value: ViewMode;
  onChange: (v: ViewMode) => void;
  children?: ReactNode;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
      <div style={tabRow}>
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            onClick={() => onChange(v.id)}
            style={value === v.id ? tabActive : tab}
          >
            {v.emoji} {v.label}
          </button>
        ))}
      </div>
      {children}
    </div>
  );
}
