/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Phase B2 packaging: allow static export (no Node server needed)
  output: "export",
  images: { unoptimized: true },
};

module.exports = nextConfig;

