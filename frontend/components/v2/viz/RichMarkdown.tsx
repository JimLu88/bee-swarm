"use client";

/** v7 W3-1 真 markdown 渲染器: react-markdown + remark-gfm (表格/删除线/任务列表),
 *  全令牌主题化, 图片点击进 lightbox. 安全: 不用 dangerouslySetInnerHTML. */

import { useState, type CSSProperties } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Lightbox from "yet-another-react-lightbox";
import "yet-another-react-lightbox/styles.css";

type Props = { text: string };

const codeInline: CSSProperties = {
  padding: "1px 5px", borderRadius: 3, fontSize: 12,
  background: "var(--bg-subtle)", color: "var(--info)",
  fontFamily: "ui-monospace, Consolas, monospace",
};
const preStyle: CSSProperties = {
  padding: 12, borderRadius: 8, overflow: "auto",
  background: "var(--bg-subtle)", border: "1px solid var(--border)",
  fontSize: 12.5, lineHeight: 1.5,
};
const tableStyle: CSSProperties = {
  borderCollapse: "collapse", width: "100%", fontSize: 13, margin: "6px 0",
};
const thStyle: CSSProperties = {
  border: "1px solid var(--border)", padding: "6px 10px",
  background: "var(--bg-subtle)", fontWeight: 700, textAlign: "left", color: "var(--text)",
};
const tdStyle: CSSProperties = {
  border: "1px solid var(--border)", padding: "6px 10px", color: "var(--text)",
};

export function RichMarkdown({ text }: Props) {
  const [lb, setLb] = useState<string | null>(null);
  if (!text || !text.trim()) {
    return <div style={{ fontSize: 13, color: "var(--text-dim)" }}>(无内容)</div>;
  }
  return (
    <div style={{ fontSize: 13, lineHeight: 1.7, color: "var(--text)" }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (p) => <div style={{ fontSize: 17, fontWeight: 700, margin: "8px 0 4px", color: "var(--text)" }}>{p.children}</div>,
          h2: (p) => <div style={{ fontSize: 15, fontWeight: 700, margin: "8px 0 4px", color: "var(--text)" }}>{p.children}</div>,
          h3: (p) => <div style={{ fontSize: 14, fontWeight: 700, margin: "6px 0 3px", color: "var(--text)" }}>{p.children}</div>,
          p: (p) => <p style={{ margin: "4px 0" }}>{p.children}</p>,
          strong: (p) => <strong style={{ color: "var(--accent)" }}>{p.children}</strong>,
          a: (p) => <a href={p.href} target="_blank" rel="noopener noreferrer" style={{ color: "var(--info)", textDecoration: "underline" }}>{p.children}</a>,
          ul: (p) => <ul style={{ margin: "4px 0", paddingLeft: 20 }}>{p.children}</ul>,
          ol: (p) => <ol style={{ margin: "4px 0", paddingLeft: 20 }}>{p.children}</ol>,
          li: (p) => <li style={{ margin: "2px 0", lineHeight: 1.6 }}>{p.children}</li>,
          blockquote: (p) => <blockquote style={{ borderLeft: "3px solid var(--accent)", margin: "6px 0", paddingLeft: 12, color: "var(--text-dim)" }}>{p.children}</blockquote>,
          code: (p) => {
            const inline = !String(p.className || "").includes("language-");
            return inline ? <code style={codeInline}>{p.children}</code> : <code>{p.children}</code>;
          },
          pre: (p) => <pre style={preStyle}>{p.children}</pre>,
          table: (p) => <div style={{ overflowX: "auto" }}><table style={tableStyle}>{p.children}</table></div>,
          th: (p) => <th style={thStyle}>{p.children}</th>,
          td: (p) => <td style={tdStyle}>{p.children}</td>,
          img: (p) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={p.src as string} alt={(p.alt as string) || ""}
              onClick={() => setLb(p.src as string)}
              style={{ maxWidth: "100%", borderRadius: 8, cursor: "zoom-in", margin: "6px 0" }} />
          ),
          hr: () => <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "10px 0" }} />,
        }}
      >
        {text}
      </ReactMarkdown>
      {lb && (
        <Lightbox open close={() => setLb(null)} slides={[{ src: lb }]}
          render={{ buttonPrev: () => null, buttonNext: () => null }} />
      )}
    </div>
  );
}
