import type { Mode } from './contracts';
export async function api<T>(path:string, mode:Mode, options:RequestInit = {}):Promise<T> {
  const response = await fetch(path, {...options, cache:'no-store', headers:{'Content-Type':'application/json','X-Research-Mode':mode,...options.headers}});
  const body = await response.json().catch(()=>({error:'Backend returned an unreadable response.'}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status}).`);
  return body;
}
