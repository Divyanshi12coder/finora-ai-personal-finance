import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { ApiError, authApi, setUnauthorizedHandler, tokenStore } from '@/api'
import type { OnboardingPayload, User } from '@/types'

interface AuthContextValue {
  user: User | null
  /** True until the stored token has been validated against the API. */
  initialising: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<User>
  register: (data: {
    email: string
    password: string
    full_name: string
    currency?: string
  }) => Promise<User>
  logout: () => Promise<void>
  completeOnboarding: (payload: OnboardingPayload) => Promise<User>
  updateProfile: (data: Partial<User>) => Promise<User>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [initialising, setInitialising] = useState(true)

  // Validate any stored token on boot. A token can be expired or belong to a
  // deleted account, so the server is the authority — not localStorage.
  useEffect(() => {
    let cancelled = false

    async function restore() {
      if (!tokenStore.get()) {
        setInitialising(false)
        return
      }
      try {
        const profile = await authApi.me()
        if (!cancelled) setUser(profile)
      } catch (error) {
        if (error instanceof ApiError && error.isUnauthorized) tokenStore.clear()
      } finally {
        if (!cancelled) setInitialising(false)
      }
    }

    void restore()
    return () => {
      cancelled = true
    }
  }, [])

  // Any 401 from anywhere in the app clears the session.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null))
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login({ email, password })
    tokenStore.set(response.access_token)
    setUser(response.user)
    return response.user
  }, [])

  const register = useCallback(
    async (data: { email: string; password: string; full_name: string; currency?: string }) => {
      const response = await authApi.register(data)
      tokenStore.set(response.access_token)
      setUser(response.user)
      return response.user
    },
    [],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      // The token may already be invalid; the client-side clear is what matters.
    } finally {
      tokenStore.clear()
      setUser(null)
    }
  }, [])

  const completeOnboarding = useCallback(async (payload: OnboardingPayload) => {
    const updated = await authApi.completeOnboarding(payload)
    setUser(updated)
    return updated
  }, [])

  const updateProfile = useCallback(async (data: Partial<User>) => {
    const updated = await authApi.updateProfile(data)
    setUser(updated)
    return updated
  }, [])

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) return
    try {
      setUser(await authApi.me())
    } catch {
      /* handled by the global 401 handler */
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      initialising,
      isAuthenticated: Boolean(user),
      login,
      register,
      logout,
      completeOnboarding,
      updateProfile,
      refresh,
    }),
    [user, initialising, login, register, logout, completeOnboarding, updateProfile, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
