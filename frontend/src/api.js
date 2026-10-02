export const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

function errorMessage(body, status) {
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => item.msg).join('; ')
  }
  return `Request failed with status ${status}`
}

async function request(path, options) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, options)
  } catch {
    throw new Error(`Could not reach the Double-Take API at ${API_URL}. Is the backend running?`)
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const error = new Error(errorMessage(body, response.status))
    error.status = response.status
    throw error
  }
  return body
}

export function uploadDocuments(files) {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  return request('/documents/upload', { method: 'POST', body: form })
}

export function getAnalysisResults(documentIds) {
  if (!documentIds?.length) return request('/analysis/results')
  return request(`/analysis/results?document_ids=${documentIds.map(encodeURIComponent).join(',')}`)
}

export function getAnalysisResult(id) {
  return request(`/analysis/results/${encodeURIComponent(id)}`)
}

export function runAnalysis(documentIds) {
  return request('/analysis/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_ids: documentIds }),
  })
}
