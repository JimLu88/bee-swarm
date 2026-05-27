"use client";

import type { CSSProperties } from "react";
import { useState } from "react";

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
  font: "inherit",
};

const HINTS = [
  "试试: 帮我整理本周的销售数据",
  "试试: 明天演讲的 PPT,主题是公司年度规划",
  "试试: 把这个截图里的文字提出来",
  "试试: 我下半年应该做什么业务",
];

export function TaskInput({ value, onChange, placeholder, onVoiceClick, onScreenshotClick, onUploadClick }: Props) {
  const [hint] = useState(() => HINTS[Math.floor(Math.random() * HINTS.length)]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? hint}
        style={box}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" style={btn} onClick={onVoiceClick} title="语音输入 (faster-whisper)">🎤 录音</button>
        <button type="button" style={btn} onClick={onScreenshotClick} title="截图 / 上传图片 (Claude Vision)">📷 截图</button>
        <button type="button" style={btn} onClick={onUploadClick} title="上传文件">📎 文件</button>
      </div>
    </div>
  );
}
