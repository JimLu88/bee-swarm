"use client";

/** 📚 书库面板 — 扫描到位 / 灌库 / 导出书单 / 合法书源自动下载。
 * 盗版站(Z-Library)批量下载不在系统内实现;用"导出书单"喂自己的 Olib/Calibre。 */

import { useCallback, useEffect, useState, type CSSProperties } from "react";

type Inv = {
  total?: number; done?: number; in_place?: number; missing?: number;
  extra?: number; dropzone?: string; files_in_dropzone?: number; error?: string;
};
type Store = { books?: number; chunks?: number; vector?: boolean; dim?: number; note?: string; error?: string };

type Props = { backendUrl: string };

const card: CSSProperties = {
  border: "1px solid var(--border)", borderRadius: 10, padding: 14,
  background: "var(--bg-card)", display: "flex", flexDirection: "column", gap: 10,
};
const statRow: CSSProperties = { display: "flex", flexWrap: "wrap", gap: 14, fontSize: 13 };
const btn = (kind: "primary" | "plain" = "plain"): CSSProperties => ({
  padding: "8px 14px", fontSize: 13, fontWeight: 600, borderRadius: 8, cursor: "pointer",
  border: "1px solid " + (kind === "primary" ? "var(--accent)" : "var(--border)"),
  background: kind === "primary" ? "var(--accent-bg)" : "var(--bg-subtle)",
  color: "var(--text)",
});
const note: CSSProperties = { fontSize: 12, color: "var(--text-muted)", lineHeight: 1.6 };

export function BooksPanel({ backendUrl }: Props) {
  const [inv, setInv] = useState<Inv>({});
  const [store, setStore] = useState<Store>({});
  const [busy, setBusy] = useState<string>("");
  const [msg, setMsg] = useState<string>("");

  const api = useCallback(async (path: string, method: "GET" | "POST", body?: unknown) => {
    const r = await fetch(`${backendUrl}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  }, [backendUrl]);

  const refresh = useCallback(async () => {
    try {
      const d = await api("/api/books/status", "GET");
      setInv(d.inventory || {});
      setStore(d.store || {});
    } catch (e) { setMsg("状态获取失败:" + String(e)); }
  }, [api]);

  useEffect(() => { void refresh(); }, [refresh]);

  const run = async (label: string, path: string, body?: unknown) => {
    setBusy(label); setMsg("");
    try {
      const d = await api(path, "POST", body);
      setMsg(`${label} 完成:` + JSON.stringify(d).slice(0, 400));
      await refresh();
    } catch (e) {
      setMsg(`${label} 失败:` + String(e));
    } finally { setBusy(""); }
  };

  const N = (v: number | undefined) => (typeof v === "number" ? v : "—");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* 到位统计 */}
      <div style={card}>
        <div style={{ fontWeight: 700, fontSize: 14 }}>📊 书库到位情况</div>
        <div style={statRow}>
          <span>书单总需 <b>{N(inv.total)}</b></span>
          <span style={{ color: "var(--success, #16a34a)" }}>✅ 已灌(被程序使用) <b>{N(inv.done)}</b></span>
          <span style={{ color: "var(--info)" }}>📥 已到位未灌 <b>{N(inv.in_place)}</b></span>
          <span style={{ color: "var(--danger, #dc2626)" }}>❌ 缺失 <b>{N(inv.missing)}</b></span>
          <span style={{ color: "var(--text-muted)" }}>❓ 多余 <b>{N(inv.extra)}</b></span>
        </div>
        <div style={note}>
          向量库:{store.error ? `异常 ${store.error}` :
            `已收 ${N(store.books)} 本 / ${N(store.chunks)} 块 · ${store.vector ? `向量(dim ${N(store.dim)})` : "FTS5关键词"}${store.note ? " · " + store.note : ""}`}
          <br />投书文件夹:<code>{inv.dropzone || "—"}</code>(现有 {N(inv.files_in_dropzone)} 个文件)
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" style={btn()} onClick={() => void refresh()}>↻ 刷新</button>
          <button type="button" style={btn()} disabled={!!busy}
            onClick={() => void run("扫描", "/api/books/scan")}>
            {busy === "扫描" ? "扫描中…" : "🔍 扫描到位"}
          </button>
          <button type="button" style={btn("primary")} disabled={!!busy}
            onClick={() => void run("灌库", "/api/books/ingest", {})}>
            {busy === "灌库" ? "灌库中…(可能数分钟)" : "📥 灌库(切块+向量入库)"}
          </button>
        </div>
      </div>

      {/* 导出书单 */}
      <div style={card}>
        <div style={{ fontWeight: 700, fontSize: 14 }}>📤 导出书单(给 Olib / Calibre 用)</div>
        <div style={note}>
          导出 <code>_导出_全部书单.csv</code>(书名/作者/豆瓣/Goodreads/类/场景)+
          <code>_导出_书名清单.txt</code>(纯书名,可直接喂 Olib 批量搜索)。
          文件落在 <code>backend/app/seed_knowledge/booklists/</code>。
        </div>
        <button type="button" style={btn()} disabled={!!busy}
          onClick={() => void run("导出书单", "/api/books/export")}>
          {busy === "导出书单" ? "导出中…" : "📄 导出书单 CSV + TXT"}
        </button>
      </div>

      {/* 合法源自动下载 */}
      <div style={card}>
        <div style={{ fontWeight: 700, fontSize: 14 }}>⬇️ 自动下载(仅合法公版源)</div>
        <div style={note}>
          从 <b>Project Gutenberg 等公有领域源</b>自动抓取并放进投书文件夹(然后点上面"灌库")。
          <br />⚠️ 现代中文/专业书在公版源命中率有限;<b>Z-Library 等盗版站不在系统内下载</b> ——
          那部分请用上面"导出的书名清单"在你自己的 Olib 里操作。
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" style={btn()} disabled={!!busy}
            onClick={() => void run("合法下载", "/api/books/fetch-legal", { limit: 30 })}>
            {busy === "合法下载" ? "下载中…" : "⬇️ 试下 30 本(公版源)"}
          </button>
        </div>
      </div>

      {msg && <div style={{ ...note, whiteSpace: "pre-wrap", color: "var(--text)" }}>{msg}</div>}
    </div>
  );
}
