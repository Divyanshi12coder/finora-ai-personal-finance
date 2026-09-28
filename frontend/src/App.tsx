import { Suspense, lazy } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { AppLayout } from '@/components/layout/AppLayout'
import { LogoMark } from '@/components/layout/Logo'
import { AuthProvider, useAuth } from '@/context/AuthContext'
import { ThemeProvider } from '@/context/ThemeContext'
import { ToastProvider } from '@/context/ToastContext'

import LandingPage from '@/pages/LandingPage'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import ForgotPasswordPage from '@/pages/ForgotPasswordPage'
import ResetPasswordPage from '@/pages/ResetPasswordPage'
import OnboardingPage from '@/pages/OnboardingPage'
import DashboardPage from '@/pages/DashboardPage'
import NotFoundPage from '@/pages/NotFoundPage'

// Heavier feature pages are split out so the landing page and login stay fast.
const TransactionsPage = lazy(() => import('@/pages/TransactionsPage'))
const BudgetsPage = lazy(() => import('@/pages/BudgetsPage'))
const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage'))
const ReceiptsPage = lazy(() => import('@/pages/ReceiptsPage'))
const InsightsPage = lazy(() => import('@/pages/InsightsPage'))
const GoalsPage = lazy(() => import('@/pages/GoalsPage'))
const AssistantPage = lazy(() => import('@/pages/AssistantPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))

function FullScreenLoader({ label = 'Loading Finora' }: { label?: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-canvas">
      <div className="relative">
        <span className="absolute inset-0 animate-pulse-ring rounded-xl bg-navy/30" aria-hidden />
        <LogoMark size={44} className="relative" />
      </div>
      <p className="text-sm font-medium text-muted">{label}…</p>
    </div>
  )
}

/**
 * Gate for authenticated routes.
 *
 * Note this is a UX control, not a security boundary: every endpoint enforces
 * authentication and per-user ownership server-side. Removing this component
 * would reveal empty shells, never another user's data.
 */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, initialising, user } = useAuth()
  const location = useLocation()

  if (initialising) return <FullScreenLoader label="Restoring your session" />

  if (!isAuthenticated) {
    // Remember where they were headed so login can return them there.
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  if (!user?.onboarding_completed && location.pathname !== '/onboarding') {
    return <Navigate to="/onboarding" replace />
  }

  return <>{children}</>
}

/** Keeps a logged-in user away from the login/register screens. */
function RedirectIfAuthenticated({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, initialising, user } = useAuth()

  if (initialising) return <FullScreenLoader label="Restoring your session" />
  if (isAuthenticated) {
    return <Navigate to={user?.onboarding_completed ? '/app' : '/onboarding'} replace />
  }
  return <>{children}</>
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />

      <Route
        path="/login"
        element={
          <RedirectIfAuthenticated>
            <LoginPage />
          </RedirectIfAuthenticated>
        }
      />
      <Route
        path="/register"
        element={
          <RedirectIfAuthenticated>
            <RegisterPage />
          </RedirectIfAuthenticated>
        }
      />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      <Route
        path="/onboarding"
        element={
          <RequireAuth>
            <OnboardingPage />
          </RequireAuth>
        }
      />

      <Route
        path="/app"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route
          path="transactions"
          element={
            <Suspense fallback={<PageFallback />}>
              <TransactionsPage />
            </Suspense>
          }
        />
        <Route
          path="budgets"
          element={
            <Suspense fallback={<PageFallback />}>
              <BudgetsPage />
            </Suspense>
          }
        />
        <Route
          path="analytics"
          element={
            <Suspense fallback={<PageFallback />}>
              <AnalyticsPage />
            </Suspense>
          }
        />
        <Route
          path="receipts"
          element={
            <Suspense fallback={<PageFallback />}>
              <ReceiptsPage />
            </Suspense>
          }
        />
        <Route
          path="insights"
          element={
            <Suspense fallback={<PageFallback />}>
              <InsightsPage />
            </Suspense>
          }
        />
        <Route
          path="goals"
          element={
            <Suspense fallback={<PageFallback />}>
              <GoalsPage />
            </Suspense>
          }
        />
        <Route
          path="assistant"
          element={
            <Suspense fallback={<PageFallback />}>
              <AssistantPage />
            </Suspense>
          }
        />
        <Route
          path="settings"
          element={
            <Suspense fallback={<PageFallback />}>
              <SettingsPage />
            </Suspense>
          }
        />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

function PageFallback() {
  return (
    <div className="space-y-4">
      <div className="skeleton h-8 w-52" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="skeleton h-32 rounded-2xl" />
        ))}
      </div>
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <ToastProvider>
            <AppRoutes />
          </ToastProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  )
}
