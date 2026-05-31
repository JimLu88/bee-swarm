"use client";

import type { CSSProperties } from "react";

export type Persona = {
  persona_id: string;
  name: string;
  title?: string;
  sub_specialty?: string;
  ocean?: { O?: number; C?: number; E?: number; A?: number; N?: number };
  personality?: string;
  diagnostic_style?: string;
  model_modeA?: string;
  model_modeB?: string;
  model_vendor?: string;
  prompt?: string;
};

type Props = {
  persona: Persona;
  role: "head" | "staff" | "ceo";
  busy?: boolean;
  onRegen: (personaId: string) => void;
  onEditPrompt: (persona: Persona) => void;
};

const roleEmoji: Record<Props["role"], string> = {
  head: "👑",
  staff: "👤",
  ceo: "🎩",
};

const card: CSSProperties = {
  padding: "10px 12px",
  borderRadius: 8,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--bg-hover)",
  background: "var(--bg-subtle)",
  display: "flex",
  flexDirection: "column",
  gap: 6,
  fontSize: 12,
};

const headerRow: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 6,
};

const btnSmall: CSSProperties = {
  padding: "3px 8px",
  fontSize: 11,
  borderRadius: 6,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  color: "inherit",
  cursor: "pointer",
};

function shortModel(m?: string): string {
  if (!m) return "";
  if (m.startsWith("ollama/")) return m.slice(7) + " · 本地";
  const last = m.split("/").pop() || m;
  return last.replace(/^claude-/, "").replace(/^gpt-/, "GPT-");
}

export function PersonaCard({ persona, role, busy, onRegen, onEditPrompt }: Props) {
  const ocean = persona.ocean || {};
  const oceanText = ["O", "C", "E", "A", "N"]
    .map((k) => `${k}${(((ocean as Record<string, number | undefined>)[k] ?? 0.5) * 10).toFixed(0)}`)
    .join("·");

  return (
    <div style={card}>
      <div style={headerRow}>
        <div style={{ fontWeight: 600 }}>
          {roleEmoji[role]} {persona.name}
          {persona.title && <span style={{ opacity: 0.55, marginLeft: 4 }}>· {persona.title}</span>}
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          <button type="button" style={btnSmall} disabled={busy}
                  onClick={() => onEditPrompt(persona)}>✏️ Prompt</button>
          {role !== "ceo" && (
            <button type="button" style={btnSmall} disabled={busy}
                    onClick={() => onRegen(persona.persona_id)}>🔄 重生</button>
          )}
        </div>
      </div>
      {persona.sub_specialty && (
        <div style={{ opacity: 0.7 }}>🎯 {persona.sub_specialty}</div>
      )}
      {persona.personality && (
        <div style={{ opacity: 0.55, fontSize: 11 }}>💭 {persona.personality}</div>
      )}
      <div style={{ display: "flex", gap: 8, opacity: 0.55, fontSize: 11 }}>
        <span title="OCEAN 五维">{oceanText}</span>
        {persona.model_modeA && (
          <span title={persona.model_modeA}>
            🤖 {shortModel(persona.model_modeA)}
            {persona.model_vendor && ` · ${persona.model_vendor}`}
          </span>
        )}
      </div>
    </div>
  );
}
