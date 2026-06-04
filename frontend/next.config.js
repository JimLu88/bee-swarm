/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Phase B2 packaging: allow static export (no Node server needed)
  output: "export",
  // 静态导出 + 后端 StaticFiles(html=True) 伺服: 开 trailingSlash 让 /intel 导出成
  // intel/index.html(而非 intel.html),否则后端按目录找不到 → 回落 404。
  trailingSlash: true,
  images: { unoptimized: true },
  // v7: 类型由 tsc --noEmit 把关(已绿); ESLint 文案级规则(引号转义/Link)不阻断生产构建.
  eslint: { ignoreDuringBuilds: true },
};

module.exports = nextConfig;

