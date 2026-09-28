/**
 * Typed API surface, grouped by resource.
 *
 * Components import from here and never construct URLs themselves, so an
 * endpoint change is a one-line edit in this file.
 */

import { api } from './client'
import type {
  AIStatus,
  Analytics,
  AnomalyResponse,
  Budget,
  BudgetInput,
  BudgetRecommendations,
  CategorizePreview,
  CategorizerStatus,
  Category,
  ChatResponse,
  Conversation,
  ConversationDetail,
  Dashboard,
  Forecast,
  Goal,
  GoalInput,
  HealthCheck,
  HealthScore,
  Insight,
  InsightGenerateResponse,
  OCRStatus,
  OnboardingPayload,
  Page,
  Receipt,
  TokenResponse,
  Transaction,
  TransactionInput,
  TransactionQuery,
  User,
} from '@/types'

export { ApiError, tokenStore, setUnauthorizedHandler, resourceUrl } from './client'

// --- Auth -------------------------------------------------------------------
export const authApi = {
  register: (data: {
    email: string
    password: string
    full_name: string
    currency?: string
  }) => api.post<TokenResponse>('/auth/register', { currency: 'INR', ...data }),

  login: (data: { email: string; password: string }) =>
    api.post<TokenResponse>('/auth/login', data),

  logout: () => api.post<{ detail: string }>('/auth/logout'),

  me: (signal?: AbortSignal) => api.get<User>('/auth/me', undefined, signal),

  updateProfile: (data: Partial<User>) => api.patch<User>('/auth/me', data),

  completeOnboarding: (data: OnboardingPayload) =>
    api.post<User>('/auth/onboarding', data),

  changePassword: (data: { current_password: string; new_password: string }) =>
    api.post<{ detail: string }>('/auth/change-password', data),

  forgotPassword: (email: string) =>
    api.post<{ detail: string; reset_token: string | null }>('/auth/forgot-password', {
      email,
    }),

  resetPassword: (data: { token: string; new_password: string }) =>
    api.post<{ detail: string }>('/auth/reset-password', data),
}

// --- Categories -------------------------------------------------------------
export const categoryApi = {
  list: (signal?: AbortSignal) => api.get<Category[]>('/categories', undefined, signal),

  create: (data: { name: string; kind?: string; color?: string; icon?: string }) =>
    api.post<Category>('/categories', data),

  update: (id: string, data: { name?: string; color?: string; icon?: string }) =>
    api.patch<Category>(`/categories/${id}`, data),

  remove: (id: string) => api.delete<{ detail: string }>(`/categories/${id}`),
}

// --- Transactions -----------------------------------------------------------
export const transactionApi = {
  list: (query: TransactionQuery = {}, signal?: AbortSignal) =>
    api.get<Page<Transaction>>(
      '/transactions',
      query as Record<string, string | number | boolean | undefined>,
      signal,
    ),

  get: (id: string, signal?: AbortSignal) =>
    api.get<Transaction>(`/transactions/${id}`, undefined, signal),

  create: (data: TransactionInput) => api.post<Transaction>('/transactions', data),

  update: (id: string, data: Partial<TransactionInput> & { is_recurring?: boolean }) =>
    api.put<Transaction>(`/transactions/${id}`, data),

  remove: (id: string) => api.delete<{ detail: string }>(`/transactions/${id}`),

  bulkRemove: (ids: string[]) =>
    api.post<{ detail: string }>('/transactions/bulk-delete', { ids }),

  paymentMethods: (signal?: AbortSignal) =>
    api.get<string[]>('/transactions/payment-methods', undefined, signal),

  /** Live ML suggestion for the transaction form. Writes nothing. */
  categorizePreview: (
    data: {
      description?: string | null
      merchant?: string | null
      payment_method?: string | null
      type?: string
    },
    signal?: AbortSignal,
  ) => api.post<CategorizePreview>('/transactions/categorize-preview', data, signal),

  anomalyFeedback: (id: string, status: 'confirmed' | 'expected' | 'ignored') =>
    api.post<Transaction>(`/transactions/${id}/anomaly-feedback`, { status }),

  modelStatus: (signal?: AbortSignal) =>
    api.get<CategorizerStatus>('/ml/categorizer-status', undefined, signal),
}

// --- Budgets ----------------------------------------------------------------
export const budgetApi = {
  list: (signal?: AbortSignal) => api.get<Budget[]>('/budgets', undefined, signal),

  current: (signal?: AbortSignal) =>
    api.get<Budget | null>('/budgets/current', undefined, signal),

  get: (id: string, signal?: AbortSignal) =>
    api.get<Budget>(`/budgets/${id}`, undefined, signal),

  create: (data: BudgetInput) => api.post<Budget>('/budgets', data),

  update: (id: string, data: Partial<BudgetInput>) => api.put<Budget>(`/budgets/${id}`, data),

  remove: (id: string) => api.delete<{ detail: string }>(`/budgets/${id}`),

  recommendations: (periodMonth?: string, signal?: AbortSignal) =>
    api.get<BudgetRecommendations>(
      '/budgets/recommendations',
      periodMonth ? { period_month: periodMonth } : undefined,
      signal,
    ),

  applyRecommendations: (periodMonth: string, categoryIds?: string[]) =>
    api.post<Budget>('/budgets/recommendations/apply', {
      period_month: periodMonth,
      category_ids: categoryIds ?? null,
    }),
}

// --- Analytics --------------------------------------------------------------
export const analyticsApi = {
  dashboard: (signal?: AbortSignal) => api.get<Dashboard>('/dashboard', undefined, signal),

  spending: (
    params: { range?: string; start?: string; end?: string },
    signal?: AbortSignal,
  ) => api.get<Analytics>('/analytics/spending', params, signal),

  forecast: (horizon = 3, signal?: AbortSignal) =>
    api.get<Forecast>('/forecast', { horizon }, signal),

  healthScore: (signal?: AbortSignal) =>
    api.get<HealthScore>('/health-score', undefined, signal),

  anomalies: (signal?: AbortSignal) =>
    api.get<AnomalyResponse>('/anomalies', undefined, signal),
}

// --- Insights ---------------------------------------------------------------
export const insightApi = {
  list: (params: { include_dismissed?: boolean; limit?: number } = {}, signal?: AbortSignal) =>
    api.get<Insight[]>('/insights', params, signal),

  generate: () => api.post<InsightGenerateResponse>('/insights/generate'),

  markRead: (id: string) => api.post<Insight>(`/insights/${id}/read`),

  dismiss: (id: string) => api.post<{ detail: string }>(`/insights/${id}/dismiss`),
}

// --- Goals ------------------------------------------------------------------
export const goalApi = {
  list: (signal?: AbortSignal) => api.get<Goal[]>('/goals', undefined, signal),

  get: (id: string, signal?: AbortSignal) => api.get<Goal>(`/goals/${id}`, undefined, signal),

  create: (data: GoalInput) => api.post<Goal>('/goals', data),

  update: (id: string, data: Partial<GoalInput> & { status?: string }) =>
    api.put<Goal>(`/goals/${id}`, data),

  remove: (id: string) => api.delete<{ detail: string }>(`/goals/${id}`),

  contribute: (id: string, data: { amount: string; occurred_on?: string; note?: string }) =>
    api.post<Goal>(`/goals/${id}/contributions`, data),
}

// --- Receipts ---------------------------------------------------------------
export const receiptApi = {
  ocrStatus: (signal?: AbortSignal) =>
    api.get<OCRStatus>('/receipts/ocr-status', undefined, signal),

  list: (signal?: AbortSignal) => api.get<Receipt[]>('/receipts', undefined, signal),

  get: (id: string, signal?: AbortSignal) =>
    api.get<Receipt>(`/receipts/${id}`, undefined, signal),

  upload: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.upload<Receipt>('/receipts/upload', formData)
  },

  process: (id: string) => api.post<Receipt>(`/receipts/${id}/process`),

  update: (
    id: string,
    data: {
      merchant?: string | null
      receipt_date?: string | null
      subtotal?: string | null
      tax?: string | null
      total?: string | null
      suggested_category_id?: string | null
      items?: { name: string; quantity?: string | null; total_price?: string | null }[]
    },
  ) => api.patch<Receipt>(`/receipts/${id}`, data),

  confirm: (
    id: string,
    data: {
      merchant: string
      total: string
      occurred_on: string
      category_id?: string | null
      payment_method?: string | null
      notes?: string | null
      tax?: string | null
    },
  ) => api.post<Transaction>(`/receipts/${id}/confirm`, data),

  remove: (id: string) => api.delete<{ detail: string }>(`/receipts/${id}`),
}

// --- AI ---------------------------------------------------------------------
export const aiApi = {
  status: (signal?: AbortSignal) => api.get<AIStatus>('/ai/status', undefined, signal),

  suggestions: (signal?: AbortSignal) =>
    api.get<string[]>('/ai/suggestions', undefined, signal),

  chat: (message: string, conversationId?: string | null) =>
    api.post<ChatResponse>('/ai/chat', {
      message,
      conversation_id: conversationId ?? null,
    }),

  conversations: (signal?: AbortSignal) =>
    api.get<Conversation[]>('/ai/conversations', undefined, signal),

  conversation: (id: string, signal?: AbortSignal) =>
    api.get<ConversationDetail>(`/ai/conversations/${id}`, undefined, signal),

  removeConversation: (id: string) =>
    api.delete<{ detail: string }>(`/ai/conversations/${id}`),
}

// --- System -----------------------------------------------------------------
export const systemApi = {
  health: (signal?: AbortSignal) => api.get<HealthCheck>('/health', undefined, signal),
}
