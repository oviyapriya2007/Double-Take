import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { getAnalysisResults } from '../api.js'
import { Confidence } from '../components/Confidence.jsx'
import { Icon } from '../components/Icon.jsx'
import { PageHeader } from '../components/PageHeader.jsx'
import { StatementTag } from '../components/StatementTag.jsx'
import { EmptyState, ErrorState } from '../components/Status.jsx'
import { VerdictBadge } from '../components/Verdict.jsx'
import { loadCurrentAnalysis, resultsPath } from '../currentAnalysis.js'
import { formatConfidence, formatDate } from '../format.js'
import { evidenceQuote, statementTone } from '../statements.js'
import { verdictStyle } from '../verdicts.js'

const SORTS = [
  { value: 'newest', label: 'Newest first', compare: null },
  { value: 'confidence', label: 'Highest confidence', compare: (a, b) => (b.confidence ?? -1) - (a.confidence ?? -1) },
]

const SECONDARY_SECTIONS = [
  { verdict: 'UNCERTAIN', defaultOpen: true },
  { verdict: 'CONSISTENT', defaultOpen: false },
  { verdict: null, defaultOpen: false },
]

function matchesQuery(result, query) {
  if (!query) return true
  return [result.topic, result.reasoning, result.statement_a?.filename, result.statement_b?.filename].some((value) =>
    value?.toLowerCase().includes(query),
  )
}

function groupByVerdict(results) {
  const groups = { CONTRADICTION: [], UNCERTAIN: [], CONSISTENT: [], null: [] }
  for (const result of results) (groups[result.verdict] ?? groups.null).push(result)
  return groups
}

function ConflictingStatement({ label, statement, quote }) {
  if (!statement) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 px-4 py-3 text-sm text-slate-400">
        Statement {label} unavailable
      </div>
    )
  }
  const tone = statementTone(label)
  return (
    <div className={`min-w-0 rounded-xl border border-l-4 border-iris-100 px-4 py-3 ${tone.quote} ${tone.header}`}>
      <div className="flex min-w-0 items-center gap-2 text-xs">
        <StatementTag label={label} />
        <span className="min-w-0 truncate font-medium text-slate-700" title={statement.filename ?? undefined}>
          {statement.filename ?? 'Unknown document'}
        </span>
        {statement.page_number != null && <span className="shrink-0 text-slate-400">p. {statement.page_number}</span>}
      </div>
      <p className="mt-2 line-clamp-4 break-words text-sm leading-relaxed text-slate-800">
        {quote ? `“${quote}”` : statement.text}
      </p>
    </div>
  )
}

function ContradictionCard({ result }) {
  const created = formatDate(result.created_at)
  return (
    <li>
      <Link
        to={`/results/${result.id}`}
        className="card focus-ring group block overflow-hidden border-petal-200 border-l-4 border-l-petal-500 bg-linear-to-br from-white via-white to-petal-50/70 transition hover:-translate-y-px hover:border-petal-300 hover:border-l-petal-500 hover:shadow-lg hover:shadow-petal-300/30"
      >
        <div className="p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <VerdictBadge verdict="CONTRADICTION" />
                {created && <span className="text-xs text-slate-400">{created}</span>}
              </div>
              <h3 className="mt-2 text-lg font-semibold leading-snug tracking-tight text-slate-900 transition-colors group-hover:text-iris-700 sm:text-xl">
                {result.topic || 'Untitled comparison'}
              </h3>
            </div>
            <Confidence value={result.confidence} />
          </div>

          <div className="relative mt-4 grid gap-3 md:grid-cols-2 md:gap-5">
            <ConflictingStatement label="A" statement={result.statement_a} quote={evidenceQuote(result, 'A')} />
            <span
              aria-hidden="true"
              className="absolute left-1/2 top-1/2 z-10 hidden h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-linear-to-br from-petal-500 to-iris-600 text-[10px] font-bold uppercase text-white shadow-md shadow-petal-400/30 ring-2 ring-white md:flex"
            >
              vs
            </span>
            <ConflictingStatement label="B" statement={result.statement_b} quote={evidenceQuote(result, 'B')} />
          </div>

          {result.reasoning && (
            <p className="mt-4 line-clamp-2 text-sm leading-relaxed text-slate-600">
              <span className="font-medium text-slate-800">Why it conflicts: </span>
              {result.reasoning}
            </p>
          )}
        </div>
        <div className="flex items-center justify-end gap-1 border-t border-petal-100 bg-linear-to-r from-petal-50 via-iris-50 to-azure-50 px-5 py-2.5 text-sm font-medium text-petal-700 transition-colors group-hover:text-iris-700 sm:px-6">
          Review contradiction
          <Icon name="arrowRight" className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
        </div>
      </Link>
    </li>
  )
}

function ContradictionSection({ results, searching }) {
  const count = results.length
  return (
    <section aria-labelledby="contradictions-heading" className="space-y-4">
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-petal-500 to-iris-600 text-white shadow-md shadow-petal-400/30">
          <Icon name="alert" className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <h2 id="contradictions-heading" className="flex items-center gap-2 text-lg font-semibold text-slate-900 sm:text-xl">
            Contradictions
            <span className="rounded-full bg-petal-100 px-2 py-0.5 text-sm font-semibold tabular-nums text-petal-700 ring-1 ring-inset ring-petal-200">
              {count}
            </span>
          </h2>
          <p className="text-sm text-slate-500">Statements that cannot both be true. Review these first.</p>
        </div>
      </div>

      {count > 0 ? (
        <ul className="space-y-4">
          {results.map((result) => (
            <ContradictionCard key={result.id} result={result} />
          ))}
        </ul>
      ) : (
        <div className="flex items-center gap-3 rounded-2xl border border-aqua-300 bg-linear-to-r from-aqua-50 via-white to-azure-50 px-5 py-4 text-sm">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-aqua-400 to-azure-500 text-white">
            <Icon name="check" className="h-5 w-5" strokeWidth={2.5} />
          </span>
          <div>
            <p className="font-semibold text-slate-900">
              {searching ? 'No contradictions match your search' : 'No contradictions found'}
            </p>
            <p className="text-slate-600">
              {searching
                ? 'Clear the search to see every contradiction.'
                : 'None of the compared statements conflict with each other.'}
            </p>
          </div>
        </div>
      )}
    </section>
  )
}

function CompactRow({ result }) {
  const style = verdictStyle(result.verdict)
  return (
    <li>
      <Link
        to={`/results/${result.id}`}
        className="focus-ring group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-iris-50/60 sm:gap-4 sm:px-5"
      >
        <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${style.dot}`} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-slate-800 transition-colors group-hover:text-iris-700">
            {result.topic || 'Untitled comparison'}
          </p>
          <p className="mt-0.5 truncate text-xs text-slate-500">
            {result.statement_a?.filename ?? 'Unknown document'}
            <span className="px-1.5 text-slate-300">vs</span>
            {result.statement_b?.filename ?? 'Unknown document'}
          </p>
        </div>
        <span className="shrink-0 text-sm font-medium tabular-nums text-slate-600">
          <span className="sr-only">Confidence </span>
          {formatConfidence(result.confidence)}
        </span>
        <Icon name="chevronRight" className="h-4 w-4 shrink-0 text-slate-300 transition-colors group-hover:text-iris-500" />
      </Link>
    </li>
  )
}

function SecondarySection({ verdict, results, defaultOpen }) {
  if (!results.length) return null
  const style = verdictStyle(verdict)
  return (
    <details open={defaultOpen} className={`card group/section overflow-hidden border-l-4 ${style.accent}`}>
      <summary
        className={`focus-ring flex cursor-pointer list-none items-center gap-3 px-4 py-3.5 transition-colors hover:brightness-[0.98] sm:px-5 [&::-webkit-details-marker]:hidden ${style.surface}`}
      >
        <VerdictBadge verdict={verdict} />
        <span className="text-sm font-semibold tabular-nums text-slate-800">{results.length}</span>
        <span className="hidden min-w-0 truncate text-sm text-slate-500 sm:inline">{style.description}</span>
        <Icon
          name="chevronRight"
          className="ml-auto h-4 w-4 shrink-0 text-slate-400 transition-transform group-open/section:rotate-90"
        />
      </summary>
      <ul className="divide-y divide-iris-50 border-t border-iris-100">
        {results.map((result) => (
          <CompactRow key={result.id} result={result} />
        ))}
      </ul>
    </details>
  )
}

function VerdictSummary({ groups, total, loading }) {
  const contradictions = groups.CONTRADICTION.length
  const flagged = loading || contradictions > 0
  const stats = [
    ['Uncertain', groups.UNCERTAIN.length, verdictStyle('UNCERTAIN').dot],
    ['Consistent', groups.CONSISTENT.length, verdictStyle('CONSISTENT').dot],
    ['Total findings', total, 'bg-linear-to-br from-petal-400 to-azure-400'],
  ]
  return (
    <div className="card flex flex-col overflow-hidden sm:flex-row">
      <div
        className={`flex items-center gap-4 px-5 py-4 sm:w-2/5 ${
          flagged
            ? 'bg-linear-to-br from-petal-100 via-petal-50 to-iris-100'
            : 'bg-linear-to-br from-aqua-50 via-white to-azure-50'
        }`}
      >
        <span
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-linear-to-br text-white shadow-md ${
            flagged ? 'from-petal-500 to-iris-600 shadow-petal-400/30' : 'from-aqua-400 to-azure-500 shadow-aqua-400/30'
          }`}
        >
          <Icon name={flagged ? 'alert' : 'check'} className="h-5 w-5" strokeWidth={2} />
        </span>
        <div>
          <p className={`text-3xl font-semibold leading-none tabular-nums ${flagged ? 'text-petal-600' : 'text-aqua-700'}`}>
            {loading ? '–' : contradictions}
          </p>
          <p className="mt-1 text-sm font-medium text-slate-700">
            {contradictions === 1 ? 'Contradiction found' : 'Contradictions found'}
          </p>
        </div>
      </div>
      <dl className="grid flex-1 grid-cols-3 divide-x divide-iris-100 border-t border-iris-100 sm:border-t-0 sm:border-l">
        {stats.map(([label, value, dot]) => (
          <div key={label} className="px-4 py-4">
            <dt className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
              <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
              <span className="truncate">{label}</span>
            </dt>
            <dd className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{loading ? '–' : value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function ResultsSkeleton() {
  return (
    <div role="status" className="space-y-4">
      {[0, 1].map((index) => (
        <div key={index} aria-hidden="true" className="card animate-pulse border-l-4 border-l-petal-200 p-5 sm:p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="h-5 w-32 rounded-full bg-petal-100" />
              <div className="mt-3 h-6 w-2/3 rounded bg-slate-100" />
            </div>
            <div className="h-12 w-16 rounded-lg bg-iris-50" />
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="h-24 rounded-xl bg-iris-50" />
            <div className="h-24 rounded-xl bg-petal-50" />
          </div>
        </div>
      ))}
      <span className="sr-only">Loading results…</span>
    </div>
  )
}

function analysedDocumentIds(searchParams) {
  if (searchParams.has('all')) return null
  const fromUrl = (searchParams.get('document_ids') ?? '').split(',').filter(Boolean)
  return fromUrl.length > 0 ? fromUrl : loadCurrentAnalysis()
}

function ScopeBar({ documentIds }) {
  const current = loadCurrentAnalysis()
  if (!documentIds && !current) return null
  const segment = (active) =>
    `focus-ring rounded-md px-3 py-1.5 text-sm font-medium transition ${
      active ? 'bg-white text-iris-700 shadow-sm ring-1 ring-iris-200' : 'text-slate-600 hover:text-iris-700'
    }`
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <nav aria-label="Result scope" className="inline-flex self-start rounded-lg bg-iris-50 p-1 ring-1 ring-iris-100">
        {documentIds ? (
          <span aria-current="page" className={segment(true)}>
            Current analysis
          </span>
        ) : (
          <Link to={resultsPath(current)} className={segment(false)}>
            Current analysis
          </Link>
        )}
        {documentIds ? (
          <Link to="/results?all" className={segment(false)}>
            All stored results
          </Link>
        ) : (
          <span aria-current="page" className={segment(true)}>
            All stored results
          </span>
        )}
      </nav>
      <p className="text-sm text-slate-500">
        {documentIds
          ? `Showing the current analysis of ${documentIds.length} documents.`
          : 'Showing every stored result, including earlier analyses.'}
      </p>
    </div>
  )
}

function Results() {
  const [searchParams] = useSearchParams()
  const documentIds = analysedDocumentIds(searchParams)
  const scope = documentIds?.join(',') ?? ''
  const [state, setState] = useState({ status: 'loading', results: [], error: null, scope: null })
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState('newest')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let ignore = false
    getAnalysisResults(scope ? scope.split(',') : null)
      .then((results) => {
        if (!ignore) setState({ status: 'success', results, error: null, scope })
      })
      .catch((error) => {
        if (!ignore) setState({ status: 'error', results: [], error: error.message, scope })
      })
    return () => {
      ignore = true
    }
  }, [reloadKey, scope])

  function reload() {
    setState((current) => ({ ...current, status: 'loading', error: null }))
    setReloadKey((key) => key + 1)
  }

  const { results, error } = state
  const status = state.scope === scope ? state.status : 'loading'
  const loaded = status === 'success'
  const normalizedQuery = query.trim().toLowerCase()
  const { compare } = SORTS.find(({ value }) => value === sort)
  const matching = results.filter((result) => matchesQuery(result, normalizedQuery))
  const visible = groupByVerdict(compare ? [...matching].sort(compare) : matching)
  const secondaryCount = visible.UNCERTAIN.length + visible.CONSISTENT.length + visible.null.length

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Findings"
        title="Analysis results"
        description="Contradictions are listed first. Each finding compares two statements from different documents."
        actions={
          <button type="button" onClick={reload} disabled={status === 'loading'} className="btn-secondary">
            <Icon name="refresh" className={`h-4 w-4 ${status === 'loading' ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        }
      />

      <ScopeBar documentIds={documentIds} />

      {status !== 'error' && !(loaded && results.length === 0) && (
        <VerdictSummary groups={groupByVerdict(results)} total={results.length} loading={!loaded} />
      )}

      {status === 'loading' && <ResultsSkeleton />}

      {status === 'error' && <ErrorState title="Could not load results" message={error} onRetry={reload} />}

      {loaded && results.length === 0 && (
        <EmptyState
          icon="document"
          title={documentIds ? 'No results for the current analysis' : 'No analysis results yet'}
          description="Upload at least two documents and run an analysis to see findings here."
        >
          <Link to="/upload" className="btn-primary">
            <Icon name="upload" className="h-4 w-4" />
            Go to Upload
          </Link>
          {documentIds && (
            <Link to="/results?all" className="btn-secondary">
              Show all stored results
            </Link>
          )}
        </EmptyState>
      )}

      {loaded && results.length > 0 && (
        <>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Icon
                name="search"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
              />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search topics, reasoning or filenames"
                aria-label="Search results"
                className="input pl-9"
              />
            </div>
            <div className="flex items-center justify-between gap-3">
              {normalizedQuery && (
                <p className="text-sm whitespace-nowrap text-slate-500 tabular-nums">
                  {matching.length} of {results.length}
                </p>
              )}
              <select
                value={sort}
                onChange={(event) => setSort(event.target.value)}
                aria-label="Sort results"
                className="input w-auto cursor-pointer pr-8"
              >
                {SORTS.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {matching.length === 0 ? (
            <EmptyState title="No findings match your search" description="Try a different search term.">
              <button type="button" onClick={() => setQuery('')} className="btn-secondary">
                Clear search
              </button>
            </EmptyState>
          ) : (
            <>
              <ContradictionSection results={visible.CONTRADICTION} searching={Boolean(normalizedQuery)} />

              {secondaryCount > 0 && (
                <section aria-labelledby="other-findings-heading" className="space-y-3 pt-2">
                  <h2 id="other-findings-heading" className="section-heading">
                    Other findings
                  </h2>
                  {SECONDARY_SECTIONS.map(({ verdict, defaultOpen }) => (
                    <SecondarySection
                      key={verdict ?? 'none'}
                      verdict={verdict}
                      results={visible[verdict]}
                      defaultOpen={defaultOpen}
                    />
                  ))}
                </section>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}

export default Results
