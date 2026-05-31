"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import type { Persona } from "./PersonaCard";

type Props = {
  open: boolean;
  persona: Persona | null;
  busy?: boolean;
  onSave: (newPrompt: string) => void;
  onClose: () => void;
};

const backdrop: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "var(--overlay)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 60,
};

const modal: CSSProperties = {
  width: "min(720px, 92vw)",
  maxHeight: "85vh",
  padding: 18,
  borderRadius: 12,
  background: "#1a1a1a",
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--border)",
  display: "flex",
  flexDirection: "column",
  gap: 12,
};

const header: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const textarea: CSSProperties = {
  width: "100%",
  minHeight: 320,
  padding: 10,
  borderRadius: 6,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  color: "inherit",
  fontFamily: "Consolas, Monaco, monospace",
  fontSize: 12,
  lineHeight: 1.5,
  resize: "vertical",
};

const btn = (kind: "primary" | "default"): CSSProperties => ({
  padding: "6px 14px",
  fontSize: 13,
  borderRadius: 6,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: kind === "primary" ? "var(--accent)" : "var(--border)",
  background: kind === "primary" ? "var(--accent-bg)" : "var(--bg-subtle)",
  color: "inherit",
  cursor: "pointer",
});

export function PromptEditModal({ open, persona, busy, onSave, onClose }: Props) {
  const [text, setText] = useState("");

  useEffect(() => {
    setText(persona?.prompt ?? "");
  }, [persona]);

  if (!open || !persona) return null;

  return (
    <div style={backdrop} onClick={onClose}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <div style={header}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>
              ✏️ 改 {persona.name} 的 system prompt
            </div>
            <div style={{ fontSize: 11, opacity: 0.55, marginTop: 2 }}>
              {persona.title} · {persona.sub_specialty} · {persona.model_modeA}
            </div>
          </div>
          <button type="button" style={btn("default")} onClick={onClose}>✕ 关</button>
        </div>
        <textarea
          style={textarea}
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
        />
        <div style={{ fontSize: 11, opacity: 0.55 }}>
          💡 改了 prompt 这个人下次会诊就按新人设说话。模型 / OCEAN / 性格 这些不会变, 想换风格请用 [🔄 重生]。
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" style={btn("default")} onClick={onClose}>取消</button>
          <button type="button" style={btn("primary")} disabled={busy} onClick={() => onSave(text)}>
            {busy ? "保存中..." : "💾 保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
