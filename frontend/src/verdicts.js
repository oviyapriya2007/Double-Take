export const VERDICT_STYLES = {
  CONTRADICTION: {
    label: 'Contradiction',
    description: 'The two statements make incompatible claims about the same subject.',
    badge: 'bg-linear-to-r from-petal-600 to-iris-600 text-white ring-transparent shadow-sm shadow-petal-600/25',
    accent: 'border-l-petal-500',
    surface: 'bg-linear-to-br from-petal-50 via-white to-iris-50',
    dot: 'bg-petal-500',
    icon: 'close',
  },
  UNCERTAIN: {
    label: 'Uncertain',
    description: 'There is not enough information to tell whether the statements conflict.',
    badge: 'bg-iris-100 text-iris-800 ring-iris-300',
    accent: 'border-l-iris-400',
    surface: 'bg-linear-to-br from-iris-50 via-white to-azure-50',
    dot: 'bg-iris-400',
    icon: 'question',
  },
  CONSISTENT: {
    label: 'Consistent',
    description: 'The two statements agree on this subject.',
    badge: 'bg-aqua-100 text-aqua-800 ring-aqua-300',
    accent: 'border-l-aqua-400',
    surface: 'bg-linear-to-br from-aqua-50 via-white to-azure-50',
    dot: 'bg-aqua-400',
    icon: 'check',
  },
}

export const NO_VERDICT = {
  label: 'No verdict',
  description: 'No verdict was recorded for this comparison.',
  badge: 'bg-slate-100 text-slate-600 ring-slate-200',
  accent: 'border-l-slate-300',
  surface: 'bg-white',
  dot: 'bg-slate-400',
  icon: 'minus',
}

export function verdictStyle(verdict) {
  return VERDICT_STYLES[verdict] ?? NO_VERDICT
}
