"use client";

/** SmartResultRenderer — 把 LLM 文本切片成 Table/Timeline/Comparison/富文本块. */

import type { CSSProperties } from "react";
import { DataTable } from "./DataTable";
import { Timeline, type TimelineItem } from "./Timeline";
import { ComparisonGrid, type ComparisonOption } from "./ComparisonGrid";
import { RichMarkdown } from "./RichMarkdown";

type Block =
  | { kind: "table"; headers: string[]; rows: string[][] }
  | { kind: "timeline"; items: TimelineItem[]; title?: string }
  | { kind: "compare"; options: ComparisonOption[] }
  | { kind: "text"; text: string };

function parseBlocks(text: string): Block[] {
  if (!text || !text.trim()) return [];
  const blocks: Block[] = [];
  const sections = text.split(/\n{2,}/);
  for (const sec of sections) {
    if (!sec.trim()) continue;
    const tbl = tryMarkdownTable(sec);
    if (tbl) { blocks.push(tbl); continue; }
    const cmp = tryComparison(sec);
    if (cmp) { blocks.push(cmp); continue; }
    const tl = tryNumberedTimeline(sec);
    if (tl) { blocks.push(tl); continue; }
    blocks.push({ kind: "text", text: sec });
  }
  const merged: Block[] = [];
  for (const b of blocks) {
    const last = merged[merged.length - 1];
    if (b.kind === "text" && last?.kind === "text") {
      last.text = last.text + "\n\n" + b.text;
    } else {
      merged.push(b);
    }
  }
  return merged;
}

function tryMarkdownTable(s: string): Block | null {
  const lines = s.split("\n").filter(l => l.trim().startsWith("|"));
  if (lines.length < 2) return null;
  if (!/^\|[\s:|\-]+\|$/.test(lines[1].trim())) return null;
  const headers = lines[0].split("|").map(c => c.trim()).filter((_, i, a) => i > 0 && i < a.length - 1);
  const rows = lines.slice(2).map(l =>
    l.split("|").map(c => c.trim()).filter((_, i, a) => i > 0 && i < a.length - 1)
  );
  if (headers.length === 0 || rows.length === 0) return null;
  return { kind: "table", headers, rows };
}

function tryNumberedTimeline(s: string): Block | null {
  const m = s.match(/(?:^|\n)\s*(\d+)[.、)]\s+/g);
  if (!m || m.length < 3) return null;
  const parts = s.split(/(?:^|\n)\s*\d+[.、)]\s+/).slice(1);
  if (parts.length < 3) return null;
  const items: TimelineItem[] = parts.map((p, i) => {
    const [first, ...rest] = p.split("\n");
    return {
      title: `步骤 ${i + 1}: ${first.trim().slice(0, 80)}`,
      body: rest.join("\n").trim() || undefined,
      tone: "neutral",
    };
  });
  return { kind: "timeline", items };
}

function tryComparison(s: string): Block | null {
  const splits = s.split(/(?:^|\n)\s*(?:选项|方案|Option|推荐)\s*[A-Za-z0-9]+[:：]?\s*/);
  if (splits.length < 3) return null;
  const candidates = splits.slice(1);
  const options: ComparisonOption[] = candidates.map((c, i) => {
    const lines = c.trim().split("\n");
    const title = lines[0].trim().slice(0, 40) || `方案 ${i + 1}`;
    const body = lines.slice(1).join("\n");
    const pros: string[] = [];
    const cons: string[] = [];
    body.split("\n").forEach(ln => {
      const t = ln.trim();
      if (!t) return;
      if (/^[+✓✔].|^优[:：]|^优势[:：]|^pros?[:：]/i.test(t))
        pros.push(t.replace(/^[+✓✔]\s*|^(优势?|pros?)[:：]\s*/i, "").trim());
      else if (/^[-✗✘×].|^劣[:：]|^劣势[:：]|^缺点[:：]|^cons?[:：]/i.test(t))
        cons.push(t.replace(/^[-✗✘×]\s*|^(劣势?|缺点|cons?)[:：]\s*/i, "").trim());
    });
    return { title, pros, cons, recommended: /推荐|首选/i.test(title) };
  });
  if (options.every(o => (o.pros?.length ?? 0) + (o.cons?.length ?? 0) === 0)) return null;
  return { kind: "compare", options };
}

const wrap: CSSProperties = {
  display: "flex", flexDirection: "column", gap: 12,
};

export function SmartResultRenderer({ text }: { text: string }) {
  const blocks = parseBlocks(text || "");
  if (blocks.length === 0) {
    return <div style={{ fontSize: 13, color: "var(--text-dim)" }}>(无内容)</div>;
  }
  return (
    <div style={wrap}>
      {blocks.map((b, i) => {
        if (b.kind === "table") {
          return <DataTable key={i} headers={b.headers} rows={b.rows} />;
        }
        if (b.kind === "timeline") {
          return <Timeline key={i} items={b.items} />;
        }
        if (b.kind === "compare") {
          return <ComparisonGrid key={i} options={b.options} />;
        }
        return <RichMarkdown key={i} text={b.text} />;
      })}
    </div>
  );
}
