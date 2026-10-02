import { formatConfidence } from '../format.js'

export function Confidence({ value, size = 'sm' }) {
  const percent = typeof value === 'number' ? Math.min(100, Math.max(0, value * 100)) : null
  const large = size === 'lg'
  return (
    <div
      className={`shrink-0 text-right ${large ? 'rounded-xl border border-iris-100 bg-white/90 px-4 py-3 shadow-sm shadow-iris-900/5' : ''}`}
    >
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">Confidence</p>
      <p className={`font-semibold tabular-nums text-slate-900 ${large ? 'text-3xl' : 'text-lg leading-tight'}`}>
        {formatConfidence(value)}
      </p>
      {percent != null && (
        <div
          aria-hidden="true"
          className={`ml-auto mt-1.5 h-1.5 overflow-hidden rounded-full bg-iris-100 ${large ? 'w-28' : 'w-16'}`}
        >
          <div
            className="h-full rounded-full bg-linear-to-r from-petal-400 via-iris-500 to-azure-400"
            style={{ width: `${percent}%` }}
          />
        </div>
      )}
    </div>
  )
}
