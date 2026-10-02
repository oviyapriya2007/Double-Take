import { BrowserRouter, Link, Navigate, NavLink, Route, Routes } from 'react-router'
import { Icon } from './components/Icon.jsx'
import ContradictionDetail from './pages/ContradictionDetail.jsx'
import Results from './pages/Results.jsx'
import Upload from './pages/Upload.jsx'

const NAV_ITEMS = [
  { to: '/upload', label: 'Upload', icon: 'upload' },
  { to: '/results', label: 'Results', icon: 'list' },
]

function navLinkClass({ isActive }) {
  return `focus-ring inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-linear-to-r from-petal-100 to-iris-100 text-iris-800 ring-1 ring-inset ring-iris-200'
      : 'text-slate-600 hover:bg-petal-50 hover:text-iris-700'
  }`
}

function LogoMark() {
  return <img src="/logo-mark.png" alt="" width={249} height={144} className="h-9 w-auto shrink-0 sm:h-10" />
}

function Backdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-[30rem] bg-linear-to-b from-iris-50 via-petal-50/40 to-transparent" />
      <div className="absolute -right-32 -top-24 size-[26rem] rounded-full bg-petal-200/30 blur-3xl" />
      <div className="absolute -left-32 top-48 size-[22rem] rounded-full bg-aqua-200/25 blur-3xl" />
    </div>
  )
}

function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-iris-100 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
        <Link to="/upload" className="focus-ring flex min-w-0 items-center gap-3 rounded-lg">
          <LogoMark />
          <div className="min-w-0">
            <p className="text-lg font-bold leading-tight tracking-tight">
              <span className="brand-text">Double-Take</span>
            </p>
            <p className="hidden truncate text-xs text-slate-500 sm:block">
              Contradiction detection for technical documentation
            </p>
          </div>
        </Link>
        <nav aria-label="Main" className="flex shrink-0 gap-1">
          {NAV_ITEMS.map(({ to, label, icon }) => (
            <NavLink key={to} to={to} className={navLinkClass}>
              <Icon name={icon} className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div aria-hidden="true" className="brand-gradient absolute inset-x-0 -bottom-px h-0.5" />
    </header>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="relative isolate min-h-screen text-slate-900">
        <Backdrop />
        <Header />
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
          <Routes>
            <Route path="/upload" element={<Upload />} />
            <Route path="/results" element={<Results />} />
            <Route path="/results/:id" element={<ContradictionDetail />} />
            <Route path="*" element={<Navigate to="/upload" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
