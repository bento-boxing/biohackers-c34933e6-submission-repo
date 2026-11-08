'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { Mode } from '@/lib/contracts';
import { stepHighlight } from '@/lib/discovery-ui';

type Suggestion = { id: string; name: string };
type Props = { value: string; mode: Mode; disabled: boolean; onChange: (value: string) => void; onSubmit: (value: string) => void };

/** Search box with a suggestion dropdown fed by `GET /api/diseases?q=` (Open Targets fuzzy search; recorded list offline). */
export function DiseaseSearch({ value, mode, disabled, onChange, onSubmit }: Props) {
  const [items, setItems] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const [typed, setTyped] = useState(false);
  const listId = useId();
  const wrapper = useRef<HTMLDivElement>(null);

  // Fetch suggestions 250 ms after the last keystroke; stale responses are dropped.
  useEffect(() => {
    const query = value.trim();
    const wanted = typed && query.length >= 2;
    let active = true;
    const timer = setTimeout(() => {
      if (!wanted) { setItems([]); return; }
      api<{ diseases: Suggestion[] }>(`/api/diseases?q=${encodeURIComponent(query)}`, mode)
        .then(res => { if (active) { setItems(res.diseases); setHighlight(-1); setOpen(true); } })
        .catch(() => { if (active) setItems([]); });
    }, wanted ? 250 : 0);
    return () => { active = false; clearTimeout(timer); };
  }, [value, mode, typed]);

  useEffect(() => {
    const close = (e: MouseEvent) => { if (!wrapper.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  const choose = (s: Suggestion) => { setTyped(false); setOpen(false); setItems([]); onChange(s.name); onSubmit(s.name); };
  const visible = open && items.length > 0;
  return <div className="search-box" ref={wrapper}>
    <div className="search-row"><span aria-hidden="true">⌕</span>
      <input id="disease" role="combobox" aria-expanded={visible} aria-controls={listId} aria-autocomplete="list" aria-activedescendant={highlight >= 0 ? `${listId}-${highlight}` : undefined} autoComplete="off"
        value={value} placeholder="e.g. Parkinson disease" disabled={disabled}
        onChange={e => { setTyped(true); onChange(e.target.value); }}
        onFocus={() => { if (items.length) setOpen(true); }}
        onKeyDown={e => {
          if (visible && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); setHighlight(h => stepHighlight(h, e.key, items.length)); return; }
          if (e.key === 'Escape') { setOpen(false); return; }
          if (e.key === 'Enter' && !disabled && value.trim()) { if (visible && highlight >= 0) choose(items[highlight]); else { setOpen(false); onSubmit(value); } }
        }}/>
      <button className="button primary" onClick={() => { setOpen(false); onSubmit(value); }} disabled={disabled || !value.trim()}>{disabled ? 'Retrieving evidence…' : 'Discover targets →'}</button>
    </div>
    {visible && <ul className="suggestions" id={listId} role="listbox" aria-label="Matching diseases">
      {items.map((s, i) => <li key={s.id} id={`${listId}-${i}`} role="option" aria-selected={i === highlight} className={i === highlight ? 'highlight' : ''}
        onMouseEnter={() => setHighlight(i)} onMouseDown={e => e.preventDefault()} onClick={() => choose(s)}>
        <span>{s.name}</span><small className="mono">{s.id}</small></li>)}
    </ul>}
    {typed && open && items.length === 0 && value.trim().length >= 2 && <p className="suggestions-note">{mode === 'offline' ? 'The recorded demo only covers Parkinson disease.' : 'No matching disease yet; press Enter to search with the exact text.'}</p>}
  </div>;
}
