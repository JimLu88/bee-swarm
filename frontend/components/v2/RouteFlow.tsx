"use client";

// v10 横向路线流图(方案A): 分诊官 → 部门 chip 并排 → 综合.
// 提问后自动生成, 显示调用了哪几个部门/哪些人; 可 ✕移除 / ＋加部门, 改完「重新会诊」用新阵容重跑.
import { useState } from "react";
import { Icon } from "./Icon";
import { avBg, initial } from "../../lib/scenes";
import type { DeptHeat } from "./SwarmDashboardModal";

function shortLabel(name: string): string {
  return name.split(/[\s(（]/)[0] || name;
}

type Persona = { persona_id?: string; name?: string; role?: string; dept_id?: string; model?: string };

type Props = {
  heats: DeptHeat[];
  labels: Record<string, string>;
  personas?: Persona[];
  /** 可加部门池 (mode 全部门 + 横切, 来自 deptLabels keys) */
  candidates: string[];
  /** 仅最后一轮可重跑; 非最后轮只读展示 */
  editable?: boolean;
  busy?: boolean;
  onRerun?: (depts: string[]) => void;
  /** v10 计划模式: 提问后、真跑前的"确认阵容"——无信心值, 按钮=开始会诊 */
  planMode?: boolean;
};

const ROLE_CN: Record<string, string> = { head: "主管", staff: "职员", ceo: "总顾问" };

export function RouteFlow({ heats, labels, personas = [], candidates, editable = false, busy, onRerun, planMode = false }: Props) {
  const baseDepts = heats.map((h) => h.dept);
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const [added, setAdded] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);

  // 计划模式即使无建议部门也要渲染(让用户从全部门自己点选); 仅非计划模式空了才不显示
  if (!baseDepts.length && !planMode) return null;

  const effective = [...baseDepts.filter((d) => !removed.has(d)), ...added];
  const changed = removed.size > 0 || added.length > 0;
  const nameOf = (d: string) => shortLabel(heats.find((h) => h.dept === d)?.label ?? labels[d] ?? d);
  const peopleOf = (d: string) => personas.filter((p) => p.dept_id === d);
  const addable = candidates.filter((d) => !effective.includes(d) && d !== "__ceo__");

  const toggleRemove = (d: string) => {
    if (added.includes(d)) { setAdded((a) => a.filter((x) => x !== d)); return; }
    setRemoved((s) => { const n = new Set(s); if (n.has(d)) { n.delete(d); } else { n.add(d); } return n; });
  };
  const addDept = (d: string) => { setAdded((a) => [...a, d]); setAddOpen(false); };
  const reset = () => { setRemoved(new Set()); setAdded([]); };

  // v10 计划模式: 一次性切换某部门是否参与 (平铺多选, 不用躲在下拉里)
  const togglePick = (d: string) => {
    if (effective.includes(d)) {
      if (added.includes(d)) setAdded((a) => a.filter((x) => x !== d));
      else setRemoved((s) => { const n = new Set(s); n.add(d); return n; });
    } else {
      if (removed.has(d)) setRemoved((s) => { const n = new Set(s); n.delete(d); return n; });
      else setAdded((a) => [...a, d]);
    }
  };

  // ===== 计划模式: 提问后确认阵容 — 全部门平铺成可点选的格子 =====
  if (planMode) {
    const gridDepts = Array.from(new Set([...baseDepts, ...candidates])).filter((d) => d && d !== "__ceo__");
    return (
      <div style={{
        marginTop: 4, padding: "12px 14px", borderRadius: 14,
        background: "var(--bg-subtle, rgba(127,127,127,0.06))", border: "1px solid var(--border)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
          <Icon name="groups" />
          <span style={{ fontSize: 13, fontWeight: 700 }}>选要参与的顾问</span>
          <span style={{ fontSize: 11, color: "var(--text-faint)" }}>点一下加入/移除 · 已选 {effective.length} 位</span>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {gridDepts.map((d, i) => {
            const on = effective.includes(d);
            const nm = shortLabel(labels[d] ?? d);
            return (
              <button key={d} type="button" onClick={() => togglePick(d)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  padding: "7px 12px", borderRadius: 999, cursor: "pointer", fontSize: 13,
                  border: "1px solid", borderColor: on ? "var(--accent)" : "var(--border)",
                  background: on ? "var(--accent-bg)" : "var(--bg-card)",
                  color: on ? "var(--accent)" : "var(--text)", fontWeight: on ? 600 : 400,
                }}>
                <span style={{
                  width: 20, height: 20, borderRadius: "50%", background: on ? avBg(i) : "var(--border)",
                  color: "#fff", fontSize: 10, display: "flex", alignItems: "center", justifyContent: "center",
                }}>{on ? initial(nm) : "+"}</span>
                {nm}
                {on && <Icon name="check" size={15} />}
              </button>
            );
          })}
        </div>
        <div style={{ marginTop: 12 }}>
          <button type="button" disabled={busy || effective.length === 0}
            onClick={() => onRerun?.(effective)}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 18px", borderRadius: 999,
              border: "none", background: "var(--accent)", color: "#fff", cursor: busy ? "default" : "pointer",
              fontSize: 13.5, fontWeight: 600, opacity: busy || !effective.length ? 0.6 : 1,
            }}>
            <Icon name={busy ? "progress_activity" : "play_arrow"} className={busy ? "spinning" : ""} size={18} />
            开始讨论（{effective.length} 位顾问）
          </button>
        </div>
      </div>
    );
  }

  const chips = [
    ...baseDepts.map((d) => ({ dept: d, added: false })),
    ...added.map((d) => ({ dept: d, added: true })),
  ];

  const node = (label: string, icon: string): React.ReactNode => (
    <div style={{
      flex: "0 0 auto", display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
      padding: "8px 10px", borderRadius: 10, background: "var(--bg-card)",
      border: "1px solid var(--border)", minWidth: 56,
    }}>
      <Icon name={icon} />
      <span style={{ fontSize: 11, color: "var(--text-dim)", whiteSpace: "nowrap" }}>{label}</span>
    </div>
  );

  const arrow = (
    <span style={{ flex: "0 0 auto", color: "var(--text-faint)", alignSelf: "center" }}>
      <Icon name="chevron_right" />
    </span>
  );

  return (
    <div style={{
      marginTop: 10, padding: "10px 12px", borderRadius: 12,
      background: "var(--bg-subtle, rgba(127,127,127,0.06))", border: "1px solid var(--border)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <Icon name="route" />
        <span style={{ fontSize: 12.5, fontWeight: 700 }}>{planMode ? "建议阵容" : "路线图"}</span>
        <span style={{ fontSize: 11, color: "var(--text-faint)" }}>
          {planMode
            ? `打算让这 ${effective.length} 位顾问讨论 · 可增减后开跑`
            : `分诊官调用了 ${effective.length} 个部门${editable ? " · 可增减后重新讨论" : ""}`}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "flex-start", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
        {node("分诊官", "hub")}
        {arrow}

        <div style={{ flex: "1 1 auto", display: "flex", flexWrap: "wrap", gap: 6, alignContent: "flex-start" }}>
          {chips.map(({ dept, added: isAdded }, i) => {
            const isRemoved = removed.has(dept);
            const heat = heats.find((h) => h.dept === dept);
            const conf = heat?.confidence != null ? heat.confidence : heat?.heat ?? 0;
            const pct = Math.round(Math.max(0, Math.min(1, conf)) * 100);
            const nm = nameOf(dept);
            const ppl = peopleOf(dept);
            const isOpen = expanded === dept;
            return (
              <div key={dept + i} style={{
                flex: "0 0 auto", borderRadius: 10, border: "1px solid",
                borderColor: isRemoved ? "var(--border)" : isAdded ? "var(--accent)" : "var(--border)",
                background: isRemoved ? "transparent" : "var(--bg-card)",
                opacity: isRemoved ? 0.45 : 1, maxWidth: 220,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 7px" }}>
                  <button type="button" onClick={() => setExpanded(isOpen ? null : dept)}
                    style={{
                      display: "flex", alignItems: "center", gap: 6, border: "none",
                      background: "transparent", cursor: "pointer", padding: 0, color: "var(--text)",
                    }}>
                    <span style={{
                      width: 22, height: 22, borderRadius: "50%", background: avBg(i),
                      color: "#fff", fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center",
                      textDecoration: isRemoved ? "line-through" : "none",
                    }}>{initial(nm)}</span>
                    <span style={{ fontSize: 12.5, fontWeight: 600, textDecoration: isRemoved ? "line-through" : "none" }}>{nm}</span>
                    {!isAdded && !planMode && <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{pct}%</span>}
                    {isAdded && <span style={{ fontSize: 10, color: "var(--accent)" }}>新增</span>}
                  </button>
                  {editable && (
                    <button type="button" onClick={() => toggleRemove(dept)} title={isRemoved ? "恢复" : "移除"}
                      style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--text-faint)", padding: 0, lineHeight: 1 }}>
                      <Icon name={isRemoved ? "undo" : "close"} size={15} />
                    </button>
                  )}
                </div>
                {isOpen && (
                  <div style={{ padding: "2px 8px 8px", fontSize: 11, color: "var(--text-dim)" }}>
                    {ppl.length === 0 ? (
                      <span>主管 + 职员（团队就绪后展开看名字）</span>
                    ) : (
                      ppl.map((p, j) => (
                        <div key={j} style={{ display: "flex", gap: 6, padding: "1px 0" }}>
                          <span style={{ color: "var(--accent)" }}>{ROLE_CN[p.role || ""] || p.role || "成员"}</span>
                          <span>{p.name || p.persona_id || ""}</span>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {editable && addable.length > 0 && (
            <div style={{ position: "relative", flex: "0 0 auto" }}>
              <button type="button" onClick={() => setAddOpen((v) => !v)}
                style={{
                  display: "flex", alignItems: "center", gap: 4, padding: "6px 10px",
                  borderRadius: 10, border: "1px dashed var(--border)", background: "transparent",
                  color: "var(--text-dim)", cursor: "pointer", fontSize: 12.5,
                }}>
                <Icon name="add" size={15} />加部门
              </button>
              {addOpen && (
                <>
                  <div onClick={() => setAddOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 40 }} />
                  <div style={{
                    position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 41,
                    width: 200, maxHeight: 260, overflowY: "auto", padding: 6, borderRadius: 10,
                    background: "var(--bg-card)", border: "1px solid var(--border)", boxShadow: "0 8px 28px rgba(0,0,0,0.35)",
                  }}>
                    {addable.map((d) => (
                      <button key={d} type="button" onClick={() => addDept(d)}
                        style={{
                          display: "block", width: "100%", textAlign: "left", padding: "6px 8px",
                          border: "none", background: "transparent", cursor: "pointer", fontSize: 13,
                          color: "var(--text)", borderRadius: 6,
                        }}>
                        {shortLabel(labels[d] ?? d)}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {arrow}
        {node("综合", "summarize")}
      </div>

      {editable && (planMode || changed) && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
          <button type="button" disabled={busy || effective.length === 0}
            onClick={() => onRerun?.(effective)}
            style={{
              display: "flex", alignItems: "center", gap: 5, padding: "6px 14px", borderRadius: 999,
              border: "none", background: "var(--accent)", color: "#fff", cursor: busy ? "default" : "pointer",
              fontSize: 12.5, fontWeight: 600, opacity: busy || !effective.length ? 0.6 : 1,
            }}>
            <Icon name={busy ? "progress_activity" : (planMode ? "play_arrow" : "refresh")} className={busy ? "spinning" : ""} size={16} />
            {planMode ? "开始讨论" : "重新讨论"}（{effective.length} 部门）
          </button>
          {!planMode && (
            <button type="button" onClick={reset}
              style={{ border: "none", background: "transparent", color: "var(--text-faint)", cursor: "pointer", fontSize: 12 }}>
              复原
            </button>
          )}
        </div>
      )}
    </div>
  );
}
