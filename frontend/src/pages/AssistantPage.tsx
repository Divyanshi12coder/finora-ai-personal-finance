import { AnimatePresence, motion } from 'framer-motion'
import {
  Bot,
  ChevronDown,
  Database,
  Info,
  Plus,
  Send,
  Sparkles,
  Trash2,
} from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'

import { ApiError, aiApi } from '@/api'
import { PageHeader } from '@/components/layout/AppLayout'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Misc'
import { ErrorState } from '@/components/ui/States'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { useApi } from '@/hooks/useApi'
import { formatRelative, initials } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { AIMessage, ToolCall } from '@/types'

/** Shows exactly which backend data the answer was built from. */
function ToolTrace({ tools }: { tools: ToolCall[] }) {
  const [open, setOpen] = useState(false)
  if (tools.length === 0) return null

  return (
    <div className="mt-2.5 border-t border-line/70 pt-2.5">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1.5 text-2xs font-semibold text-navy hover:underline"
      >
        <Database className="h-3 w-3" />
        {tools.length} data {tools.length === 1 ? 'lookup' : 'lookups'} used
        <ChevronDown className={cn('h-3 w-3 transition-transform', open && 'rotate-180')} />
      </button>

      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-2 space-y-1.5">
              {tools.map((tool, index) => (
                <div key={index} className="rounded-lg bg-black/[0.04] px-2.5 py-2">
                  <p className="font-mono text-2xs font-semibold text-navy">
                    {tool.name}()
                  </p>
                  <p className="mt-0.5 text-2xs leading-relaxed text-muted">
                    {tool.summary}
                  </p>
                </div>
              ))}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}

function MessageBubble({ message, userName }: { message: AIMessage; userName: string }) {
  const isUser = message.role === 'user'

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      className={cn('flex gap-3', isUser && 'flex-row-reverse')}
    >
      <span
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-2xs font-bold',
          isUser ? 'bg-subtle text-ink' : 'bg-navy text-white',
        )}
        aria-hidden
      >
        {isUser ? initials(userName) : <Bot className="h-4 w-4" />}
      </span>

      <div className={cn('min-w-0 max-w-[85%]', isUser && 'text-right')}>
        <div
          className={cn(
            'inline-block rounded-2xl px-4 py-3 text-left',
            isUser
              ? 'bg-navy text-white'
              : 'border border-line bg-surface text-ink',
          )}
        >
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>

          {!isUser && message.tools_used && message.tools_used.length > 0 ? (
            <ToolTrace tools={message.tools_used} />
          ) : null}
        </div>

        <p className="mt-1 px-1 text-2xs text-faint">
          {formatRelative(message.created_at)}
          {!isUser && message.generation_mode ? (
            <span> · {message.generation_mode === 'llm' ? 'AI phrased' : 'built-in explainer'}</span>
          ) : null}
        </p>
      </div>
    </motion.div>
  )
}

export default function AssistantPage() {
  const { user } = useAuth()
  const toast = useToast()

  const [conversationId, setConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AIMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const { data: status } = useApi((signal) => aiApi.status(signal), [])
  const { data: starters } = useApi((signal) => aiApi.suggestions(signal), [])
  const { data: conversations, refetch: refetchConversations } = useApi(
    (signal) => aiApi.conversations(signal),
    [],
  )

  // Keep the newest message in view.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    })
  }, [messages, sending])

  async function send(text: string) {
    const question = text.trim()
    if (!question || sending) return

    setSending(true)
    setError(null)
    setInput('')

    // Optimistic user message so the conversation feels immediate.
    const pending: AIMessage = {
      id: `pending-${Date.now()}`,
      role: 'user',
      content: question,
      tools_used: null,
      retrieved_facts: null,
      generation_mode: null,
      created_at: new Date().toISOString(),
    }
    setMessages((current) => [...current, pending])

    try {
      const response = await aiApi.chat(question, conversationId)
      setConversationId(response.conversation_id)
      setMessages((current) => [...current, response.message])
      setSuggestions(response.suggestions)
      void refetchConversations()
    } catch (caught) {
      // Roll the optimistic message back so the transcript stays truthful.
      setMessages((current) => current.filter((message) => message.id !== pending.id))
      setInput(question)
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not reach the assistant. Please try again.',
      )
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  async function openConversation(id: string) {
    try {
      const detail = await aiApi.conversation(id)
      setConversationId(detail.id)
      setMessages(detail.messages)
      setError(null)
    } catch {
      toast.error('Could not open that conversation')
    }
  }

  async function removeConversation(id: string) {
    try {
      await aiApi.removeConversation(id)
      if (conversationId === id) {
        setConversationId(null)
        setMessages([])
      }
      void refetchConversations()
      toast.success('Conversation deleted')
    } catch {
      toast.error('Could not delete that conversation')
    }
  }

  function startNew() {
    setConversationId(null)
    setMessages([])
    setSuggestions([])
    setError(null)
    inputRef.current?.focus()
  }

  const quickQuestions = suggestions.length > 0 ? suggestions : (starters ?? []).slice(0, 4)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Finora Assistant"
        description="Ask about your finances. Answers are built from your real records, never guessed."
        actions={
          <Button variant="outline" onClick={startNew} leftIcon={<Plus className="h-4 w-4" />}>
            New chat
          </Button>
        }
      />

      {/* How it works / provider status */}
      {status ? (
        <div
          className={cn(
            'flex items-start gap-3 rounded-xl border p-4',
            status.configured
              ? 'border-navy/20 bg-navy-tint/50'
              : 'border-line bg-subtle/60',
          )}
        >
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-navy" aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-semibold text-ink">
                {status.configured ? 'AI phrasing enabled' : 'Built-in explainer'}
              </p>
              <Badge tone={status.configured ? 'navy' : 'neutral'}>
                {status.mode === 'llm' ? status.model ?? status.provider : 'deterministic'}
              </Badge>
            </div>
            <p className="mt-1 text-2xs leading-relaxed text-muted">{status.message}</p>
            <details className="mt-1.5">
              <summary className="cursor-pointer text-2xs font-semibold text-navy hover:underline">
                What data can it look up?
              </summary>
              <ul className="mt-1.5 grid gap-1 sm:grid-cols-2">
                {status.available_tools.map((tool) => (
                  <li key={tool.name} className="text-2xs text-muted">
                    <span className="font-mono text-navy">{tool.name}</span> —{' '}
                    {tool.description}
                  </li>
                ))}
              </ul>
            </details>
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-4">
        {/* Conversation history */}
        <Card className="hidden lg:block">
          <CardHeader title="Conversations" />
          <div className="max-h-[28rem] divide-y divide-line overflow-y-auto">
            {!conversations || conversations.length === 0 ? (
              <p className="px-5 py-6 text-center text-2xs text-muted">
                Your past conversations will appear here.
              </p>
            ) : (
              conversations.map((conversation) => (
                <div
                  key={conversation.id}
                  className={cn(
                    'group flex items-center gap-2 px-4 py-2.5 transition-colors hover:bg-subtle/60',
                    conversationId === conversation.id && 'bg-navy-tint/60',
                  )}
                >
                  <button
                    type="button"
                    onClick={() => void openConversation(conversation.id)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <p className="truncate text-xs font-medium text-ink">
                      {conversation.title}
                    </p>
                    <p className="text-2xs text-muted">
                      {conversation.message_count} messages ·{' '}
                      {formatRelative(conversation.updated_at)}
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={() => void removeConversation(conversation.id)}
                    className="shrink-0 rounded-md p-1.5 text-faint opacity-0 transition-opacity hover:bg-accent-soft hover:text-accent group-hover:opacity-100"
                    aria-label="Delete conversation"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* Chat */}
        <Card className="flex flex-col lg:col-span-3" style={{ minHeight: '32rem' }}>
          <div
            ref={scrollRef}
            className="flex-1 space-y-4 overflow-y-auto p-5"
            style={{ maxHeight: '32rem' }}
          >
            {messages.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center py-8 text-center">
                <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-navy-gradient text-white">
                  <Sparkles className="h-6 w-6" />
                </span>
                <h2 className="mt-4 font-display text-lg font-bold text-ink">
                  Ask me about your money
                </h2>
                <p className="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-muted">
                  I look up your actual transactions, budgets, goals and forecasts
                  before answering — and I&apos;ll tell you when I don&apos;t have
                  the data rather than guessing.
                </p>

                <div className="mt-6 grid w-full max-w-lg gap-2 sm:grid-cols-2">
                  {(starters ?? []).slice(0, 6).map((question) => (
                    <button
                      key={question}
                      type="button"
                      onClick={() => void send(question)}
                      className="rounded-xl border border-line bg-surface px-3.5 py-2.5 text-left text-xs text-ink transition-all duration-200 hover:border-navy/40 hover:bg-subtle"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                {messages.map((message) => (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    userName={user?.full_name ?? 'You'}
                  />
                ))}

                {sending ? (
                  <div className="flex gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-navy text-white">
                      <Bot className="h-4 w-4" />
                    </span>
                    <div className="rounded-2xl border border-line bg-surface px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        {[0, 1, 2].map((index) => (
                          <motion.span
                            key={index}
                            className="h-1.5 w-1.5 rounded-full bg-muted"
                            animate={{ opacity: [0.3, 1, 0.3] }}
                            transition={{
                              duration: 1.2,
                              repeat: Infinity,
                              delay: index * 0.18,
                            }}
                          />
                        ))}
                        <span className="ml-1.5 text-2xs text-muted">
                          Looking up your data…
                        </span>
                      </div>
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </div>

          {error ? (
            <div className="px-5">
              <ErrorState
                compact
                title="Could not get an answer"
                error={new Error(error)}
                onRetry={() => setError(null)}
              />
            </div>
          ) : null}

          {/* Follow-up suggestions */}
          {messages.length > 0 && quickQuestions.length > 0 && !sending ? (
            <div className="scroll-x no-scrollbar flex gap-2 border-t border-line px-5 py-2.5">
              {quickQuestions.slice(0, 3).map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => void send(question)}
                  className="shrink-0 rounded-full border border-line bg-surface px-3 py-1.5 text-2xs text-muted transition-colors hover:border-navy/40 hover:text-ink"
                >
                  {question}
                </button>
              ))}
            </div>
          ) : null}

          {/* Composer */}
          <form
            onSubmit={(event: FormEvent) => {
              event.preventDefault()
              void send(input)
            }}
            className="border-t border-line p-4"
          >
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  // Enter sends; Shift+Enter adds a newline.
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    void send(input)
                  }
                }}
                placeholder="How much did I spend on food this month?"
                rows={1}
                maxLength={2000}
                className="max-h-32 min-h-[2.75rem] flex-1 resize-none rounded-lg border border-line bg-surface px-3.5 py-3 text-sm text-ink placeholder:text-faint focus:border-navy/50 focus:outline-none focus:ring-2 focus:ring-navy/25"
                aria-label="Your question"
              />
              <Button
                type="submit"
                size="icon"
                className="h-11 w-11"
                loading={sending}
                disabled={!input.trim()}
                aria-label="Send message"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
            <p className="mt-2 text-2xs leading-relaxed text-faint">
              Finora retrieves your figures from the backend before answering. It
              does not give financial advice, and it will say so when the data
              isn&apos;t there.
            </p>
          </form>
        </Card>
      </div>
    </div>
  )
}
