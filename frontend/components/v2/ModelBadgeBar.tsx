"use client";

/** v6-N 模型 badge 条 — 聊天框上方显示当前会用到的 CEO/Head/Staff 模型. */

import { useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Persona = {
  persona_id?: string;
  name?: string;
  model_modeA?: string;
  model_vendor?: string;
};

type Dept = { dept_id?: string; head?: Persona; staff?: Persona[] };
type Team = { ceo?: Persona; departments?: Dept[] };

type Props = { backendUrl: string; modeId: string };

function vendorOf(model: string): string {
  if (!model) return "?";
  if (model.startsWith("anthropic/")) return "Anthropic";
  if (model.startsWith("openai/")) return "OpenAI";
  if (model.startsWith("deepseek/")) return "DeepSeek";
  if (model.startsWith("gemini/")) return "Gemini";
  if (model.startsWith("xai/")) return "xAI";
  if (model.startsWith("moonshot/")) return "Moonshot";
  if (model.startsWith("zhipu/")) return "智谱";
  if (model.startsWith("qwen/")) return "通义";
  if (model.startsWith("ollama") || model.startsWith("ollama_chat/")) return "本地 Ollama";
  return model.split("/")[0] || "?";
}

function isLocal(model: string): boolean {
  return !!model && (model.startsWith("ollama") || model.startsWith("ollama_chat/"));
}

const wrap: CSSProperties = {
  display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center",
  padding: "6px 10px", borderRadius: 8,
  background: "var(--bg-subtle)",
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--bg-hover)",
  fontSize: 11,
};

const badge = (local: boolean): CSSProperties => ({
  padding: "2px 8px", borderRadius: 4,
  background: local ? "rgba(76,175,80,0.12)" : "var(--info-bg)",
  borderWidth: 1, borderStyle: "solid",
  borderColor: local ? "rgba(76,175,80,0.30)" : "var(--info-bg)",
  color: local ? "#9ccc65" : "var(--info)",
  display: "inline-flex", alignItems: "center", gap: 4,
  fontWeight: 600,
});

export function ModelBadgeBar({ backendUrl, modeId }: Props) {
  const [team, setTeam] = useState<Team | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!modeId) return;
    setLoading(true);
    (async () => {
      try {
        const r = await fetchWithTimeout(
          `${backendUrl}/api/team/${encodeURIComponent(modeId)}`,
          undefined, TIMEOUT_MS.default,
        );
        if (r.ok) {
          const j = await r.json();
          setTeam(j.team || j || null);
        } else {
          setTeam(null);
        }
      } catch {
        setTeam(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [backendUrl, modeId]);

  if (loading) {
    return (
      <div style={wrap}>
        <span style={{ color: "var(--text-dim)" }}>正在读模型配置...</span>
      </div>
    );
  }

  if (!team || !team.ceo) {
    return (
      <div style={wrap}>
        <span style={{ color: "var(--text-dim)" }}>
          📋 这个场景还没召集顾问团. 用进阶视图的 TeamPanel 点 "召集" 让 AI 一次性生成全套部门 + 人设.
        </span>
      </div>
    );
  }

  const ceoModel = team.ceo?.model_modeA || "?";
  const heads: { dept: string; model: string }[] = (team.departments || []).map(d => ({
    dept: d.dept_id || "?",
    model: d.head?.model_modeA || "?",
  }));
  const staffModels = new Set<string>();
  (team.departments || []).forEach(d => {
    (d.staff || []).forEach(s => {
      if (s.model_modeA) staffModels.add(s.model_modeA);
    });
  });

  const localCount = (heads.filter(h => isLocal(h.model)).length)
    + Array.from(staffModels).filter(isLocal).length;
  const cloudCount = (heads.filter(h => !isLocal(h.model)).length)
    + Array.from(staffModels).filter(m => !isLocal(m)).length
    + 1; // CEO

  return (
    <div style={wrap}>
      <span style={badge(isLocal(ceoModel))} title={ceoModel}>
        🎯 CEO: {vendorOf(ceoModel)}
      </span>
      <span style={{ color: "var(--text-faint)" }}>·</span>
      {heads.map((h, i) => (
        <span key={i} style={badge(isLocal(h.model))} title={`${h.dept} → ${h.model}`}>
          👑 {h.dept}: {vendorOf(h.model)}
        </span>
      ))}
      {staffModels.size > 0 && (
        <>
          <span style={{ color: "var(--text-faint)" }}>·</span>
          <span style={badge(Array.from(staffModels).some(isLocal))}>
            👥 Staff: {Array.from(staffModels).map(vendorOf).join(" / ")}
          </span>
        </>
      )}
      <span style={{ color: "var(--text-faint)", marginLeft: "auto", fontSize: 10 }}>
        ☁ 云 {cloudCount} · 💾 本地 {localCount}
      </span>
    </div>
  );
}
