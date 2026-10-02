export function formatConfidence(confidence) {
  return typeof confidence === 'number' ? `${Math.round(confidence * 100)}%` : '—'
}

export function formatDate(value) {
  if (!value) return null
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}
