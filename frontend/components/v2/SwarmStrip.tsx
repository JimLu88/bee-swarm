"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "./Icon";
import { avBg, initial } from "../../lib/scenes";
import type { DeptHeat } from "./SwarmDashboardModal";

type Props = {
  heats: DeptHeat[];
  /** 决策仍在进行 */
  running: boolean;
  /** 决策已完成 (decision_done) */
  done: boolean;
  /** 并行讨论轮数 (done 标题用) */
  rounds?: number;
  /** 完成态顾问数 (优先于 heats.length) */
  advisorCount?: number;
  /** progress 0-100, 用于推断红队步骤 */
  progress?: number;
  /** 部门 id → 中文名 (来自 /api/modes department_labels), 没有则回退 dept id */
  labels?: Record<string, string>;
};

/** 中文标签取「括号前」的短名: "内科 (常见病/慢病)" → "内科" */
function shortLabel(name: string): string {
  const cut = name.split(/[\s(（]/)[0];
  return cut || name;
}

type StepDef = { text: ReactNode; done: boolean };

export function SwarmStrip({ heats, running, done, rounds = 2, advisorCount, progress = 0, labels = {} }: Props) {
  const nameOf = (h: DeptHeat): string => shortLabel(h.label ?? labels[h.dept] ?? h.dept);
  const [open, setOpen] = useState(done);
  useEffect(() => { if (done) setOpen(true); }, [done]);

  const count = advisorCount ?? heats.length;
  const allDeptsDone = heats.length > 0 && heats.every((h) => h.status === "done");

  const steps: StepDef[] = [
    { text: <><b>蜂枢</b>读题，判断需要哪些顾问</>, done: done || heats.length > 0 },
    { text: <><b>{count} 位顾问</b>并行讨论 {rounds} 轮，互相质疑收敛</>, done: done || allDeptsDone },
    { text: <><b>红队</b>对结论挑刺，标注风险</>, done: done || progress >= 90 },
    { text: <><b>蜂枢</b>综合各方，给出最终建议</>, done },
  ];

  const title: ReactNode = done ? (
    <><b>{count} 位顾问</b>已完成协作 · CEO 分诊 → 并行讨论 {rounds} 轮 → 综合</>
  ) : heats.length === 0 ? (
    "蜂枢正在分配顾问…"
  ) : (
    "顾问们正在并行讨论…"
  );

  return (
    <div className={`swarm${open ? " open" : ""}`}>
      <button type="button" className="swarm-head" onClick={() => setOpen((v) => !v)}>
        <span className={`swarm-spin${done ? " done" : ""}`}>
          <Icon name={done ? "check_circle" : "progress_activity"} className={running && !done ? "spinning" : ""} />
        </span>
        <span className="swarm-title">{title}</span>
        <Icon name="expand_more" className="swarm-chev" />
      </button>
      <div className="swarm-detail">
        <div className="steps">
          {steps.map((s, i) => (
            <div key={i} className={`step${s.done ? " done" : ""}`}>
              <span className="pip"><Icon name={s.done ? "check" : "more_horiz"} /></span>
              {s.text}
            </div>
          ))}
        </div>
        {heats.length > 0 && (
          <div className="advisors">
            {heats.map((h, i) => {
              const isDone = h.status === "done";
              const isThinking = h.status === "running";
              const cls = isThinking ? "thinking" : !isDone && h.status === "idle" ? "idle" : "";
              const conf = h.confidence != null ? h.confidence : isDone ? h.heat : 0;
              const pct = Math.round(Math.max(0, Math.min(1, conf)) * 100);
              const name = nameOf(h);
              return (
                <div key={h.dept + i} className={`adv ${cls}`}>
                  <span className="adv-av" style={{ background: avBg(i) }}>{initial(name)}</span>
                  <span className="adv-info">
                    <span className="adv-name" title={name}>{name}</span>
                    <span className="adv-bar"><i style={{ width: isDone ? pct + "%" : 0 }} /></span>
                  </span>
                  <span className="adv-state">{isDone ? pct + "%" : isThinking ? "思考中" : "待命"}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
