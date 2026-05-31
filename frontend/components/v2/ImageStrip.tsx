"use client";

import { useRef, type CSSProperties } from "react";

type DocFile = { name: string; content_b64: string };

type Props = {
  images: string[];
  docFiles?: DocFile[];
  onAdd: (file: File) => void | Promise<void>;
  onRemove: (idx: number) => void;
  onRemoveDoc?: (idx: number) => void;
  warn?: string | null;
  max?: number;
};

const docChip: CSSProperties = {
  position: "relative",
  display: "flex",
  alignItems: "center",
  gap: 6,
  padding: "6px 28px 6px 10px",
  height: 36,
  borderRadius: 8,
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--info-bg)",
  background: "var(--info-bg)",
  color: "#cfe3ff",
  fontSize: 12,
  maxWidth: 220,
};

function docIcon(name: string): string {
  const ext = (name.split(".").pop() || "").toLowerCase();
  if (["xlsx", "xlsm", "csv", "tsv"].includes(ext)) return "📊";
  if (ext === "pdf") return "📕";
  if (ext === "docx") return "📄";
  if (ext === "pptx") return "📑";
  return "📎";
}

const wrap: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 8,
  marginTop: 6,
  padding: "6px 8px",
  borderRadius: 8,
  borderWidth: 1,
  borderStyle: "dashed",
  borderColor: "var(--border-strong)",
  background: "var(--bg-subtle)",
  fontSize: 12,
  color: "var(--text-dim)",
  alignItems: "center",
};

const thumb: CSSProperties = {
  position: "relative",
  width: 72,
  height: 72,
  borderRadius: 6,
  overflow: "hidden",
  borderWidth: 1,
  borderStyle: "solid",
  borderColor: "var(--border-strong)",
};

const removeBtn: CSSProperties = {
  position: "absolute",
  top: 2,
  right: 2,
  width: 20,
  height: 20,
  borderRadius: 10,
  border: "none",
  background: "var(--overlay)",
  color: "var(--text)",
  fontSize: 12,
  cursor: "pointer",
  lineHeight: "20px",
  padding: 0,
};

const addBtn: CSSProperties = {
  width: 72,
  height: 72,
  borderRadius: 6,
  borderWidth: 1,
  borderStyle: "dashed",
  borderColor: "var(--accent-bg)",
  background: "var(--accent-bg)",
  color: "var(--accent)",
  cursor: "pointer",
  fontSize: 11,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: 4,
};

export function ImageStrip({ images, docFiles = [], onAdd, onRemove, onRemoveDoc, warn, max = 4 }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const canAddImg = images.length < max;
  const canAddDoc = docFiles.length < 5;
  const isEmpty = images.length === 0 && docFiles.length === 0;

  return (
    <div style={wrap}>
      {images.map((src, idx) => (
        <div key={`img-${idx}`} style={thumb}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={src} alt={`img-${idx}`} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
          <button type="button" style={removeBtn} onClick={() => onRemove(idx)} title="移除">×</button>
        </div>
      ))}
      {docFiles.map((f, idx) => (
        <div key={`doc-${idx}`} style={docChip} title={f.name}>
          <span>{docIcon(f.name)}</span>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
          <button
            type="button"
            style={{ ...removeBtn, top: "50%", transform: "translateY(-50%)" }}
            onClick={() => onRemoveDoc?.(idx)}
            title="移除"
          >×</button>
        </div>
      ))}
      {(canAddImg || canAddDoc) && (
        <button type="button" style={addBtn} onClick={() => inputRef.current?.click()}>
          <span style={{ fontSize: 18 }}>📎</span>
          <span>加附件</span>
        </button>
      )}
      {isEmpty && (
        <span style={{ marginLeft: 4 }}>
          可粘贴 / 拖入 / 点 📎: 图片(≤{max}张,走视觉) 或 Excel/PDF/Word/PPT/CSV(≤5个,转文字)
        </span>
      )}
      {!isEmpty && (
        <span style={{ marginLeft: "auto", color: "var(--text-faint)" }}>
          {images.length > 0 && `🖼${images.length}/${max} `}
          {docFiles.length > 0 && `📄${docFiles.length}/5`}
        </span>
      )}
      {warn && <div style={{ width: "100%", color: "#f87171" }}>⚠ {warn}</div>}
      <input
        ref={inputRef}
        type="file"
        accept="image/*,.xlsx,.xlsm,.csv,.tsv,.pdf,.docx,.pptx,.txt,.md,.json,.log"
        multiple
        style={{ display: "none" }}
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          for (const f of files) void onAdd(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}
