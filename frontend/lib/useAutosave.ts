"use client";

/** v6-S10 输入崩溃自救 — 任意输入框实时备份到 localStorage, 刷新/崩溃不丢. */

import { useEffect, useRef, useState } from "react";

const KEY_PREFIX = "h-semas:autosave:";
const DEBOUNCE_MS = 400;

export type AutosaveResult<T> = {
  value: T;
  setValue: (v: T) => void;
  /** 调用此函数表示输入已"消费"(提交/取消), 清掉备份 */
  clear: () => void;
  /** 是否从备份恢复了内容 */
  restored: boolean;
};

/**
 * 用法:
 *   const { value, setValue, clear, restored } = useAutosave("task-input", "");
 *   <input value={value} onChange={(e) => setValue(e.target.value)} />
 *   // 提交完调 clear()
 */
export function useAutosave<T extends string | object>(
  key: string,
  initial: T,
): AutosaveResult<T> {
  const storageKey = KEY_PREFIX + key;
  const [restored, setRestored] = useState(false);
  const [value, setValueState] = useState<T>(() => {
    if (typeof window === "undefined") return initial;
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw == null) return initial;
      if (typeof initial === "string") return raw as T;
      return JSON.parse(raw) as T;
    } catch {
      return initial;
    }
  });

  const firstRun = useRef(true);
  useEffect(() => {
    if (!firstRun.current) return;
    firstRun.current = false;
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(storageKey);
    if (raw != null && raw !== (typeof initial === "string" ? initial : JSON.stringify(initial))) {
      setRestored(true);
    }
  }, [storageKey, initial]);

  const writeTimer = useRef<number | null>(null);
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (writeTimer.current) window.clearTimeout(writeTimer.current);
    writeTimer.current = window.setTimeout(() => {
      try {
        const raw = typeof value === "string" ? (value as string) : JSON.stringify(value);
        if (!raw || raw === "\"\"" || raw === "{}" || raw === "[]") {
          window.localStorage.removeItem(storageKey);
        } else {
          window.localStorage.setItem(storageKey, raw);
        }
      } catch { /* quota / serialization fail — silent */ }
    }, DEBOUNCE_MS) as unknown as number;
    return () => { if (writeTimer.current) window.clearTimeout(writeTimer.current); };
  }, [storageKey, value]);

  const setValue = (v: T) => {
    setValueState(v);
    if (restored) setRestored(false);
  };

  const clear = () => {
    if (typeof window !== "undefined") {
      try { window.localStorage.removeItem(storageKey); } catch { /* ignore */ }
    }
    setRestored(false);
  };

  return { value, setValue, clear, restored };
}
