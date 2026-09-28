import { AnimatePresence, motion } from 'framer-motion'
import {
  BarChart3,
  Bot,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  PiggyBank,
  Receipt,
  Settings,
  Sparkles,
  Sun,
  Target,
  Wallet,
  X,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { Logo, LogoMark } from '@/components/layout/Logo'
import { Button } from '@/components/ui/Button'
import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/context/ThemeContext'
import { useToast } from '@/context/ToastContext'
import { initials } from '@/lib/format'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
  icon: typeof LayoutDashboard
  /** Shown in the mobile bottom bar (space for five). */
  primary?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { to: '/app', label: 'Dashboard', icon: LayoutDashboard, primary: true },
  { to: '/app/transactions', label: 'Transactions', icon: Wallet, primary: true },
  { to: '/app/budgets', label: 'Budgets', icon: PiggyBank, primary: true },
  { to: '/app/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/app/receipts', label: 'Receipts', icon: Receipt },
  { to: '/app/insights', label: 'Insights', icon: Sparkles, primary: true },
  { to: '/app/goals', label: 'Goals', icon: Target },
  { to: '/app/assistant', label: 'Assistant', icon: Bot, primary: true },
]

function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme()
  return (
    <button
      type="button"
      onClick={toggle}
      className={cn(
        'flex h-9 w-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-subtle hover:text-ink',
        className,
      )}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ rotate: -90, opacity: 0 }}
          animate={{ rotate: 0, opacity: 1 }}
          exit={{ rotate: 90, opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </motion.span>
      </AnimatePresence>
    </button>
  )
}

function SidebarLink({ item, onNavigate }: { item: NavItem; onNavigate?: () => void }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      // `end` only on the index route, so /app/transactions does not also
      // highlight the dashboard link.
      end={item.to === '/app'}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200',
          isActive
            ? 'bg-white/10 text-white'
            : 'text-white/60 hover:bg-white/5 hover:text-white/90',
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive ? (
            <motion.span
              layoutId="sidebar-active"
              className="absolute left-0 h-6 w-[3px] rounded-r-full bg-accent"
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            />
          ) : null}
          <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden />
          <span className="truncate">{item.label}</span>
        </>
      )}
    </NavLink>
  )
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()

  async function handleLogout() {
    await logout()
    toast.success('Signed out', 'You have been logged out of Finora.')
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex h-full flex-col bg-navy-gradient">
      <div className="flex h-16 items-center px-5">
        <Logo inverted size={30} />
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2" aria-label="Main">
        {NAV_ITEMS.map((item) => (
          <SidebarLink key={item.to} item={item} onNavigate={onNavigate} />
        ))}
      </nav>

      <div className="border-t border-white/10 p-3">
        <NavLink
          to="/app/settings"
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
              isActive
                ? 'bg-white/10 text-white'
                : 'text-white/60 hover:bg-white/5 hover:text-white/90',
            )
          }
        >
          <Settings className="h-[18px] w-[18px]" aria-hidden />
          Settings
        </NavLink>

        <div className="mt-2 flex items-center gap-3 rounded-lg px-3 py-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-white">
            {initials(user?.full_name ?? 'U')}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-semibold text-white">{user?.full_name}</p>
            <p className="truncate text-2xs text-white/50">{user?.email}</p>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="rounded-md p-1.5 text-white/50 transition-colors hover:bg-white/10 hover:text-white"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string
  description?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between',
        className,
      )}
    >
      <div className="min-w-0">
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">{title}</h1>
        {description ? (
          <p className="mt-1 text-sm leading-relaxed text-muted">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  // Close the drawer whenever the route changes.
  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  // Lock scroll behind the mobile drawer.
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [mobileOpen])

  const mobileItems = NAV_ITEMS.filter((item) => item.primary)

  return (
    <div className="min-h-screen bg-canvas">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 lg:block">
        <SidebarContent />
      </aside>

      {/* Mobile drawer */}
      <AnimatePresence>
        {mobileOpen ? (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-navy/60 backdrop-blur-sm lg:hidden"
              onClick={() => setMobileOpen(false)}
              aria-hidden
            />
            <motion.aside
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
              className="fixed inset-y-0 left-0 z-50 w-64 lg:hidden"
              role="dialog"
              aria-label="Navigation menu"
            >
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="absolute right-3 top-4 z-10 rounded-lg p-2 text-white/70 hover:bg-white/10 hover:text-white"
                aria-label="Close menu"
              >
                <X className="h-5 w-5" />
              </button>
              <SidebarContent onNavigate={() => setMobileOpen(false)} />
            </motion.aside>
          </>
        ) : null}
      </AnimatePresence>

      <div className="lg:pl-60">
        {/* Sticky top bar */}
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-line bg-canvas/85 px-4 backdrop-blur-md sm:px-6">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-subtle hover:text-ink lg:hidden"
            aria-label="Open navigation menu"
          >
            <Menu className="h-5 w-5" />
          </button>

          <span className="lg:hidden">
            <LogoMark size={26} />
          </span>

          <div className="ml-auto flex items-center gap-1.5">
            <ThemeToggle />
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                window.location.href = '/app/assistant'
              }}
              leftIcon={<Bot className="h-3.5 w-3.5" />}
              className="hidden sm:inline-flex"
            >
              Ask Finora
            </Button>
          </div>
        </header>

        {/* Page body. Bottom padding leaves room for the mobile tab bar. */}
        <main className="px-4 pb-24 pt-6 sm:px-6 lg:pb-10">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="mx-auto max-w-7xl"
          >
            <Outlet />
          </motion.div>
        </main>
      </div>

      {/* Mobile bottom navigation */}
      <nav
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-canvas/95 backdrop-blur-md lg:hidden"
        aria-label="Primary"
      >
        <div className="flex items-stretch justify-around px-1 pb-[env(safe-area-inset-bottom)]">
          {mobileItems.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/app'}
                className={({ isActive }) =>
                  cn(
                    'flex flex-1 flex-col items-center gap-0.5 py-2.5 text-2xs font-semibold transition-colors',
                    isActive ? 'text-navy' : 'text-muted',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon className={cn('h-5 w-5', isActive && 'text-accent')} aria-hidden />
                    <span>{item.label}</span>
                  </>
                )}
              </NavLink>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
