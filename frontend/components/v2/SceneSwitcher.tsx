"use client";

import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";
import { BUILTIN_MODES } from "./ModePicker";
import { sceneIcon } from "../../lib/scenes";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type ModeItem = { mode_id: string; label: string; hint?: string };

type Props = {
  selected: string;
  onSelect: (mode: string) => void;
  onManage: () => void;
  backendUrl?: string;
};

const HINT_OF: Record<string, string> = Object.fromEntries(
  BUILTIN_MODES.map((m) => [m.mode_id, m.hint]),
);

export function SceneSwitcher({ selected, onSelect, onManage, backendUrl }: Props) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [modes, setModes] = useState<ModeItem[]>(
    BUILTIN_MODES.map((m) => ({ mode_id: m.mode_id, label: m.label, hint: m.hint })),
  );

  // 拉后端全部场景 (13 内置 + 自定义)
  useEffect(() => {
    if (!backendUrl) return;
    let aborted = false;
    (async () => {
      try {
        const res = await fetchWithTimeout(`${backendUrl}/api/modes`, undefined, TIMEOUT_MS.default);
        if (!res.ok) return;
        const j = await res.json();
        if (aborted || !Array.isArray(j.modes)) return;
        setModes(
          j.modes.map((m: { mode_id: string; label: string }) => ({
            mode_id: m.mode_id, label: m.label, hint: HINT_OF[m.mode_id] ?? "多位专科顾问一起讨论",
          })),
        );
      } catch { /* 保持内置兜底 */ }
    })();
    return () => { aborted = true; };
  }, [backendUrl]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const cur = modes.find((m) => m.mode_id === selected);
  const curHint = cur?.hint ?? HINT_OF[selected] ?? "多位专科顾问";

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <button type="button" className="scene-select" onClick={() => setOpen((v) => !v)}>
        <span className="scene-ico"><Icon name={sceneIcon(selected)} /></span>
        <span className="scene-txt">
          <b>{cur?.label ?? "选择场景"}</b>
          <span>{curHint}</span>
        </span>
        <Icon name="expand_more" />
      </button>
      {open && (
        <div className="pop" style={{ top: "calc(100% + 8px)", left: 0 }}>
          <div className="pop-scroll">
            {modes.map((m) => {
              const sel = m.mode_id === selected;
              return (
                <button
                  key={m.mode_id}
                  type="button"
                  className={`pop-item${sel ? " sel" : ""}`}
                  onClick={() => { onSelect(m.mode_id); setOpen(false); }}
                >
                  <span className="pi-ico"><Icon name={sceneIcon(m.mode_id)} /></span>
                  <span className="pt"><b>{m.label}</b><span>{m.hint}</span></span>
                  {sel && <Icon name="check" className="check" />}
                </button>
              );
            })}
          </div>
          <button type="button" className="pop-item" onClick={() => { onManage(); setOpen(false); }}
            style={{ borderTop: "1px solid var(--divider)", marginTop: 4, paddingTop: 11 }}>
            <span className="pi-ico"><Icon name="settings" /></span>
            <span className="pt"><b>管理场景 / 顾问团</b><span>编辑顾问、自定义场景…</span></span>
          </button>
        </div>
      )}
    </div>
  );
}
