export function PageHeader({ eyebrow, title, description, actions }) {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-iris-100 bg-linear-to-br from-petal-50 via-iris-50 to-azure-50 px-5 py-6 sm:px-8 sm:py-8">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-16 -top-20 size-56 rounded-full bg-linear-to-br from-petal-200/70 to-iris-200/50 blur-2xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-24 right-1/4 size-48 rounded-full bg-aqua-200/40 blur-2xl"
      />
      <div className="relative flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0 max-w-2xl">
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h1 className="page-title mt-3">{title}</h1>
          {description && <p className="mt-2 text-sm leading-relaxed text-slate-600 sm:text-base">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </div>
  )
}
