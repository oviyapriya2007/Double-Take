import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { runAnalysis, uploadDocuments } from '../api.js'
import { Icon } from '../components/Icon.jsx'
import { PageHeader } from '../components/PageHeader.jsx'
import { Alert, Spinner } from '../components/Status.jsx'
import { VerdictBadge } from '../components/Verdict.jsx'
import { resultsPath, saveCurrentAnalysis } from '../currentAnalysis.js'

function isPdf(file) {
  return file.name.toLowerCase().endsWith('.pdf')
}

function fileKey(file) {
  return `${file.name}:${file.size}:${file.lastModified}`
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function plural(count, word, pluralWord = `${word}s`) {
  return `${count} ${count === 1 ? word : pluralWord}`
}

function uploadLabel(count) {
  if (count === 0) return 'Upload PDFs'
  return `Upload ${plural(count, 'PDF')}`
}

function Section({ step, title, description, complete, locked, children }) {
  const marker = complete
    ? 'bg-aqua-100 text-aqua-700 ring-1 ring-aqua-300'
    : locked
      ? 'bg-slate-100 text-slate-400 ring-1 ring-slate-200'
      : 'bg-linear-to-br from-petal-500 to-iris-600 text-white shadow-sm shadow-petal-500/30'
  return (
    <section className={`card relative overflow-hidden p-5 sm:p-6 ${locked ? 'bg-slate-50/60 shadow-none' : ''}`}>
      {!locked && <div aria-hidden="true" className="brand-gradient absolute inset-x-0 top-0 h-1" />}
      <div className="mb-5 flex items-start gap-3">
        <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${marker}`}>
          {complete ? <Icon name="check" className="h-4 w-4" strokeWidth={2.5} /> : step}
        </span>
        <div className="min-w-0">
          <h2 className={`font-semibold ${locked ? 'text-slate-500' : 'text-slate-900'}`}>{title}</h2>
          {description && <p className="mt-0.5 text-sm text-slate-500">{description}</p>}
        </div>
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  )
}

function DropZone({ active, disabled, onBrowse, onDragOver, onDragLeave, onDrop }) {
  return (
    <button
      type="button"
      onClick={onBrowse}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      aria-disabled={disabled}
      className={`focus-ring group flex w-full flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition sm:py-12 ${
        disabled
          ? 'cursor-not-allowed border-slate-200 bg-slate-50 opacity-70'
          : active
            ? 'border-petal-400 bg-linear-to-br from-petal-100 via-iris-100 to-aqua-100 ring-4 ring-petal-100'
            : 'cursor-pointer border-iris-300 bg-linear-to-br from-petal-50 via-iris-50 to-aqua-50 hover:border-petal-400 hover:shadow-md hover:shadow-petal-200/50'
      }`}
    >
      <span
        className={`mb-4 flex h-14 w-14 items-center justify-center rounded-2xl transition ${
          active
            ? 'brand-gradient-strong scale-110 text-white shadow-lg shadow-petal-400/40'
            : 'brand-gradient-strong text-white shadow-md shadow-iris-500/25 group-hover:scale-105'
        }`}
      >
        <Icon name="upload" className="h-7 w-7" strokeWidth={1.6} />
      </span>
      <span className="text-base font-semibold text-slate-800">
        {active ? 'Release to add files' : 'Drop PDFs here'}
      </span>
      <span className="mt-1 text-sm text-slate-600">
        or <span className="font-medium text-iris-700 underline decoration-iris-300 underline-offset-2">browse your files</span>
      </span>
      <span className="mt-4 flex flex-wrap justify-center gap-1.5">
        <span className="chip bg-white">PDF only</span>
        <span className="chip bg-white">Text-based, not scanned</span>
        <span className="chip bg-white">Multiple files</span>
      </span>
    </button>
  )
}

function SelectedFiles({ files, disabled, onRemove, onClear }) {
  const totalBytes = files.reduce((sum, file) => sum + file.size, 0)
  return (
    <div className="overflow-hidden rounded-xl border border-iris-100">
      <div className="flex items-center justify-between gap-3 border-b border-iris-100 bg-linear-to-r from-petal-50 to-iris-50 px-4 py-2">
        <p className="text-xs font-medium text-slate-600">
          {plural(files.length, 'file')} ready <span className="text-slate-400">·</span> {formatBytes(totalBytes)}
        </p>
        <button type="button" onClick={onClear} disabled={disabled} className="btn-ghost -mr-2 px-2 py-1 text-xs">
          Clear all
        </button>
      </div>
      <ul className="divide-y divide-iris-50 bg-white">
        {files.map((file) => (
          <li key={fileKey(file)} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
            <div className="flex min-w-0 items-center gap-3">
              <span
                aria-hidden="true"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-petal-50 text-[10px] font-bold text-petal-700 ring-1 ring-petal-200"
              >
                PDF
              </span>
              <div className="min-w-0">
                <p className="truncate font-medium text-slate-800" title={file.name}>
                  {file.name}
                </p>
                <p className="text-xs text-slate-500">{formatBytes(file.size)}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onRemove(file)}
              disabled={disabled}
              className="btn-ghost shrink-0 p-1.5 hover:bg-red-50 hover:text-red-600"
              aria-label={`Remove ${file.name}`}
            >
              <Icon name="close" className="h-4 w-4" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function DocumentCard({ document }) {
  const showTitle = document.title && document.title !== document.filename.replace(/\.pdf$/i, '')
  return (
    <li className="flex gap-3 rounded-xl border border-iris-100 bg-white p-3.5 transition hover:border-petal-200 hover:shadow-sm hover:shadow-petal-100">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-aqua-100 text-aqua-700 ring-1 ring-aqua-300">
        <Icon name="document" className="h-5 w-5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-800" title={document.filename}>
          {document.filename}
        </p>
        {showTitle && (
          <p className="truncate text-xs text-slate-500" title={document.title}>
            {document.title}
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-1.5">
          <span className="chip">{plural(document.page_count, 'page')}</span>
          <span className="chip">{plural(document.chunk_count, 'chunk')}</span>
          {document.doc_type && <span className="chip">{document.doc_type}</span>}
          <span className="chip font-mono font-normal text-slate-500" title={document.id}>
            {document.id.slice(0, 8)}
          </span>
        </div>
      </div>
    </li>
  )
}

function formatElapsed(ms) {
  const seconds = Math.floor(ms / 1000)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function AnalysisProgress({ documents }) {
  const [start] = useState(() => Date.now())
  const [now, setNow] = useState(start)

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="overflow-hidden rounded-xl border border-iris-200 bg-linear-to-br from-petal-50 via-iris-50 to-aqua-50 p-4 shadow-sm shadow-iris-200/40 sm:p-5">
      <div role="status" className="flex items-start gap-3">
        <span className="brand-gradient-strong relative flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white">
          <span aria-hidden="true" className="absolute inset-0 animate-ping rounded-full bg-petal-300/40" />
          <Icon name="sparkles" className="relative h-5 w-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <p className="font-semibold text-slate-900">Analysing {plural(documents, 'document')}…</p>
            <span
              aria-hidden="true"
              className="inline-flex items-center gap-1 font-mono text-xs tabular-nums text-slate-500"
            >
              <Icon name="clock" className="h-3.5 w-3.5" />
              {formatElapsed(now - start)}
            </span>
          </div>
          <p className="mt-0.5 text-sm text-slate-600">
            Pairing related statements across documents and classifying each pair with Claude. This can take a few
            minutes; keep this page open.
          </p>
        </div>
      </div>
      <div aria-hidden="true" className="mt-4 h-2 overflow-hidden rounded-full bg-white ring-1 ring-inset ring-iris-100">
        <div className="h-full w-2/5 animate-indeterminate rounded-full bg-linear-to-r from-petal-400 via-iris-500 to-aqua-400" />
      </div>
    </div>
  )
}

const SUMMARY_FIELDS = [
  ['documents', 'Documents'],
  ['chunks', 'Chunks'],
  ['candidates_processed', 'Candidate pairs'],
  ['results_stored', 'New results'],
  ['skipped_existing', 'Already analysed'],
  ['errors', 'Errors'],
]

function AnalysisSummary({ summary }) {
  return (
    <div className="space-y-4 rounded-xl border border-aqua-300 bg-linear-to-br from-aqua-50 via-white to-iris-50 p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div role="status" className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-linear-to-br from-aqua-400 to-azure-500 text-white shadow-sm shadow-aqua-400/30">
            <Icon name="check" className="h-5 w-5" strokeWidth={2.5} />
          </span>
          <div className="text-sm">
            <p className="font-semibold text-slate-900">Analysis complete</p>
            <p className="mt-0.5 text-slate-600">
              {plural(summary.results_stored, 'new result')} stored for {plural(summary.documents, 'document')}.
            </p>
          </div>
        </div>
        <Link to={resultsPath(summary.document_ids)} className="btn-primary w-full sm:w-auto">
          View results
          <Icon name="arrowRight" className="h-4 w-4" />
        </Link>
      </div>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {SUMMARY_FIELDS.map(([key, label]) => (
          <div key={key} className="rounded-lg bg-white px-4 py-3 ring-1 ring-iris-100">
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd
              className={`mt-1 text-xl font-semibold tabular-nums ${
                key === 'errors' && summary.errors > 0 ? 'text-red-600' : 'text-slate-900'
              }`}
            >
              {summary[key]}
            </dd>
          </div>
        ))}
      </dl>
      {summary.errors > 0 && (
        <Alert tone="warning">
          {plural(summary.errors, 'candidate pair')} could not be analysed and{' '}
          {summary.errors === 1 ? 'was' : 'were'} skipped. Running the analysis again retries them.
        </Alert>
      )}
    </div>
  )
}

const HOW_IT_WORKS = [
  {
    icon: 'upload',
    tone: 'bg-petal-50 text-petal-700 ring-petal-200',
    title: 'Upload',
    text: 'Add specifications, procedures, manuals, datasheets or reports as text-based PDFs.',
  },
  {
    icon: 'sparkles',
    tone: 'bg-iris-50 text-iris-700 ring-iris-200',
    title: 'Analyse',
    text: 'Related technical statements are paired across documents and each pair is classified.',
  },
  {
    icon: 'list',
    tone: 'bg-azure-50 text-azure-700 ring-azure-200',
    title: 'Review',
    text: 'Every finding comes with a verdict, a confidence score and quoted evidence from both sources.',
  },
]

function HowItWorks() {
  return (
    <aside className="card relative space-y-5 overflow-hidden bg-linear-to-b from-white to-iris-50/70 p-5 lg:sticky lg:top-24">
      <div aria-hidden="true" className="brand-gradient absolute inset-x-0 top-0 h-1" />
      <h2 className="section-heading">How it works</h2>
      <ol className="space-y-4">
        {HOW_IT_WORKS.map(({ icon, tone, title, text }) => (
          <li key={title} className="flex gap-3">
            <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ring-1 ${tone}`}>
              <Icon name={icon} className="h-4 w-4" />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-800">{title}</p>
              <p className="mt-0.5 text-sm leading-relaxed text-slate-500">{text}</p>
            </div>
          </li>
        ))}
      </ol>
      <div className="border-t border-iris-100 pt-4">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Verdicts</p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <VerdictBadge verdict="CONTRADICTION" />
          <VerdictBadge verdict="CONSISTENT" />
          <VerdictBadge verdict="UNCERTAIN" />
        </div>
      </div>
    </aside>
  )
}

function Upload() {
  const inputRef = useRef(null)
  const [selected, setSelected] = useState([])
  const [rejected, setRejected] = useState([])
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [uploaded, setUploaded] = useState([])
  const [analysis, setAnalysis] = useState({ status: 'idle' })

  const analysing = analysis.status === 'running'
  const done = analysis.status === 'done'
  const busy = uploading || analysing

  function addFiles(fileList) {
    const files = Array.from(fileList)
    const pdfs = files.filter(isPdf)
    setRejected(files.filter((file) => !isPdf(file)).map((file) => file.name))
    setUploadError(null)
    setSelected((current) => {
      const keys = new Set(current.map(fileKey))
      return [...current, ...pdfs.filter((file) => !keys.has(fileKey(file)))]
    })
  }

  function removeFile(file) {
    setSelected((current) => current.filter((item) => fileKey(item) !== fileKey(file)))
  }

  function handleDragOver(event) {
    event.preventDefault()
    if (!busy) setDragActive(true)
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragActive(false)
    if (!busy) addFiles(event.dataTransfer.files)
  }

  function handleDragLeave(event) {
    if (!event.currentTarget.contains(event.relatedTarget)) setDragActive(false)
  }

  function handleBrowse() {
    if (!busy) inputRef.current?.click()
  }

  async function handleUpload() {
    if (!selected.length) {
      setUploadError('Select at least one PDF to upload.')
      return
    }
    setUploading(true)
    setUploadError(null)
    setRejected([])
    try {
      const documents = await uploadDocuments(selected)
      setUploaded((current) => [...current, ...documents])
      setSelected([])
      setAnalysis({ status: 'idle' })
    } catch (error) {
      setUploadError(error.message)
    } finally {
      setUploading(false)
    }
  }

  async function handleRunAnalysis() {
    if (uploaded.length < 2) return
    setAnalysis({ status: 'running' })
    try {
      const summary = await runAnalysis(uploaded.map((document) => document.id))
      saveCurrentAnalysis(summary.document_ids)
      setAnalysis({ status: 'done', summary })
    } catch (error) {
      setAnalysis({ status: 'error', error: error.message })
    }
  }

  function startOver() {
    setSelected([])
    setRejected([])
    setUploadError(null)
    setUploaded([])
    setAnalysis({ status: 'idle' })
  }

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="New analysis"
        title="Upload documents"
        description="Add two or more text-based PDFs. Double-Take compares them against each other and flags technical statements that disagree."
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_19rem] lg:items-start">
        <div className="space-y-6">
          <Section
            step={1}
            title="Add documents"
            description="Select the PDFs you want to compare."
            complete={uploaded.length >= 2 && selected.length === 0}
          >
            <DropZone
              active={dragActive}
              disabled={busy}
              onBrowse={handleBrowse}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            />
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf,.pdf"
              multiple
              className="hidden"
              onChange={(event) => {
                addFiles(event.target.files)
                event.target.value = ''
              }}
            />

            {rejected.length > 0 && (
              <Alert tone="warning" title="Some files were not added">
                Only PDF files are supported. Skipped: {rejected.join(', ')}
              </Alert>
            )}

            {selected.length > 0 && (
              <SelectedFiles
                files={selected}
                disabled={uploading}
                onRemove={removeFile}
                onClear={() => setSelected([])}
              />
            )}

            {uploadError && (
              <Alert tone="error" title="Upload failed">
                {uploadError}
              </Alert>
            )}

            {(selected.length > 0 || uploading) && (
              <button
                type="button"
                onClick={handleUpload}
                disabled={busy || !selected.length}
                className="btn-primary w-full sm:w-auto"
              >
                {uploading ? <Spinner /> : <Icon name="upload" className="h-4 w-4" />}
                {uploading ? 'Uploading…' : uploadLabel(selected.length)}
              </button>
            )}
          </Section>

          <Section
            step={2}
            title="Run analysis"
            description="Compare the uploaded documents against each other."
            complete={done}
            locked={uploaded.length === 0}
          >
            {uploaded.length === 0 ? (
              <p className="flex items-center gap-2 text-sm text-slate-500">
                <Icon name="lock" className="h-4 w-4 shrink-0 text-slate-400" />
                Upload at least two PDFs to enable analysis.
              </p>
            ) : (
              <>
                <div>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                    Analysis set · {plural(uploaded.length, 'document')}
                  </p>
                  <ul className="grid gap-3 sm:grid-cols-2">
                    {uploaded.map((document) => (
                      <DocumentCard key={document.id} document={document} />
                    ))}
                  </ul>
                </div>

                {uploaded.length < 2 && (
                  <Alert tone="info" title="Upload at least one more PDF">
                    Analysis compares documents against each other, so it needs at least two documents.
                  </Alert>
                )}

                {analysing && <AnalysisProgress documents={uploaded.length} />}

                {analysis.status === 'error' && (
                  <Alert tone="error" title="Analysis failed">
                    {analysis.error}
                  </Alert>
                )}

                {done && <AnalysisSummary summary={analysis.summary} />}

                <div className="flex flex-col gap-3 border-t border-iris-100 pt-4 sm:flex-row sm:items-center">
                  <button
                    type="button"
                    onClick={handleRunAnalysis}
                    disabled={busy || uploaded.length < 2}
                    className={done ? 'btn-secondary' : 'btn-primary'}
                  >
                    {analysing ? <Spinner /> : <Icon name={done ? 'refresh' : 'play'} className="h-4 w-4" />}
                    {analysing ? 'Analysing…' : done ? 'Run analysis again' : 'Run analysis'}
                  </button>
                  <button type="button" onClick={startOver} disabled={busy} className="btn-ghost sm:ml-auto">
                    Start over
                  </button>
                </div>
              </>
            )}
          </Section>
        </div>

        <HowItWorks />
      </div>
    </div>
  )
}

export default Upload
