"use client";

/** 意图澄清弹窗(clarify-only)。
 *  发送前先 probe; 若 AI 判断有"会改变答案方向"的歧义 → 弹出结构化小问答
 *  (标签/滑杆/分段/数值/排序/快捷追问 + 末尾自由补充), 收集后把答案拼进 task,
 *  再交回上层走原有"阵容确认 → 开跑"流程。无歧义则自动放行, 不打扰。 */

import { useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

export type ClarifyQuestion = {
  id: string;
  type: "chips" | "slider" | "segmented" | "range" | "rank" | "quick" | "text";
  prompt: string;
  why?: string;
  options?: string[];
  multi?: boolean;
  min?: number;
  max?: number;
  default?: number;
  min_label?: string;
  max_label?: string;
  unit?: string;
};

type ProbeResp = {
  clarify: boolean;
  reason: string;
  session_id?: string;
  questions?: ClarifyQuestion[];
};

type Props = {
  backendUrl: string;
  task: string;
  open: boolean;
  onCancel: () => void;
  /** 澄清完成(或无需澄清/跳过)→ 回传最终 task 给上层继续跑 */
  onConfirm: (finalTask: string) => void;
};

type Val = string | number | string[];

const backdrop: CSSProperties = {
  position: "fixed", inset: 0, background: "var(--overlay)", zIndex: 300,
  display: "flex", alignItems: "center", justifyContent: "center", padding: 12,
};
const box: CSSProperties = {
  width: "92vw", maxWidth: 600, maxHeight: "86vh", overflow: "auto",
  background: "var(--bg-card)", borderRadius: 16, padding: 18,
  border: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 14,
};
const inputStyle: CSSProperties = {
  width: "100%", boxSizing: "border-box", padding: "10px 12px", fontSize: 15,
  background: "var(--bg-subtle)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: 10, outline: "none",
};
const btn = (primary: boolean): CSSProperties => ({
  padding: "9px 16px", fontSize: 14, borderRadius: 10, cursor: "pointer",
  border: "1px solid " + (primary ? "var(--accent)" : "var(--border)"),
  background: primary ? "var(--accent)" : "var(--bg-subtle)",
  color: primary ? "#fff" : "var(--text)", fontWeight: primary ? 600 : 500,
});
const pill = (active: boolean): CSSProperties => ({
  padding: "8px 14px", borderRadius: 999, fontSize: 14, cursor: "pointer",
  border: "1px solid " + (active ? "var(--accent)" : "var(--border)"),
  background: active ? "var(--accent-bg)" : "var(--bg-card)",
  color: active ? "var(--accent)" : "var(--text)", fontWeight: active ? 600 : 400,
  userSelect: "none",
});

function initVal(q: ClarifyQuestion): Val {
  if (q.type === "chips") return [];
  if (q.type === "rank") return [...(q.options || [])];
  if (q.type === "slider" || q.type === "range") return q.default ?? q.min ?? 0;
  return "";
}

function fmt(q: ClarifyQuestion, v: Val): string {
  if (q.type === "chips" || q.type === "rank") {
    const arr = (v as string[]) || [];
    if (!arr.length) return "";
    return q.type === "rank" ? arr.map((o, i) => `${i + 1}.${o}`).join(" ") : arr.join("、");
  }
  if (q.type === "slider") {
    const n = v as number;
    const lab = q.min_label || q.max_label ? ` (${q.min_label || q.min}↔${q.max_label || q.max})` : "";
    return `${n}/${q.max ?? 100}${lab}`;
  }
  if (q.type === "range") return v === "" || v == null ? "" : `${q.unit || ""}${v}`;
  return ((v as string) || "").trim();
}

export function ClarifyAndPlanModal(props: Props) {
  const { backendUrl, task, open, onCancel, onConfirm } = props;
  const [step, setStep] = useState<"loading" | "clarify">("loading");
  const [error, setError] = useState("");
  const [probeData, setProbeData] = useState<ProbeResp | null>(null);
  const [vals, setVals] = useState<Record<string, Val>>({});
  const [extra, setExtra] = useState("");

  useEffect(() => {
    if (!open) return;
    setStep("loading"); setError(""); setVals({}); setExtra("");
    (async () => {
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/intent/probe`,
          { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ task }) },
          TIMEOUT_MS.decisionStart,
        );
        const j = (await res.json()) as ProbeResp;
        if (j.clarify && j.questions && j.questions.length > 0) {
          setProbeData(j);
          const init: Record<string, Val> = {};
          j.questions.forEach((q) => { init[q.id] = initVal(q); });
          setVals(init);
          setStep("clarify");
        } else {
          onConfirm(task); // 无歧义 → 直接放行, 不打扰
        }
      } catch {
        onConfirm(task); // 探测失败 → 不挡用户, 原样继续
      }
    })();
  }, [open, backendUrl, task, onConfirm]);

  if (!open || step === "loading") {
    return open ? (
      <div style={backdrop}>
        <div style={{ ...box, alignItems: "center", color: "var(--text-dim)" }}>正在分析你的问题…</div>
      </div>
    ) : null;
  }

  const setV = (id: string, v: Val) => setVals((p) => ({ ...p, [id]: v }));
  const submit = () => {
    const qs = probeData?.questions || [];
    const answers = qs.map((q) => fmt(q, vals[q.id]));
    if (!probeData?.session_id) { onConfirm(task); return; }
    (async () => {
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/intent/resolve`,
          { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: probeData.session_id, answers, extra }) },
          TIMEOUT_MS.default,
        );
        const j = await res.json();
        onConfirm(j.task_final || task);
      } catch {
        onConfirm(task);
      }
    })();
  };

  const renderWidget = (q: ClarifyQuestion) => {
    const v = vals[q.id];
    if (q.type === "chips" || q.type === "segmented") {
      const sel = q.type === "chips" ? ((v as string[]) || []) : [];
      const single = (v as string) || "";
      return (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {(q.options || []).map((o) => {
            const on = q.type === "chips" ? sel.includes(o) : single === o;
            return (
              <span key={o} style={pill(on)} onClick={() => {
                if (q.type === "chips") setV(q.id, on ? sel.filter((x) => x !== o) : [...sel, o]);
                else setV(q.id, on ? "" : o);
              }}>{o}</span>
            );
          })}
        </div>
      );
    }
    if (q.type === "quick") {
      const cur = (v as string) || "";
      const opts = q.options || [];
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {opts.map((o) => (
              <span key={o} style={pill(cur === o)} onClick={() => setV(q.id, cur === o ? "" : o)}>{o}</span>
            ))}
          </div>
          <input style={inputStyle} placeholder="或自己补一句…"
            value={opts.includes(cur) ? "" : cur} onChange={(e) => setV(q.id, e.target.value)} />
        </div>
      );
    }
    if (q.type === "slider" || q.type === "range") {
      const n = (v as number) ?? (q.default ?? q.min ?? 0);
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <input type="range" min={q.min ?? 0} max={q.max ?? 100} value={n}
            onChange={(e) => setV(q.id, Number(e.target.value))}
            style={{ width: "100%", accentColor: "var(--accent)" }} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-dim)" }}>
            <span>{q.min_label || (q.type === "range" ? `${q.unit || ""}${q.min ?? 0}` : q.min ?? 0)}</span>
            <b style={{ color: "var(--accent)", fontSize: 14 }}>
              {q.type === "range" ? `${q.unit || ""}${n}` : `${n}/${q.max ?? 100}`}
            </b>
            <span>{q.max_label || (q.type === "range" ? `${q.unit || ""}${q.max ?? 100}` : q.max ?? 100)}</span>
          </div>
        </div>
      );
    }
    if (q.type === "rank") {
      const arr = (v as string[]) || [];
      const move = (i: number, d: number) => {
        const j = i + d;
        if (j < 0 || j >= arr.length) return;
        const a = [...arr]; const t = a[i]; a[i] = a[j]; a[j] = t; setV(q.id, a);
      };
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {arr.map((o, i) => (
            <div key={o} style={{ display: "flex", alignItems: "center", gap: 8,
              padding: "8px 10px", borderRadius: 10, background: "var(--bg-subtle)", border: "1px solid var(--border)" }}>
              <b style={{ color: "var(--accent)", width: 18 }}>{i + 1}</b>
              <span style={{ flex: 1, color: "var(--text)" }}>{o}</span>
              <button type="button" style={btn(false)} onClick={() => move(i, -1)} disabled={i === 0}>↑</button>
              <button type="button" style={btn(false)} onClick={() => move(i, 1)} disabled={i === arr.length - 1}>↓</button>
            </div>
          ))}
        </div>
      );
    }
    return (
      <input style={inputStyle} placeholder="(可留空跳过这条)"
        value={(v as string) || ""} onChange={(e) => setV(q.id, e.target.value)} />
    );
  };

  return (
    <div style={backdrop} onClick={onCancel}>
      <div style={box} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text)" }}>🤔 先帮我了解几点(点选即可)</div>
        {error && <div style={{ color: "var(--danger)", fontSize: 13 }}>⚠ {error}</div>}

        {(probeData?.questions || []).map((q, i) => (
          <div key={q.id} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 14.5, fontWeight: 600, color: "var(--text)" }}>
              {i + 1}. {q.prompt}
              {q.why ? <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-faint)" }}>　({q.why})</span> : null}
            </div>
            {renderWidget(q)}
          </div>
        ))}

        <div style={{ display: "flex", flexDirection: "column", gap: 8, borderTop: "1px solid var(--divider)", paddingTop: 12 }}>
          <div style={{ fontSize: 14.5, fontWeight: 600, color: "var(--text)" }}>
            还有什么补充想告诉顾问的?<span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-faint)" }}>　(选填)</span>
          </div>
          <input style={inputStyle} placeholder="例如:他最近迷上钓鱼 / 不要太贵 / 想要有面子…"
            value={extra} onChange={(e) => setExtra(e.target.value)} />
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
          <button type="button" style={btn(false)} onClick={() => onConfirm(task)}>跳过</button>
          <button type="button" style={btn(true)} onClick={submit}>提交 →</button>
        </div>
      </div>
    </div>
  );
}
