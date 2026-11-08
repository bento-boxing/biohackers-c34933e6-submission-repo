import { COLUMN_HELP, type ColumnKey } from '@/lib/discovery-ui';

/** Table header with a hover/focus speech bubble explaining the column and its effect on the ranking. */
export function HelpHeader({ column, children }: { column: ColumnKey; children: React.ReactNode }) {
  const help = COLUMN_HELP[column];
  return <th scope="col"><span className="th-help" tabIndex={0} aria-describedby={`help-${column}`}>{children}<i aria-hidden="true">?</i>
    <span role="tooltip" id={`help-${column}`} className="tooltip"><strong>{help.title}</strong>{help.body}</span></span></th>;
}
