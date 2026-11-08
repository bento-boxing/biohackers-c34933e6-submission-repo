import type { NextConfig } from 'next';
import path from 'node:path';

const config: NextConfig = {
  distDir: process.env.RESEARCH_BUILD_DIR || '.next',
  devIndicators: false,
  turbopack: { root: path.resolve(process.cwd(), '..') },
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${process.env.RESEARCH_BACKEND_URL || 'http://127.0.0.1:5050'}/api/:path*` }];
  },
};
export default config;
