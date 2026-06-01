"use client";

/** v7 W4 自定义场景向导: 分步问答 → AI 草拟部门 → 确认落地为新场景. */

import { useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Dept = { id: string; label: string };
type Draft = {
  mode_id: string; label: string; ceo_title: string;
  scenario_description: string; departments: Dept[]; llm_error?: string;
};

type Props = {
  backendUrl: string;
  open: boolean;
  onClose: () => void;
  onCreated?: (modeId: string) => void;
};

// 按大类分组的领域种子 (~50): 先选大类, 再选具体领域; 也可直接手输.
const DOMAIN_GROUPS: { cat: string; items: string[] }[] = [
  { cat: "健康医疗", items: ["中医调理", "慢病管理", "心理疏导", "育儿喂养", "老人照护", "口腔护理", "皮肤护理"] },
  { cat: "饮食运动", items: ["健身减脂", "增肌训练", "减重饮食", "素食营养", "跑步马拉松"] },
  { cat: "家庭生活", items: ["装修设计", "收纳整理", "家电选购", "宠物养护", "园艺种植", "二手车评估"] },
  { cat: "住房置业", items: ["租房买房", "民宿运营", "房产投资", "物业纠纷"] },
  { cat: "财务理财", items: ["理财规划", "保险配置", "个税筹划", "债务规划", "退休养老"] },
  { cat: "职业发展", items: ["求职面试", "简历优化", "职场晋升", "转行规划", "谈薪沟通"] },
  { cat: "创业经营", items: ["副业创业", "电商运营", "自媒体", "门店经营", "私域增长"] },
  { cat: "法律维权", items: ["劳动纠纷", "合同审查", "消费维权", "婚姻家事", "知识产权"] },
  { cat: "教育学习", items: ["亲子教育", "升学规划", "语言学习", "考研考证", "兴趣培养"] },
  { cat: "情感关系", items: ["恋爱沟通", "婚姻关系", "人际社交", "婚礼策划"] },
  { cat: "旅行休闲", items: ["自由行规划", "亲子游", "出境游", "周边游"] },
  { cat: "兴趣爱好", items: ["摄影入门", "乐器学习", "咖啡品鉴", "收藏鉴赏"] },
];

const backdrop: CSSProperties = {
  position: "fixed", inset: 0, background: "var(--overlay)", zIndex: 320,
  display: "flex", alignItems: "center", justifyContent: "center",
};
const box: CSSProperties = {
  width: "min(560px, 94vw)", maxHeight: "88vh", overflow: "auto",
  background: "var(--bg-card)", color: "var(--text)", borderRadius: 12, padding: 20,
  border: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 14,
};
const inp: CSSProperties = {
  width: "100%", padding: "8px 10px", fontSize: 13, borderRadius: 6,
  border: "1px solid var(--border)", background: "var(--bg-subtle)", color: "var(--text)",
};
const btn = (primary: boolean): CSSProperties => ({
  padding: "8px 16px", fontSize: 13, fontWeight: 600, borderRadius: 8, cursor: "pointer",
  border: primary ? "1px solid var(--accent)" : "1px solid var(--border)",
  background: primary ? "var(--accent)" : "var(--bg-subtle)",
  color: primary ? "#000" : "var(--text)",
});
const chip = (active: boolean): CSSProperties => ({
  padding: "5px 11px", fontSize: 12, borderRadius: 16, cursor: "pointer",
  border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
  background: active ? "var(--accent-bg)" : "transparent", color: "var(--text)",
});

export function ScenarioWizard({ backendUrl, open, onClose, onCreated }: Props) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [domain, setDomain] = useState("");
  const [examples, setExamples] = useState("");
  const [angles, setAngles] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);

  if (!open) return null;

  const reset = () => { setStep(1); setDomain(""); setExamples(""); setAngles(""); setDraft(null); setError(null); };
  const close = () => { reset(); onClose(); };

  const doDraft = async () => {
    if (!domain.trim()) { setError("先填你想咨询的领域"); return; }
    setLoading(true); setError(null);
    try {
      const res = await fetchWithTimeout(`${backendUrl}/api/wizard/draft`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ domain, examples, angles_hint: angles }) },
        TIMEOUT_MS.decisionStart);
      if (!res.ok) throw new Error(`draft ${res.status}`);
      setDraft(await res.json() as Draft);
      setStep(3);
    } catch (e) { setError(`AI 草拟失败: ${(e as Error).message}`); }
    finally { setLoading(false); }
  };

  const updateDept = (i: number, field: "id" | "label", v: string) => {
    if (!draft) return;
    setDraft({ ...draft, departments: draft.departments.map((d, idx) => idx === i ? { ...d, [field]: v } : d) });
  };
  const removeDept = (i: number) => {
    if (!draft) return;
    setDraft({ ...draft, departments: draft.departments.filter((_, idx) => idx !== i) });
  };
  const addDept = () => {
    if (!draft) return;
    setDraft({ ...draft, departments: [...draft.departments, { id: `dept_${draft.departments.length + 1}`, label: "新部门" }] });
  };

  const doCreate = async () => {
    if (!draft) return;
    setLoading(true); setError(null);
    try {
      const res = await fetchWithTimeout(`${backendUrl}/api/wizard/create`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode_id: draft.mode_id, label: draft.label,
            scenario_description: draft.scenario_description,
            departments: draft.departments,
          }) },
        TIMEOUT_MS.teamGenerate ?? TIMEOUT_MS.decisionStart);
      if (!res.ok) { const t = await res.text(); throw new Error(`${res.status}: ${t.slice(0, 120)}`); }
      const j = await res.json();
      onCreated?.(j.mode_id);
      close();
    } catch (e) { setError(`创建失败: ${(e as Error).message}`); }
    finally { setLoading(false); }
  };

  return (
    <div style={backdrop} onClick={close}>
      <div style={box} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontSize: 16, fontWeight: 700 }}>✨ 自定义场景向导 ({step}/3)</div>
          <button type="button" onClick={close} style={{ ...btn(false), padding: "4px 10px" }}>✕</button>
        </div>

        {step === 1 && (
          <>
            <div style={{ fontSize: 13, fontWeight: 600 }}>① 你想咨询什么领域?</div>
            <div style={{ fontSize: 12, opacity: 0.7 }}>从下面挑一个，或直接手输你自己的领域：</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, maxHeight: "44vh", overflowY: "auto", paddingRight: 4 }}>
              {DOMAIN_GROUPS.map((g) => (
                <div key={g.cat}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-faint, var(--text))", opacity: 0.65, marginBottom: 5 }}>{g.cat}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {g.items.map((d) => (
                      <span key={d} style={chip(domain === d)} onClick={() => setDomain(d)}>{d}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <input style={inp} placeholder="或自己输入 (如: 二手车评估 / 民宿运营)"
              value={domain} onChange={(e) => setDomain(e.target.value)} />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button type="button" style={btn(true)} disabled={!domain.trim()} onClick={() => setStep(2)}>下一步 →</button>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <div style={{ fontSize: 13, fontWeight: 600 }}>② 帮 AI 更懂你 (可跳过)</div>
            <div style={{ fontSize: 12, opacity: 0.7 }}>典型问题举例:</div>
            <textarea style={{ ...inp, minHeight: 60, resize: "vertical" }}
              placeholder="如: 这套二手房值不值这个价? 合同有没有坑?"
              value={examples} onChange={(e) => setExamples(e.target.value)} />
            <div style={{ fontSize: 12, opacity: 0.7 }}>希望从哪些角度分析:</div>
            <input style={inp} placeholder="如: 法律风险 / 性价比 / 长期价值"
              value={angles} onChange={(e) => setAngles(e.target.value)} />
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <button type="button" style={btn(false)} onClick={() => setStep(1)}>← 返回</button>
              <button type="button" style={btn(true)} disabled={loading} onClick={doDraft}>
                {loading ? "🤔 AI 草拟中..." : "🪄 让 AI 草拟顾问团 →"}
              </button>
            </div>
          </>
        )}

        {step === 3 && draft && (
          <>
            <div style={{ fontSize: 13, fontWeight: 600 }}>③ 确认 / 微调 (可改名删增)</div>
            <input style={inp} value={draft.label}
              onChange={(e) => setDraft({ ...draft, label: e.target.value })} placeholder="场景名" />
            <input style={inp} value={draft.scenario_description}
              onChange={(e) => setDraft({ ...draft, scenario_description: e.target.value })} placeholder="一句话说明" />
            <div style={{ fontSize: 12, opacity: 0.7 }}>顾问团 ({draft.departments.length} 个角色):</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {draft.departments.map((d, i) => (
                <div key={i} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  <input style={{ ...inp, flex: "0 0 130px" }} value={d.id}
                    onChange={(e) => updateDept(i, "id", e.target.value)} placeholder="英文id" />
                  <input style={{ ...inp, flex: 1 }} value={d.label}
                    onChange={(e) => updateDept(i, "label", e.target.value)} placeholder="中文角色名" />
                  <button type="button" style={{ ...btn(false), padding: "4px 8px" }} onClick={() => removeDept(i)}>✕</button>
                </div>
              ))}
              <button type="button" style={{ ...btn(false), alignSelf: "flex-start" }} onClick={addDept}>+ 加角色</button>
            </div>
            <div style={{ fontSize: 11, opacity: 0.6 }}>
              点&quot;创建&quot;后 AI 会用便宜模型给每个角色配人设 (约 30 秒); 不满意可在场景页&quot;重生整场&quot;.
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <button type="button" style={btn(false)} onClick={() => setStep(2)}>← 重来</button>
              <button type="button" style={btn(true)} disabled={loading || draft.departments.length === 0} onClick={doCreate}>
                {loading ? "⏳ 创建中 (配人设)..." : "✅ 创建场景"}
              </button>
            </div>
          </>
        )}

        {error && <div style={{ color: "var(--bad)", fontSize: 12 }}>⚠ {error}</div>}
      </div>
    </div>
  );
}
