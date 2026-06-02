"use client";

import { useState } from "react";
import { Icon } from "./Icon";
import { BUILTIN_MODES } from "./ModePicker";
import { sceneIcon } from "../../lib/scenes";
import type { HistoryRow } from "./HistoryPanel";

type Props = {
  /** 「最近」列表 (来自 /api/memory/{mode}) */
  history: HistoryRow[];
  /** 当前选中的历史决策 id (高亮) */
  activeId?: string | null;
  onNewConsult: () => void;
  onPickHistory: (decisionId: string) => void;
  onOpenScenario: () => void;
  onOpenSwarm: () => void;
  onOpenSettings: () => void;
  onCollapse: () => void;
  /** 顶部用户行 */
  userName?: string;
  tier: "A" | "B" | "C";
  onUserClick?: () => void;
};

const TIER_LABEL: Record<"A" | "B" | "C", string> = {
  A: "高档脑子 · 旗舰",
  B: "中档脑子 · 便宜云",
  C: "本地脑子 · 离线",
};

function modeLabel(modeId?: string): string {
  if (!modeId) return "通用咨询";
  return BUILTIN_MODES.find((m) => m.mode_id === modeId)?.label ?? modeId;
}

export function Sidebar({
  history,
  activeId,
  onNewConsult,
  onPickHistory,
  onOpenScenario,
  onOpenSwarm,
  onOpenSettings,
  onCollapse,
  userName = "我",
  tier,
  onUserClick,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <aside className="rail">
      <div className="rail-inner">
        <div className="rail-head">
          <div className="brand-tile"><Icon name="diversity_3" fill /></div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="brand-name">智囊团</div>
            <div className="brand-sub">H-SEMAS · 多智能体顾问</div>
          </div>
          <button type="button" className="rail-icon-btn" onClick={onCollapse} title="收起侧栏" aria-label="收起侧栏">
            <Icon name="left_panel_close" />
          </button>
        </div>

        <button type="button" className="new-btn" onClick={onNewConsult}>
          <Icon name="add" /> 新咨询
        </button>

        <div className="rail-section">最近</div>
        <div className="rail-list app-scroll">
          {history.length === 0 && (
            <div style={{ padding: "10px 12px", font: "400 12px var(--font-sans)", color: "var(--fg-4)" }}>
              还没有咨询记录，点上面「新咨询」开始
            </div>
          )}
          {history.map((h, i) => {
            const id = h.decision_id;
            const active = !!id && id === activeId;
            return (
              <button
                key={`${id ?? "noid"}-${i}`}
                type="button"
                className={`conv${active ? " active" : ""}`}
                onClick={() => id && onPickHistory(id)}
                title={h.task ?? ""}
              >
                <span className="conv-ico"><Icon name={sceneIcon(h.mode_id ?? "")} /></span>
                <span className="conv-body">
                  <span className="conv-title">{h.task || "(无标题咨询)"}</span>
                  <span className="conv-meta">{modeLabel(h.mode_id)} · 顾问团</span>
                </span>
              </button>
            );
          })}
        </div>

        <div className="rail-foot" style={{ position: "relative" }}>
          {menuOpen && (
            <>
              {/* 点击空白处关闭 */}
              <div
                onClick={() => setMenuOpen(false)}
                style={{ position: "fixed", inset: 0, zIndex: 40 }}
              />
              <div
                role="menu"
                style={{
                  position: "absolute",
                  bottom: "calc(100% + 8px)",
                  left: 0,
                  right: 0,
                  zIndex: 41,
                  background: "var(--bg-card, #fff)",
                  border: "1px solid var(--border)",
                  borderRadius: 12,
                  boxShadow: "0 10px 36px rgba(0,0,0,0.16)",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    padding: "10px 12px",
                    borderBottom: "1px solid var(--border)",
                    font: "600 12px var(--font-sans)",
                    color: "var(--fg-3)",
                  }}
                >
                  {userName} · {TIER_LABEL[tier]}
                </div>
                <button
                  type="button"
                  className="foot-item"
                  onClick={() => { setMenuOpen(false); onOpenScenario(); }}
                >
                  <Icon name="grid_view" /> 切换场景 · 顾问团
                </button>
                <button
                  type="button"
                  className="foot-item"
                  onClick={() => { setMenuOpen(false); onOpenSwarm(); }}
                >
                  <Icon name="hub" /> 看顾问怎么协作
                </button>
                <button
                  type="button"
                  className="foot-item"
                  onClick={() => { setMenuOpen(false); onOpenSettings(); }}
                >
                  <Icon name="settings" /> 设置
                </button>
              </div>
            </>
          )}
          <button
            type="button"
            className="foot-user"
            onClick={() => setMenuOpen((o) => !o)}
            title="菜单"
            aria-expanded={menuOpen}
          >
            <div className="avatar">{userName.slice(0, 1)}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ font: "600 13px var(--font-sans)", color: "var(--fg-1)" }}>{userName}</div>
            </div>
            <Icon name={menuOpen ? "expand_more" : "expand_less"} />
          </button>
        </div>
      </div>
    </aside>
  );
}
