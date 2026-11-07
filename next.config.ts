import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Live scout runs can take minutes (≈4 upstream calls per target); the default proxy timeout is 30 s.
  experimental: { proxyTimeout: 180_000 },
  // Tailwind v4 via the Turbopack loader (the skeleton installed it but never registered it).
  turbopack: {
    rules: {
      "*.css": { loaders: ["@tailwindcss/turbopack"] },
    },
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:5000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
