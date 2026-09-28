import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, CheckCircle2, Info, TriangleAlert, X } from 'lucide-react'
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { cn } from '@/lib/utils'

type ToastVariant = 'success' | 'error' | 'warning' | 'info'

interface Toast {
  id: number
  title: string
  description?: string
  variant: ToastVariant
  action?: { label: string; onClick: () => void }
}

interface ToastContextValue {
  toast: (options: Omit<Toast, 'id'>) => void
  success: (title: string, description?: string) => void
  error: (title: string, description?: string) => void
  warning: (title: string, description?: string) => void
  info: (title: string, description?: string) => void
  dismiss: (id: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const DURATIONS: Record<ToastVariant, number> = {
  success: 3500,
  info: 4000,
  warning: 6000,
  // Errors stay longer: the user usually needs to read and act on them.
  error: 7000,
}

const ICONS = {
  success: CheckCircle2,
  error: AlertCircle,
  warning: TriangleAlert,
  info: Info,
} as const

const STYLES: Record<ToastVariant, string> = {
  success: 'border-positive/30 bg-surface',
  error: 'border-accent/40 bg-surface',
  warning: 'border-warning/40 bg-surface',
  info: 'border-navy/25 bg-surface',
}

const ICON_STYLES: Record<ToastVariant, string> = {
  success: 'text-positive',
  error: 'text-accent',
  warning: 'text-warning',
  info: 'text-navy',
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const counter = useRef(0)
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((item) => item.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const toast = useCallback(
    (options: Omit<Toast, 'id'>) => {
      counter.current += 1
      const id = counter.current
      // Cap the stack so a burst of failures cannot cover the screen.
      setToasts((current) => [...current.slice(-2), { ...options, id }])

      const timer = setTimeout(() => dismiss(id), DURATIONS[options.variant])
      timers.current.set(id, timer)
    },
    [dismiss],
  )

  const value = useMemo<ToastContextValue>(
    () => ({
      toast,
      dismiss,
      success: (title, description) => toast({ title, description, variant: 'success' }),
      error: (title, description) => toast({ title, description, variant: 'error' }),
      warning: (title, description) => toast({ title, description, variant: 'warning' }),
      info: (title, description) => toast({ title, description, variant: 'info' }),
    }),
    [toast, dismiss],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}

      <div
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[100] flex flex-col items-center gap-2 p-4 sm:inset-auto sm:bottom-6 sm:right-6 sm:items-end"
        // Announced politely so a screen reader is not interrupted mid-sentence.
        role="status"
        aria-live="polite"
      >
        <AnimatePresence initial={false}>
          {toasts.map((item) => {
            const Icon = ICONS[item.variant]
            return (
              <motion.div
                key={item.id}
                layout
                initial={{ opacity: 0, y: 16, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 8, scale: 0.97 }}
                transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                className={cn(
                  'pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border p-3.5 shadow-float',
                  STYLES[item.variant],
                )}
              >
                <Icon
                  className={cn('mt-0.5 h-5 w-5 shrink-0', ICON_STYLES[item.variant])}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-ink">{item.title}</p>
                  {item.description ? (
                    <p className="mt-0.5 text-xs leading-relaxed text-muted">
                      {item.description}
                    </p>
                  ) : null}
                  {item.action ? (
                    <button
                      type="button"
                      onClick={() => {
                        item.action?.onClick()
                        dismiss(item.id)
                      }}
                      className="mt-2 text-xs font-semibold text-navy underline-offset-2 hover:underline"
                    >
                      {item.action.label}
                    </button>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => dismiss(item.id)}
                  className="shrink-0 rounded-md p-1 text-faint transition-colors hover:bg-subtle hover:text-ink"
                  aria-label="Dismiss notification"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used within a ToastProvider')
  return context
}
