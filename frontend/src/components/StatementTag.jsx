import { statementTone } from '../statements.js'

export function StatementTag({ label, children }) {
  return (
    <span
      className={`inline-flex items-center rounded-md px-1.5 py-px align-middle text-[11px] font-semibold ring-1 ring-inset ${
        statementTone(label).tag
      }`}
    >
      {children ?? label}
    </span>
  )
}
