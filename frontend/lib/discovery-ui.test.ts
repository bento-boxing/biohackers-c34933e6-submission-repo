import { describe, expect, it } from 'vitest';
import { COLUMN_HELP, stepHighlight } from './discovery-ui';

describe('column help', () => {
  it('explains every scored column and how weights act on the total', () => {
    for (const key of ['rank', 'target', 'score', 'genetic', 'association', 'druggability', 'literature', 'safety'] as const) {
      expect(COLUMN_HELP[key].title.length).toBeGreaterThan(0);
      expect(COLUMN_HELP[key].body.length).toBeGreaterThan(40);
    }
    for (const key of ['genetic', 'association', 'druggability', 'literature'] as const) expect(COLUMN_HELP[key].body).toMatch(/weight/i);
    expect(COLUMN_HELP.safety.body).toMatch(/not/i);
  });
});

describe('stepHighlight', () => {
  it('moves down and wraps, treating -1 (nothing highlighted) as the start', () => {
    expect(stepHighlight(-1, 'ArrowDown', 3)).toBe(0);
    expect(stepHighlight(2, 'ArrowDown', 3)).toBe(0);
    expect(stepHighlight(0, 'ArrowUp', 3)).toBe(2);
    expect(stepHighlight(-1, 'ArrowUp', 3)).toBe(2);
  });
  it('ignores other keys and empty lists', () => {
    expect(stepHighlight(1, 'Enter', 3)).toBe(1);
    expect(stepHighlight(1, 'ArrowDown', 0)).toBe(-1);
  });
});
