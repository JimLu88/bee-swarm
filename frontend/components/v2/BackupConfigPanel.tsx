"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Stats = {
  total_shards: number;
  pending_upload: number;
  memories_backed_up: number;
  per_pool: Record<string, number>;
  pool_quotas: Record<string, { configured?: boolean; accounts?: number; note?: string }>;
};

type Props = { backendUrl: string };

const wrap: CSSProperties = {
  padding: 14, borderRadius: 12,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  background: "var(--bg-subtle)",
  display: "flex", flexDirection: "column", gap: 10,
};

const poolRow: CSSProperties = {
  display: "flex", justifyContent: "space-between", alignItems: "center",
  padding: "8px 10px", borderRadius: 6,
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--bg-hover)",
};

const POOLS = [
  { id: "gist", label: "GitHub Gist", envKey: "GITHUB_GIST_TOKENS", hint: "多账号逗号分隔 (国内时通时不通)" },
  { id: "webdav", label: "坚果云 WebDAV", envKey: "WEBDAV_URL", hint: "国内直连·最简单。需 WEBDAV_USER / WEBDAV_PASS(应用密码)" },
  { id: "notion", label: "Notion", envKey: "NOTION_TOKEN", hint: "需要 NOTION_DATABASE_ID (国内需梯子)" },
  { id: "gitee", label: "Gitee 码云", envKey: "GITEE_TOKEN", hint: "国内直连·长期免费·无30天限制。需 GITEE_OWNER / GITEE_REPO(私有仓库)" },
  { id: "gdrive", label: "Google Drive", envKey: "GOOGLE_DRIVE_SA_JSON", hint: "服务账号 JSON (国内需梯子)" },
];

// v6-O 5 池 Key 输入器 — 直接在 UI 配, 写到 bee-memory/data/pool_config.json
const KEY_FIELDS: { group: string; help: string; fields: { key: string; placeholder: string; secret?: boolean }[] }[] = [
  {
    group: "GitHub Gist",
    help: "📋 详细步骤 (打开 GitHub):\n" +
          "1) 登 github.com → 右上头像 → Settings → Developer settings → Personal access tokens → Tokens (classic)\n" +
          "   (注意: 你截图那种 Fine-grained 也可以, 但 classic 配置更简单)\n" +
          "2) Generate new token (classic) → 描述写 'bee-memory-shards'\n" +
          "3) Expiration 选 No expiration (或 1 年)\n" +
          "4) Scopes 只勾 ☑ gist 一个即可 (其它都不用)\n" +
          "5) 拉到底 Generate token → 复制 ghp_xxxxxxxxxxxx 那串 → 粘到下面\n" +
          "💡 想多账号轮换? 不同 GitHub 账号各做一个 token, 这里用逗号分隔",
    fields: [{ key: "GITHUB_GIST_TOKENS", placeholder: "ghp_xxxx 或 ghp_xxxx,ghp_yyyy", secret: true }],
  },
  {
    group: "坚果云 WebDAV (推荐·国内直连·最简单)",
    help: "📋 步骤 (打开 jianguoyun.com):\n" +
          "1) 登录坚果云网页版 → 右上头像 → 账户信息 → 安全选项\n" +
          "2) 找到「第三方应用管理」→ 添加应用 → 名字写 bee-memory → 生成「应用密码」\n" +
          "   (这串才是 WEBDAV_PASS, 不是你的登录密码!)\n" +
          "3) WEBDAV_URL 填: https://dav.jianguoyun.com/dav/bee-memory/  (结尾的 / 不能少, 目录会自动创建)\n" +
          "4) WEBDAV_USER 填你的坚果云登录邮箱\n" +
          "💡 也支持任意 WebDAV (Nextcloud/TeraCLOUD), 改 URL 即可",
    fields: [
      { key: "WEBDAV_URL", placeholder: "https://dav.jianguoyun.com/dav/bee-memory/" },
      { key: "WEBDAV_USER", placeholder: "你的坚果云登录邮箱" },
      { key: "WEBDAV_PASS", placeholder: "应用密码(非登录密码)", secret: true },
    ],
  },
  {
    group: "Notion", help: "notion.so/my-integrations 建 integration, 拿 token + 数据库 ID",
    fields: [
      { key: "NOTION_TOKEN", placeholder: "secret_xxx...", secret: true },
      { key: "NOTION_DATABASE_ID", placeholder: "32 位字符 (UUID 去掉 -)" },
    ],
  },
  {
    group: "Gitee 码云 (推荐·国内直连·长期免费·无30天限制)",
    help: "📋 步骤 (打开 gitee.com):\n" +
          "1) 注册并登录码云 → 右上「+」→ 新建仓库 → 名字填 bee-backup → 选「私有」→ 创建\n" +
          "   (GITEE_OWNER = 你的用户名, 即仓库地址 gitee.com/【用户名】/bee-backup 里那段)\n" +
          "2) 右上头像 → 设置 → 左侧「私人令牌」→ 生成新令牌 → 勾选 ☑ projects(仓库) 权限 → 提交\n" +
          "3) 复制生成的令牌串 (只显示一次!) 粘到下面 GITEE_TOKEN\n" +
          "4) GITEE_REPO 填仓库名 bee-backup; GITEE_BRANCH 一般留空(默认 master)\n" +
          "💡 加密分片直接存进这个私有仓库的 shards/ 目录, 长期免费、国内秒连",
    fields: [
      { key: "GITEE_TOKEN", placeholder: "私人令牌 (勾 projects 权限)", secret: true },
      { key: "GITEE_OWNER", placeholder: "你的码云用户名" },
      { key: "GITEE_REPO", placeholder: "bee-backup (私有仓库名)" },
      { key: "GITEE_BRANCH", placeholder: "master (默认, 可留空)" },
    ],
  },
  {
    group: "Google Drive (国内需梯子·可选)",
    help: "📋 用服务账号 JSON (贴一次即可, 不会过期):\n" +
          "1) Google Cloud Console → 建项目 → 启用 Google Drive API\n" +
          "2) IAM → 服务账号 → 建一个 → 建密钥(JSON) → 下载那张 JSON\n" +
          "3) 把整张 JSON 文件内容(从 { 到 } 全部)粘到下面 GOOGLE_DRIVE_SA_JSON\n" +
          "⚠ 关键: 服务账号自己没有网盘配额! 你得在自己 Google Drive 建个文件夹,\n" +
          "   右键共享给 JSON 里那个 client_email(xxx@xxx.iam.gserviceaccount.com),\n" +
          "   再把该文件夹 ID 填到 GOOGLE_DRIVE_FOLDER, 否则上传会失败.\n" +
          "💡 嫌麻烦可跳过 Google Drive, 坚果云+码云+Gist 已够 3 池恢复",
    fields: [
      { key: "GOOGLE_DRIVE_SA_JSON", placeholder: "粘贴整张服务账号 JSON ({...})", secret: true },
      { key: "GOOGLE_DRIVE_FOLDER", placeholder: "共享给服务账号的文件夹 ID" },
    ],
  },
];

function PoolKeyEditor({ memBase, onSaved }: { memBase: string; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [savedFields, setSavedFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!open) return;
    (async () => {
      try {
        const r = await fetchWithTimeout(`${memBase}/memory/backup/config`, undefined, TIMEOUT_MS.default);
        if (!r.ok) return;
        const j = await r.json();
        setSavedFields(j.fields || {});
      } catch { /* ignore */ }
    })();
  }, [open, memBase]);

  const save = async () => {
    const nonEmpty: Record<string, string> = {};
    for (const k in values) if (values[k]) nonEmpty[k] = values[k];
    if (Object.keys(nonEmpty).length === 0) {
      setMsg("没填任何字段, 没事可做");
      return;
    }
    setBusy(true); setMsg("");
    try {
      const r = await fetchWithTimeout(`${memBase}/memory/backup/config`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(nonEmpty),
      }, TIMEOUT_MS.default);
      const j = await r.json();
      if (j.saved) {
        setMsg(`✓ 已保存 ${(j.fields_updated || []).length} 个字段. ${j.note || ""}`);
        setValues({});
        onSaved();
      } else if (j._proxy_error) {
        setMsg("❌ " + j._proxy_error);
      } else {
        setMsg("❌ 保存失败: " + JSON.stringify(j));
      }
    } catch (e) {
      setMsg("❌ 网络错误: " + (e as Error).message);
    } finally { setBusy(false); }
  };

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} style={{
        padding: "8px 14px", borderRadius: 6, fontSize: 13, cursor: "pointer",
        borderWidth: 1, borderStyle: "solid", borderColor: "var(--accent)",
        background: "var(--accent-bg)", color: "var(--accent)", fontWeight: 600,
        alignSelf: "flex-start",
      }}>🔑 配置 5 池 Key (一次性, 在此填)</button>
    );
  }

  return (
    <div style={{
      padding: 14, borderRadius: 8,
      background: "var(--accent-bg)",
      borderWidth: 1, borderStyle: "solid", borderColor: "var(--accent-bg)",
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--accent)" }}>
          🔑 5 池 Key 配置
        </div>
        <button type="button" onClick={() => setOpen(false)} style={{
          padding: "3px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
          borderWidth: 1, borderStyle: "solid", borderColor: "var(--border-strong)",
          background: "var(--bg-card)", color: "var(--text)",
        }}>收起</button>
      </div>

      {KEY_FIELDS.map((g) => (
        <div key={g.group} style={{
          padding: 10, borderRadius: 6,
          background: "var(--bg-subtle)",
          borderWidth: 1, borderStyle: "solid", borderColor: "var(--bg-hover)",
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text)", marginBottom: 4 }}>
            {g.group}
          </div>
          <div style={{ fontSize: 10, color: "var(--text-dim)", marginBottom: 8, whiteSpace: "pre-line", lineHeight: 1.6 }}>{g.help}</div>
          {g.fields.map((f) => (
            <div key={f.key} style={{
              display: "flex", gap: 8, alignItems: "center", marginBottom: 5,
            }}>
              <label style={{
                fontSize: 11, color: "var(--text-dim)", width: 160,
                fontFamily: "ui-monospace, Consolas, monospace",
              }}>{f.key}</label>
              <input
                type={f.secret ? "password" : "text"}
                value={values[f.key] || ""}
                onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                placeholder={savedFields[f.key] ? `已存: ${savedFields[f.key]} (留空 = 不改)` : f.placeholder}
                style={{
                  flex: 1, padding: "5px 8px", fontSize: 12, borderRadius: 4,
                  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
                  background: "var(--bg-subtle)", color: "var(--text)",
                  fontFamily: "ui-monospace, Consolas, monospace",
                }}
              />
            </div>
          ))}
        </div>
      ))}

      {msg && (
        <div style={{
          fontSize: 12, padding: 8, borderRadius: 4,
          background: msg.startsWith("✓") ? "rgba(76,175,80,0.10)" : "rgba(255,179,0,0.10)",
          color: msg.startsWith("✓") ? "#9ccc65" : "#ffb300",
        }}>{msg}</div>
      )}

      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button type="button" onClick={save} disabled={busy} style={{
          padding: "8px 18px", borderRadius: 6, fontSize: 13, cursor: busy ? "wait" : "pointer",
          borderWidth: 1, borderStyle: "solid", borderColor: "var(--accent)",
          background: "var(--accent)", color: "#1a1a1a", fontWeight: 700,
        }}>
          {busy ? "保存中..." : "💾 保存到 pool_config.json"}
        </button>
      </div>
    </div>
  );
}

export function BackupConfigPanel({ backendUrl }: Props) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // v6-O 走 swarm 代理 (跨域 + bearer)
  const memBase = `${backendUrl}/api`;

  const reload = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchWithTimeout(`${memBase}/memory/backup/stats`,
        { headers: { Authorization: "Bearer dev-token-change-me" } }, TIMEOUT_MS.default);
      if (res.ok) setStats(await res.json());
    } catch (e) {
      setError((e as Error).message);
    }
  }, [memBase]);

  useEffect(() => { reload(); }, [reload]);

  const retryPending = useCallback(async () => {
    setBusy(true);
    try {
      await fetchWithTimeout(`${memBase}/memory/backup/retry?limit=100`,
        { method: "POST", headers: { Authorization: "Bearer dev-token-change-me" } }, TIMEOUT_MS.decisionStart);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [memBase, reload]);

  return (
    <div style={wrap}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>🔒 v3-E 记忆 5 池备份</div>
        {stats && (
          <div style={{ fontSize: 11, opacity: 0.65 }}>
            备份 {stats.memories_backed_up} 条记忆 · 共 {stats.total_shards} 分片 ·
            待上传 {stats.pending_upload}
          </div>
        )}
      </div>

      {/* G4: 说清"记忆是什么" */}
      <div style={{
        padding: "10px 12px", borderRadius: 6, fontSize: 11,
        background: "var(--info-bg)",
        borderWidth: 1, borderStyle: "solid", borderColor: "var(--info-bg)",
        color: "var(--text-dim)", lineHeight: 1.7,
      }}>
        <b style={{ color: "var(--info)" }}>💡 "记忆"是指什么?</b> 蜂群系统在 bee-memory (端口 8004) 里存了 4 类东西:
        <ul style={{ margin: "4px 0", paddingLeft: 18 }}>
          <li><b>人设知识库</b>: 每个部门主管的专业知识 (书单/案例/坑/标准等 8 层, v6-C)</li>
          <li><b>问答历史</b>: 每次决策的完整对话 + CEO 回答 (默认留 100 条, 你 ⭐ 收藏的永久留)</li>
          <li><b>趋势采集</b>: p2/p17 evolver 每天扫的 arxiv 论文 / GitHub 热门</li>
          <li><b>用户偏好</b>: 你的反馈、纠正、点 ⭐ 的内容</li>
        </ul>
        <b style={{ color: "var(--info)" }}>5 池备份做啥?</b> 把这些记忆切成加密分片, 散存到 5 个云服务 (GitHub Gist/R2/Notion/阿里/Google Drive),
        任 3 个还活着就能恢复. <b style={{ color: "#ffb300" }}>不配 Key 也能用</b> — 数据存本地, 5 池只是"额外保险".
      </div>

      {error && (
        <div style={{
          padding: "10px 12px", borderRadius: 8, fontSize: 12,
          background: "rgba(255,179,0,0.08)",
          borderWidth: 1, borderStyle: "solid", borderColor: "rgba(255,179,0,0.30)",
          color: "#ffb300", lineHeight: 1.6,
        }}>
          <b>⚠ 暂时取不到备份池状态</b>
          <div style={{ color: "var(--text-dim)", marginTop: 4 }}>
            可能原因: bee-memory (端口 8004) 没启动 / 5 池 token 未配 (见每池 env 提示).
          </div>
          <div style={{ color: "var(--info)", marginTop: 4, fontSize: 11 }}>
            修法: 托盘启 bee-memory; token 配在 .env. 详情: {error}
          </div>
        </div>
      )}

      {POOLS.map((p) => {
        const quota = stats?.pool_quotas?.[p.id] || {};
        const count = stats?.per_pool?.[p.id] || 0;
        const ok = !!quota.configured;
        return (
          <div key={p.id} style={poolRow}>
            <div>
              <div style={{ fontWeight: 500, fontSize: 13 }}>
                {ok ? "✓" : "○"} {p.label} ({count} 分片)
              </div>
              <div style={{ fontSize: 11, opacity: 0.55 }}>
                env <code>{p.envKey}</code> · {p.hint}
              </div>
            </div>
            <div style={{ fontSize: 11, opacity: 0.65 }}>
              {ok ? `${quota.accounts || 1} 账号` : "未配 key"}
            </div>
          </div>
        );
      })}

      {/* v6-O 直接在这里加 5 池 Key, 不用去改 .env */}
      <PoolKeyEditor memBase={memBase} onSaved={reload} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
        <div style={{ fontSize: 11, opacity: 0.55 }}>
          💡 保存后会落到 <code>bee-memory/backend/data/pool_config.json</code>;
          托盘重启 bee-memory 让 pool adapters 重读, 然后点 retry 上传堆积的本地分片.
        </div>
        <button type="button" disabled={busy} onClick={retryPending}
                style={{
                  padding: "5px 12px", fontSize: 12, borderRadius: 6,
                  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
                  background: "var(--bg-subtle)", color: "inherit", cursor: "pointer",
                }}>
          {busy ? "上传中..." : "🔃 重试待上传"}
        </button>
      </div>
    </div>
  );
}
