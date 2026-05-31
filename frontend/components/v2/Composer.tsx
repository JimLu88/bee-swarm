"use client";

import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { Icon } from "./Icon";
import type { Difficulty } from "./DifficultySlider";

type Props = {
  value: string;
  onChange: (v: string) => void;
  effort: Difficulty;
  onEffortChange: (e: Difficulty) => void;
  onSend: () => void;
  onAttach?: () => void;
  busy?: boolean;
  error?: string | null;
  placeholder?: string;
  /** 待发送的附件预览 (ImageStrip) — 渲染在输入框上方 */
  attachSlot?: ReactNode;
};

const EFFORTS: { lv: Difficulty; label: string }[] = [
  { lv: 1, label: "简单" },
  { lv: 2, label: "一般" },
  { lv: 3, label: "深入" },
  { lv: 4, label: "全力" },
];

export function Composer({
  value, onChange, effort, onEffortChange, onSend, onAttach, busy, error, placeholder, attachSlot,
}: Props) {
  const taRef = useRef<HTMLTextAreaElement>(null);

  // 自适应高度
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 170) + "px";
  }, [value]);

  const ready = value.trim().length > 0 && !busy;

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (ready) onSend();
    }
  };

  return (
    <div className="composer">
      {attachSlot}
      <div className="comp-box">
        <div className="comp-top">
          <textarea
            ref={taRef}
            className="comp-input"
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={placeholder ?? "把你的问题写清楚一点，顾问们会更准…"}
          />
        </div>
        <div className="comp-bottom">
          {onAttach && (
            <button type="button" className="comp-ico" onClick={onAttach} title="添加图片 / 文档" aria-label="添加图片或文档">
              <Icon name="add_circle" />
            </button>
          )}
          <span className="eff-label"><Icon name="tune" />努力程度</span>
          <div className="effort">
            {EFFORTS.map((e) => (
              <button
                key={e.lv}
                type="button"
                className={`eff l${e.lv}${effort === e.lv ? " active" : ""}`}
                onClick={() => onEffortChange(e.lv)}
                aria-pressed={effort === e.lv}
              >
                <span className="dot" />{e.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            className={`send${ready ? " ready" : ""}`}
            onClick={() => ready && onSend()}
            disabled={!ready}
            title={busy ? "顾问们正在讨论…" : "开始"}
            aria-label="发送"
          >
            <Icon name={busy ? "progress_activity" : "arrow_upward"} className={busy ? "spinning" : ""} />
          </button>
        </div>
      </div>
      {error
        ? <div className="comp-err">{error}</div>
        : <div className="comp-hint"><Icon name="bolt" /> 「深入」会让顾问们并行讨论 2 轮 · 回车发送，Shift+回车换行</div>}
    </div>
  );
}
