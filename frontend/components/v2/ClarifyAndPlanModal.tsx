"use client";

import { useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type ProbeResp = {
  clarify: boolean;
  reason: string;
  session_id?: string;
  questions?: string[];
};

export type Plan = {
  mode: "single_opus" | "single_dept" | "multi_dept_parallel" | "multi_dept_debate";
  depts: number;
  rounds: number;
  est_seconds: number;
  est_cost_yuan: number;
};

type Props = {
  backendUrl: string;
  task: string;
  modeId: string;
  open: boolean;
  onCancel: () => void;
  onConfirm: (finalTask: string, plan: Plan) => void;
};

const backdrop: CSSProperties = {
  position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
  background: "var(--overlay)", zIndex: 300,
  display: "flex", alignItems: "center", justifyContent: "center",
};

const box: CSSProperties = {
  width: "92vw", maxWidth: 620, maxHeight: "85vh", overflow: "auto",
  background: "var(--bg-card)", borderRadius: 12, padding: 18,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  display: "flex", flexDirection: "column", gap: 14,
};

const stepHeader: CSSProperties = {
  fontSize: 13, fontWeight: 600, opacity: 0.85,
};

const inputStyle: CSSProperties = {
  width: "100%", padding: "6px 10px", fontSize: 13,
  background: "var(--bg-subtle)", color: "inherit",
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  borderRadius: 6,
};

const btn = (primary: boolean): CSSProperties => ({
  padding: "6px 14px", fontSize: 12, borderRadius: 6, cursor: "pointer",
  borderWidth: 1, borderStyle: "solid",
  borderColor: primary ? "var(--accent)" : "var(--border)",
  background: primary ? "var(--accent-bg)" : "var(--bg-subtle)",
  color: "inherit", fontWeight: primary ? 600 : 400,
});

const planCard = (active: boolean): CSSProperties => ({
  padding: "10px 12px", borderRadius: 8, cursor: "pointer",
  borderWidth: 1, borderStyle: "solid",
  borderColor: active ? "var(--accent)" : "var(--border)",
  background: active ? "var(--accent-bg)" : "var(--bg-subtle)",
  display: "flex", flexDirection: "column", gap: 4,
});

function deriveDefaultPlan(task: string): Plan {
  const len = task.length;
  if (len < 60) {
    return { mode: "single_opus", depts: 0, rounds: 0, est_seconds: 8, est_cost_yuan: 0.3 };
  }
  if (len < 200) {
    return { mode: "multi_dept_parallel", depts: 4, rounds: 1, est_seconds: 30, est_cost_yuan: 0.8 };
  }
  return { mode: "multi_dept_debate", depts: 6, rounds: 2, est_seconds: 60, est_cost_yuan: 2.5 };
}

const PRESETS: { id: Plan["mode"]; label: string; desc: string; mk: () => Plan }[] = [
  { id: "single_opus", label: "⚡ 极速 (Opus 直出)", desc: "不开部门, 直接 CEO Opus; 最快最便宜",
    mk: () => ({ mode: "single_opus", depts: 0, rounds: 0, est_seconds: 8, est_cost_yuan: 0.3 }) },
  { id: "single_dept", label: "🎯 单部门精修", desc: "选 1 个最相关部门深入回答, 不开会; 适合垂直问题",
    mk: () => ({ mode: "single_dept", depts: 1, rounds: 1, est_seconds: 12, est_cost_yuan: 0.5 }) },
  { id: "multi_dept_parallel", label: "🐝 多部门并行 (默认)", desc: "4-6 部门同时给意见, CEO 综合; 性价比最好",
    mk: () => ({ mode: "multi_dept_parallel", depts: 5, rounds: 1, est_seconds: 30, est_cost_yuan: 1.2 }) },
  { id: "multi_dept_debate", label: "🔥 多部门辩论 (复杂)", desc: "部门间多轮辩论 + 红队挑刺; 慢但最严谨",
    mk: () => ({ mode: "multi_dept_debate", depts: 6, rounds: 2, est_seconds: 65, est_cost_yuan: 2.8 }) },
];

export function ClarifyAndPlanModal(props: Props) {
  const { backendUrl, task, open, onCancel, onConfirm } = props;
  const [step, setStep] = useState<"probe" | "clarify" | "plan" | "loading">("loading");
  const [error, setError] = useState("");
  const [probeData, setProbeData] = useState<ProbeResp | null>(null);
  const [answers, setAnswers] = useState<string[]>([]);
  const [finalTask, setFinalTask] = useState(task);
  const [plan, setPlan] = useState<Plan>(() => deriveDefaultPlan(task));

  useEffect(() => {
    if (!open) return;
    setStep("loading");
    setError("");
    setFinalTask(task);
    setAnswers([]);
    setPlan(deriveDefaultPlan(task));
    (async () => {
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/intent/probe`,
          { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ task }) },
          TIMEOUT_MS.decisionStart,
        );
        const j = (await res.json()) as ProbeResp;
        setProbeData(j);
        if (j.clarify && j.questions && j.questions.length > 0) {
          setAnswers(Array(j.questions.length).fill(""));
          setStep("clarify");
        } else {
          setStep("plan");
        }
      } catch (e) {
        setError(`澄清探测失败: ${(e as Error).message}`);
        setStep("plan");
      }
    })();
  }, [open, backendUrl, task]);

  const resolveAndProceed = async () => {
    if (!probeData?.session_id) {
      setStep("plan"); return;
    }
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/intent/resolve`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: probeData.session_id, answers }) },
        TIMEOUT_MS.default,
      );
      const j = await res.json();
      setFinalTask(j.task_final || task);
      setStep("plan");
    } catch (e) {
      setError(`澄清提交失败: ${(e as Error).message}`);
      setStep("plan");
    }
  };

  if (!open) return null;

  return (
    <div style={backdrop} onClick={onCancel}>
      <div style={box} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>
          {step === "clarify" ? "🤔 先澄清几个问题" : "📋 选择决策方式"}
        </div>

        {error && <div style={{ color: "#f44336", fontSize: 12 }}>⚠ {error}</div>}

        {step === "loading" && (
          <div style={{ padding: 30, textAlign: "center", opacity: 0.55 }}>
            正在分析任务意图...
          </div>
        )}

        {step === "clarify" && probeData?.questions && (
          <>
            <div style={{ fontSize: 11, opacity: 0.55 }}>{probeData.reason}</div>
            {probeData.questions.map((q, i) => (
              <div key={i} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={stepHeader}>Q{i + 1}. {q}</div>
                <input
                  style={inputStyle}
                  placeholder="(可留空跳过这条)"
                  value={answers[i] || ""}
                  onChange={(e) => {
                    const a = [...answers]; a[i] = e.target.value; setAnswers(a);
                  }}
                />
              </div>
            ))}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 6 }}>
              <button type="button" style={btn(false)} onClick={() => setStep("plan")}>跳过澄清</button>
              <button type="button" style={btn(true)} onClick={resolveAndProceed}>提交答案 →</button>
            </div>
          </>
        )}

        {step === "plan" && (
          <>
            <div style={{ fontSize: 11, opacity: 0.55 }}>
              选一档决策方式 (建议: {plan.mode}). 可点选切换:
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {PRESETS.map((p) => (
                <div key={p.id} style={planCard(plan.mode === p.id)} onClick={() => setPlan(p.mk())}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{p.label}</div>
                  <div style={{ fontSize: 11, opacity: 0.65 }}>{p.desc}</div>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 11, opacity: 0.55, padding: "6px 4px" }}>
              当前方案: <b>{plan.depts}</b> 个部门 · <b>{plan.rounds}</b> 轮辩论 ·
              预估 <b>{plan.est_seconds}s</b> / <b>¥{plan.est_cost_yuan}</b>
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button type="button" style={btn(false)} onClick={onCancel}>取消</button>
              <button type="button" style={btn(true)} onClick={() => onConfirm(finalTask, plan)}>
                确定 ▶ 开跑
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
