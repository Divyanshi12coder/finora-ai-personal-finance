import { AlertCircle, KeyRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { ApiError, authApi } from '@/api'
import { AuthShell } from '@/components/layout/AuthShell'
import { Button } from '@/components/ui/Button'
import { Input, PasswordInput } from '@/components/ui/Input'
import { useToast } from '@/context/ToastContext'

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()

  const [token, setToken] = useState(searchParams.get('token') ?? '')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const mismatch = confirmation.length > 0 && password !== confirmation

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (mismatch) return

    setSubmitting(true)
    setError(null)
    setFieldErrors({})

    try {
      await authApi.resetPassword({ token, new_password: password })
      toast.success('Password reset', 'You can now sign in with your new password.')
      navigate('/login', { replace: true })
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message)
        setFieldErrors(caught.fieldErrors)
      } else {
        setError('Could not reset your password. Please request a new link.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      title="Choose a new password"
      subtitle="Reset links are single-use and expire 30 minutes after they are issued."
      footer={
        <Link to="/login" className="font-medium text-muted hover:text-navy">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-accent/30 bg-accent-tint px-3 py-2.5 text-xs text-accent-strong"
          >
            <AlertCircle className="mt-px h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        ) : null}

        <Input
          label="Reset token"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          error={fieldErrors.token}
          leftIcon={<KeyRound className="h-4 w-4" />}
          placeholder="Paste the token from your reset link"
          className="font-mono text-xs"
          required
        />

        <PasswordInput
          label="New password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.new_password}
          hint="At least 8 characters, including a letter and a number."
          required
        />

        <PasswordInput
          label="Confirm new password"
          autoComplete="new-password"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          error={mismatch ? 'Passwords do not match' : null}
          required
        />

        <Button
          type="submit"
          size="lg"
          fullWidth
          loading={submitting}
          disabled={mismatch || !token || !password}
        >
          Reset password
        </Button>
      </form>
    </AuthShell>
  )
}
