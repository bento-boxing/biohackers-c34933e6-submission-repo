import type { Mode } from './contracts';

const HOSTED_LIMIT = 'Hosted investigations are limited to 300 seconds; a target with very many registry trials can exceed it. Try again (public responses are cached for a while), or choose a target with fewer trials.';

/** JSON fetch with the research-mode header; turns transport failures into readable messages. */
export async function api<T>(path:string, mode:Mode, options:RequestInit = {}):Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {...options, cache:'no-store', headers:{'Content-Type':'application/json','X-Research-Mode':mode,...options.headers}});
  } catch {
    throw new Error(`The connection to the backend dropped before a response arrived. ${HOSTED_LIMIT}`);
  }
  const body = await response.json().catch(()=>null);
  if (!response.ok) {
    if (body?.error) throw new Error(body.error);
    if (response.status === 504 || response.status === 502) throw new Error(`The investigation exceeded the hosting time limit or the backend did not answer (HTTP ${response.status}). ${HOSTED_LIMIT}`);
    if (response.status === 413) throw new Error('The request was too large for the hosted backend (HTTP 413).');
    throw new Error(`Request failed (${response.status}).`);
  }
  if (body === null) throw new Error('Backend returned an unreadable response.');
  return body;
}
