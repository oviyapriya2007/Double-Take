const STORAGE_KEY = 'double-take:current-analysis'

export function saveCurrentAnalysis(documentIds) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(documentIds))
  } catch {
    // Without storage the Results page still filters by the document_ids in its URL.
  }
}

export function loadCurrentAnalysis() {
  try {
    const ids = JSON.parse(localStorage.getItem(STORAGE_KEY))
    return Array.isArray(ids) && ids.length > 0 ? ids : null
  } catch {
    return null
  }
}

export function resultsPath(documentIds) {
  return `/results?document_ids=${documentIds.map(encodeURIComponent).join(',')}`
}
