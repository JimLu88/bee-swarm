"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";

const SEEN_KEY = "bee_onboarding_seen_v1";

const STEPS = [
  {
    emoji: "🐝",
    title: "你好, 我是你的 AI 智囊团",
    body: "不是一个 AI 在跟你聊, 而是 6 位不同视角的 AI 顾问 + 1 位 CEO 综合.",
  },
  {
    emoji: "🎯",
    title: "我能帮你做什么",
    body: "做 PPT、写代码、出方案、整理资料、看股票、规划旅行... 任何需要思考的事都行.",
  },
  {
    emoji: "💰",
    title: "费用透明, 你说了算",
    body: "每个任务有 4 档难度. 简单任务约几分钱, 战略级最多 50 元. AI 会建议, 你最终拍板.",
  },
  {
    emoji: "🔐",
    title: "你的数据全在本地",
    body: "API Key、对话记录、文件全部存你电脑里, 永远不会上传. AI 调用走聚合服务.",
  },
  {
    emoji: "🚀",
    title: "现在开始吧",
    body: "先去 ⚙ AI 设置 把 Key 填上, 然后在主页输入任务, 点开始即可.",
  },
];

const overlay: CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)",
  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 24,
};
const modal: CSSProperties = {
  background: "#1a1a1f", borderRadius: 16, padding: 32, width: "min(480px,94vw)",
  border: "1px solid rgba(255,255,255,0.1)", textAlign: "center",
};
const dot: CSSProperties = {
  width: 8, height: 8, borderRadius: 4, background: "rgba(255,255,255,0.15)", display: "inline-block", margin: "0 3px",
};

export function Onboarding() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    try {
      const seen = window.localStorage.getItem(SEEN_KEY);
      if (!seen) setOpen(true);
    } catch { /* ignore */ }
  }, []);

  if (!open) return null;
  const s = STEPS[step];
  const last = step === STEPS.length - 1;

  const close = () => {
    try { window.localStorage.setItem(SEEN_KEY, "1"); } catch { /* ignore */ }
    setOpen(false);
  };

  return (
    <div style={overlay} onClick={close}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 56, marginBottom: 16 }}>{s.emoji}</div>
        <div style={{ fontSize: 22, fontWeight: 700, marginBottom: 12 }}>{s.title}</div>
        <div style={{ fontSize: 14, opacity: 0.8, lineHeight: 1.7, marginBottom: 24 }}>{s.body}</div>
        <div style={{ marginBottom: 20 }}>
          {STEPS.map((_, i) => (
            <span key={i} style={{ ...dot, background: i === step ? "#facc15" : "rgba(255,255,255,0.15)" }} />
          ))}
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
          {step > 0 && (
            <button type="button" onClick={() => setStep(step - 1)} style={btnGhost}>上一步</button>
          )}
          {last ? (
            <button type="button" onClick={close} style={btnPrimary}>开始使用 🚀</button>
          ) : (
            <button type="button" onClick={() => setStep(step + 1)} style={btnPrimary}>下一步</button>
          )}
          {!last && (
            <button type="button" onClick={close} style={{ ...btnGhost, opacity: 0.6 }}>跳过</button>
          )}
        </div>
      </div>
    </div>
  );
}

const btnPrimary: CSSProperties = {
  padding: "10px 24px", borderRadius: 8, border: "none",
  background: "#facc15", color: "#000", cursor: "pointer", fontWeight: 600,
};
const btnGhost: CSSProperties = {
  padding: "10px 16px", borderRadius: 8,
  border: "1px solid rgba(255,255,255,0.15)", background: "transparent",
  color: "inherit", cursor: "pointer",
};