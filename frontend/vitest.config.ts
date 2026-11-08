import { defineConfig } from 'vitest/config';

// Unit tests only; Playwright specs under tests/ run with `npm run test:e2e`.
export default defineConfig({ test: { include: ['lib/**/*.test.ts'] } });
