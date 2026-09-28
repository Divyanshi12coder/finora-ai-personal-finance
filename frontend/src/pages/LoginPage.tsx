import { AlertCircle, Mail, Sparkles } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '@/api'
import { AuthShell } from '@/components/layout/AuthShell'
import { Button } from '@/components/ui/Button'
import { Input, PasswordInput } from '@/components/ui/Input'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'

const DEMO_EMAIL = 'demo@finora.app'
const DEMO_PASSWORD = 'FinoraDemo123!'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/app'

  async function submit(credentials: { email: string; password: string }) {
    setSubmitting(true)
    setFormError(null)
    setFieldErrors({})

    try {
      const user = await login(credentials.email, credentials.password)
      toast.success(`Welcome back, ${user.full_name.split(' ')[0]}`)
      navigate(user.onboarding_completed ? redirectTo : '/onboarding', { replace: true })
    } catch (error) {
      if (error instanceof ApiError) {
        setFormError(error.message)
        setFieldErrors(error.fieldErrors)
      } else {
        setFormError('Could not sign in. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    void submit({ email, password })
  }

  function handleDemo() {
    setEmail(DEMO_EMAIL)
    setPassword(DEMO_PASSWORD)
    void submit({ email: DEMO_EMAIL, password: DEMO_PASSWORD })
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to pick up where you left off."
      footer={
        <span className="text-muted">
          New to Finora?{' '}
          <Link to="/register" className="font-semibold text-navy hover:underline">
            Create an account
          </Link>
        </span>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {formError ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-accent/30 bg-accent-tint px-3 py-2.5 text-xs text-accent-strong"
          >
            <AlertCircle className="mt-px h-4 w-4 shrink-0" aria-hidden />
            <span>{formError}</span>
          </div>
        ) : null}

        <Input
          label="Email address"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldErrors.email}
          leftIcon={<Mail className="h-4 w-4" />}
          required
        />

        <div>
          <PasswordInput
            label="Password"
            autoComplete="current-password"
            placeholder="Your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            error={fieldErrors.password}
            required
          />
          <div className="mt-2 text-right">
            <Link
              to="/forgot-password"
              className="text-xs font-medium text-muted hover:text-navy hover:underline"
            >
              Forgot your password?
            </Link>
          </div>
        </div>

        <Button type="submit" size="lg" fullWidth loading={submitting}>
          Sign in
        </Button>
      </form>

      <div className="my-5 flex items-center gap-3">
        <span className="h-px flex-1 bg-line" />
        <span className="text-2xs font-semibold uppercase tracking-wider text-faint">or</span>
        <span className="h-px flex-1 bg-line" />
      </div>

      {/*
        The demo account is real: it is created by `python -m app.seed` and its
        data goes through the same API as any other account.
      */}
      <Button
        variant="outline"
        size="lg"
        fullWidth
        onClick={handleDemo}
        disabled={submitting}
        leftIcon={<Sparkles className="h-4 w-4 text-accent" />}
      >
        Explore the demo account
      </Button>
      <p className="mt-2 text-center text-2xs leading-relaxed text-faint">
        Nine months of realistic seeded data. Requires the backend seed to have
        been run.
      </p>
    </AuthShell>
  )
}
