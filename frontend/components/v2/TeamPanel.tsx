"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";
import { DeptCard, type Dept, type DeptStats } from "./DeptCard";
import { PersonaCard, type Persona } from "./PersonaCard";
import { PromptEditModal } from "./PromptEditModal";

type Team = {
  mode_id: string;
  generated_at?: number;
  generator_model?: string;
  ceo: Persona;
  departments: Dept[];
  missing_api_keys?: string[];
};

type Props = {
  mode: string;
  modeLabel?: string;
  backendUrl: string;
};

const wrap: CSSProperties = {
  padding: 14,
  borderRadius: 12,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  display: "flex",
  flexDirection: "column",
  gap: 12,
};

const headerRow: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  flexWrap: "wrap",
  gap: 8,
};

const btnPrimary: CSSProperties = {
  padding: "8px 14px",
  fontSize: 13,
  fontWeight: 600,
  borderRadius: 8,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--accent)",
  background: "var(--accent-bg)",
  color: "inherit",
  cursor: "pointer",
};

const btnGhost: CSSProperties = {
  padding: "5px 12px",
  fontSize: 12,
  borderRadius: 6,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  color: "inherit",
  cursor: "pointer",
};

const deptList: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 10,
};

const warnBox: CSSProperties = {
  padding: "8px 12px",
  borderRadius: 6,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "rgba(244, 67, 54, 0.5)",
  background: "rgba(244, 67, 54, 0.08)",
  fontSize: 12,
};

export function TeamPanel({ mode, modeLabel, backendUrl }: Props) {
  const [team, setTeam] = useState<Team | null>(null);
  const [status, setStatus] = useState<"loading" | "not_generated" | "ready" | "error">("loading");
  const [busy, setBusy] = useState(false);
  const [busyMsg, setBusyMsg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ deptId: string; persona: Persona } | null>(null);
  // v6-S8 每个 dept 的近况
  const [statsMap, setStatsMap] = useState<Record<string, DeptStats>>({});
  const [teamGeneratedAt, setTeamGeneratedAt] = useState<number | undefined>(undefined);

  const reload = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/team/${encodeURIComponent(mode)}`,
        undefined,
        TIMEOUT_MS.default,
      );
      if (!res.ok) throw new Error(`team ${res.status}`);
      const j = await res.json();
      if (j.status === "not_generated") {
        setTeam(null);
        setStatus("not_generated");
      } else if (j.team) {
        setTeam(j.team as Team);
        setStatus("ready");
      } else {
        setStatus("error");
      }
    } catch (e) {
      setError((e as Error).message);
      setStatus("error");
    }
  }, [backendUrl, mode]);

  useEffect(() => { reload(); }, [reload]);

  // v6-S8 拉 persona-stats; team 就绪后才有意义
  useEffect(() => {
    if (status !== "ready") return;
    let aborted = false;
    (async () => {
      try {
        const res = await fetchWithTimeout(
          `${backendUrl}/api/team/${encodeURIComponent(mode)}/persona-stats?last_n=8`,
          undefined, TIMEOUT_MS.default,
        );
        if (!res.ok) return;
        const j = await res.json();
        if (aborted) return;
        setStatsMap((j.stats || {}) as Record<string, DeptStats>);
        setTeamGeneratedAt(j.team_generated_at ?? undefined);
      } catch { /* silent */ }
    })();
    return () => { aborted = true; };
  }, [backendUrl, mode, status]);

  const generate = useCallback(async () => {
    if (!window.confirm(
      "⚠ 重生整场会调 Opus 4.7 大模型, 花费 ~¥3, 耗时 60-90 秒.\n\n" +
      "替代方案: 不满意某个主任可单独重生 (~¥0.5), 不满意某人可单独重生 (~¥0.2), 或直接编辑 prompt (0 成本).\n\n" +
      "确认重生整场?",
    )) return;
    setBusy(true);
    setBusyMsg("Opus 4.7 正在为这个场景设计部门 + 召集医生 (大约 1 分钟, 最多 3 分钟)...");
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/team/generate/${encodeURIComponent(mode)}`,
        { method: "POST" },
        TIMEOUT_MS.teamGenerate,  // v6-T 180s — Opus 联网生成需 60-90s
      );
      if (!res.ok) {
        const txt = await res.text();
        if (res.status === 502 || res.status === 503) {
          throw new Error(`AI 服务暂不可用 (${res.status})。常见原因: ⚙️设置 → AI大脑 里 Opus key 没配 / 网关临时挂了。详情: ${txt.slice(0, 200)}`);
        }
        throw new Error(`生成失败 (${res.status}): ${txt.slice(0, 200)}`);
      }
      await reload();
    } catch (e) {
      const err = e as Error;
      if (err.name === "FetchTimeoutError") {
        setError("3 分钟还没回, 大概率是 Opus 慢爆了 / API key 没配。建议: ⚙️设置 → AI大脑 检查 key, 或换成 Sonnet 重试。");
      } else {
        setError(err.message);
      }
    } finally {
      setBusy(false);
      setBusyMsg("");
    }
  }, [backendUrl, mode, reload]);

  const regenDept = useCallback(async (deptId: string) => {
    if (!window.confirm(`确定重生 [${deptId}] 整个部门? 大约 30 秒, ~¥0.5`)) return;
    setBusy(true); setBusyMsg(`正在重新设计 ${deptId} 部门...`);
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/team/regen-dept/${encodeURIComponent(mode)}/${encodeURIComponent(deptId)}`,
        { method: "POST" },
        TIMEOUT_MS.teamGenerate,  // v6-T 也走 180s 安全档
      );
      if (!res.ok) throw new Error(`regen-dept ${res.status}`);
      await reload();
    } catch (e) {
      const err = e as Error;
      setError(err.name === "FetchTimeoutError"
        ? "3 分钟没回, 检查 Opus key / 网关"
        : err.message);
    } finally {
      setBusy(false); setBusyMsg("");
    }
  }, [backendUrl, mode, reload]);

  const regenPersona = useCallback(async (deptId: string, personaId: string) => {
    setBusy(true); setBusyMsg(`正在重生人设 ${personaId}...`);
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/team/regen-persona/${encodeURIComponent(mode)}/${encodeURIComponent(deptId)}/${encodeURIComponent(personaId)}`,
        { method: "POST" },
        TIMEOUT_MS.decisionStart,
      );
      if (!res.ok) throw new Error(`regen-persona ${res.status}`);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false); setBusyMsg("");
    }
  }, [backendUrl, mode, reload]);

  const openEdit = useCallback((deptId: string, persona: Persona) => {
    setEditing({ deptId, persona });
  }, []);

  const savePrompt = useCallback(async (newPrompt: string) => {
    if (!editing) return;
    setBusy(true); setBusyMsg("保存 prompt...");
    setError(null);
    try {
      const res = await fetchWithTimeout(
        `${backendUrl}/api/team/prompt/${encodeURIComponent(mode)}/${encodeURIComponent(editing.deptId)}/${encodeURIComponent(editing.persona.persona_id)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: newPrompt }),
        },
        TIMEOUT_MS.default,
      );
      if (!res.ok) throw new Error(`put-prompt ${res.status}`);
      setEditing(null);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false); setBusyMsg("");
    }
  }, [backendUrl, mode, editing, reload]);

  if (status === "loading") {
    return <div style={wrap}>⏳ 读取团队配置...</div>;
  }

  if (status === "not_generated") {
    // v6-V 13 个场景默认 team.yaml 已预置, 理论上不应再触发. 提示用户排查
    return (
      <div style={wrap}>
        <div style={{ fontSize: 14, fontWeight: 600 }}>⚠ {modeLabel || mode} 团队配置未找到</div>
        <div style={{ fontSize: 12, opacity: 0.7, lineHeight: 1.7 }}>
          系统已为 13 个内置场景预置完整团队 (无需 LLM 生成)。
          如果你看到这条消息, 可能是:
          <ul style={{ marginTop: 6, marginBottom: 6 }}>
            <li>① 自定义场景 — 需要手写 yaml 到 <code>backend/data/persona/{mode}/team.yaml</code></li>
            <li>② 文件被误删 — 从 git 恢复或重启后端</li>
          </ul>
        </div>
        {error && <div style={warnBox}>⚠ {error}</div>}
      </div>
    );
  }

  if (!team) {
    return <div style={wrap}>⚠ 团队数据异常 <button style={btnGhost} onClick={reload}>重试</button></div>;
  }

  return (
    <div style={wrap}>
      <div style={headerRow}>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14 }}>
            🐝 {modeLabel || mode} 顾问团 ({team.departments?.length || 0} 部门)
          </div>
          {team.generator_model && (
            <div style={{ fontSize: 11, opacity: 0.55 }}>
              生成: {team.generator_model} · {team.generated_at ? new Date(team.generated_at * 1000).toLocaleString() : "?"}
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {/* v15: "重生整场"(LLM 召集顾问团) 已移除 —— 避免高额模型花费; 团队用预置 yaml。 */}
          <button type="button" style={btnGhost} disabled={busy} onClick={reload}>🔃</button>
        </div>
      </div>

      {team.missing_api_keys && team.missing_api_keys.length > 0 && (
        <div style={warnBox}>
          ⚠ 这些模型还没配 API key, 请去 <strong>⚙ AI 设置</strong> 加上, 否则该主管会 fallback:
          <div style={{ marginTop: 4 }}>
            {team.missing_api_keys.map((m) => <code key={m} style={{ marginRight: 8 }}>{m}</code>)}
          </div>
        </div>
      )}

      {busyMsg && <div style={{ fontSize: 12, opacity: 0.75 }}>⏳ {busyMsg}</div>}
      {error && <div style={warnBox}>⚠ {error}</div>}

      <PersonaCard
        persona={team.ceo}
        role="ceo"
        busy={busy}
        onRegen={() => { /* CEO 不能单独重生, 重生整场即可 */ }}
        onEditPrompt={(p) => openEdit("__ceo__", p)}
      />

      <div style={deptList}>
        {team.departments?.map((d) => (
          <DeptCard
            key={d.dept_id}
            dept={d}
            busy={busy}
            stats={statsMap[d.dept_id]}
            teamGeneratedAt={teamGeneratedAt}
            onRegenDept={regenDept}
            onRegenPersona={regenPersona}
            onEditPrompt={openEdit}
          />
        ))}
      </div>

      {/* v6-V 横切部门提示 - 让用户知道这俩一直在跑 */}
      <div style={{
        padding: "10px 14px", borderRadius: 8, marginTop: 4,
        background: "var(--info-bg)",
        borderWidth: 1, borderStyle: "dashed", borderColor: "var(--info-bg)",
        display: "flex", flexDirection: "column", gap: 6,
      }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--info)" }}>
          🌍 系统自动注入 (每次决策都会加, 无需配置)
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, color: "var(--text-dim)", lineHeight: 1.6 }}>
          <div>
            <b>🔭 外部平行架构对比员</b> <span style={{ opacity: 0.7 }}>· parallel_architecture_scout</span>
            <div style={{ fontSize: 11, color: "var(--text-dim)", marginLeft: 16 }}>
              扫全球同类方案/产品/最新进展, 给本场景借鉴清单 + 抄/改/避判定
            </div>
          </div>
          <div>
            <b>💥 破局思考员</b> <span style={{ opacity: 0.7 }}>· out_of_box_breakthrough</span>
            <div style={{ fontSize: 11, color: "var(--text-dim)", marginLeft: 16 }}>
              反主流叙事, 给 3 个相反假设 + 最短证伪路径 (Think out of the box)
            </div>
          </div>
        </div>
        <div style={{ fontSize: 10, color: "var(--text-faint)", marginTop: 4 }}>
          想关: 设 env <code>BEE_DISABLE_VISION_EXPANSION=1</code> 重启后端
        </div>
      </div>

      <PromptEditModal
        open={editing !== null}
        persona={editing?.persona ?? null}
        busy={busy}
        onSave={savePrompt}
        onClose={() => setEditing(null)}
      />
    </div>
  );
}
