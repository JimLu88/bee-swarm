import type { MetadataRoute } from "next";

// 兼容 next.config output:"export" 静态导出 (否则 build 报 manifest.webmanifest 错)
export const dynamic = "force-static";

/** PWA manifest → Next 自动暴露为 /manifest.webmanifest.
 *  让手机浏览器可「添加到主屏」, standalone 全屏打开, 像 App 一样 (无需上架审核). */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "智囊团 — H-SEMAS",
    short_name: "智囊团",
    description: "多智能体 AI 顾问团 · 把你纠结的事交给一套 AI",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#ffffff",
    theme_color: "#ffffff",
    lang: "zh-CN",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
  };
}
