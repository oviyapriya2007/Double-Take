import { StatementTag } from './StatementTag.jsx'

export function SourceChip({ label, statement }) {
  if (!statement) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 px-2.5 py-1.5 text-sm text-slate-400">
        Statement {label} unavailable
      </div>
    )
  }
  return (
    <div className="flex min-w-0 items-center gap-2 rounded-lg border border-iris-100 bg-white/90 px-2.5 py-1.5 text-sm">
      <StatementTag label={label} />
      <span className="min-w-0 truncate font-medium text-slate-700" title={statement.filename ?? undefined}>
        {statement.filename ?? 'Unknown document'}
      </span>
      {statement.page_number != null && (
        <span className="shrink-0 text-xs text-slate-400">p. {statement.page_number}</span>
      )}
    </div>
  )
}

export function SourcePair({ a, b }) {
  return (
    <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] sm:items-center">
      <SourceChip label="A" statement={a} />
      <span aria-hidden="true" className="hidden text-[11px] font-semibold uppercase text-slate-400 sm:block">
        vs
      </span>
      <SourceChip label="B" statement={b} />
    </div>
  )
}
