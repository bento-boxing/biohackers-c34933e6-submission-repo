import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('api error messages', () => {
  it('explains a dropped connection instead of surfacing the browser TypeError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('NetworkError when attempting to fetch resource.')));
    await expect(api('/api/investigations', 'live', { method: 'POST' })).rejects.toThrow(/connection to the backend dropped.*300 seconds/i);
  });
  it('explains a gateway timeout that comes back without JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('An error occurred', { status: 504 })));
    await expect(api('/api/investigations', 'live')).rejects.toThrow(/exceeded the hosting time limit/i);
  });
  it('still returns the backend error text when there is one', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: 'Scout run was produced in a different research mode.' }), { status: 400 })));
    await expect(api('/api/investigations', 'live')).rejects.toThrow('Scout run was produced in a different research mode.');
  });
});
