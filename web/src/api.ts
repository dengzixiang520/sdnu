import { useIdentity } from './identity'

export interface AgentResponse {
  success: boolean
  message: string
  data: Record<string, unknown>
  routed_to?: string
}

export type ChatMode = 'wellbeing' | 'academic_interview'
export interface ChatMessage { role: 'user' | 'assistant'; content: string }
export interface ChatStreamResult { providerOnline: boolean; escalated: boolean }

function identityHeaders(): Record<string, string> {
  const { identity } = useIdentity()
  return {
    'Content-Type': 'application/json',
    'X-User-Id': identity.value.userId,
    'X-Session-Id': identity.value.sessionId,
    'X-User-Role': identity.value.role,
  }
}

async function readErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json() as { detail?: unknown; message?: unknown }
    const detail = body.detail ?? body.message
    if (typeof detail === 'string' && detail.trim()) return detail
  } catch {
    // Non-JSON error bodies (proxy HTML, empty responses) fall through.
  }
  return fallback
}

/**
 * Fetch a JSON endpoint and fail loudly.
 *
 * Bare `fetch` plus `console.log` hides every backend fault from the user: a 500 or a
 * proxy HTML page leaves the screen blank with no hint. This helper raises an Error with
 * the backend's own `detail`/`message` text so callers can show it.
 */
export async function requestJson<T>(input: string, init: RequestInit = {}, fallback = '服务暂时不可用'): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) throw new Error(await readErrorMessage(response, fallback))
  return await response.json() as T
}

/** Call a bounded backend Skill action through the development API bridge. */
export async function command(capability: string, action: string, text = '', payload: Record<string, unknown> = {}): Promise<AgentResponse> {
  const response = await fetch('/api/v1/commands', {
    method: 'POST',
    headers: identityHeaders(),
    body: JSON.stringify({ capability, action, text, payload }),
  })
  if (!response.ok) throw new Error(await readErrorMessage(response, '服务暂时不可用'))
  const result = await response.json() as AgentResponse
  if (!result.success) throw new Error(result.message || '操作未完成')
  return result
}

/** Load the current session's owner-only conversation history. */
export async function chatHistory(mode: ChatMode): Promise<ChatMessage[]> {
  const response = await fetch(`/api/v1/chat/history?mode=${encodeURIComponent(mode)}`, { headers: identityHeaders() })
  if (!response.ok) throw new Error(await readErrorMessage(response, '无法读取对话记录'))
  const result = await response.json() as { messages: ChatMessage[] }
  return result.messages.filter((item) => item.role !== ('system' as ChatMessage['role']))
}

/** Stream one AI turn through the backend safety gateway. */
export async function streamChat(
  mode: ChatMode,
  message: string,
  metadata: Record<string, string>,
  onToken: (token: string) => void,
): Promise<ChatStreamResult> {
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: identityHeaders(),
    body: JSON.stringify({ mode, message, metadata }),
  })
  if (!response.ok) throw new Error(await readErrorMessage(response, '对话服务暂时不可用'))
  if (!response.body) throw new Error('当前浏览器不支持流式对话')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let providerOnline = true
  let escalated = false
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''
    for (const event of events) {
      const line = event.split('\n').find((item) => item.startsWith('data: '))
      if (!line) continue
      try {
        const payload = JSON.parse(line.slice(6)) as { type: string; value?: string | boolean }
        if (payload.type === 'token' && typeof payload.value === 'string') onToken(payload.value)
        if (payload.type === 'provider_online') providerOnline = Boolean(payload.value)
        if (payload.type === 'escalated') escalated = Boolean(payload.value)
      } catch {
        // Skip malformed SSE frames instead of aborting the whole stream.
      }
    }
    if (done) break
  }
  return { providerOnline, escalated }
}
