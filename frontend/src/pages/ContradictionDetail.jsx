import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { getAnalysisResult } from '../api.js'
import { Confidence } from '../components/Confidence.jsx'
import { Icon } from '../components/Icon.jsx'
import { SourcePair } from '../components/SourceChip.jsx'
import { StatementTag } from '../components/StatementTag.jsx'
import { EmptyState, ErrorState, LoadingState } from '../components/Status.jsx'
import { VerdictBadge } from '../components/Verdict.jsx'
import { formatDate } from '../format.js'
import { statementLabel, statementTone } from '../statements.js'
import { verdictStyle } from '../verdicts.js'

const HIGHLIGHT =
  'rounded-sm bg-petal-100 px-0.5 text-slate-900 ring-1 ring-petal-300 box-decoration-clone'

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Evidence quotes are validated against the chunk text with whitespace normalised, so a
// quote may differ from the text in spacing and line breaks.
function quotePattern(quote) {
  const words = (quote ?? '').trim().split(/\s+/).filter(Boolean)
  return words.length ? words.map(escapeRegExp).join('\\s+') : null
}

function highlightQuotes(text, quotes) {
  const patterns = quotes
    .map(quotePattern)
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
  if (!patterns.length) return [{ text, marked: false }]

  const parts = []
  let last = 0
  for (const match of text.matchAll(new RegExp(patterns.join('|'), 'g'))) {
    if (match.index > last) parts.push({ text: text.slice(last, match.index), marked: false })
    parts.push({ text: match[0], marked: true })
    last = match.index + match[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last), marked: false })
  return parts
}

function displaySection(section) {
  return section && section !== 'unknown' ? section : 'Unknown'
}

function Breadcrumb({ id }) {
  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-sm text-slate-500">
      <Link
        to="/results"
        className="group inline-flex shrink-0 items-center gap-1 font-medium text-slate-600 hover:text-iris-700"
      >
        <Icon name="arrowLeft" className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
        Results
      </Link>
      <Icon name="chevronRight" className="h-3.5 w-3.5 shrink-0 text-slate-300" />
      <span aria-current="page" className="truncate">
        Finding <span className="font-mono text-xs text-slate-600">{id.slice(0, 8)}</span>
      </span>
    </nav>
  )
}

function Card({ title, children, className = '' }) {
  return (
    <section className={`card p-5 sm:p-6 ${className}`}>
      {title && <h2 className="section-heading mb-3">{title}</h2>}
      {children}
    </section>
  )
}

function MetaItem({ label, children, className = '' }) {
  return (
    <div className={`min-w-0 rounded-lg bg-white/80 px-3 py-2 ring-1 ring-inset ring-iris-100 ${className}`}>
      <dt className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 break-words font-medium text-slate-800">{children}</dd>
    </div>
  )
}

function StatementCard({ label, statement, quotes }) {
  if (!statement) {
    return (
      <Card>
        <p className="text-sm text-slate-500">Statement {label} is not available.</p>
      </Card>
    )
  }
  const showTitle = statement.title && statement.title !== statement.filename?.replace(/\.pdf$/i, '')
  const tone = statementTone(label)
  return (
    <section className={`card flex min-w-0 flex-col overflow-hidden ${tone.panel}`}>
      <div aria-hidden="true" className={`h-1 ${tone.bar}`} />
      <div className={`border-b border-iris-100 px-5 py-4 ${tone.header}`}>
        <div className="flex items-center gap-2">
          <StatementTag label={label}>Statement {label}</StatementTag>
        </div>
        <p className="mt-2 break-all font-semibold text-slate-900">{statement.filename ?? 'Unknown document'}</p>
        {showTitle && <p className="text-sm text-slate-500">{statement.title}</p>}
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
          <MetaItem label="Page">{statement.page_number ?? 'Unknown'}</MetaItem>
          <MetaItem label="Section">{displaySection(statement.section)}</MetaItem>
          {statement.doc_type && <MetaItem label="Type">{statement.doc_type}</MetaItem>}
        </dl>
      </div>
      <div className="flex-1 px-5 py-4">
        <p className="whitespace-pre-wrap break-words text-sm leading-7 text-slate-700">
          {highlightQuotes(statement.text ?? '', quotes).map((part, index) =>
            part.marked ? (
              <mark key={index} className={HIGHLIGHT}>
                {part.text}
              </mark>
            ) : (
              <span key={index}>{part.text}</span>
            ),
          )}
        </p>
      </div>
    </section>
  )
}

function EvidenceItem({ item, label }) {
  const accent = label ? statementTone(label).quote : 'border-l-iris-300'
  return (
    <li
      className={`rounded-xl border border-l-4 border-iris-100 bg-white px-4 py-3 shadow-sm shadow-iris-900/5 ${accent}`}
    >
      <blockquote className="break-words text-sm leading-relaxed text-slate-800">“{item.quote}”</blockquote>
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5 text-xs">
        {label && <StatementTag label={label}>Statement {label}</StatementTag>}
        <span className="chip break-all font-normal">{item.document}</span>
        {item.page != null && <span className="chip font-normal">p. {item.page}</span>}
        <span className="chip font-normal">Section: {displaySection(item.section)}</span>
      </div>
    </li>
  )
}

function EvidenceSection({ evidence, result }) {
  if (!evidence.length) {
    return (
      <Card title="Evidence">
        <p className="text-sm text-slate-500">No evidence quotes were returned for this result.</p>
      </Card>
    )
  }

  const groups = { A: [], B: [], other: [] }
  for (const item of evidence) groups[statementLabel(item, result) ?? 'other'].push(item)
  const columns = groups.A.length > 0 || groups.B.length > 0

  return (
    <Card title={`Evidence · ${evidence.length}`}>
      {columns && (
        <div className="grid gap-4 lg:grid-cols-2">
          {['A', 'B'].map((label) => {
            const statement = label === 'A' ? result.statement_a : result.statement_b
            return (
              <div key={label} className="min-w-0">
                <p className="mb-2 flex min-w-0 items-center gap-2 text-xs font-medium text-slate-500">
                  <StatementTag label={label} />
                  <span className="truncate">{statement?.filename ?? 'Unknown document'}</span>
                </p>
                {groups[label].length ? (
                  <ul className="space-y-3">
                    {groups[label].map((item, index) => (
                      <EvidenceItem key={index} item={item} label={label} />
                    ))}
                  </ul>
                ) : (
                  <p className="rounded-xl border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-400">
                    No quotes from this statement.
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}
      {groups.other.length > 0 && (
        <ul className={`space-y-3 ${columns ? 'mt-4' : ''}`}>
          {groups.other.map((item, index) => (
            <EvidenceItem key={index} item={item} label={null} />
          ))}
        </ul>
      )}
    </Card>
  )
}

function ResultView({ result }) {
  const style = verdictStyle(result.verdict)
  const evidence = result.evidence ?? []
  const quotes = evidence.map((item) => item.quote)
  const created = formatDate(result.created_at)

  return (
    <div className="space-y-6">
      <section className={`card border-l-4 p-5 sm:p-7 ${style.accent} ${style.surface}`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <VerdictBadge verdict={result.verdict} size="lg" />
            <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
              {result.topic || 'Untitled comparison'}
            </h1>
            <p className="mt-1.5 text-sm text-slate-600">{style.description}</p>
          </div>
          <Confidence value={result.confidence} size="lg" />
        </div>
        <div className="mt-5">
          <SourcePair a={result.statement_a} b={result.statement_b} />
        </div>
        <dl className="mt-5 grid gap-3 border-t border-iris-100 pt-4 text-sm sm:grid-cols-3">
          <MetaItem label="Result ID" className={result.method ? '' : 'sm:col-span-2'}>
            <span className="break-all font-mono text-xs font-normal text-slate-700">{result.id}</span>
          </MetaItem>
          {result.method && <MetaItem label="Method">{result.method}</MetaItem>}
          {created && <MetaItem label="Analysed">{created}</MetaItem>}
        </dl>
      </section>

      <Card title="Reasoning" className="bg-linear-to-br from-white via-white to-iris-50/70">
        <p className="border-l-4 border-petal-300 pl-4 leading-relaxed text-slate-800">
          {result.reasoning || 'No reasoning was provided.'}
        </p>
      </Card>

      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="section-heading">Compared statements</h2>
          {quotes.length > 0 && (
            <p className="text-xs text-slate-500">
              <mark className={HIGHLIGHT}>Highlighted</mark> text is quoted as evidence.
            </p>
          )}
        </div>
        <div className="relative grid gap-4 lg:grid-cols-2 lg:gap-6">
          <StatementCard label="A" statement={result.statement_a} quotes={quotes} />
          <span
            aria-hidden="true"
            className="absolute left-1/2 top-8 z-10 hidden h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full bg-linear-to-br from-petal-500 to-iris-600 text-[11px] font-bold uppercase text-white shadow-md shadow-petal-400/30 ring-4 ring-white lg:flex"
          >
            vs
          </span>
          <StatementCard label="B" statement={result.statement_b} quotes={quotes} />
        </div>
      </section>

      <EvidenceSection evidence={evidence} result={result} />

      <Link to="/results" className="btn-secondary">
        <Icon name="arrowLeft" className="h-4 w-4" />
        Back to results
      </Link>
    </div>
  )
}

function ContradictionDetail() {
  const { id } = useParams()
  const [state, setState] = useState({ id: null, status: 'loading', result: null, error: null })
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let ignore = false
    getAnalysisResult(id)
      .then((result) => {
        if (!ignore) setState({ id, status: 'success', result, error: null })
      })
      .catch((error) => {
        if (ignore) return
        // 422: the id is not a valid UUID, so no result can have it.
        const notFound = error.status === 404 || error.status === 422
        setState({ id, status: notFound ? 'not-found' : 'error', result: null, error: error.message })
      })
    return () => {
      ignore = true
    }
  }, [id, reloadKey])

  function reload() {
    setState({ id: null, status: 'loading', result: null, error: null })
    setReloadKey((key) => key + 1)
  }

  const status = state.id === id ? state.status : 'loading'

  return (
    <div className="space-y-6">
      <Breadcrumb id={id} />

      {status === 'loading' && <LoadingState>Loading finding…</LoadingState>}

      {status === 'not-found' && (
        <EmptyState
          title="Result not found"
          description={
            <>
              No analysis result exists with the ID <span className="break-all font-mono">{id}</span>. It may have
              been removed, or the link is incorrect.
            </>
          }
        >
          <Link to="/results" className="btn-primary">
            <Icon name="arrowLeft" className="h-4 w-4" />
            Back to results
          </Link>
        </EmptyState>
      )}

      {status === 'error' && <ErrorState title="Could not load this result" message={state.error} onRetry={reload} />}

      {status === 'success' && <ResultView result={state.result} />}
    </div>
  )
}

export default ContradictionDetail
