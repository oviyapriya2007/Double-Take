export const STATEMENT_TONES = {
  A: {
    tag: 'bg-iris-100 text-iris-800 ring-iris-200',
    panel: 'border-iris-200',
    header: 'bg-iris-50/70',
    bar: 'bg-linear-to-r from-iris-400 to-azure-400',
    quote: 'border-l-iris-400',
  },
  B: {
    tag: 'bg-petal-100 text-petal-700 ring-petal-200',
    panel: 'border-petal-200',
    header: 'bg-petal-50',
    bar: 'bg-linear-to-r from-petal-300 to-iris-300',
    quote: 'border-l-petal-400',
  },
}

export function statementTone(label) {
  return STATEMENT_TONES[label] ?? STATEMENT_TONES.A
}

export function statementLabel(item, result) {
  const a = result.statement_a?.filename
  const b = result.statement_b?.filename
  if (a === b) return null
  if (item.document === a) return 'A'
  if (item.document === b) return 'B'
  return null
}

export function evidenceQuote(result, label) {
  return (result.evidence ?? []).find((item) => statementLabel(item, result) === label)?.quote ?? null
}
