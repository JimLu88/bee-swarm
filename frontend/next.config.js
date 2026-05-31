/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Phase B2 packaging: allow static export (no Node server needed)
  output: "export",
  images: { unoptimized: true },
  // v7: 类型由 tsc --noEmit 把关(已绿); ESLint 文案级规则(引号转义/Link)不阻断生产构建.
  eslint: { ignoreDuringBuilds: true },
};

module.exports = nextConfig;

