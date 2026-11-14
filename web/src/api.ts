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

/** 一处规范化改动：前端要逐条展示，所以依据一起带回来。 */
export interface NormalizeChange {
  index: number
  category: string
  target: string
  before: string
  after: string
  basis: string
}

export interface NormalizeChecklistItem {
  item: string
  present: boolean
  note: string
}

export interface NormalizeResult {
  doc_type: string
  doc_type_name: string
  paragraphs: number
  text_chars: number
  total_changes: number
  by_category: Record<string, number>
  level_counts: Record<string, number>
  changes: NormalizeChange[]
  warnings: string[]
  checklist: NormalizeChecklistItem[]
  standard: string
  rule: string
  token: string
  filename: string
  expires_in: number
}

export interface NormalizeResponse {
  success: boolean
  message: string
  data: NormalizeResult
}

/**
 * 上传一份已经写好的公文，让后端按国标重排版式。
 *
 * 这里不能复用 `identityHeaders()`：它固定写死 `Content-Type: application/json`，
 * 而 multipart 必须让浏览器自己带 boundary，手写会直接 400。
 */
export async function uploadDocumentForNormalize(file: File, docType: string): Promise<NormalizeResponse> {
  const { identity } = useIdentity()
  const form = new FormData()
  form.append('file', file)
  form.append('doc_type', docType)
  const response = await fetch('/api/v1/documents/normalize', {
    method: 'POST',
    headers: {
      'X-User-Id': identity.value.userId,
      'X-Session-Id': identity.value.sessionId,
      'X-User-Role': identity.value.role,
    },
    body: form,
  })
  if (!response.ok) throw new Error(await readErrorMessage(response, '这份文档没能改成功'))
  return await response.json() as NormalizeResponse
}

/** 评价聚合：赛题把「用户评分」列进评审维度，这里给出真实数字。 */
export interface FeedbackTarget {
  target: string
  target_name: string
  total: number
  helpful: number
  rate: number
}

export interface FeedbackSummary {
  total: number
  helpful: number
  rate: number
  by_target: FeedbackTarget[]
  recent_notes: string[]
  covered_targets: string[]
  available_targets: { id: string; name: string }[]
  note: string
}

export interface FeedbackAck {
  success: boolean
  message: string
  data: { record_id: string; target: string; target_name: string; helpful: boolean }
}

export async function submitFeedback(target: string, helpful: boolean, note = ''): Promise<FeedbackAck> {
  return await requestJson<FeedbackAck>('/api/v1/feedback', {
    method: 'POST',
    headers: identityHeaders(),
    body: JSON.stringify({ target, helpful, note }),
  }, '评价没发出去')
}

export async function feedbackSummary(): Promise<FeedbackSummary> {
  const response = await requestJson<{ success: boolean; data: FeedbackSummary }>(
    '/api/v1/feedback/summary',
    {},
    '暂时读不到评价',
  )
  return response.data
}

/** 规则依据：线下展示时评委最常追问的一页。 */
export interface EvidenceItem {
  rule: string
  how: string
  source: string
  url: string
}

export interface EvidenceGroup {
  id: string
  title: string
  summary: string
  items: EvidenceItem[]
}

export interface EvidencePayload {
  groups: EvidenceGroup[]
  total: number
  note: string
}

export async function loadEvidence(): Promise<EvidencePayload> {
  const response = await requestJson<{ success: boolean; data: EvidencePayload }>(
    '/api/v1/evidence',
    {},
    '暂时读不到依据清单',
  )
  return response.data
}

/** 五育分布：把积分折算成德智体美劳，对应教育部要求的「全要素横向评价」。 */
export interface FiveDimension {
  id: string
  label: string
  note: string
  points: number
  share: number
}

export interface FiveDimensionSummary {
  user_id: string
  total: number
  dimensions: FiveDimension[]
  unclassified: number
  unclassified_share: number
  summary: string
  note: string
}

export async function loadFiveDimensions(userId: string): Promise<FiveDimensionSummary> {
  const response = await requestJson<{ success: boolean; data: FiveDimensionSummary }>(
    `/api/v1/points/user/${encodeURIComponent(userId)}/five-dimensions`,
    {},
    '暂时读不到五育分布',
  )
  return response.data
}
