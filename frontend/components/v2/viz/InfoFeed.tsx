"use client";

/** v7 W3-2 信息流: 「📎展开更多」展开后, 把各部门原话 + 爬虫图文聚合成瀑布流卡片.
 *  masonry 布局 + framer-motion 入场 + 图片 lightbox. 全令牌主题. */

import { useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { motion } from "framer-motion";
import Masonry from "react-masonry-css";
import Lightbox from "yet-another-react-lightbox";
import "yet-another-react-lightbox/styles.css";

export type MediaCard = {
  type: "text" | "image" | "video" | "link";
  title?: string;
  body?: string;
  url?: string;
  image_url?: string;
  source?: string;
};

export type DeptQuote = {
  dept: string;
  consensus?: string;
  conflicts?: string[];
};

type Props = {
  deptQuotes?: DeptQuote[];
  mediaCards?: MediaCard[];
};

const cardBase: CSSProperties = {
  borderRadius: 10, padding: 12, marginBottom: 12,
  background: "var(--bg-card)", border: "1px solid var(--border)",
  boxShadow: "var(--shadow)",
};
const cardTitle: CSSProperties = { fontSize: 12, fontWeight: 700, color: "var(--info)", marginBottom: 6 };
const cardBody: CSSProperties = { fontSize: 12.5, lineHeight: 1.6, color: "var(--text)", whiteSpace: "pre-wrap" };
const srcLine: CSSProperties = { fontSize: 10.5, color: "var(--text-faint)", marginTop: 6 };

const BREAKPOINTS = { default: 3, 900: 2, 560: 1 };

export function InfoFeed({ deptQuotes = [], mediaCards = [] }: Props) {
  const [lb, setLb] = useState<string | null>(null);

  const items: { key: string; node: ReactNode }[] = [];

  deptQuotes.forEach((q, i) => {
    items.push({
      key: `dq-${i}`,
      node: (
        <div style={cardBase}>
          <div style={cardTitle}>🗣 {q.dept}</div>
          {q.consensus && <div style={cardBody}>{q.consensus}</div>}
          {q.conflicts && q.conflicts.length > 0 && (
            <div style={{ marginTop: 6, fontSize: 11, color: "var(--warn)" }}>
              ⚡ {q.conflicts.join("; ")}
            </div>
          )}
        </div>
      ),
    });
  });

  mediaCards.forEach((m, i) => {
    let inner: ReactNode = null;
    if (m.type === "image" && m.image_url) {
      inner = (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={m.image_url} alt={m.title || ""} onClick={() => setLb(m.image_url!)}
          style={{ width: "100%", borderRadius: 8, cursor: "zoom-in" }} />
      );
    } else if (m.type === "video" && m.url) {
      inner = (
        <a href={m.url} target="_blank" rel="noopener noreferrer"
          style={{ display: "block", fontSize: 13, color: "var(--info)" }}>
          ▶ {m.title || "查看视频"}
        </a>
      );
    } else if (m.type === "link") {
      inner = (
        <a href={m.url} target="_blank" rel="noopener noreferrer"
          style={{ display: "block", fontSize: 13, color: "var(--info)", textDecoration: "underline" }}>
          🔗 {m.title || m.url}
        </a>
      );
    } else {
      inner = <div style={cardBody}>{m.body}</div>;
    }
    items.push({
      key: `mc-${i}`,
      node: (
        <div style={cardBase}>
          {m.title && m.type !== "link" && m.type !== "video" && <div style={cardTitle}>{m.title}</div>}
          {inner}
          {m.source && <div style={srcLine}>来源: {m.source}</div>}
        </div>
      ),
    });
  });

  if (items.length === 0) {
    return <div style={{ fontSize: 12, color: "var(--text-dim)" }}>暂无更多信息</div>;
  }

  return (
    <>
      <Masonry breakpointCols={BREAKPOINTS} className="bee-masonry" columnClassName="bee-masonry-col">
        {items.map((it, idx) => (
          <motion.div key={it.key}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(idx * 0.03, 0.4), duration: 0.25 }}>
            {it.node}
          </motion.div>
        ))}
      </Masonry>
      <style>{`
        .bee-masonry { display: flex; margin-left: -12px; width: auto; }
        .bee-masonry-col { padding-left: 12px; background-clip: padding-box; }
      `}</style>
      {lb && (
        <Lightbox open close={() => setLb(null)} slides={[{ src: lb }]}
          render={{ buttonPrev: () => null, buttonNext: () => null }} />
      )}
    </>
  );
}
