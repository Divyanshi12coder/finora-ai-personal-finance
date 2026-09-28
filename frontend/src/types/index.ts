/**
 * API types.
 *
 * These mirror the Pydantic schemas the backend exposes at /api/openapi.json.
 * Money arrives as a JSON string (the backend uses Decimal end to end and never
 * serialises money as a float), so amounts are typed `string` and converted at
 * the display boundary by `lib/format.ts`.
 */

export type TransactionType = 'income' | 'expense' | 'transfer'
export type CategoryKind = 'income' | 'expense' | 'both'
export type TransactionSource = 'manual' | 'receipt' | 'seed' | 'import'
export type AnomalyStatus = 'none' | 'flagged' | 'confirmed' | 'expected' | 'ignored'
export type ReceiptStatus = 'uploaded' | 'processing' | 'processed' | 'failed' | 'confirmed'
export type GoalStatus = 'active' | 'achieved' | 'paused' | 'archived'
export type BudgetingPreference = 'strict' | 'balanced' | 'flexible'
export type InsightSeverity = 'positive' | 'info' | 'warning' | 'critical'
export type BudgetItemStatusKind = 'on_track' | 'watch' | 'at_risk' | 'exceeded'

/** A money value: a decimal string such as "1234.56". */
export type Money = string

// --- Auth -------------------------------------------------------------------
export interface User {
  id: string
  email: string
  full_name: string
  currency: string
  monthly_income: Money | null
  income_source: string | null
  typical_monthly_expenses: Money | null
  savings_goal_amount: Money | null
  emergency_fund_target: Money | null
  budgeting_preference: BudgetingPreference
  onboarding_completed: boolean
  created_at: string
  last_login_at: string | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface OnboardingGoalInput {
  name: string
  target_amount: string
  target_date?: string | null
  goal_type: string
}

export interface OnboardingPayload {
  monthly_income: string
  income_source: string
  typical_monthly_expenses: string
  savings_goal_amount?: string | null
  emergency_fund_target?: string | null
  currency: string
  budgeting_preference: BudgetingPreference
  goals: OnboardingGoalInput[]
}

// --- Categories & transactions ---------------------------------------------
export interface Category {
  id: string
  name: string
  kind: CategoryKind
  color: string
  icon: string
  is_system: boolean
}

export interface Transaction {
  id: string
  amount: Money
  type: TransactionType
  occurred_on: string
  merchant: string | null
  description: string | null
  payment_method: string | null
  notes: string | null
  tags: string[] | null
  category: Category | null
  source: TransactionSource
  is_recurring: boolean
  ai_categorized: boolean
  ai_confidence: number | null
  anomaly_status: AnomalyStatus
  anomaly_score: number | null
  anomaly_reason: string | null
  receipt_id: string | null
  created_at: string
  updated_at: string
}

export interface TransactionInput {
  amount: string
  type: TransactionType
  occurred_on: string
  merchant?: string | null
  description?: string | null
  payment_method?: string | null
  notes?: string | null
  tags?: string[]
  category_id?: string | null
  auto_categorize?: boolean
  receipt_id?: string | null
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface TransactionQuery {
  search?: string
  type?: TransactionType | ''
  category_id?: string
  start?: string
  end?: string
  min_amount?: string
  max_amount?: string
  payment_method?: string
  anomalies_only?: boolean
  sort_by?: 'occurred_on' | 'amount' | 'merchant' | 'created_at'
  sort_dir?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export interface CategorySuggestion {
  category: string
  confidence: number
}

export interface CategorizePreview {
  available: boolean
  category: string | null
  category_id: string | null
  confidence: number | null
  alternatives: CategorySuggestion[]
  explanation: { token: string; contribution: number }[]
  model_version: string | null
  message: string | null
}

export interface CategorizerStatus {
  total_predictions: number
  accepted: number
  corrected: number
  acceptance_rate: number | null
  mean_confidence: number | null
  pending_training_examples: number
  model: {
    available: boolean
    pipeline_version: string | null
    trained_at: string | null
    age_days: number | null
    labels: string[]
    auto_apply_threshold: number
    high_confidence_threshold: number
    error: string | null
  }
}

// --- Budgets ----------------------------------------------------------------
export interface BudgetItemStatus {
  id: string
  category: Category
  limit_amount: Money
  spent: Money
  remaining: Money
  utilization: number
  status: BudgetItemStatusKind
  transaction_count: number
  daily_average: Money
  projected_spend: Money
  projected_overspend: Money
  recommended_amount: Money | null
  recommendation_basis: string | null
  warning: string | null
}

export interface Budget {
  id: string
  name: string
  period_month: string
  period_label: string
  total_limit: Money | null
  notes: string | null
  allocated: Money
  spent: Money
  remaining: Money
  utilization: number
  days_total: number
  days_elapsed: number
  days_remaining: number
  expected_utilization: number
  status: BudgetItemStatusKind
  items: BudgetItemStatus[]
  warnings: string[]
}

export interface BudgetInput {
  name: string
  period_month: string
  total_limit?: string | null
  notes?: string | null
  items: { category_id: string; limit_amount: string }[]
}

export interface BudgetRecommendationItem {
  category_id: string
  category_name: string
  recommended_amount: Money
  current_limit: Money | null
  method: string
  confidence: 'low' | 'medium' | 'high'
  months_analyzed: number
  monthly_history: { month: string; amount: number }[]
  mean: Money
  median: Money
  std_dev: Money
  trend_pct: number | null
  rationale: string
}

export interface BudgetRecommendations {
  period_month: string
  generated_at: string
  months_analyzed: number
  sufficient_data: boolean
  message: string | null
  total_recommended: Money
  items: BudgetRecommendationItem[]
  methodology: string
}

// --- Dashboard & analytics --------------------------------------------------
export interface MetricCard {
  key: string
  label: string
  value: Money
  previous_value: Money | null
  change_pct: number | null
  trend: 'up' | 'down' | 'flat'
  direction_is_good: boolean | null
  unit: 'currency' | 'percent'
  hint: string | null
}

export interface CategorySpend {
  category_id: string | null
  category: string
  color: string
  amount: Money
  percentage: number
  transaction_count: number
  average: Money
  previous_amount: Money | null
  change_pct: number | null
}

export interface MerchantSpend {
  merchant: string
  amount: Money
  transaction_count: number
  average: Money
  last_seen: string
  category: string | null
}

export interface RecurringExpense {
  merchant: string
  category: string | null
  occurrences: number
  average_amount: Money
  total_amount: Money
  median_interval_days: number
  cadence: string
  last_seen: string
  next_expected: string | null
  confidence: number
}

export interface MonthlyPoint {
  month: string
  label: string
  income: Money
  expense: Money
  savings: Money
  savings_rate: number
}

export interface DailyPoint {
  date: string
  label: string
  expense: Money
  income: Money
  transaction_count: number
}

export interface HealthComponent {
  key: string
  label: string
  score: number
  weight: number
  value: string
  impact: 'positive' | 'neutral' | 'negative'
  explanation: string
  available: boolean
}

export interface HealthScore {
  score: number
  grade: string
  band: string
  components: HealthComponent[]
  positives: string[]
  negatives: string[]
  methodology: string
  disclaimer: string
  computed_at: string
  has_data: boolean
}

export interface DashboardBudgetSummary {
  id: string
  name: string
  period_label: string
  spent: Money
  allocated: Money
  total_limit: Money | null
  remaining: Money
  utilization: number
  expected_utilization: number
  days_remaining: number
  status: BudgetItemStatusKind
  warnings: string[]
  top_categories: {
    id: string
    category: string
    category_id: string
    color: string
    icon: string
    limit_amount: Money
    spent: Money
    remaining: Money
    utilization: number
    status: BudgetItemStatusKind
    warning: string | null
  }[]
}

export interface GoalSummary {
  total_goals: number
  active_goals: number
  achieved_goals: number
  total_target: Money
  total_saved: Money
  overall_progress: number
  next_goal: Goal | null
}

export interface Dashboard {
  period: { start: string; end: string; label: string; days_elapsed: number }
  currency: string
  metrics: MetricCard[]
  income_vs_expense: { month: string; label: string; income: Money; expense: Money; savings: Money }[]
  category_breakdown: CategorySpend[]
  daily_spending: DailyPoint[]
  monthly_trend: MonthlyPoint[]
  recent_transactions: Transaction[]
  budget_summary: DashboardBudgetSummary | null
  goal_summary: GoalSummary
  health_score: Pick<HealthScore, 'score' | 'grade' | 'band' | 'components' | 'has_data'>
  top_insights: Insight[]
  anomaly_count: number
  has_data: boolean
}

export interface Analytics {
  period: { start: string; end: string; days: number }
  comparison_period: { start: string; end: string; days: number }
  currency: string
  totals: {
    income: Money
    expense: Money
    savings: Money
    savings_rate: number
    previous_income: Money
    previous_expense: Money
    income_change_pct: number | null
    expense_change_pct: number | null
  }
  by_category: CategorySpend[]
  by_merchant: MerchantSpend[]
  by_month: MonthlyPoint[]
  by_day: DailyPoint[]
  by_weekday: { weekday: string; amount: Money; transaction_count: number; average: Money }[]
  largest_expenses: Transaction[]
  recurring: RecurringExpense[]
  stats: {
    transaction_count: number
    expense_count: number
    average_transaction: Money
    median_transaction: Money
    largest_transaction: Money
    smallest_transaction: Money
    daily_average_spend: Money
    active_days: number
    distinct_merchants: number
  }
  has_data: boolean
}

// --- Forecast ---------------------------------------------------------------
export interface ForecastPoint {
  period: string
  date: string
  value: Money
  lower: Money | null
  upper: Money | null
  is_forecast: boolean
}

export interface ForecastSeries {
  name: string
  method: string
  history: ForecastPoint[]
  forecast: ForecastPoint[]
  model_detail: string
}

export interface Forecast {
  sufficient_data: boolean
  message: string | null
  months_of_history: number
  horizon_months: number
  generated_at: string
  currency: string
  income: ForecastSeries | null
  expense: ForecastSeries | null
  net_cashflow: ForecastPoint[]
  projected_balance: ForecastPoint[]
  limitations: string[]
  method_explanation: string
}

// --- Anomalies --------------------------------------------------------------
export interface Anomaly {
  transaction: Transaction
  score: number
  reason: string
  detail: Record<string, unknown>
}

export interface AnomalyResponse {
  sufficient_data: boolean
  message: string | null
  method: string
  analyzed_transactions: number
  anomalies: Anomaly[]
  baseline: Record<string, number>
  explanation: string
}

// --- Insights ---------------------------------------------------------------
export interface Insight {
  id: string
  type: string
  severity: InsightSeverity
  title: string
  summary: string
  why_it_matters: string | null
  suggested_action: string | null
  ai_explanation: string | null
  data: Record<string, unknown> | null
  period_start: string | null
  period_end: string | null
  is_read: boolean
  is_dismissed: boolean
  created_at: string
}

export interface InsightGenerateResponse {
  generated: number
  insights: Insight[]
  ai_enabled: boolean
  note: string | null
}

// --- Goals ------------------------------------------------------------------
export interface Contribution {
  id: string
  amount: Money
  occurred_on: string
  note: string | null
  created_at: string
}

export interface Goal {
  id: string
  name: string
  goal_type: string
  target_amount: Money
  current_amount: Money
  target_date: string | null
  status: GoalStatus
  icon: string
  color: string
  notes: string | null
  created_at: string
  progress_pct: number
  remaining: Money
  months_remaining: number | null
  suggested_monthly_contribution: Money | null
  projected_completion: string | null
  on_track: boolean | null
  pace_note: string
  contributions: Contribution[]
}

export interface GoalInput {
  name: string
  target_amount: string
  current_amount?: string
  target_date?: string | null
  goal_type?: string
  icon?: string
  color?: string
  notes?: string | null
}

// --- Receipts ---------------------------------------------------------------
export interface ReceiptItem {
  id: string
  line_number: number
  name: string
  quantity: Money | null
  unit_price: Money | null
  total_price: Money | null
}

export interface Receipt {
  id: string
  original_filename: string
  content_type: string
  file_size: number
  status: ReceiptStatus
  error_message: string | null
  merchant: string | null
  receipt_date: string | null
  subtotal: Money | null
  tax: Money | null
  total: Money | null
  currency: string
  ocr_engine: string | null
  ocr_confidence: number | null
  processing_ms: number | null
  field_confidence: Record<string, number> | null
  warnings: string[] | null
  items: ReceiptItem[]
  suggested_category: Category | null
  transaction_id: string | null
  raw_text: string | null
  created_at: string
  processed_at: string | null
  image_url: string
}

export interface OCRStatus {
  available: boolean
  engine: string
  version: string | null
  languages: string[]
  message: string
  install_hint: string | null
}

// --- AI ---------------------------------------------------------------------
export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  summary: string
}

export interface AIMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  tools_used: ToolCall[] | null
  retrieved_facts: Record<string, unknown> | null
  generation_mode: string | null
  created_at: string
}

export interface ChatResponse {
  conversation_id: string
  message: AIMessage
  tools_used: ToolCall[]
  generation_mode: 'llm' | 'deterministic'
  ai_configured: boolean
  suggestions: string[]
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface ConversationDetail {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages: AIMessage[]
}

export interface AIStatus {
  configured: boolean
  provider: string
  model: string | null
  mode: 'llm' | 'deterministic'
  message: string
  available_tools: { name: string; description: string }[]
}

// --- System -----------------------------------------------------------------
export interface HealthCheck {
  status: string
  version: string
  environment: string
  database: { connected: boolean; engine: string; error: string | null }
  ml_categorizer: { available: boolean; version: string | null; trained_at: string | null }
  ocr: { available: boolean; engine: string }
  ai: { configured: boolean; mode: string }
}
