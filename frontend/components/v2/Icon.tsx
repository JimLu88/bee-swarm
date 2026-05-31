"use client";

import type { CSSProperties } from "react";

/**
 * Icon — Material Symbols Rounded 包装 (替代全站 emoji).
 * 字体在 app/layout.tsx 的 <head> 通过 Google Fonts CDN 引入.
 * fill=true → 实心 (选中/品牌); 默认 outline.
 */
export function Icon({
  name,
  fill = false,
  size,
  className = "",
  style,
}: {
  name: string;
  fill?: boolean;
  size?: number;
  className?: string;
  style?: CSSProperties;
}) {
  const cls = `material-symbols-rounded${fill ? " ms-fill" : ""}${className ? " " + className : ""}`;
  return (
    <span
      className={cls}
      aria-hidden="true"
      style={size != null ? { fontSize: size, ...style } : style}
    >
      {name}
    </span>
  );
}
