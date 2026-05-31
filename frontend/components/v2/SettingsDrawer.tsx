"use client";

/** v6-R 设置抽屉 — 把"进阶+技术"内容都搬这里, 主页只剩"日常". */

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { SettingsPanel } from "./SettingsPanel";
import { ReviewPanel } from "./ReviewPanel";
import { BackupConfigPanel } from "./BackupConfigPanel";
import { UpgradeLogPanel } from "./UpgradeLogPanel";
import { ThinkingFrameworksPanel } from "./advanced/ThinkingFrameworksPanel";
import { GeneEditor } from "./advanced/GeneEditor";
import { ScenarioYamlAuthor } from "./advanced/ScenarioYamlAuthor";
import { SandboxPanel } from "./engineer/SandboxPanel";
import { ShadowABPanel } from "./engineer/ShadowABPanel";
import { CoordinatorPanel } from "./engineer/CoordinatorPanel";
import { LogsPanel } from "./LogsPanel";
import { ModePicker, BUILTIN_MODES } from "./ModePicker";
import { TeamPanel } from "./TeamPanel";
import { ModelBadgeBar } from "./ModelBadgeBar";
import { ScenarioWizard } from "./ScenarioWizard";

type Tab = "scenario" | "ai" | "memory" | "advanced" | "tech";

const TAB_LS_KEY = "h-semas:settings:tab";
const DETAILS_LS_KEY = "h-semas:settings:details";

type DetailsState = { think: boolean; gene: boolean; scenario: boolean };

function loadDetails(): DetailsState {
  if (typeof window === "undefined") return { think: false, gene: false, scenario: false };
  try {
    const raw = window.localStorage.getItem(DETAILS_LS_KEY);
    if (!raw) return { think: false, gene: false, scenario: false };
    return JSON.parse(raw) as DetailsState;
  } catch { return { think: false, gene: false, scenario: false }; }
}

function saveDetails(s: DetailsState) {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(DETAILS_LS_KEY, JSON.stringify(s)); } catch { /* ignore */ }
}

type Props = {
  open: boolean;
  onClose: () => void;
  backendUrl: string;
  frameworks: string[];
  aiFrameworks: string[];
  onToggleFramework: (id: string) => void;
  /** v6-S/C 父级要求强制打开某个 tab (如点"复习"→memory) */
  initialTab?: Tab;
  /** v7 场景 tab: 当前场景 + 切换回调 */
  mode?: string;
  onSelectMode?: (m: string) => void;
};

const backdrop: CSSProperties = {
  position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
  background: "var(--overlay)", zIndex: 280,
};

const drawer: CSSProperties = {
  position: "fixed", top: 0, right: 0, bottom: 0,
  width: "min(960px, 96vw)", background: "var(--bg)", color: "var(--text)",
  borderLeftWidth: 1, borderLeftStyle: "solid",
  borderLeftColor: "var(--border-strong)",
  zIndex: 290, display: "flex", flexDirection: "column",
  boxShadow: "-10px 0 40px rgba(0,0,0,0.6)",
};

const headerBar: CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "space-between",
  padding: "14px 18px",
  borderBottomWidth: 1, borderBottomStyle: "solid",
  borderBottomColor: "var(--border)",
  background: "var(--bg-card)",
};

const tabBar: CSSProperties = {
  display: "flex", gap: 4, padding: "8px 14px",
  borderBottomWidth: 1, borderBottomStyle: "solid",
  borderBottomColor: "var(--border)",
  background: "var(--bg-elev)",
};

const tabBtn = (active: boolean): CSSProperties => ({
  padding: "6px 14px", fontSize: 13, cursor: "pointer", borderRadius: 6,
  borderWidth: 1, borderStyle: "solid",
  borderColor: active ? "var(--accent)" : "var(--border)",
  background: active ? "var(--accent-bg)" : "var(--bg-subtle)",
  color: active ? "var(--accent)" : "#e0e0e0",
  fontWeight: active ? 700 : 500,
});

const body: CSSProperties = {
  flex: 1, overflowY: "auto", padding: 18,
  display: "flex", flexDirection: "column", gap: 12,
};

const sectionTitle: CSSProperties = {
  fontSize: 12, fontWeight: 700, color: "var(--info)",
  letterSpacing: 0.5, textTransform: "uppercase",
  marginTop: 4, marginBottom: -4,
};

function Wrap({ children }: { children: ReactNode }) {
  return <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>{children}</div>;
}

export function SettingsDrawer(props: Props) {
  const { open, onClose, backendUrl, frameworks, aiFrameworks, onToggleFramework, initialTab, mode, onSelectMode } = props;
  const [tab, setTab] = useState<Tab>(() => {
    if (typeof window === "undefined") return "scenario";
    const saved = window.localStorage.getItem(TAB_LS_KEY) as Tab | null;
    return saved && ["scenario", "ai", "memory", "advanced", "tech"].includes(saved) ? saved : "scenario";
  });
  const [details, setDetails] = useState<DetailsState>(loadDetails);
  const [wizardOpen, setWizardOpen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try { window.localStorage.setItem(TAB_LS_KEY, tab); } catch { /* ignore */ }
  }, [tab]);

  // v6-S/C 父级请求强制切 tab (每次 open=true 或 initialTab 变化时生效)
  useEffect(() => {
    if (open && initialTab) setTab(initialTab);
  }, [open, initialTab]);

  const onToggleDetails = (key: keyof DetailsState) => (e: React.SyntheticEvent<HTMLDetailsElement>) => {
    const next = { ...details, [key]: (e.currentTarget as HTMLDetailsElement).open };
    setDetails(next);
    saveDetails(next);
  };

  if (!open) return null;

  return (
    <>
      <div style={backdrop} onClick={onClose} />
      <div style={drawer} onClick={(e) => e.stopPropagation()}>
        <div style={headerBar}>
          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text)" }}>
            ⚙️ 设置 & 工具
          </div>
          <button type="button" onClick={onClose} style={{
            padding: "5px 14px", fontSize: 12, borderRadius: 4, cursor: "pointer",
            borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-strong)",
            background: "var(--bg-card)", color: "var(--text)",
          }}>✕ 关闭</button>
        </div>

        <div style={tabBar}>
          <button type="button" style={tabBtn(tab === "scenario")} onClick={() => setTab("scenario")}>
            🎬 场景
          </button>
          <button type="button" style={tabBtn(tab === "ai")} onClick={() => setTab("ai")}>
            🧠 AI 大脑
          </button>
          <button type="button" style={tabBtn(tab === "memory")} onClick={() => setTab("memory")}>
            💾 记忆 & 备份
          </button>
          <button type="button" style={tabBtn(tab === "advanced")} onClick={() => setTab("advanced")}>
            🛠️ 高级 (人工干预)
          </button>
          <button type="button" style={tabBtn(tab === "tech")} onClick={() => setTab("tech")}>
            🔧 技术 (开发者)
          </button>
        </div>

        <div style={body}>
          {tab === "scenario" && (
            <Wrap>
              <div style={sectionTitle}>选场景 = 换一套专科顾问团; 下方可看/重生/编辑团队</div>
              {onSelectMode && (
                <ModePicker selected={mode || ""} onSelect={onSelectMode}
                  onOpenCustom={() => setWizardOpen(true)} />
              )}
              <button type="button" onClick={() => setWizardOpen(true)}
                style={{
                  alignSelf: "flex-start", padding: "8px 14px", fontSize: 13, fontWeight: 600,
                  borderRadius: 8, cursor: "pointer", border: "1px solid var(--accent)",
                  background: "var(--accent-bg)", color: "var(--text)",
                }}>
                ✨ 自定义新场景 (向导)
              </button>
              {mode && (
                <>
                  <ModelBadgeBar backendUrl={backendUrl} modeId={mode} />
                  <TeamPanel mode={mode}
                    modeLabel={BUILTIN_MODES.find((m) => m.mode_id === mode)?.label}
                    backendUrl={backendUrl} />
                </>
              )}
              <ScenarioWizard backendUrl={backendUrl} open={wizardOpen}
                onClose={() => setWizardOpen(false)}
                onCreated={(mid) => { onSelectMode?.(mid); }} />
            </Wrap>
          )}
          {tab === "ai" && (
            <Wrap>
              <div style={sectionTitle}>AI 模型配置 (网关 / Key / 备用链 / 自更新)</div>
              <SettingsPanel />
            </Wrap>
          )}

          {tab === "memory" && (
            <Wrap>
              <div style={sectionTitle}>v3-F 复习闸 & v3-E 5 池备份</div>
              <ReviewPanel backendUrl={backendUrl} />
              <BackupConfigPanel backendUrl={backendUrl} />
              <UpgradeLogPanel backendUrl={backendUrl} />
            </Wrap>
          )}

          {tab === "advanced" && (
            <Wrap>
              <div style={sectionTitle}>3 个"想干预 AI 时才用"的工具</div>

              <details open={details.think} onToggle={onToggleDetails("think")} style={{
                padding: 12, borderRadius: 8,
                background: "var(--bg-subtle)",
                borderWidth: 1, borderStyle: "solid",
                borderColor: "var(--border)",
              }}>
                <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600, color: "var(--info)" }}>
                  🧠 思考方法 (默认 AI 自己选, 一般不用动)
                </summary>
                <div style={{
                  fontSize: 11, color: "var(--text-dim)", marginTop: 8, marginBottom: 10,
                  lineHeight: 1.6, padding: 8, borderRadius: 4,
                  background: "var(--info-bg)",
                }}>
                  <b>这是什么:</b> 8 套思考方法 (Chain-of-Thought / Tree-of-Thoughts / Self-Ask / Reflexion ...).
                  AI 分诊官会根据你的任务自动选 0-2 个最合适的, 不需要你操心.
                  <br/><b>什么时候动手:</b> 你想强制让 AI 用某个特定方法时.
                </div>
                <ThinkingFrameworksPanel
                  enabled={frameworks} aiPicked={aiFrameworks}
                  onToggle={onToggleFramework} />
              </details>

              <details open={details.gene} onToggle={onToggleDetails("gene")} style={{
                padding: 12, borderRadius: 8,
                background: "var(--bg-subtle)",
                borderWidth: 1, borderStyle: "solid",
                borderColor: "var(--border)",
              }}>
                <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600, color: "#ffb300" }}>
                  🧬 基因编辑器 (直接改某部门的 system prompt)
                </summary>
                <div style={{
                  fontSize: 11, color: "var(--text-dim)", marginTop: 8, marginBottom: 10,
                  lineHeight: 1.6, padding: 8, borderRadius: 4,
                  background: "rgba(255,179,0,0.06)",
                }}>
                  <b>这是什么:</b> "基因" = 某个部门的底层 system prompt. 蜂群每天自演化 (p4/p8/p15) 会改它,
                  你也可以人工改.
                  <br/><b>什么时候动手:</b> 看到某部门多次给出离谱回答时.
                  建议先用 "👤 团队管理 → 重生成 persona" 试一次.
                </div>
                <GeneEditor />
              </details>

              <details open={details.scenario} onToggle={onToggleDetails("scenario")} style={{
                padding: 12, borderRadius: 8,
                background: "var(--bg-subtle)",
                borderWidth: 1, borderStyle: "solid",
                borderColor: "var(--border)",
              }}>
                <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600, color: "#ce93d8" }}>
                  📝 自定义场景 YAML (写一个新场景)
                </summary>
                <div style={{
                  fontSize: 11, color: "var(--text-dim)", marginTop: 8, marginBottom: 10,
                  lineHeight: 1.6, padding: 8, borderRadius: 4,
                  background: "rgba(206,147,216,0.06)",
                }}>
                  <b>这是什么:</b> 现有 14 个内置场景如果不够, 在这里写 YAML 加新场景.
                  <br/><b>什么时候动手:</b> 14 个里没有你想要的.
                </div>
                <ScenarioYamlAuthor />
              </details>
            </Wrap>
          )}

          {tab === "tech" && (
            <Wrap>
              <div style={{
                padding: 12, borderRadius: 8,
                background: "var(--accent-bg)",
                borderWidth: 1, borderStyle: "solid", borderColor: "var(--accent-bg)",
                fontSize: 12, color: "var(--text-dim)", lineHeight: 1.6,
              }}>
                <b style={{ color: "var(--accent)" }}>🔧 这里给开发者看的</b> — 三个工具:
                <ul style={{ margin: "6px 0", paddingLeft: 18 }}>
                  <li><b>沙箱 (SandboxPanel)</b>: 跑临时命令试错, 不影响生产</li>
                  <li><b>Shadow A/B</b>: 对比新旧 prompt 在 60 任务上的胜率, 决定是否升级</li>
                  <li><b>Coordinator</b>: 手动触发 18 个 evolvers (p0~p17), 看每个跑什么</li>
                </ul>
                普通用户不用碰这里; 自更新走 AI 大脑 tab 顶部的 "📦 系统自更新" 按钮即可.
              </div>
              <div style={sectionTitle}>📋 系统日志 (7 服务聚合)</div>
              <LogsPanel backendUrl={backendUrl} />
              <SandboxPanel />
              <ShadowABPanel />
              <CoordinatorPanel />
            </Wrap>
          )}
        </div>
      </div>
    </>
  );
}
