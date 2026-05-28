"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";

type Props = {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  onVoiceClick?: () => void;
  onScreenshotClick?: () => void;
  onUploadClick?: () => void;
};

const box: CSSProperties = {
  width: "100%",
  minHeight: 80,
  padding: "12px 14px",
  borderRadius: 10,
  border: "1px solid rgba(255,255,255,0.1)",
  background: "rgba(0,0,0,0.25)",
  color: "inherit",
  fontSize: 14,
  fontFamily: "inherit",
  resize: "vertical",
};

const btn: CSSProperties = {
  padding: "6px 10px",
  borderRadius: 6,
  border: "1px solid rgba(255,255,255,0.12)",
  background: "rgba(255,255,255,0.05)",
  cursor: "pointer",
  color: "inherit",
  fontFamily: "inherit",
};

const HINTS = [
  "比如: 写一篇产品推广文案,卖点是省心",
  "比如: 帮我看看这周该买哪只股票",
  "比如: 我下半年的人生应该怎么规划",
  "比如: 解释一下 Docker 是什么",
  "比如: 给我推荐一个 5 道菜的家庭晚餐",
  "比如: 整理本周销售数据,做个 PPT",
  "比如: 帮我写一份周报模板",
];

export function TaskInput({ value, onChange, placeholder, onVoiceClick, onScreenshotClick, onUploadClick }: Props) {
  const [hint, setHint] = useState(HINTS[0]);
  useEffect(() => {
    // 仅在客户端水合后随机, 避免 SSR/CSR placeholder 不一致触发 hydration warning
    setHint(HINTS[Math.floor(Math.random() * HINTS.length)]);
  }, []);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? hint}
        style={box}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" style={btn} onClick={onVoiceClick} title="录一段话(语音转文字)">🎤 录音</button>
        <button type="button" style={btn} onClick={onScreenshotClick} title="截屏或上传图片让 AI 看">📷 截图</button>
        <button type="button" style={btn} onClick={onUploadClick} title="附件 (文档/PDF/Excel)">📎 文件</button>
      </div>
    </div>
  );
}
