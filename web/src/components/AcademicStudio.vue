<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  PhArrowLeft,
  PhCaretDown,
  PhCaretUp,
  PhClock,
  PhDownloadSimple,
  PhFileText,
  PhListChecks,
  PhMagicWand,
  PhMicrophone,
  PhNotebook,
  PhTreeStructure,
  PhTrash,
  PhWaveform,
  PhX,
} from '@phosphor-icons/vue'
import { command } from '../api'

interface TodoItem { task: string; timestamp_seconds: number }
interface NoteSegment { start_seconds: number; end_seconds: number; text: string }
interface NoteSource { kind?: string; name?: string; duration_seconds?: number | null; timestamp_source?: string }
interface StructuredNote {
  three_sentence_summary: string[]
  markdown_knowledge_tree: string
  todo_items: TodoItem[]
  segments?: NoteSegment[]
  source?: NoteSource
}
interface HistoryEntry { at: string; source: string; note: StructuredNote }

const MAX_BYTES = 20 * 1024 * 1024
const HISTORY_KEY = 'zhq-notes-history-v1'

const transcript = ref('本次组会讨论了多 Agent 路由的验证方案。\n需要：周五前补充压力测试数据。\n待办：整理答辩演示流程。')
const loading = ref(false)
const error = ref('')
const progressHint = ref('')
const note = ref<StructuredNote | null>(null)

const audioInput = ref<HTMLInputElement | null>(null)
const documentInput = ref<HTMLInputElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const audioFile = ref<File | null>(null)
const documentFile = ref<File | null>(null)
const audioDuration = ref<number | null>(null)

const sentLineIndexes = ref<number[]>([])
const jumpHint = ref('')
const jumpedIndex = ref<number | null>(null)
const sourceExcerpt = ref<{ range: string; text: string } | null>(null)

const history = ref<HistoryEntry[]>([])
const historyOpen = ref(false)
const historyError = ref('')

const noteKind = computed(() => note.value?.source?.kind ?? 'text')
const noteTitle = computed(() => {
  const source = note.value?.source
  if (!source?.name) return '本次整理结果'
  if (source.kind === 'audio') return `音频 · ${source.name}`
  if (source.kind === 'document') return `文档 · ${source.name}`
  return '文本粘贴'
})
const audioDurationLabel = computed(() => (audioDuration.value ? formatClock(audioDuration.value) : ''))
const timestampNote = computed(() => {
  const source = note.value?.source
  if (!source) return ''
  if (source.kind === 'audio') return source.timestamp_source === 'measured' ? '时间戳按音频实际时长对齐' : '时间戳按识别字数估算'
  if (source.kind === 'document') return '时间戳按段落顺序估算，仅用于定位'
  return ''
})

function messageOf(reason: unknown): string {
  return reason instanceof Error ? reason.message : '整理失败'
}

function formatClock(total: number): string {
  const safe = Math.max(0, Math.round(Number(total) || 0))
  const pad = (value: number) => String(value).padStart(2, '0')
  const hours = Math.floor(safe / 3600)
  const minutes = Math.floor((safe % 3600) / 60)
  const seconds = safe % 60
  return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${pad(minutes)}:${pad(seconds)}`
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

function formatTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '未知时间'
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function stamp(date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
}

function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result ?? '')
      const comma = result.indexOf(',')
      resolve(comma >= 0 ? result.slice(comma + 1) : result)
    }
    reader.onerror = () => reject(new Error('文件读取失败，请重试'))
    reader.readAsDataURL(file)
  })
}

function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as HistoryEntry[]
    history.value = Array.isArray(parsed)
      ? parsed.filter((entry) => entry && typeof entry.at === 'string' && entry.note && Array.isArray(entry.note.three_sentence_summary)).slice(0, 10)
      : []
  } catch {
    history.value = []
  }
}

function saveHistory() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value.slice(0, 10)))
    historyError.value = ''
  } catch {
    historyError.value = '浏览器存储不可用，这次历史只保留在当前页面'
  }
}

function remember(value: StructuredNote, sourceLabel: string) {
  history.value = [{ at: new Date().toISOString(), source: sourceLabel, note: value }, ...history.value].slice(0, 10)
  saveHistory()
}

function clearHistory() {
  history.value = []
  historyError.value = ''
  try {
    localStorage.removeItem(HISTORY_KEY)
  } catch {
    historyError.value = '浏览器存储不可用，历史已从页面移除'
  }
}

function restore(entry: HistoryEntry) {
  note.value = entry.note
  sentLineIndexes.value = []
  jumpHint.value = ''
  jumpedIndex.value = null
  sourceExcerpt.value = null
  error.value = ''
}

function applyNote(value: StructuredNote, sourceLabel: string) {
  note.value = value
  jumpHint.value = ''
  jumpedIndex.value = null
  sourceExcerpt.value = null
  remember(value, sourceLabel)
}

function pickAudio() {
  audioInput.value?.click()
}

function pickDocument() {
  documentInput.value?.click()
}

function probeAudioDuration(file: File) {
  audioDuration.value = null
  const url = URL.createObjectURL(file)
  const probe = new Audio()
  probe.preload = 'metadata'
  probe.onloadedmetadata = () => {
    audioDuration.value = Number.isFinite(probe.duration) && probe.duration > 0 ? probe.duration : null
    URL.revokeObjectURL(url)
  }
  probe.onerror = () => {
    URL.revokeObjectURL(url)
  }
  probe.src = url
}

function onAudioPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  error.value = ''
  if (!file) return
  if (file.size > MAX_BYTES) {
    audioFile.value = null
    audioDuration.value = null
    error.value = `音频 ${formatSize(file.size)} 超过 20MB，请先裁剪后再上传`
    return
  }
  audioFile.value = file
  documentFile.value = null
  probeAudioDuration(file)
}

function onDocumentPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  error.value = ''
  if (!file) return
  if (file.size > MAX_BYTES) {
    documentFile.value = null
    error.value = `文档 ${formatSize(file.size)} 超过 20MB，请先精简后再上传`
    return
  }
  documentFile.value = file
  audioFile.value = null
  audioDuration.value = null
}

function clearPicked() {
  audioFile.value = null
  documentFile.value = null
  audioDuration.value = null
  progressHint.value = ''
}

async function organize() {
  if (loading.value) return
  error.value = ''
  progressHint.value = ''
  const picked = transcript.value
    .split('\n')
    .map((text, lineIndex) => ({ text: text.trim(), lineIndex }))
    .filter((item) => item.text.length > 0)
  if (!picked.length) {
    error.value = '先粘贴一段转录文本，或在上面选择音频 / 文档'
    return
  }
  loading.value = true
  const segments = picked.map((item, order) => ({ start_seconds: order * 20, end_seconds: order * 20 + 19, text: item.text }))
  try {
    const result = await command('academic', 'organize_transcript', '', { segments })
    sentLineIndexes.value = picked.map((item) => item.lineIndex)
    applyNote(result.data as unknown as StructuredNote, '文本')
  } catch (reason) {
    error.value = messageOf(reason)
  } finally {
    loading.value = false
  }
}

async function organizeAudio() {
  const file = audioFile.value
  if (!file || loading.value) return
  error.value = ''
  progressHint.value = '正在转写并整理，音频越长越久…'
  loading.value = true
  try {
    const audio_base64 = await readBase64(file)
    const payload: Record<string, unknown> = { audio_base64, mime_type: file.type || 'audio/webm', filename: file.name }
    if (audioDuration.value) payload.duration_seconds = audioDuration.value
    const result = await command('academic', 'organize_audio', '', payload)
    sentLineIndexes.value = []
    applyNote(result.data as unknown as StructuredNote, file.name)
  } catch (reason) {
    error.value = messageOf(reason)
  } finally {
    loading.value = false
    progressHint.value = ''
  }
}

async function organizeDocument() {
  const file = documentFile.value
  if (!file || loading.value) return
  error.value = ''
  progressHint.value = '正在解析文档并整理…'
  loading.value = true
  try {
    const document_base64 = await readBase64(file)
    const result = await command('academic', 'organize_document', '', { document_base64, filename: file.name })
    sentLineIndexes.value = []
    applyNote(result.data as unknown as StructuredNote, file.name)
  } catch (reason) {
    error.value = messageOf(reason)
  } finally {
    loading.value = false
    progressHint.value = ''
  }
}

function focusLine(lineIndex: number): boolean {
  const area = textareaRef.value
  if (!area) return false
  const lines = transcript.value.split('\n')
  if (lineIndex < 0 || lineIndex >= lines.length) return false
  let start = 0
  for (let index = 0; index < lineIndex; index += 1) start += lines[index].length + 1
  const end = start + lines[lineIndex].length
  area.focus()
  area.setSelectionRange(start, end)
  const lineHeight = Number.parseFloat(getComputedStyle(area).lineHeight || '') || 24
  area.scrollTop = Math.max(0, lineIndex * lineHeight - area.clientHeight / 2)
  return true
}

function resolveLineIndex(segmentIndex: number, segment: NoteSegment | null): number {
  if (segmentIndex >= 0 && sentLineIndexes.value.length > segmentIndex) return sentLineIndexes.value[segmentIndex]
  if (segment) {
    const found = transcript.value.split('\n').findIndex((line) => line.trim() === segment.text)
    if (found >= 0) return found
  }
  return segmentIndex
}

function jumpToTodo(item: TodoItem, index: number) {
  jumpedIndex.value = index
  window.setTimeout(() => {
    if (jumpedIndex.value === index) jumpedIndex.value = null
  }, 2800)
  const segments = note.value?.segments ?? []
  const segmentIndex = segments.findIndex((segment) => segment.start_seconds === item.timestamp_seconds)
  const segment = segmentIndex >= 0 ? segments[segmentIndex] : null
  if (noteKind.value === 'text') {
    const lineIndex = resolveLineIndex(segmentIndex, segment)
    if (focusLine(lineIndex)) {
      jumpHint.value = `已定位到左侧第 ${lineIndex + 1} 行原文`
      sourceExcerpt.value = null
      return
    }
  }
  if (segment) {
    sourceExcerpt.value = {
      range: `${formatClock(segment.start_seconds)} – ${formatClock(segment.end_seconds)}`,
      text: segment.text,
    }
    jumpHint.value = `已展开 ${formatClock(segment.start_seconds)} 起的原文片段`
    return
  }
  sourceExcerpt.value = null
  jumpHint.value = '这次结果没有可定位的原文片段，已高亮这条待办'
}

function buildMarkdown(value: StructuredNote): string {
  const summary = value.three_sentence_summary.map((line, index) => `${index + 1}. ${line}`).join('\n')
  const todos = value.todo_items.length
    ? value.todo_items.map((item) => `- [ ] ${formatClock(item.timestamp_seconds)} ${item.task}`).join('\n')
    : '- [ ] 本次材料没有识别出明确待办'
  return `# 结构化笔记\n\n## 三句摘要\n${summary}\n\n## 待办清单\n${todos}\n\n## 知识树\n${value.markdown_knowledge_tree}\n`
}

function exportMarkdown() {
  const value = note.value
  if (!value) return
  try {
    const blob = new Blob([buildMarkdown(value)], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `结构化笔记-${stamp()}.md`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (reason) {
    error.value = reason instanceof Error ? `导出失败：${reason.message}` : '导出失败'
  }
}

onMounted(loadHistory)
</script>
<template>
  <section class="notes-studio">
    <RouterLink to="/academic"><PhArrowLeft :size="18" /> 返回功能选择</RouterLink>
    <header>
      <div>
        <PhNotebook :size="36" weight="duotone" />
        <h1>把一段杂乱记录，<br><em>整理成下一步。</em></h1>
      </div>
      <p>粘贴转录文本，或直接上传音频 / 文档。整理结果可导出 Markdown，待办时间戳能回跳原文。</p>
    </header>
    <div class="notes-desk">
      <article class="source-paper">
        <div class="studx-upload-row">
          <button type="button" class="studx-upload-trigger" :disabled="loading" @click="pickAudio">
            <PhMicrophone :size="17" /> 选择音频
          </button>
          <button type="button" class="studx-upload-trigger" :disabled="loading" @click="pickDocument">
            <PhFileText :size="17" /> 选择文档
          </button>
          <input ref="audioInput" class="studx-file-input" type="file" accept="audio/*,video/*" @change="onAudioPicked" />
          <input ref="documentInput" class="studx-file-input" type="file" accept=".txt,.md,.pdf,.docx,.csv" @change="onDocumentPicked" />
        </div>
        <p class="studx-upload-note">音频先转写再整理；文档支持 txt / md / csv / pdf / docx。单个文件上限 20MB。</p>

        <div v-if="audioFile" class="studx-picked">
          <PhWaveform :size="18" />
          <div class="studx-picked-copy">
            <strong>{{ audioFile.name }}</strong>
            <small>
              {{ formatSize(audioFile.size) }} · 音频<template v-if="audioDurationLabel"> · 时长 {{ audioDurationLabel }}</template>
            </small>
          </div>
          <button type="button" class="studx-primary" :disabled="loading" @click="organizeAudio">开始整理</button>
          <button type="button" class="studx-ghost" :disabled="loading" @click="clearPicked"><PhX :size="14" /> 移除</button>
        </div>

        <div v-else-if="documentFile" class="studx-picked">
          <PhFileText :size="18" />
          <div class="studx-picked-copy">
            <strong>{{ documentFile.name }}</strong>
            <small>{{ formatSize(documentFile.size) }} · 文档</small>
          </div>
          <button type="button" class="studx-primary" :disabled="loading" @click="organizeDocument">开始整理</button>
          <button type="button" class="studx-ghost" :disabled="loading" @click="clearPicked"><PhX :size="14" /> 移除</button>
        </div>

        <label>课堂或组会转录<textarea ref="textareaRef" v-model="transcript" placeholder="每行可以作为一个时间片段…"></textarea></label>
        <button type="button" :disabled="loading" @click="organize">
          <PhMagicWand :size="19" /> {{ loading ? '正在整理' : '生成结构化笔记' }}
        </button>
        <p v-if="progressHint" class="studx-progress">{{ progressHint }}</p>
      </article>

      <article class="organized-paper">
        <div v-if="note">
          <div class="studx-result-head">
            <span class="studx-result-source">
              <PhWaveform v-if="noteKind === 'audio'" :size="16" />
              <PhFileText v-else-if="noteKind === 'document'" :size="16" />
              <PhListChecks v-else :size="16" />
              {{ noteTitle }}
            </span>
            <button type="button" class="studx-export" @click="exportMarkdown">
              <PhDownloadSimple :size="17" /> 导出 Markdown
            </button>
          </div>
          <section>
            <h2>三句摘要</h2>
            <ol>
              <li v-for="(line, index) in note.three_sentence_summary" :key="`summary-${index}`">{{ line }}</li>
            </ol>
          </section>
          <section>
            <h2><PhClock :size="20" /> 待办清单</h2>
            <p v-if="timestampNote" class="studx-timestamp-note">{{ timestampNote }}</p>
            <ul v-if="note.todo_items.length" class="studx-todos">
              <li
                v-for="(item, index) in note.todo_items"
                :key="`todo-${index}`"
                :class="['studx-todo', { 'studx-todo-active': jumpedIndex === index }]"
              >
                <button
                  type="button"
                  class="studx-stamp"
                  :title="`跳转到 ${formatClock(item.timestamp_seconds)} 的原文`"
                  @click="jumpToTodo(item, index)"
                >
                  {{ formatClock(item.timestamp_seconds) }}
                </button>
                <span>{{ item.task }}</span>
              </li>
            </ul>
            <p v-else class="studx-quiet">这次材料里没有识别到明确待办。</p>
            <p v-if="jumpHint" class="studx-jump-hint">{{ jumpHint }}</p>
            <blockquote v-if="sourceExcerpt" class="studx-excerpt">
              <small>{{ sourceExcerpt.range }} 原文</small>
              <p>{{ sourceExcerpt.text }}</p>
            </blockquote>
          </section>
          <section>
            <h2><PhTreeStructure :size="20" /> Markdown 知识树</h2>
            <pre>{{ note.markdown_knowledge_tree }}</pre>
          </section>
        </div>
        <div v-else class="notes-empty">
          <PhTreeStructure :size="42" weight="duotone" />
          <strong>整理结果会出现在这里</strong>
          <p>不补写原文中不存在的事实。</p>
        </div>

        <section class="studx-history">
          <button type="button" class="studx-history-toggle" @click="historyOpen = !historyOpen">
            <PhClock :size="17" /> 最近整理（{{ history.length }}）
            <PhCaretUp v-if="historyOpen" :size="15" />
            <PhCaretDown v-else :size="15" />
          </button>
          <div v-if="historyOpen" class="studx-history-body">
            <p v-if="!history.length" class="studx-quiet">还没有整理记录，成功整理一次就会出现在这里。</p>
            <ul v-else>
              <li v-for="(entry, index) in history" :key="`history-${index}-${entry.at}`">
                <button type="button" class="studx-history-item" @click="restore(entry)">
                  <span class="studx-history-time">{{ formatTime(entry.at) }}</span>
                  <span class="studx-history-source">{{ entry.source }}</span>
                  <span class="studx-history-line">{{ entry.note.three_sentence_summary?.[0] ?? '（无摘要）' }}</span>
                </button>
              </li>
            </ul>
            <button v-if="history.length" type="button" class="studx-ghost" @click="clearHistory">
              <PhTrash :size="14" /> 清空历史
            </button>
            <p v-if="historyError" class="studx-error">{{ historyError }}</p>
          </div>
        </section>
      </article>
    </div>
    <p v-if="error" class="inline-error">{{ error }}</p>
  </section>
</template>

<style scoped>
.studx-upload-row { margin-bottom: .35rem; display: flex; flex-wrap: wrap; gap: .5rem; }
.studx-upload-trigger { margin-top: 0 !important; min-height: 38px; padding: .45rem .8rem; display: inline-flex; align-items: center; gap: .4rem; color: #253854; background: #eef2ec; border: 1px solid #cfd9cf; border-radius: 9px; font-size: .82rem; font-weight: 700; }
.studx-upload-trigger:hover { background: #e2ece2; border-color: #9cb6aa; }
.studx-file-input { display: none; }
.studx-upload-note { margin: 0 0 .9rem; color: var(--muted); font-size: .76rem; line-height: 1.6; }
.studx-picked { margin: .2rem 0 .9rem; padding: .7rem .8rem; display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: center; gap: .6rem; color: #253854; background: #f2f6f0; border: 1px dashed #b9c9b8; border-radius: 12px; }
.studx-picked-copy { min-width: 0; display: grid; gap: .15rem; }
.studx-picked-copy strong { overflow: hidden; font-size: .84rem; text-overflow: ellipsis; white-space: nowrap; }
.studx-picked-copy small { color: var(--muted); font-size: .74rem; }
.studx-primary { margin-top: 0 !important; min-height: 34px; padding: .4rem .85rem; color: white; background: var(--navy); border: 0; border-radius: 8px; font-size: .8rem; font-weight: 700; }
.studx-primary:hover { background: #0f3235; }
.studx-ghost { margin-top: 0 !important; min-height: 34px; padding: .35rem .6rem; display: inline-flex; align-items: center; gap: .3rem; color: #4d5f5b; background: transparent; border: 1px solid #c8d3c8; border-radius: 8px; font-size: .78rem; }
.studx-ghost:hover { background: #eef2ec; }
.studx-progress { margin: .55rem 0 0; display: flex; align-items: center; gap: .45rem; color: #7a5a1f; font-size: .78rem; }
.studx-progress::before { content: ""; width: 9px; height: 9px; border-radius: 50%; background: var(--gold); animation: studx-pulse 1.1s ease-in-out infinite; }
@keyframes studx-pulse { 0%, 100% { opacity: .35; transform: scale(.8); } 50% { opacity: 1; transform: scale(1.1); } }
.studx-result-head { padding-bottom: .7rem; display: flex; align-items: center; justify-content: space-between; gap: .6rem; }
.studx-result-source { max-width: 58%; overflow: hidden; display: inline-flex; align-items: center; gap: .35rem; color: var(--muted); font-size: .78rem; text-overflow: ellipsis; white-space: nowrap; }
.studx-export { min-height: 34px; padding: .4rem .8rem; display: inline-flex; align-items: center; gap: .35rem; color: var(--navy); background: #e5eee6; border: 1px solid #c4d5c5; border-radius: 9px; font-size: .8rem; font-weight: 700; }
.studx-export:hover { background: #d6e6d8; }
.studx-todos { margin: 0; padding: 0; list-style: none; }
.studx-timestamp-note { margin: -.15rem 0 .55rem; color: var(--muted); font-size: .72rem; }
.studx-todo { display: flex; align-items: baseline; gap: .55rem; }
.studx-todo > span { margin-right: 0; color: var(--ink); }
.studx-todo-active > span { color: var(--green); font-weight: 700; }
.studx-stamp { flex: none; padding: .1rem .5rem; color: #fff; background: var(--coral); border: 0; border-radius: 999px; font: 700 .74rem/1.6 "Noto Sans SC Variable", sans-serif; font-variant-numeric: tabular-nums; }
.studx-stamp:hover { background: #c0503c; }
.studx-todo-active .studx-stamp { box-shadow: 0 0 0 3px rgba(216, 97, 77, .22); }
.studx-jump-hint { margin: .5rem 0 0; color: var(--green); font-size: .78rem; }
.studx-excerpt { margin: .6rem 0 0; padding: .7rem .85rem; background: #f5f7ef; border-left: 3px solid var(--gold); border-radius: 0 10px 10px 0; }
.studx-excerpt small { color: #7a6a3d; font-size: .72rem; }
.studx-excerpt p { margin: .3rem 0 0; font-size: .86rem; line-height: 1.7; }
.studx-quiet { margin: .4rem 0; color: var(--muted); font-size: .82rem; }
.studx-error { margin: .5rem 0 0; padding: .5rem .7rem; color: #9e3030; background: #fff0ed; border-radius: 9px; font-size: .78rem; }
.studx-history { margin-top: .4rem; }
.studx-history-toggle { width: 100%; min-height: 36px; padding: .4rem .2rem; display: flex; align-items: center; gap: .4rem; color: #3d5551; background: transparent; border: 0; font-size: .84rem; font-weight: 700; }
.studx-history-toggle > svg:last-child { margin-left: auto; }
.studx-history-body { display: grid; gap: .5rem; }
.studx-history-body ul { margin: 0; padding: 0; display: grid; gap: .35rem; list-style: none; }
.studx-history-item { width: 100%; padding: .5rem .6rem; display: grid; grid-template-columns: auto auto minmax(0, 1fr); align-items: baseline; gap: .5rem; text-align: left; color: var(--ink); background: #f7f8f1; border: 1px solid #e2e7dc; border-radius: 9px; font-size: .78rem; }
.studx-history-item:hover { background: #eef3e8; border-color: #c2d1bd; }
.studx-history-item span { margin-right: 0; }
.studx-history-time { color: var(--muted); font-variant-numeric: tabular-nums; }
.studx-history-source { max-width: 8rem; overflow: hidden; color: var(--green); font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.studx-history-line { overflow: hidden; color: #3f5350; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 720px) {
  .studx-picked { grid-template-columns: auto minmax(0, 1fr); }
  .studx-history-item { grid-template-columns: auto minmax(0, 1fr); }
  .studx-history-line { grid-column: 1 / -1; }
}
</style>
