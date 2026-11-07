import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Live scout runs can take minutes (≈4 upstream calls per target); the default proxy timeout is 30 s.
  experimental: { proxyTimeout: 180_000 },
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
