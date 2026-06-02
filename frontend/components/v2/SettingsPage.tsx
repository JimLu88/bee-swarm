"use client";

/** v7 设置整页 (Jim Clear / iOS 风) — 日常设置项.
 *  「并存」: 日常项在此整页; MCP/开发模式/技术 等高级项仍由 SettingsDrawer 抽屉承载 (onOpenAdvanced)。
 *  只换皮 + 绑定现有状态/回调, 不动决策链路。通知偏好持久化到 localStorage (SSR 安全: useEffect 读)。 */

import { useEffect, useState } from "react";
import { Icon } from "./Icon";

type ThemePref = "light" | "dark" | "system";
type Tier = "A" | "B" | "C";

type Props = {
  onBack: () => void;
  theme: ThemePref;
  onSetTheme: (t: ThemePref) => void;
  tier: Tier;
  onSetTier: (t: Tier) => void;
  effort: number; // 1..4 默认努力程度
  onSetEffort: (n: number) => void;
  sceneLabel: string;
  onOpenScenario: () => void;
  onOpenAdvanced: () => void;
  memoryOn?: boolean;
  onToggleMemory?: (v: boolean) => void;
  onClearSessions?: () => void;
  version?: string;
};

const THEMES: { v: ThemePref; label: string }[] = [
  { v: "light", label: "浅色" }, { v: "dark", label: "深色" }, { v: "system", label: "系统" },
];
const EFFORTS = [{ n: 1, label: "简单" }, { n: 2, label: "一般" }, { n: 3, label: "深入" }, { n: 4, label: "全力" }];
const TIERS: { v: Tier; label: string; hint: string }[] = [
  { v: "A", label: "标准", hint: "便宜快速" },
  { v: "B", label: "高档", hint: "均衡好用" },
  { v: "C", label: "旗舰", hint: "最强推理" },
];
const NOTIF_KEY = "h-semas:notif";

export function SettingsPage(props: Props) {
  const { onBack, theme, onSetTheme, tier, onSetTier, effort, onSetEffort,
    sceneLabel, onOpenScenario, onOpenAdvanced,
    onClearSessions, version = "v7" } = props;

  // 通知偏好 (本地持久化; SSR 安全)
  const [notif, setNotif] = useState({ done: true, risk: true, weekly: false });
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(NOTIF_KEY);
      if (raw) setNotif((p) => ({ ...p, ...JSON.parse(raw) }));
    } catch { /* ignore */ }
  }, []);
  const setNotifKey = (k: "done" | "risk" | "weekly", v: boolean) => {
    const next = { ...notif, [k]: v };
    setNotif(next);
    try { window.localStorage.setItem(NOTIF_KEY, JSON.stringify(next)); } catch { /* ignore */ }
  };

  // 记忆历史偏好 (本地持久化; 真实存储, 后端可读 h-semas:memoryOn)
  const [memOn, setMemOn] = useState(true);
  useEffect(() => {
    try { const v = window.localStorage.getItem("h-semas:memoryOn"); if (v != null) setMemOn(v !== "0"); } catch { /* ignore */ }
  }, []);
  const toggleMem = (v: boolean) => {
    setMemOn(v);
    try { window.localStorage.setItem("h-semas:memoryOn", v ? "1" : "0"); } catch { /* ignore */ }
  };

  const Seg = <T,>({ opts, value, onPick }: { opts: { v: T; label: string }[]; value: T; onPick: (v: T) => void }) => (
    <div className="seg">
      {opts.map((o) => (
        <button key={String(o.v)} type="button" className={value === o.v ? "on" : ""} onClick={() => onPick(o.v)}>{o.label}</button>
      ))}
    </div>
  );
  const Switch = ({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) => (
    <button type="button" className={`switch${on ? " on" : ""}`} aria-pressed={on} aria-label="开关" onClick={() => onChange(!on)}><i /></button>
  );

  return (
    <div className="scroll app-scroll">
      <div className="page">
        <div className="page-head">
          <button type="button" className="page-back" onClick={onBack} title="返回" aria-label="返回"><Icon name="arrow_back" /></button>
          <div>
            <div className="page-title">设置</div>
            <div className="page-sub">外观、顾问与讨论、脑子档位、隐私 —— 决策逻辑不变,只调偏好</div>
          </div>
        </div>

        {/* 外观 */}
        <div className="set-group">
          <div className="set-group-h"><Icon name="palette" /> 外观</div>
          <div className="set-card">
            <div className="set-row">
              <span className="set-ico"><Icon name="dark_mode" /></span>
              <div className="stx"><b>主题</b><span>浅色 / 深色 / 跟随系统</span></div>
              <Seg opts={THEMES} value={theme} onPick={onSetTheme} />
            </div>
          </div>
        </div>

        {/* 顾问与讨论 */}
        <div className="set-group">
          <div className="set-group-h"><Icon name="groups" /> 顾问与讨论</div>
          <div className="set-card">
            <div className="set-row nav" onClick={onOpenScenario}>
              <span className="set-ico"><Icon name="grid_view" /></span>
              <div className="stx"><b>默认场景</b><span>换一套专科顾问团</span></div>
              <span className="set-rowval">{sceneLabel}<Icon name="chevron_right" /></span>
            </div>
            <div className="set-row">
              <span className="set-ico"><Icon name="bolt" /></span>
              <div className="stx"><b>默认努力程度</b><span>越深入,越多顾问并行多轮讨论</span></div>
              <Seg opts={EFFORTS.map((e) => ({ v: e.n, label: e.label }))} value={effort} onPick={onSetEffort} />
            </div>
          </div>
        </div>

        {/* 脑子档位 */}
        <div className="set-group">
          <div className="set-group-h"><Icon name="memory" /> 脑子档位</div>
          <div className="tiers">
            {TIERS.map((t) => (
              <button key={t.v} type="button" className={`tier${tier === t.v ? " on" : ""}`} onClick={() => onSetTier(t.v)}>
                <b>{t.label}</b><span>{t.hint}</span>
              </button>
            ))}
          </div>
        </div>

        {/* 通知 */}
        <div className="set-group">
          <div className="set-group-h"><Icon name="notifications" /> 通知</div>
          <div className="set-card">
            <div className="set-row">
              <span className="set-ico"><Icon name="task_alt" /></span>
              <div className="stx"><b>咨询完成提醒</b></div>
              <Switch on={notif.done} onChange={(v) => setNotifKey("done", v)} />
            </div>
            <div className="set-row">
              <span className="set-ico"><Icon name="gpp_maybe" /></span>
              <div className="stx"><b>红队高风险提醒</b></div>
              <Switch on={notif.risk} onChange={(v) => setNotifKey("risk", v)} />
            </div>
            <div className="set-row">
              <span className="set-ico"><Icon name="calendar_month" /></span>
              <div className="stx"><b>每周回顾</b></div>
              <Switch on={notif.weekly} onChange={(v) => setNotifKey("weekly", v)} />
            </div>
          </div>
        </div>

        {/* 隐私与数据 */}
        <div className="set-group">
          <div className="set-group-h"><Icon name="lock" /> 隐私与数据</div>
          <div className="set-card">
            <div className="set-row">
              <span className="set-ico"><Icon name="history" /></span>
              <div className="stx"><b>记忆历史</b><span>关闭后不再保存新咨询到记忆库</span></div>
              <Switch on={memOn} onChange={toggleMem} />
            </div>
            {onClearSessions && (
              <div className="set-row nav" onClick={onClearSessions}>
                <span className="set-ico danger"><Icon name="delete_sweep" /></span>
                <div className="stx"><b style={{ color: "var(--danger)" }}>清除所有会话</b><span>不可恢复</span></div>
                <span className="set-rowval"><Icon name="chevron_right" /></span>
              </div>
            )}
          </div>
        </div>

        {/* 高级 (并存: 进抽屉) + 关于 */}
        <div className="set-group">
          <div className="set-group-h"><Icon name="tune" /> 高级 / 关于</div>
          <div className="set-card">
            <div className="set-row nav" onClick={onOpenAdvanced}>
              <span className="set-ico"><Icon name="construction" /></span>
              <div className="stx"><b>高级设置</b><span>场景/顾问团、🔌 工具(MCP)、🛠 开发模式、待审、技术</span></div>
              <span className="set-rowval"><Icon name="chevron_right" /></span>
            </div>
            <div className="set-row">
              <span className="set-ico"><Icon name="info" /></span>
              <div className="stx"><b>版本</b></div>
              <span className="set-rowval">{version}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
