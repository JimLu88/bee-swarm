"use client";

/** v7 个人页 (Jim Clear / iOS 风): 会员卡 + 统计 + 常用顾问 + 账户.
 *  纯展示 + 回调; 统计/常用顾问数据由父级从 /api/memory 聚合与历史频次派生后传入, 不在此发请求改逻辑。 */

import { Icon } from "./Icon";

type Tier = "A" | "B" | "C";
type Fav = { name: string; pct: number; color?: string };

type Props = {
  onBack: () => void;
  userName: string;
  email?: string;
  tier: Tier;
  stats?: { consults?: number; advisorCalls?: number; avgConsensus?: number };
  favAdvisors?: Fav[];
  onOpenSettings: () => void;
  onLogout?: () => void;
};

const TIER_LABEL: Record<Tier, string> = { A: "标准会员", B: "高档会员", C: "旗舰会员" };
const AV_COLORS = ["#1F66E6", "#8E7BF0", "#1E9E63", "#E0A11A", "#3B73F0", "#5E8DFA", "#14834F"];

export function ProfilePage(props: Props) {
  const { onBack, userName, email, tier, stats = {}, favAdvisors = [], onOpenSettings, onLogout } = props;
  const fmt = (n?: number, suffix = "") => (n == null ? "—" : `${n}${suffix}`);

  return (
    <div className="scroll app-scroll">
      <div className="page">
        <div className="page-head">
          <button type="button" className="page-back" onClick={onBack} title="返回" aria-label="返回"><Icon name="arrow_back" /></button>
          <div className="page-title">我的</div>
        </div>

        {/* 会员卡 */}
        <div className="prof-hero">
          <div className="prof-av">{userName.slice(0, 1) || "我"}</div>
          <div style={{ minWidth: 0 }}>
            <div className="prof-name">{userName}</div>
            {email && <div className="prof-email">{email}</div>}
            <span className="prof-badge"><Icon name="diamond" /> {TIER_LABEL[tier]}</span>
          </div>
        </div>

        {/* 统计 */}
        <div className="stat-grid">
          <div className="stat"><div className="sv">{fmt(stats.consults)}</div><div className="sl">本月咨询</div></div>
          <div className="stat"><div className="sv">{fmt(stats.advisorCalls)}</div><div className="sl">顾问调用</div></div>
          <div className="stat"><div className="sv">{stats.avgConsensus == null ? "—" : `${Math.round(stats.avgConsensus * 100)}%`}</div><div className="sl">平均共识度</div></div>
        </div>

        {/* 常用顾问 */}
        {favAdvisors.length > 0 && (
          <div className="set-group">
            <div className="set-group-h"><Icon name="groups" /> 最常请教的顾问</div>
            <div className="set-card">
              {favAdvisors.slice(0, 6).map((f, i) => (
                <div key={f.name + i} className="fav-row">
                  <span className="adv-av" style={{ background: f.color || AV_COLORS[i % AV_COLORS.length], width: 28, height: 28 }}>{f.name.slice(0, 1)}</span>
                  <span style={{ font: "500 14.5px var(--font-sans)", color: "var(--fg-1)", flex: "none", minWidth: 88, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
                  <span className="fav-bar"><i style={{ width: `${Math.max(4, Math.min(100, f.pct))}%` }} /></span>
                  <span className="fav-pct">{Math.round(f.pct)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 账户 */}
        <div className="set-group">
          <div className="set-group-h"><Icon name="manage_accounts" /> 账户</div>
          <div className="set-card">
            <div className="set-row nav" onClick={onOpenSettings}>
              <span className="set-ico"><Icon name="settings" /></span>
              <div className="stx"><b>偏好设置</b><span>外观、顾问与讨论、隐私</span></div>
              <span className="set-rowval"><Icon name="chevron_right" /></span>
            </div>
            {onLogout && (
              <div className="set-row nav" onClick={onLogout}>
                <span className="set-ico danger"><Icon name="logout" /></span>
                <div className="stx"><b style={{ color: "var(--danger)" }}>退出登录</b></div>
                <span className="set-rowval"><Icon name="chevron_right" /></span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
