import { verdictStyle } from '../verdicts.js'
import { Icon } from './Icon.jsx'

export function VerdictBadge({ verdict, size = 'sm' }) {
  const style = verdictStyle(verdict)
  const sizing = size === 'lg' ? 'px-3.5 py-1.5 text-sm' : 'px-2.5 py-0.5 text-[11px]'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold uppercase tracking-wide ring-1 ring-inset ${sizing} ${style.badge}`}
    >
      <Icon name={style.icon} className={size === 'lg' ? 'h-4 w-4' : 'h-3.5 w-3.5'} strokeWidth={2.5} />
      {style.label}
    </span>
  )
}
