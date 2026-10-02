import { Icon } from './Icon.jsx'

export function Spinner({ className = '' }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent ${className}`}
    />
  )
}

const ALERT_TONES = {
  error: { box: 'border-red-200 bg-red-50 text-red-800', icon: 'alert', iconColor: 'text-red-500' },
  warning: { box: 'border-amber-200 bg-amber-50 text-amber-900', icon: 'alert', iconColor: 'text-amber-500' },
  info: { box: 'border-azure-200 bg-azure-50 text-slate-800', icon: 'info', iconColor: 'text-azure-700' },
}

export function Alert({ tone, title, children }) {
  const style = ALERT_TONES[tone]
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`flex gap-3 break-words rounded-xl border px-4 py-3 text-sm ${style.box}`}
    >
      <Icon name={style.icon} className={`mt-0.5 h-5 w-5 shrink-0 ${style.iconColor}`} />
      <div className="min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={title ? 'mt-0.5' : ''}>{children}</div>}
      </div>
    </div>
  )
}

export function LoadingState({ children }) {
  return (
    <div role="status" className="card flex items-center justify-center gap-3 px-5 py-12 text-sm text-slate-600">
      <Spinner className="text-iris-500" />
      {children}
    </div>
  )
}

export function ErrorState({ title, message, onRetry }) {
  return (
    <div role="alert" className="card border-red-200 px-6 py-10 text-center">
      <span className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-500 ring-1 ring-red-200">
        <Icon name="alert" className="h-6 w-6" />
      </span>
      <p className="font-semibold text-slate-900">{title}</p>
      <p className="mx-auto mt-1 max-w-lg break-words text-sm text-slate-600">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary mt-5">
          <Icon name="refresh" className="h-4 w-4" />
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({ icon = 'search', title, description, children }) {
  return (
    <div className="rounded-2xl border border-dashed border-iris-200 bg-linear-to-br from-white via-iris-50/40 to-petal-50/60 px-6 py-12 text-center">
      <span className="brand-gradient-strong mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl text-white shadow-md shadow-iris-500/25">
        <Icon name={icon} className="h-6 w-6" />
      </span>
      {title && <p className="font-semibold text-slate-900">{title}</p>}
      {description && <div className="mx-auto mt-1 max-w-md text-sm text-slate-600">{description}</div>}
      {children && <div className="mt-5 flex flex-wrap items-center justify-center gap-3">{children}</div>}
    </div>
  )
}
