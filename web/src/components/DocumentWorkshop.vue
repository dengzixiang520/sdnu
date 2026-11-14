<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import {
  PhFileText, PhDownload, PhEye, PhCopy, PhTrash, PhSparkle, PhMagicWand,
  PhBookmarkSimple, PhClock, PhQuotes, PhListChecks, PhArrowRight, PhPlus,
  PhUploadSimple, PhSealCheck, PhWarningCircle, PhFileDoc, PhCheckCircle, PhCircle,
} from '@phosphor-icons/vue'
import { command, requestJson, uploadDocumentForNormalize } from '../api'
import type { NormalizeResult } from '../api'
import AnswerFeedback from './AnswerFeedback.vue'

interface DocumentElements {
  reference_number: string
  title: string
  body: string
  signature: string
  issue_date: string
}

interface DocTemplate {
  id: string
  name: string
  banner: string
  scenario: string
  reference_sample: string
  recipient: string
  closing: string
  structure: string[]
  format_notes: string[]
  pitfalls: string[]
  example: string
}

interface Banner {
  id: string
  name: string
  prefix: string
  usage: string
}

/* 起草助手语料。与模板库同源放在后端（/api/v1/documents/phrases）：
   文种 id 必须和 TEMPLATE_CATALOG 对得上，两处各写一份迟早会走样。 */
interface PhraseItem { id: string, slot: string, text: string }
interface PhraseGroup { id: string, label: string, hint: string, items: PhraseItem[] }
interface GenreRow {
  id: string
  name: string
  template_id: string
  direction: string
  reply: string
  when: string
  closing: string
  sign: string
}
interface GenreContrast { pair: string, verdict: string, items: string[] }
interface DeadlineRule { id: string, label: string, workdays: number, note: string }

/* 草稿本与导出记录只存本机 localStorage：这是浏览器里的草稿，不是已交付的文件。 */
interface SavedDraft {
  id: string
  title: string
  docType: string
  docTypeName: string
  draft: string
  savedAt: string
  chars: number
}
interface ExportRecord { id: string, title: string, docTypeName: string, at: string }

const DRAFT_STORE = 'zhq-doc-drafts-v1'
const EXPORT_STORE = 'zhq-doc-exports-v1'

/* 一句话成稿的示例，覆盖校内最高频的三类场景 */
const BRIEF_EXAMPLES = [
  '下周三下午两点组织全院消防疏散演练，各年级辅导员和班长必须参加',
  '申请采购10台图形工作站用于人工智能实验教学，经费80万元',
  '2026届毕业生就业工作情况，需向省教育厅汇报',
]

const activeTab = ref<'templates' | 'normalize' | 'assist' | 'editor' | 'preview' | 'format' | 'library'>('templates')
const draft = ref('')
const elements = ref<DocumentElements | null>(null)
const message = ref('')
const loading = ref(false)
const selectedTemplate = ref('')

/* 起草助手 */
const brief = ref('')
const drafting = ref(false)
const draftSource = ref<'' | 'deepseek' | 'local'>('')
const phraseGroups = ref<PhraseGroup[]>([])
const genres = ref<GenreRow[]>([])
const contrasts = ref<GenreContrast[]>([])
const deadlineRules = ref<DeadlineRule[]>([])
const activePhraseGroup = ref('opening')

/* 草稿本 */
const savedDrafts = ref<SavedDraft[]>([])
const exportRecords = ref<ExportRecord[]>([])
const draftEl = ref<HTMLTextAreaElement | null>(null)

// 模板库与版头由后端提供（唯一数据源），前端不再硬编码骨架文本。
const templates = ref<DocTemplate[]>([])
const banners = ref<Banner[]>([])

// 版式要素
const docType = ref('notice')
const bannerName = ref('山东师范大学文件')
const recipient = ref('')
const attachments = ref('')
const cc = ref('')
const keywords = ref('')
const urgency = ref('')
const secrecy = ref('')
const signer = ref('')
const printAgency = ref('山东师范大学校长办公室')

const currentTemplate = computed(() => templates.value.find((item) => item.id === docType.value) ?? null)
const currentBanner = computed(() => banners.value.find((item) => item.name === bannerName.value) ?? null)

async function loadTemplates() {
  try {
    const data = await requestJson<{ success: boolean, data: { templates: DocTemplate[], banners: Banner[] } }>(
      '/api/v1/documents/templates', {}, '模板库加载失败')
    if (data.success) {
      templates.value = data.data.templates
      banners.value = data.data.banners
      // 首次进入停留在「文种模板」页，让用户先看到 8 个文种的区别；
      // 只把第一个文种预填进草稿，不切换标签页。
      if (!draft.value && templates.value.length) {
        applyTemplate(templates.value[0], false)
      }
    }
  } catch (reason) {
    message.value = reason instanceof Error ? reason.message : '模板库加载失败'
  }
}

function applyTemplate(template: DocTemplate, switchTab = true) {
  draft.value = template.example
  selectedTemplate.value = template.id
  docType.value = template.id
  const banner = banners.value.find((item) => item.id === template.banner)
  bannerName.value = banner?.name ?? '山东师范大学文件'
  recipient.value = template.recipient
  elements.value = null
  message.value = `已载入「${template.name}」模板：${template.scenario}`
  if (switchTab) {
    activeTab.value = 'editor'
  }
}

function splitList(text: string): string[] {
  return text.split(/[,，、\n]/).map((item) => item.trim()).filter(Boolean)
}

async function parseDraft() {
  loading.value = true
  message.value = ''
  try {
    const result = await command('document_engine', 'extract_elements', draft.value)
    elements.value = result.data as unknown as DocumentElements
    message.value = result.message
  } catch (error) {
    message.value = error instanceof Error ? error.message : '解析失败'
  } finally {
    loading.value = false
  }
}

function payload() {
  const base = elements.value ?? {
    reference_number: '',
    title: '',
    body: draft.value,
    signature: '',
    issue_date: '',
  }
  return {
    ...base,
    doc_type: docType.value,
    banner_name: bannerName.value,
    recipient: recipient.value,
    attachments: splitList(attachments.value),
    cc: splitList(cc.value),
    keywords: splitList(keywords.value),
    urgency: urgency.value,
    secrecy: secrecy.value,
    signer: signer.value,
    closing: '',
    print_agency: printAgency.value,
  }
}

async function exportDocx() {
  if (!elements.value) {
    message.value = '请先解析草稿'
    return
  }
  loading.value = true
  try {
    const response = await fetch('/api/v1/documents/export-docx', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload()),
    })

    if (response.ok) {
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${elements.value.title || '文档'}.docx`
      a.click()
      URL.revokeObjectURL(url)
      message.value = `已按《山东师范大学行政文件格式细则》导出「${currentTemplate.value?.name ?? '公文'}」DOCX`
      recordExport(elements.value.title || '未命名文档')
    } else {
      message.value = '导出失败'
    }
  } catch {
    message.value = '导出失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function clearDraft() {
  draft.value = ''
  elements.value = null
  message.value = ''
}

function copyDraft() {
  navigator.clipboard.writeText(draft.value)
  message.value = '已复制到剪贴板'
}

/* ---------- 起草助手 ---------- */
async function loadPhrases() {
  try {
    const data = await requestJson<{
      success: boolean
      data: { groups: PhraseGroup[], genres: GenreRow[], contrasts: GenreContrast[], deadlines: DeadlineRule[] }
    }>('/api/v1/documents/phrases', {}, '句式库加载失败')
    if (data.success) {
      phraseGroups.value = data.data.groups
      genres.value = data.data.genres
      contrasts.value = data.data.contrasts
      deadlineRules.value = data.data.deadlines
      if (data.data.groups.length && !data.data.groups.some((item) => item.id === activePhraseGroup.value)) {
        activePhraseGroup.value = data.data.groups[0].id
      }
    }
  } catch (reason) {
    message.value = reason instanceof Error ? reason.message : '句式库加载失败'
  }
}

const currentPhraseGroup = computed(
  () => phraseGroups.value.find((item) => item.id === activePhraseGroup.value) ?? phraseGroups.value[0] ?? null,
)
const phraseCount = computed(() => phraseGroups.value.reduce((sum, group) => sum + group.items.length, 0))

/** 一句话成稿。生成后直接落到「文档编辑」，用户接着改字而不是从零写。 */
async function composeDraft() {
  const briefText = brief.value.trim()
  if (!briefText) {
    message.value = '先写一句需求，例如「下周三组织消防演练，各班班长参加」'
    return
  }
  drafting.value = true
  message.value = ''
  try {
    const result = await command('document_engine', 'compose_draft', briefText, { doc_type: docType.value })
    const data = result.data as { draft: string, source: string }
    draft.value = data.draft
    draftSource.value = data.source === 'deepseek' ? 'deepseek' : 'local'
    elements.value = null
    selectedTemplate.value = docType.value
    message.value = result.message
    activeTab.value = 'editor'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '起草失败'
  } finally {
    drafting.value = false
  }
}

/** 切换文种但不覆盖已有草稿：只改文种与版头，让用户自己决定要不要重写。 */
function useGenre(row: GenreRow) {
  docType.value = row.template_id
  const template = templates.value.find((item) => item.id === row.template_id)
  if (template) {
    const banner = banners.value.find((item) => item.id === template.banner)
    bannerName.value = banner?.name ?? bannerName.value
  }
  message.value = `已切换到「${row.name}」（${row.direction}·${row.reply}）：${row.when}`
}

/** 把句式插到正文光标处，而不是覆盖已有内容。 */
function insertPhrase(text: string) {
  const el = draftEl.value
  const current = draft.value
  if (!el) {
    draft.value = current ? `${current}\n${text}` : text
    message.value = `已插入：${text.slice(0, 20)}${text.length > 20 ? '…' : ''}`
    return
  }
  const start = el.selectionStart ?? current.length
  const end = el.selectionEnd ?? current.length
  const before = current.slice(0, start)
  const after = current.slice(end)
  const pad = before && !before.endsWith('\n') ? '\n' : ''
  draft.value = `${before}${pad}${text}${after}`
  const caret = before.length + pad.length + text.length
  void nextTick(() => {
    el.focus()
    el.setSelectionRange(caret, caret)
  })
  message.value = `已插入到正文：${text.slice(0, 20)}${text.length > 20 ? '…' : ''}`
}

/* ---------- 草稿本与导出记录 ----------
   只写本机 localStorage：这是浏览器里的草稿，换设备看不到，
   真正交付还是导出 DOCX。不写后端是为了不把未定稿的公文留在服务器上。 */
function readStore<T>(key: string): T[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    return Array.isArray(parsed) ? parsed as T[] : []
  } catch {
    return []
  }
}

function writeStore(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 隐私模式下写不进去，不影响当前会话
  }
}

function loadLibrary() {
  savedDrafts.value = readStore<SavedDraft>(DRAFT_STORE)
  exportRecords.value = readStore<ExportRecord>(EXPORT_STORE)
}

function fmtWhen(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function saveDraft() {
  const text = draft.value.trim()
  if (!text) {
    message.value = '草稿是空的，没什么可存的'
    return
  }
  const title = previewTitle() || '未命名文档'
  const item: SavedDraft = {
    id: `d-${Date.now()}`,
    title,
    docType: docType.value,
    docTypeName: currentTemplate.value?.name ?? '公文',
    draft: draft.value,
    savedAt: new Date().toISOString(),
    chars: previewBody().length,
  }
  // 同标题同文种视为覆盖，避免存出一堆重复条目
  savedDrafts.value = [
    item,
    ...savedDrafts.value.filter((entry) => !(entry.title === title && entry.docType === docType.value)),
  ].slice(0, 30)
  writeStore(DRAFT_STORE, savedDrafts.value)
  message.value = `已存入草稿本：${title}（${item.chars} 字）`
}

function openSaved(item: SavedDraft) {
  draft.value = item.draft
  docType.value = item.docType
  const template = templates.value.find((entry) => entry.id === item.docType)
  if (template) {
    const banner = banners.value.find((entry) => entry.id === template.banner)
    bannerName.value = banner?.name ?? bannerName.value
    recipient.value = template.recipient
  }
  elements.value = null
  activeTab.value = 'editor'
  message.value = `已打开草稿：${item.title}`
}

function removeSaved(id: string) {
  const target = savedDrafts.value.find((entry) => entry.id === id)
  savedDrafts.value = savedDrafts.value.filter((entry) => entry.id !== id)
  writeStore(DRAFT_STORE, savedDrafts.value)
  message.value = target ? `已删除草稿：${target.title}` : '已删除'
}

function recordExport(title: string) {
  const record: ExportRecord = {
    id: `e-${Date.now()}`,
    title,
    docTypeName: currentTemplate.value?.name ?? '公文',
    at: new Date().toISOString(),
  }
  exportRecords.value = [record, ...exportRecords.value].slice(0, 20)
  writeStore(EXPORT_STORE, exportRecords.value)
}

function clearExports() {
  exportRecords.value = []
  writeStore(EXPORT_STORE, exportRecords.value)
  message.value = '已清空导出记录'
}

/* 细则：特急件 1 个工作日、急件 2 个工作日、正常件 5 个工作日。
   只跳周末，不算法定节假日——真要用还得查校历，界面上如实说明。 */
const deadlineInfo = computed(() => {
  const rule = deadlineRules.value.find((item) => item.label === urgency.value)
  if (!rule) return null
  const day = new Date()
  let left = rule.workdays
  while (left > 0) {
    day.setDate(day.getDate() + 1)
    const weekday = day.getDay()
    if (weekday !== 0 && weekday !== 6) left -= 1
  }
  const stamp = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
  return { label: rule.label, workdays: rule.workdays, date: stamp, note: rule.note }
})

/* ---------- 格式校验 ---------- */
interface FormatCheck {
  ok: boolean
  name: string
  detail: string
  /** error 表示细则硬性要求，warn 表示提醒 */
  level: 'error' | 'warn'
  /** 按细则的章节归组，避免一次甩出十几条让人无从下手 */
  group: 'title' | 'head' | 'body' | 'sign' | 'register'
}

const CHECK_GROUPS = [
  { id: 'title', label: '标题与文种' },
  { id: 'head', label: '版头与主送' },
  { id: 'body', label: '正文与附件' },
  { id: 'sign', label: '落款与成文日期' },
  { id: 'register', label: '版记与时限' },
] as const

const formatChecks = ref<FormatCheck[]>([])
const formatChecked = ref(false)
const groupedChecks = computed(() => CHECK_GROUPS
  .map((group) => ({ ...group, items: formatChecks.value.filter((item) => item.group === group.id) }))
  .filter((group) => group.items.length > 0))
const errorCount = computed(() => formatChecks.value.filter((item) => !item.ok && item.level === 'error').length)

/** 汉字成文日期，如「二○二六年十一月十三日」。细则第三十四条要求汉字标全。 */
const CHINESE_DATE = /^[〇零○一二三四五六七八九]{4}年[一二三四五六七八九十]{1,2}月[一二三四五六七八九十]{1,3}日$/
const DIGIT_DATE = /^\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,3}\s*日$/

/* ---------- 草稿本地解析 ----------
   模板草稿是「发文字号：…／标题：…／主送机关：…／正文：…／落款：…」这种带标签写法。
   点「解析」才走后端，但预览和格式校验必须先能用，否则标签会被当成正文印到 A4 纸上。
   后端 TemplatePreParser 是权威实现，这里只做同一套标签的最小镜像。 */
interface ParsedDraft {
  reference_number: string
  title: string
  body: string
  signature: string
  issue_date: string
  recipient: string
  signer: string
  attachments: string
}

const DRAFT_LABEL = /^\s*(发文字号|文号|标题|主送机关|主送单位|正文|落款|署名|成文日期|日期|签发人)\s*[：:]\s*(.*)$/
const ATTACH_HEAD = /^\s*附件\s*[：:]\s*(.*)$/
const ATTACH_ITEM = /^[（(]?\d+[）).、．]/

function parseLabeledDraft(text: string): ParsedDraft {
  const out: ParsedDraft = {
    reference_number: '', title: '', body: '', signature: '',
    issue_date: '', recipient: '', signer: '', attachments: '',
  }
  const body: string[] = []
  const attaches: string[] = []
  let inBody = false
  let stopped = false
  let inAttach = false

  for (const rawLine of text.split('\n')) {
    const line = rawLine.replace(/\s+$/, '')
    const label = line.match(DRAFT_LABEL)
    if (label) {
      const [, name, value] = label
      const field = value.trim()
      inAttach = false
      if (name === '发文字号' || name === '文号') { out.reference_number = field; continue }
      if (name === '标题') { out.title = field; continue }
      if (name === '主送机关' || name === '主送单位') { out.recipient = field; continue }
      if (name === '落款' || name === '署名') { out.signature = field; inBody = false; stopped = true; continue }
      if (name === '日期' || name === '成文日期') { out.issue_date = field; inBody = false; stopped = true; continue }
      if (name === '签发人') { out.signer = field; continue }
      // 正文：从这一行开始，后面所有非标签行都算正文
      inBody = true
      if (field) body.push(field)
      continue
    }

    const attachHead = line.match(ATTACH_HEAD)
    if (attachHead) {
      inAttach = true
      if (attachHead[1].trim()) attaches.push(attachHead[1].trim())
      continue
    }
    if (inAttach) {
      const cont = line.trim()
      // 续行是条目编号即算附件，缩进与否都收：细则要求对齐，但手打和模型输出经常顶格
      if (cont && ATTACH_ITEM.test(cont)) { attaches.push(cont); continue }
      inAttach = false
    }
    if (!stopped && inBody) body.push(line)
  }

  out.body = body.join('\n').trim()
  out.attachments = attaches.join('\n')
  return out
}

function previewTitle(): string {
  return (elements.value?.title
    || parseLabeledDraft(draft.value).title
    || draft.value.split('\n').map((line) => line.trim()).find(Boolean)
    || '').trim()
}

function previewBody(): string {
  return (elements.value?.body || parseLabeledDraft(draft.value).body || draft.value).trim()
}

/* 版式要素一律「后端解析结果优先，本地镜像兜底」：
   没点「解析草稿」之前，校验和 A4 预览也得能用。 */
function previewReference(): string {
  return (elements.value?.reference_number || parseLabeledDraft(draft.value).reference_number || '').trim()
}

function previewSignature(): string {
  return (elements.value?.signature || parseLabeledDraft(draft.value).signature || '').trim()
}

function previewDate(): string {
  return (elements.value?.issue_date || parseLabeledDraft(draft.value).issue_date || '').trim()
}

/** 正文实际字数，用于「够不够一份像样的公文」和 A4 页数估算 */
const bodyChars = computed(() => previewBody().length)

function checkFormat() {
  const title = previewTitle()
  const bodyText = previewBody()
  const dateText = previewDate()
  const reference = previewReference()
  const signature = previewSignature()
  const rc = recipient.value.trim()
  const att = attachments.value.trim()
  const keywordList = splitList(keywords.value)
  const ccList = splitList(cc.value)
  const checks: FormatCheck[] = []

  /* 标题与文种 */
  checks.push({
    ok: title.includes('山东师范大学'),
    name: '标题标明发文机关',
    detail: title.includes('山东师范大学')
      ? '已包含「山东师范大学」'
      : '细则要求标题一般应标明发文机关，如「山东师范大学关于……的通知」',
    level: 'warn',
    group: 'title',
  })

  checks.push({
    ok: title.length > 0 && title.length <= 40,
    name: '标题不超过 40 字',
    detail: title.length === 0 ? '标题为空' : `当前 ${title.length} 字${title.length > 40 ? '，建议精简' : ''}`,
    level: title.length > 40 ? 'error' : 'warn',
    group: 'title',
  })

  checks.push({
    ok: !/[。；;]$/.test(title),
    name: '标题结尾不加句号',
    detail: /[。；;]$/.test(title) ? '公文标题是一个名词性短语，结尾不加标点' : '格式正确',
    level: 'error',
    group: 'title',
  })

  /* 版头与主送 */
  checks.push({
    ok: !rc || /[：:]$/.test(rc),
    name: '主送机关以冒号收尾',
    detail: !rc
      ? '未填主送机关；通知、请示类文种应当填写'
      : /[：:]$/.test(rc)
        ? '格式正确'
        : '主送机关应以全角冒号「：」结尾，且顶格书写',
    level: rc ? 'error' : 'warn',
    group: 'head',
  })

  checks.push({
    ok: !reference || /〔\d{4}〕/.test(reference),
    name: '发文字号用六角括号',
    detail: !reference
      ? '未填发文字号'
      : /〔\d{4}〕/.test(reference)
        ? '格式正确'
        : '应形如「山东师大校字〔2026〕15号」，年份用六角括号〔〕，不用[]、()、［］',
    level: reference ? 'error' : 'warn',
    group: 'head',
  })

  checks.push({
    ok: !(docType.value === 'request' || docType.value === 'report') || Boolean(signer.value.trim()),
    name: '上行文标注签发人',
    detail: docType.value === 'request' || docType.value === 'report'
      ? (signer.value.trim() ? `已填签发人：${signer.value.trim()}` : '请示、报告等上报文件应当在文号右侧标注签发人')
      : '当前文种无需签发人',
    level: docType.value === 'request' || docType.value === 'report' ? 'error' : 'warn',
    group: 'head',
  })

  /* 正文与附件 */
  checks.push({
    ok: bodyText.length >= 50,
    name: '正文不少于 50 字',
    detail: bodyText.length === 0 ? '正文为空' : `当前 ${bodyText.length} 字`,
    level: 'warn',
    group: 'body',
  })

  const halfWidth = /\([一二三四五六七八九十]+\)/.test(bodyText) || /^\s*\d\.[^\d]/m.test(bodyText)
  checks.push({
    ok: !halfWidth,
    name: '层次序数用全角符号',
    detail: halfWidth
      ? '检测到半角「(一)」或「1.」，细则要求写成「（一）」「1．」'
      : '一级「一、」、二级「（一）」、三级「1．」均为全角',
    level: 'error',
    group: 'body',
  })

  const trailingPunct = /^[一二三四五六七八九十]+、[^\n]*[。，；]$/m.test(bodyText)
  checks.push({
    ok: !trailingPunct,
    name: '一级标题句尾不加标点',
    detail: trailingPunct
      ? '「一、」这类一级标题是标题不是句子，句尾不加句号、逗号、分号'
      : '未发现带标点的一级标题',
    level: 'warn',
    group: 'body',
  })

  checks.push({
    ok: !att || bodyText.includes('附件'),
    name: '附件说明与正文呼应',
    detail: !att
      ? '未填附件'
      : bodyText.includes('附件')
        ? '正文已提及附件'
        : '填了附件说明，但正文没有出现「附件」字样',
    level: 'warn',
    group: 'body',
  })

  // 起草助手和模板都用「×」占位：交出去之前必须补实，否则对方收到的是一份没写完的公文
  const placeholderHits = (draft.value.match(/×/g) ?? []).length
  checks.push({
    ok: placeholderHits === 0,
    name: '占位符已补实',
    detail: placeholderHits === 0
      ? '没有残留的 × 占位符'
      : `还有 ${placeholderHits} 处 × 没填实（时间、地点、人名、电话、金额等），导出前逐一替换`,
    level: 'warn',
    group: 'body',
  })

  /* 落款与成文日期 */
  checks.push({
    ok: CHINESE_DATE.test(dateText),
    name: '成文日期用汉字标全',
    detail: !dateText
      ? '未填成文日期'
      : CHINESE_DATE.test(dateText)
        ? '格式正确'
        : dateText.includes('×')
          ? '日期里还有 × 没填实，补齐成「二○二六年十一月十三日」这种形式'
          : DIGIT_DATE.test(dateText)
            ? '用了阿拉伯数字，细则要求写成「二○二六年十一月十三日」'
            : '日期格式无法识别，应形如「二○二六年十一月十三日」',
    level: dateText ? 'error' : 'warn',
    group: 'sign',
  })

  checks.push({
    ok: Boolean(signature),
    name: '落款单位已填写',
    detail: signature || '未填落款；印章盖在成文时间中间上方，没有落款就没法盖章',
    level: signature ? 'warn' : 'error',
    group: 'sign',
  })

  const closings = ['特此通知', '特此公告', '特此报告', '特此通报', '请批示', '请批复', '请遵照执行', '此复', '请予支持']
  const hasClosing = closings.some((item) => bodyText.includes(item))
  checks.push({
    ok: hasClosing,
    name: '正文有结束语',
    detail: hasClosing ? '已包含规范结束语' : `结尾建议补一句：${currentTemplate.value?.closing || '特此通知。'}`,
    level: 'warn',
    group: 'sign',
  })

  /* 版记与时限 */
  checks.push({
    ok: keywordList.length <= 5,
    name: '主题词不超过 5 个',
    detail: keywordList.length === 0
      ? '未填主题词'
      : `当前 ${keywordList.length} 个${keywordList.length > 5 ? '，超出细则上限' : ''}`,
    level: keywordList.length > 5 ? 'error' : 'warn',
    group: 'register',
  })

  checks.push({
    ok: Boolean(printAgency.value.trim()),
    name: '印发机关已填写',
    detail: printAgency.value.trim() || '版记最后一栏需要印发机关与印发日期',
    level: printAgency.value.trim() ? 'warn' : 'error',
    group: 'register',
  })

  const overlap = ccList.filter((item) => keywordList.includes(item))
  checks.push({
    ok: overlap.length === 0,
    name: '抄送不与主题词重复',
    detail: overlap.length === 0 ? '未发现重复' : `重复项：${overlap.join('、')}`,
    level: 'warn',
    group: 'register',
  })

  formatChecks.value = checks
  formatChecked.value = true
  const failed = checks.filter((item) => !item.ok).length
  const hard = checks.filter((item) => !item.ok && item.level === 'error').length
  message.value = failed === 0
    ? `格式检查：${checks.length} 项全部通过，可以导出 DOCX`
    : `格式检查：${checks.length - failed} 项通过，${failed} 项待改${hard ? `（其中 ${hard} 项是细则硬性要求）` : ''}`
}

/* ---------- 上传规范化（命题三：上传已有公文 → 一键改版式） ---------- */
/* 这条路和「起草」是两件事：起草负责写，规范化负责改。所以它单独一个 tab，
   不混进编辑器里，避免用户以为要先粘一遍正文。 */
const normalizeFile = ref<File | null>(null)
const normalizeInput = ref<HTMLInputElement | null>(null)
const normalizeBusy = ref(false)
const normalizeNotice = ref('')
const normalizeResult = ref<NormalizeResult | null>(null)
const normalizeDragging = ref(false)
const NORMALIZE_MAX_BYTES = 20 * 1024 * 1024

function setNormalizeFile(file: File | null) {
  normalizeResult.value = null
  normalizeNotice.value = ''
  if (!file) {
    normalizeFile.value = null
    return
  }
  const lower = file.name.toLowerCase()
  if (!lower.endsWith('.docx') && !lower.endsWith('.doc')) {
    normalizeFile.value = null
    normalizeNotice.value = '只接 .docx 和 .doc。如果手上是 PDF，先用 Word 另存为 .docx。'
    return
  }
  if (file.size > NORMALIZE_MAX_BYTES) {
    normalizeFile.value = null
    normalizeNotice.value = `这个文件 ${(file.size / 1024 / 1024).toFixed(1)}MB，超过 20MB 上限。`
    return
  }
  normalizeFile.value = file
}

function pickNormalizeFile() {
  normalizeInput.value?.click()
}

function onNormalizeFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  setNormalizeFile(input.files?.[0] ?? null)
  input.value = ''
}

function onNormalizeDrop(event: DragEvent) {
  normalizeDragging.value = false
  setNormalizeFile(event.dataTransfer?.files?.[0] ?? null)
}

async function runNormalize() {
  if (!normalizeFile.value || normalizeBusy.value) return
  normalizeBusy.value = true
  normalizeNotice.value = ''
  try {
    const response = await uploadDocumentForNormalize(normalizeFile.value, docType.value)
    normalizeResult.value = response.data
    normalizeNotice.value = response.message
  } catch (error) {
    normalizeNotice.value = error instanceof Error ? error.message : '这份文档没能改成功'
  } finally {
    normalizeBusy.value = false
  }
}

const normalizeDownloadUrl = computed(
  () => (normalizeResult.value ? `/api/v1/documents/normalize/${normalizeResult.value.token}` : ''),
)

/* ---------- A4 预览 ---------- */
const a4Zoom = ref(false)
/* 容器查询必须挂在外层 .dw-a4-sheet 上：元素不能查询自己的 padding，
   所以页面内所有 cqw 一律以「纸宽」为基准，1cqw = 1% 纸宽 */
const a4Page = ref<HTMLElement | null>(null)
const a4Pages = ref(1)
const a4OverflowPx = ref(0)
let a4Observer: ResizeObserver | null = null

function measureA4() {
  const el = a4Page.value
  if (!el) return
  const width = el.clientWidth
  if (!width) return
  const onePage = (width * 297) / 210
  const used = el.scrollHeight
  a4Pages.value = Math.max(1, Math.ceil((used - 2) / onePage))
  a4OverflowPx.value = Math.max(0, Math.round(used - onePage))
}

async function bindA4() {
  await nextTick()
  const el = a4Page.value
  if (!el) return
  a4Observer?.disconnect()
  a4Observer = new ResizeObserver(() => measureA4())
  a4Observer.observe(el)
  measureA4()
}

onBeforeUnmount(() => { a4Observer?.disconnect(); a4Observer = null })

const a4 = computed(() => {
  const local = parseLabeledDraft(draft.value)
  const body = previewBody() || '（正文待填）'
  const closing = currentTemplate.value?.closing ?? ''
  const recipientText = recipient.value || local.recipient
  return {
    marks: [secrecy.value, urgency.value].filter(Boolean).join('　'),
    banner: bannerName.value,
    reference: elements.value?.reference_number || local.reference_number,
    signer: signer.value || local.signer,
    title: previewTitle() || '（标题待填）',
    recipient: recipientText,
    showRecipient: Boolean(recipientText) && docType.value !== 'announcement' && docType.value !== 'minutes',
    body,
    // 正文里已经写了结束语就不再补一遍
    closing: closing && !body.includes(closing) ? closing : '',
    attachments: attachments.value || local.attachments,
    signature: elements.value?.signature || local.signature,
    issueDate: elements.value?.issue_date || local.issue_date,
    keywords: keywords.value,
    cc: cc.value,
    printAgency: printAgency.value,
  }
})

/* 进/出预览页或缩放时重新绑定观察器；正文变化只需重量一次 */
watch([activeTab, a4Zoom], () => { void bindA4() })
watch(a4, () => { void nextTick(measureA4) }, { deep: true })

onMounted(() => {
  loadTemplates()
  void loadPhrases()
  loadLibrary()
})
</script>

<template>
  <section class="document-page">
    <header class="document-head">
      <div>
        <p class="eyebrow">效率工具 / 文档工坊</p>
        <h1>公文排版，<em>按校规落地。</em></h1>
        <p>版式依据《山东师范大学行政文件格式细则》（山东师大校办字〔2007〕9 号）：2 号小标宋标题、3 号仿宋正文、汉字成文时间、主题词抄送印发三栏版记</p>
      </div>
    </header>

    <div class="document-tabs">
      <button :class="{ active: activeTab === 'templates' }" @click="activeTab = 'templates'">
        <PhCopy :size="16" /> 文种模板（{{ templates.length }}）
      </button>
      <button :class="{ active: activeTab === 'normalize' }" @click="activeTab = 'normalize'">
        <PhUploadSimple :size="16" /> 上传改格式
      </button>
      <button :class="{ active: activeTab === 'assist' }" @click="activeTab = 'assist'">
        <PhSparkle :size="16" /> 起草助手
      </button>
      <button :class="{ active: activeTab === 'editor' }" @click="activeTab = 'editor'">
        <PhFileText :size="16" /> 文档编辑
      </button>
      <button :class="{ active: activeTab === 'preview' }" @click="activeTab = 'preview'">
        <PhEye :size="16" /> A4 预览
      </button>
      <button :class="{ active: activeTab === 'format' }" @click="activeTab = 'format'">
        <PhListChecks :size="16" /> 格式细则
      </button>
      <button :class="{ active: activeTab === 'library' }" @click="activeTab = 'library'">
        <PhBookmarkSimple :size="16" /> 我的草稿（{{ savedDrafts.length }}）
      </button>
    </div>

    <!-- 文种模板 -->
    <div v-if="activeTab === 'templates'" class="templates-grid">
      <article
        v-for="template in templates"
        :key="template.id"
        class="template-card"
        :class="{ chosen: selectedTemplate === template.id }"
        @click="applyTemplate(template)"
      >
        <header class="template-card-head">
          <div>
            <h3>{{ template.name }}</h3>
            <small>{{ template.reference_sample }}</small>
          </div>
          <span class="template-banner-tag">
            {{ banners.find((item) => item.id === template.banner)?.name ?? '学校文件' }}
          </span>
        </header>

        <p class="template-scenario">{{ template.scenario }}</p>

        <div class="template-block">
          <strong>结构骨架</strong>
          <ol>
            <li v-for="item in template.structure" :key="item">{{ item }}</li>
          </ol>
        </div>

        <div class="template-block">
          <strong>格式要点</strong>
          <ul>
            <li v-for="item in template.format_notes" :key="item">{{ item }}</li>
          </ul>
        </div>

        <div class="template-block warn">
          <strong>常见错误</strong>
          <ul>
            <li v-for="item in template.pitfalls" :key="item">{{ item }}</li>
          </ul>
        </div>

        <footer class="template-card-foot">
          <span v-if="template.closing">结束语：{{ template.closing }}</span>
          <span v-else>无固定结束语</span>
          <button class="use-btn">使用模板</button>
        </footer>
      </article>
    </div>

    <!-- 上传改格式：已经写好的一份，直接按国标重排，不改一个字 -->
    <div v-if="activeTab === 'normalize'" class="dw-normalize">
      <section class="dw-norm-intro">
        <p class="eyebrow">已经写好的一份，直接改格式</p>
        <h2>上传公文，<em>按国标重排。</em></h2>
        <p class="dw-norm-lead">
          不改一个字，只把字体字号、段落行距、页边距、标题层级、序号编号、页眉页脚、落款日期改到合规。
          每一处改动都会列出来，写清依据哪一条。
        </p>
      </section>

      <div
        class="dw-norm-drop"
        :class="{ 'is-over': normalizeDragging, 'has-file': normalizeFile }"
        role="button"
        tabindex="0"
        @click="pickNormalizeFile"
        @keydown.enter.prevent="pickNormalizeFile"
        @keydown.space.prevent="pickNormalizeFile"
        @dragover.prevent="normalizeDragging = true"
        @dragleave.prevent="normalizeDragging = false"
        @drop.prevent="onNormalizeDrop"
      >
        <input ref="normalizeInput" type="file" accept=".docx,.doc" class="dw-norm-input" @change="onNormalizeFileChange">
        <PhFileDoc :size="30" weight="duotone" />
        <strong v-if="!normalizeFile">拖一份 .docx 进来，或点这里选文件</strong>
        <strong v-else>{{ normalizeFile.name }}</strong>
        <span v-if="normalizeFile">{{ (normalizeFile.size / 1024).toFixed(0) }} KB · 点一下换一份</span>
        <span v-else>支持 .docx / .doc，最大 20MB</span>
      </div>

      <div class="dw-norm-actions">
        <label class="dw-norm-type">
          <span>按哪种文种核对</span>
          <select v-model="docType">
            <option v-for="template in templates" :key="template.id" :value="template.id">{{ template.name }}</option>
          </select>
        </label>
        <button class="ink-button primary" :disabled="!normalizeFile || normalizeBusy" @click="runNormalize">
          <PhSealCheck :size="16" /> {{ normalizeBusy ? '正在重排…' : '开始规范化' }}
        </button>
      </div>

      <p v-if="normalizeNotice" class="dw-norm-notice">{{ normalizeNotice }}</p>

      <template v-if="normalizeResult">
        <section class="dw-norm-summary">
          <header>
            <div>
              <p class="micro">
                {{ normalizeResult.doc_type_name }} · {{ normalizeResult.paragraphs }} 段 ·
                {{ normalizeResult.text_chars }} 字
              </p>
              <h3>改了 {{ normalizeResult.total_changes }} 处</h3>
            </div>
            <a class="ink-button primary" :href="normalizeDownloadUrl" :download="normalizeResult.filename">
              <PhDownload :size="16" /> 下载规范化后的文件
            </a>
          </header>
          <ul class="dw-norm-cats">
            <li v-for="(count, name) in normalizeResult.by_category" :key="name">
              <span>{{ name }}</span><strong>{{ count }}</strong>
            </li>
          </ul>
          <p class="dw-norm-standard">
            依据 {{ normalizeResult.standard }}；{{ normalizeResult.rule }}。文件保留 {{ Math.round(normalizeResult.expires_in / 60) }} 分钟。
          </p>
          <AnswerFeedback target="doc_normalize" hint="这次改得对吗" />
        </section>

        <section class="dw-norm-checks">
          <h3>按「{{ normalizeResult.doc_type_name }}」的要素自检</h3>
          <ul>
            <li v-for="item in normalizeResult.checklist" :key="item.item" :class="{ ok: item.present }">
              <PhCheckCircle v-if="item.present" :size="16" />
              <PhCircle v-else :size="16" />
              <span>{{ item.item }}</span>
              <em v-if="!item.present && item.note">{{ item.note }}</em>
            </li>
          </ul>
        </section>

        <section class="dw-norm-changes">
          <h3>逐条改动</h3>
          <div class="dw-norm-table">
            <div class="dw-norm-row dw-norm-row-head">
              <span>位置</span><span>类别</span><span>原来</span><span>改成</span><span>依据</span>
            </div>
            <div
              v-for="(change, position) in normalizeResult.changes"
              :key="`${change.index}-${change.category}-${position}`"
              class="dw-norm-row"
            >
              <span>{{ change.target }}</span>
              <span class="dw-norm-tag">{{ change.category }}</span>
              <span class="dw-norm-before">{{ change.before }}</span>
              <span class="dw-norm-after">{{ change.after }}</span>
              <span class="dw-norm-basis">{{ change.basis }}</span>
            </div>
          </div>
        </section>

        <section v-if="normalizeResult.warnings.length" class="dw-norm-warnings">
          <h3><PhWarningCircle :size="16" /> 需要你再看一眼</h3>
          <ul>
            <li v-for="(warning, position) in normalizeResult.warnings" :key="position">{{ warning }}</li>
          </ul>
        </section>
      </template>
    </div>

    <!-- 起草助手：一句话成稿 + 文种选择 + 易混对照 + 句式库 -->
    <div v-if="activeTab === 'assist'" class="dw-assist">
      <p v-if="message" class="dw-status">{{ message }}</p>
      <article class="dw-assist-card dw-brief-card">
        <header class="dw-assist-head">
          <div>
            <p class="micro">01 / 一句话成稿</p>
            <strong>把口语需求写成合规草稿</strong>
            <small>说清「做什么、谁参加、什么时候」，其余按细则补齐，具体信息留成 ×× 由你填</small>
          </div>
          <PhMagicWand :size="22" />
        </header>

        <textarea
          v-model="brief"
          class="dw-brief-input"
          rows="3"
          placeholder="例如：下周三下午两点组织全院消防疏散演练，各年级辅导员和班长必须参加"
        />

        <div class="dw-brief-examples">
          <span>试试：</span>
          <button v-for="item in BRIEF_EXAMPLES" :key="item" type="button" @click="brief = item">{{ item }}</button>
        </div>

        <footer class="dw-brief-foot">
          <label class="dw-brief-genre">文种
            <select v-model="docType">
              <option v-for="template in templates" :key="template.id" :value="template.id">{{ template.name }}</option>
            </select>
          </label>
          <button class="ink-button primary" type="button" :disabled="drafting || !brief.trim()" @click="composeDraft">
            <PhSparkle :size="16" /> {{ drafting ? '起草中…' : '生成草稿' }}
          </button>
        </footer>

        <p class="dw-brief-note">
          生成后自动进入「文档编辑」，可继续改字、检查格式、导出 DOCX。
          <span v-if="draftSource === 'deepseek'" class="dw-src is-live">上次由大模型起草</span>
          <span v-else-if="draftSource === 'local'" class="dw-src">上次为本地骨架（模型不可用）</span>
        </p>
      </article>

      <article class="dw-assist-card">
        <header class="dw-assist-head">
          <div>
            <p class="micro">02 / 该用哪个文种</p>
            <strong>先看行文方向，再看要不要答复</strong>
            <small>选错文种是公文被退办的第一大原因</small>
          </div>
        </header>
        <ul class="dw-genre-list">
          <li v-for="row in genres" :key="row.id" :class="{ chosen: docType === row.template_id }">
            <div class="dw-genre-main">
              <strong>{{ row.name }}</strong>
              <span class="dw-genre-tag">{{ row.direction }}</span>
              <span class="dw-genre-tag" :class="{ ask: row.reply.includes('必须') }">{{ row.reply }}</span>
            </div>
            <p>{{ row.when }}</p>
            <small>{{ row.sign }}</small>
            <div class="dw-genre-foot">
              <span>结束语：{{ row.closing }}</span>
              <button type="button" @click="useGenre(row)">
                {{ docType === row.template_id ? '当前文种' : '用这个文种' }}
                <PhArrowRight :size="14" />
              </button>
            </div>
          </li>
        </ul>
      </article>

      <article class="dw-assist-card">
        <header class="dw-assist-head">
          <div>
            <p class="micro">03 / 易混文种对照</p>
            <strong>四组最容易写错的</strong>
            <small>每组的差别只有一句话，记住这一句就够了</small>
          </div>
        </header>
        <div class="dw-contrast-grid">
          <section v-for="row in contrasts" :key="row.pair">
            <h4>{{ row.pair }}<small>{{ row.verdict }}</small></h4>
            <ul>
              <li v-for="line in row.items" :key="line">{{ line }}</li>
            </ul>
          </section>
        </div>
      </article>

      <article class="dw-assist-card">
        <header class="dw-assist-head">
          <div>
            <p class="micro">04 / 句式库</p>
            <strong>点一下插到正文光标处</strong>
            <small>{{ phraseCount }} 条常用表达，按在公文里的位置分组，不覆盖你已写的内容</small>
          </div>
          <PhQuotes :size="22" />
        </header>
        <div class="dw-phrase-tabs">
          <button
            v-for="group in phraseGroups"
            :key="group.id"
            type="button"
            :class="{ active: activePhraseGroup === group.id }"
            @click="activePhraseGroup = group.id"
          >
            {{ group.label }}
          </button>
        </div>
        <p v-if="currentPhraseGroup" class="dw-phrase-hint">{{ currentPhraseGroup.hint }}</p>
        <ul class="dw-phrase-list">
          <li v-for="item in currentPhraseGroup?.items ?? []" :key="item.id">
            <button type="button" @click="insertPhrase(item.text)">
              <span class="dw-phrase-text">{{ item.text }}</span>
              <span class="dw-phrase-slot">{{ item.slot }}</span>
              <PhPlus :size="14" />
            </button>
          </li>
        </ul>
        <p class="dw-phrase-tip">
          插入的句子是占位模板，记得把「……」换成你自己的内容；「×」是细则里的占位符，导出前要补实。
        </p>
      </article>
    </div>

    <!-- 我的草稿：草稿本 + 导出记录 -->
    <div v-if="activeTab === 'library'" class="dw-library">
      <p v-if="message" class="dw-status">{{ message }}</p>
      <article class="dw-lib-card">
        <header class="dw-lib-head">
          <div>
            <p class="micro">草稿本</p>
            <strong>{{ savedDrafts.length }} 份</strong>
            <small>存在本机浏览器，换设备看不到；导出 DOCX 才算真正交付</small>
          </div>
          <button class="ink-button" type="button" :disabled="!draft.trim()" @click="saveDraft">
            <PhPlus :size="16" /> 存当前草稿
          </button>
        </header>
        <ul v-if="savedDrafts.length" class="dw-lib-list">
          <li v-for="item in savedDrafts" :key="item.id">
            <div class="dw-lib-main">
              <strong>{{ item.title }}</strong>
              <small>{{ item.docTypeName }} · {{ item.chars }} 字 · {{ fmtWhen(item.savedAt) }}</small>
            </div>
            <div class="dw-lib-actions">
              <button type="button" @click="openSaved(item)">打开</button>
              <button type="button" class="danger" @click="removeSaved(item.id)">删除</button>
            </div>
          </li>
        </ul>
        <p v-else class="dw-lib-empty">
          还没存过草稿。在「文档编辑」里写好后点「存草稿」，或点右上角「存当前草稿」。
        </p>
      </article>

      <article class="dw-lib-card">
        <header class="dw-lib-head">
          <div>
            <p class="micro">导出记录</p>
            <strong>{{ exportRecords.length }} 次</strong>
            <small>只记录本机导出过的文件名与文种，不保存文件内容</small>
          </div>
          <button class="ink-button" type="button" :disabled="!exportRecords.length" @click="clearExports">
            清空记录
          </button>
        </header>
        <ul v-if="exportRecords.length" class="dw-lib-list">
          <li v-for="item in exportRecords" :key="item.id">
            <div class="dw-lib-main">
              <strong>{{ item.title }}.docx</strong>
              <small>{{ item.docTypeName }} · {{ fmtWhen(item.at) }}</small>
            </div>
          </li>
        </ul>
        <p v-else class="dw-lib-empty">
          还没导出过。在「文档编辑」里解析草稿后点「导出 DOCX」。
        </p>
      </article>
    </div>

    <!-- 文档编辑 -->
    <div v-if="activeTab === 'editor'" class="document-grid">
      <article class="draft-card">
        <div class="card-header">
          <p class="micro">01 / 原始草稿</p>
          <div class="card-actions">
            <button class="icon-btn" title="复制" @click="copyDraft"><PhCopy :size="16" /></button>
            <button class="icon-btn" title="清空" @click="clearDraft"><PhTrash :size="16" /></button>
          </div>
        </div>

        <div class="doc-controls">
          <label>文种
            <select v-model="docType">
              <option v-for="template in templates" :key="template.id" :value="template.id">{{ template.name }}</option>
            </select>
          </label>
          <label>版头
            <select v-model="bannerName">
              <option v-for="banner in banners" :key="banner.id" :value="banner.name">{{ banner.name }}</option>
            </select>
          </label>
          <label>主送机关<input v-model="recipient" placeholder="校内各单位："></label>
          <label>紧急程度
            <select v-model="urgency">
              <option value="">无</option>
              <option value="特急">特急</option>
              <option value="急件">急件</option>
            </select>
          </label>
          <label>密级<input v-model="secrecy" placeholder="秘密★1年（可空）"></label>
          <label>签发人<input v-model="signer" placeholder="上报文件需填"></label>
          <label>附件<input v-model="attachments" placeholder="多个用逗号分隔"></label>
          <label>抄送<input v-model="cc" placeholder="多个用逗号分隔"></label>
          <label>主题词<input v-model="keywords" placeholder="不超过 5 个，逗号分隔"></label>
          <label>印发机关<input v-model="printAgency"></label>
        </div>

        <p v-if="deadlineInfo" class="dw-deadline">
          <PhClock :size="14" />
          {{ deadlineInfo.label }}件按细则须 {{ deadlineInfo.workdays }} 个工作日内报送，最晚
          <strong>{{ deadlineInfo.date }}</strong>。{{ deadlineInfo.note }}（只跳周末，未计法定节假日）
        </p>

        <textarea
          ref="draftEl"
          v-model="draft"
          class="document-draft"
          placeholder="输入公文内容，或用上方「文种模板」载入骨架，也可以在「起草助手」里一句话生成…"
        ></textarea>
        <div class="card-footer">
          <button class="ink-button" :disabled="loading || !draft.trim()" @click="parseDraft">
            {{ loading ? '解析中...' : '解析草稿' }}
          </button>
          <button class="ink-button" :disabled="!draft.trim()" @click="saveDraft">
            <PhBookmarkSimple :size="16" /> 存草稿
          </button>
          <button class="ink-button primary" :disabled="loading || !elements" @click="exportDocx">
            <PhDownload :size="16" /> 导出 DOCX
          </button>
        </div>
        <p class="form-hint">
          {{ message || '选择文种与版头后解析草稿，导出的 DOCX 会带上版头红线、版记与页码' }}
          <span v-if="draftSource === 'deepseek'" class="dw-src is-live">大模型起草</span>
          <span v-else-if="draftSource === 'local'" class="dw-src">本地骨架</span>
        </p>
      </article>

      <article class="preview-card">
        <p class="micro">02 / 版式预览</p>
        <template v-if="elements">
          <p v-if="secrecy || urgency" class="preview-marks">{{ [secrecy, urgency].filter(Boolean).join('　') }}</p>
          <p class="preview-banner">{{ bannerName }}</p>
          <div class="red-rule"></div>
          <p class="reference">
            {{ elements.reference_number }}
            <span v-if="signer">　签发人：{{ signer }}</span>
          </p>
          <h2>{{ elements.title }}</h2>
          <p v-if="recipient && docType !== 'announcement' && docType !== 'minutes'" class="preview-recipient">{{ recipient }}</p>
          <p class="body-preview">{{ elements.body }}</p>
          <p v-if="currentTemplate?.closing" class="body-preview">{{ currentTemplate.closing }}</p>
          <p v-if="attachments" class="body-preview">附件：{{ attachments }}</p>
          <div class="signature-block">
            <p class="signature">{{ elements.signature }}</p>
            <p class="issue-date">{{ elements.issue_date }}</p>
          </div>
          <div v-if="keywords || cc" class="preview-register">
            <p v-if="keywords">主题词：{{ keywords }}</p>
            <p v-if="cc">抄送：{{ cc }}</p>
            <p>{{ printAgency }}　{{ elements.issue_date }}印发</p>
          </div>
        </template>
        <div v-else class="empty-preview">
          <PhEye :size="48" />
          <p>尚未解析</p>
          <small>系统将识别文号、标题、正文、落款与日期</small>
        </div>
      </article>
    </div>

    <!-- 格式校验：逐条对照细则，给出可改的清单 -->
    <section v-if="activeTab === 'editor'" class="dw-check-panel">
      <header class="dw-check-head">
        <div>
          <strong>格式校验</strong>
          <small>按《山东师范大学行政文件格式细则》逐条检查，不通过项直接告诉你改哪里</small>
        </div>
        <button class="ink-button" type="button" @click="checkFormat">检查格式</button>
      </header>

      <div v-if="formatChecked" class="dw-check-body">
        <p class="dw-check-summary" :class="{ pass: formatChecks.every((item) => item.ok) }">
          {{ formatChecks.every((item) => item.ok)
            ? `${formatChecks.length} 项检查全部通过`
            : `${formatChecks.filter((item) => item.ok).length} / ${formatChecks.length} 项通过${errorCount ? `，其中 ${errorCount} 项是细则硬性要求` : ''}` }}
        </p>
        <section v-for="group in groupedChecks" :key="group.id" class="dw-check-group">
          <h4>{{ group.label }}</h4>
          <ul class="dw-check-list">
            <li v-for="item in group.items" :key="item.name" :class="[item.ok ? 'is-ok' : 'is-bad', item.level]">
              <span class="dw-check-mark">{{ item.ok ? '✓' : (item.level === 'error' ? '✕' : '!') }}</span>
              <div>
                <strong>{{ item.name }}</strong>
                <p>{{ item.detail }}</p>
              </div>
            </li>
          </ul>
        </section>
      </div>
      <p v-else class="dw-check-idle">
        填好标题、正文与落款后点「检查格式」，会按标题、版头、正文、落款、版记五组逐条列出通过项和待改项。
      </p>

      <p class="dw-check-note">
        报送时限：特急件 1 个工作日、急件 2 个工作日、正常件 5 个工作日；一般公文需提前 3 天报送。
        特急、急件须经校领导批准后标注，不得自行确定。
      </p>
    </section>

    <!-- A4 预览：按 210×297 比例渲染，字号随纸宽缩放 -->
    <div v-if="activeTab === 'preview'" class="dw-a4-wrap">
      <header class="dw-a4-toolbar">
        <div>
          <strong>预览 · A4</strong>
          <small>210 × 297 mm，左侧装订，正文 3 号仿宋</small>
        </div>
        <div class="dw-a4-toolbar-right">
          <span class="dw-a4-chip">{{ bodyChars }} 字</span>
          <span class="dw-a4-chip" :class="{ 'is-over': a4Pages > 1 }">
            {{ a4Pages > 1 ? `约 ${a4Pages} 页` : '1 页' }}
          </span>
          <button class="ink-button" type="button" @click="a4Zoom = !a4Zoom">
            {{ a4Zoom ? '还原' : '放大' }}
          </button>
        </div>
      </header>

      <div class="dw-a4-stage">
        <div class="dw-a4-sheet" :class="{ 'is-zoomed': a4Zoom }">
          <article ref="a4Page" class="dw-a4-page">
            <p v-if="a4.marks" class="dw-a4-marks">{{ a4.marks }}</p>
            <p class="dw-a4-banner">{{ a4.banner }}</p>
            <div class="dw-a4-rule" />
            <p class="dw-a4-reference">
              {{ a4.reference || '山东师大校字〔20××〕×号' }}
              <span v-if="a4.signer">　签发人：{{ a4.signer }}</span>
            </p>
            <h2 class="dw-a4-title">{{ a4.title }}</h2>
            <p v-if="a4.showRecipient" class="dw-a4-recipient">{{ a4.recipient }}</p>
            <p class="dw-a4-body">{{ a4.body }}</p>
            <p v-if="a4.closing" class="dw-a4-body">{{ a4.closing }}</p>
            <p v-if="a4.attachments" class="dw-a4-body dw-a4-attach">
              <span>附件：{{ a4.attachments.split('\n')[0] }}</span>
              <span
                v-for="(item, index) in a4.attachments.split('\n').slice(1)"
                :key="index"
                class="dw-a4-attach-line"
              >{{ item }}</span>
            </p>
            <div class="dw-a4-sign">
              <p>{{ a4.signature }}</p>
              <p>{{ a4.issueDate || '二○二六年××月××日' }}</p>
            </div>
            <div v-if="a4.keywords || a4.cc" class="dw-a4-register">
              <p v-if="a4.keywords">主题词：{{ a4.keywords }}</p>
              <p v-if="a4.cc">抄送：{{ a4.cc }}</p>
              <p>{{ a4.printAgency }}　{{ a4.issueDate || '二○二六年××月××日' }}印发</p>
            </div>
            <p class="dw-a4-page-no">— 1 —</p>
          </article>
        </div>
      </div>
      <p v-if="a4OverflowPx > 0" class="dw-a4-overflow">
        正文已超出 A4 单页（当前约 {{ a4Pages }} 页），导出 DOCX 后 Word 会自动分页；想压在一页内可精简正文或去掉版记。
      </p>
    </div>

    <!-- 格式细则 -->
    <div v-if="activeTab === 'format'" class="format-panel">
      <article v-for="template in templates" :key="template.id" class="format-row">
        <h3>{{ template.name }}<small>{{ template.reference_sample }}</small></h3>
        <p class="format-scenario">{{ template.scenario }}</p>
        <ul>
          <li v-for="item in template.format_notes" :key="item">{{ item }}</li>
        </ul>
      </article>
      <article class="format-row">
        <h3>通用硬规则<small>细则第三～二十二条</small></h3>
        <ul>
          <li>发文字号：山东师大校字〔20××〕×号 / 山东师大校办字〔20××〕×号 / 山东师大校干聘字 / 山东师大外字 / 山东师大人合退字</li>
          <li>纸张 A4（210mm×297mm），左侧装订，文字从左往右横排，不得使用异体字、繁体字</li>
          <li>标题 2 号小标宋，红线下空 2 行；正文 3 号仿宋，每段左空 2 字、回行顶格</li>
          <li>层次序数：一级「一、」3 号黑体（句尾不加标点）、二级「（一）」3 号楷体、三级「1．」3 号仿宋</li>
          <li>成文时间用汉字标全（二○二六年九月二十八日），印章盖于成文时间中间上方</li>
          <li>版记三栏：主题词（≤5 个，3 号黑体顶格）→ 抄送机关 → 印发机关与印发日期（行首行末各空 1 字）</li>
          <li>页码 4 号半角阿拉伯数码，置于版心下边缘之下一行</li>
          <li>报送时限：特急件 1 个工作日、急件 2 个工作日、正常件 5 个工作日；一般公文需提前 3 天报送</li>
        </ul>
      </article>
      <p class="format-source">
        依据：山东师大校办字〔2007〕9 号《关于印发〈山东师范大学行政发文文稿审核制发规范〉、
        〈山东师范大学行政文件格式细则〉、〈山东师范大学行政公文及文稿处理退办规定〉、
        〈山东师范大学内部请示报告运转规范〉等 4 个文件的通知》。
      </p>
    </div>
  </section>
</template>

<style scoped>
/* ---------- 格式校验 ---------- */
.dw-check-panel {
  margin-top: 22px;
  padding: 20px 22px;
  border: 1px solid rgba(47, 74, 69, 0.12);
  border-radius: 16px;
  background: rgba(255, 253, 248, 0.82);
}

.dw-check-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.dw-check-head strong {
  display: block;
  color: #2f4a45;
  font-size: 16px;
}

.dw-check-head small {
  display: block;
  margin-top: 4px;
  color: #7b8b86;
  font-size: 12.5px;
  line-height: 1.6;
}

.dw-check-body {
  margin-top: 16px;
}

.dw-check-summary {
  margin: 0 0 12px;
  color: #a8501f;
  font-size: 13px;
  font-weight: 600;
}

.dw-check-summary.pass {
  color: #2f7a52;
}

.dw-check-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.dw-check-list li {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 9px 12px;
  border-radius: 10px;
  background: rgba(47, 74, 69, 0.04);
}

.dw-check-list li.is-ok {
  background: rgba(47, 122, 82, 0.07);
}

.dw-check-list li.is-bad.error {
  background: rgba(184, 74, 48, 0.08);
}

.dw-check-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: #2f7a52;
}

.dw-check-list li.is-bad.error .dw-check-mark {
  background: #b84a30;
}

.dw-check-list li.is-bad.warn .dw-check-mark {
  background: #c98a2b;
}

.dw-check-list strong {
  display: block;
  color: #2f4a45;
  font-size: 13.5px;
  font-weight: 600;
}

.dw-check-list p {
  margin: 3px 0 0;
  color: #6d7d78;
  font-size: 12.5px;
  line-height: 1.65;
}

.dw-check-idle {
  margin: 14px 0 0;
  color: #8a9994;
  font-size: 12.5px;
}

.dw-check-note {
  margin: 14px 0 0;
  padding-top: 10px;
  border-top: 1px dashed rgba(47, 74, 69, 0.14);
  color: #8a9994;
  font-size: 12px;
  line-height: 1.7;
}

/* ---------- A4 预览 ---------- */
.dw-a4-wrap {
  margin-top: 22px;
}

.dw-a4-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.dw-a4-toolbar strong {
  display: block;
  color: #2f4a45;
  font-size: 16px;
}

.dw-a4-toolbar small {
  display: block;
  margin-top: 4px;
  color: #7b8b86;
  font-size: 12.5px;
}

.dw-a4-toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dw-a4-chip {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(47, 74, 69, 0.08);
  color: #46605a;
  font-size: 12.5px;
  font-variant-numeric: tabular-nums;
}

.dw-a4-chip.is-over {
  background: rgba(179, 38, 30, 0.1);
  color: #b3261e;
}

.dw-a4-stage {
  display: flex;
  justify-content: center;
  padding: 26px 0 34px;
  border-radius: 16px;
  background:
    repeating-linear-gradient(45deg, rgba(47, 74, 69, 0.03) 0 12px, transparent 12px 24px),
    rgba(240, 236, 228, 0.7);
}

/* 容器查询挂在这一层：它的宽度就是纸宽，且自身没有内边距，
   所以页面内 1cqw 严格等于纸宽的 1%，padding 和字号共用同一基准 */
.dw-a4-sheet {
  container-type: inline-size;
  width: min(100%, 620px);
  transition: width 0.24s ease;
}

.dw-a4-sheet.is-zoomed {
  width: min(100%, 880px);
}

.dw-a4-page {
  box-sizing: border-box;
  width: 100%;
  /* 一页 A4 的最小高度：100cqw 即纸宽，按 297/210 换算 */
  min-height: calc(100cqw * 297 / 210);
  display: flex;
  flex-direction: column;
  padding: 17.6cqw 12.4cqw 16.7cqw 13.3cqw;
  border-radius: 3px;
  background: #fffefb;
  box-shadow: 0 14px 34px rgba(40, 52, 48, 0.16), 0 1px 0 rgba(0, 0, 0, 0.05);
  color: #1c2523;
  font-family: "Songti SC", "STSong", "SimSun", serif;
}

.dw-a4-marks {
  margin: 0 0 1.2cqw;
  color: #b3261e;
  font-size: 2.6cqw;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.dw-a4-banner {
  margin: 0;
  color: #b3261e;
  font-size: 4.6cqw;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-align: center;
}

.dw-a4-rule {
  height: 0.42cqw;
  margin: 1.6cqw 0 1.4cqw;
  background: #b3261e;
}

.dw-a4-reference {
  margin: 0 0 1.4cqw;
  font-size: 2.5cqw;
  text-align: center;
}

.dw-a4-title {
  margin: 0 0 1.6cqw;
  font-size: 3.7cqw;
  font-weight: 700;
  line-height: 1.5;
  text-align: center;
}

.dw-a4-recipient {
  margin: 0 0 0.8cqw;
  font-size: 2.69cqw;
  line-height: 1.7;
}

.dw-a4-body {
  margin: 0 0 0.6cqw;
  font-size: 2.69cqw;
  line-height: 1.85;
  text-align: justify;
  text-indent: 2em;
  white-space: pre-wrap;
}

.dw-a4-attach-line {
  display: block;
  padding-left: 3.2em;
  text-indent: 0;
}

.dw-a4-sign {
  margin-top: 3.4cqw;
  font-size: 2.69cqw;
  line-height: 1.9;
  text-align: right;
}

.dw-a4-sign p {
  margin: 0;
}

.dw-a4-register {
  margin-top: 3cqw;
  padding-top: 0.9cqw;
  border-top: 0.16cqw solid #b3261e;
  font-size: 2.3cqw;
  line-height: 1.8;
}

.dw-a4-register p {
  margin: 0;
}

.dw-a4-page-no {
  margin: auto 0 0;
  padding-top: 1.4cqw;
  font-size: 2.2cqw;
  text-align: center;
}

.dw-a4-overflow {
  margin: 0 0 6px;
  padding: 9px 14px;
  border-left: 3px solid #b3261e;
  border-radius: 0 8px 8px 0;
  background: rgba(179, 38, 30, 0.06);
  color: #8c1d17;
  font-size: 13px;
  line-height: 1.6;
}

/* ---------- 起草助手 ---------- */
.dw-assist {
  display: grid;
  gap: 18px;
  margin-top: 22px;
}

/* 起草助手与草稿本没有 form-hint，操作反馈要单独给一行，否则点了没反应 */
.dw-status {
  margin: 0;
  padding: 9px 14px;
  border-left: 3px solid rgba(47, 122, 82, 0.5);
  border-radius: 0 8px 8px 0;
  background: rgba(47, 122, 82, 0.07);
  color: #2f6b4c;
  font-size: 12.5px;
  line-height: 1.65;
}

.dw-assist-card {
  padding: 20px 22px;
  border: 1px solid rgba(47, 74, 69, 0.12);
  border-radius: 16px;
  background: rgba(255, 253, 248, 0.82);
}

.dw-assist-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  color: #2f4a45;
}

.dw-assist-head strong {
  display: block;
  margin-top: 2px;
  color: #2f4a45;
  font-size: 16px;
}

.dw-assist-head small {
  display: block;
  margin-top: 4px;
  color: #7b8b86;
  font-size: 12.5px;
  line-height: 1.65;
}

.dw-assist-head .micro {
  margin: 0;
}

.dw-brief-input {
  width: 100%;
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid rgba(47, 74, 69, 0.16);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.7);
  color: #2f4a45;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.7;
  resize: vertical;
}

.dw-brief-input:focus {
  outline: none;
  border-color: rgba(47, 122, 82, 0.5);
  box-shadow: 0 0 0 3px rgba(47, 122, 82, 0.1);
}

.dw-brief-examples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}

.dw-brief-examples > span {
  color: #8a9994;
  font-size: 12.5px;
}

.dw-brief-examples button {
  max-width: 100%;
  padding: 5px 10px;
  border: 1px dashed rgba(47, 74, 69, 0.24);
  border-radius: 999px;
  background: transparent;
  color: #4c6b64;
  font-size: 12.5px;
  line-height: 1.5;
  text-align: left;
  cursor: pointer;
}

.dw-brief-examples button:hover {
  border-color: rgba(47, 122, 82, 0.45);
  background: rgba(47, 122, 82, 0.07);
  color: #2f7a52;
}

.dw-brief-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
}

.dw-brief-genre {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #6d7d78;
  font-size: 13px;
}

.dw-brief-genre select {
  padding: 7px 10px;
  border: 1px solid rgba(47, 74, 69, 0.16);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.8);
  color: #2f4a45;
  font-size: 13px;
  font-family: inherit;
}

.dw-brief-note {
  margin: 12px 0 0;
  color: #8a9994;
  font-size: 12.5px;
  line-height: 1.65;
}

.dw-src {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(47, 74, 69, 0.07);
  color: #7b8b86;
  font-size: 11.5px;
}

.dw-src.is-live {
  background: rgba(47, 122, 82, 0.12);
  color: #2f7a52;
}

.dw-genre-list {
  display: grid;
  gap: 10px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
}

.dw-genre-list li {
  padding: 12px 14px;
  border: 1px solid rgba(47, 74, 69, 0.1);
  border-radius: 12px;
  background: rgba(47, 74, 69, 0.03);
}

.dw-genre-list li.chosen {
  border-color: rgba(47, 122, 82, 0.4);
  background: rgba(47, 122, 82, 0.07);
}

.dw-genre-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.dw-genre-main strong {
  color: #2f4a45;
  font-size: 15px;
}

.dw-genre-tag {
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(47, 74, 69, 0.08);
  color: #5d726c;
  font-size: 11.5px;
}

.dw-genre-tag.ask {
  background: rgba(184, 74, 48, 0.1);
  color: #b84a30;
}

.dw-genre-list p {
  margin: 8px 0 0;
  color: #3f5852;
  font-size: 13px;
  line-height: 1.7;
}

.dw-genre-list small {
  display: block;
  margin-top: 4px;
  color: #8a9994;
  font-size: 12px;
  line-height: 1.65;
}

.dw-genre-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px dashed rgba(47, 74, 69, 0.14);
  color: #7b8b86;
  font-size: 12px;
}

.dw-genre-foot button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid rgba(47, 74, 69, 0.18);
  border-radius: 999px;
  background: transparent;
  color: #2f7a52;
  font-size: 12px;
  cursor: pointer;
}

.dw-genre-foot button:hover {
  border-color: rgba(47, 122, 82, 0.45);
  background: rgba(47, 122, 82, 0.08);
}

.dw-contrast-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.dw-contrast-grid section {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(47, 74, 69, 0.03);
}

.dw-contrast-grid h4 {
  margin: 0;
  color: #2f4a45;
  font-size: 14px;
}

.dw-contrast-grid h4 small {
  display: block;
  margin-top: 2px;
  color: #a8501f;
  font-size: 12px;
  font-weight: 500;
}

.dw-contrast-grid ul {
  display: grid;
  gap: 6px;
  margin: 9px 0 0;
  padding-left: 18px;
}

.dw-contrast-grid li {
  color: #4c6b64;
  font-size: 12.5px;
  line-height: 1.7;
}

.dw-phrase-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.dw-phrase-tabs button {
  padding: 6px 12px;
  border: 1px solid rgba(47, 74, 69, 0.14);
  border-radius: 999px;
  background: transparent;
  color: #5d726c;
  font-size: 12.5px;
  cursor: pointer;
}

.dw-phrase-tabs button.active {
  border-color: rgba(47, 122, 82, 0.45);
  background: rgba(47, 122, 82, 0.1);
  color: #2f7a52;
  font-weight: 600;
}

.dw-phrase-hint {
  margin: 10px 0 0;
  color: #8a9994;
  font-size: 12.5px;
  line-height: 1.65;
}

.dw-phrase-list {
  display: grid;
  gap: 8px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}

.dw-phrase-list button {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto 16px;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(47, 74, 69, 0.1);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.6);
  color: #3f5852;
  font-size: 13px;
  font-family: inherit;
  line-height: 1.7;
  text-align: left;
  cursor: pointer;
}

.dw-phrase-list button:hover {
  border-color: rgba(47, 122, 82, 0.4);
  background: rgba(47, 122, 82, 0.06);
}

.dw-phrase-text {
  white-space: pre-wrap;
}

.dw-phrase-slot {
  color: #a8b3af;
  font-size: 11.5px;
  white-space: nowrap;
}

.dw-phrase-tip {
  margin: 12px 0 0;
  color: #8a9994;
  font-size: 12px;
  line-height: 1.7;
}

/* ---------- 我的草稿 ---------- */
.dw-library {
  display: grid;
  gap: 18px;
  margin-top: 22px;
}

.dw-lib-card {
  padding: 20px 22px;
  border: 1px solid rgba(47, 74, 69, 0.12);
  border-radius: 16px;
  background: rgba(255, 253, 248, 0.82);
}

.dw-lib-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.dw-lib-head strong {
  display: block;
  margin-top: 2px;
  color: #2f4a45;
  font-size: 18px;
}

.dw-lib-head small {
  display: block;
  margin-top: 4px;
  color: #7b8b86;
  font-size: 12.5px;
  line-height: 1.6;
}

.dw-lib-list {
  display: grid;
  gap: 8px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
}

.dw-lib-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 13px;
  border-radius: 10px;
  background: rgba(47, 74, 69, 0.04);
}

.dw-lib-main strong {
  display: block;
  color: #2f4a45;
  font-size: 13.5px;
  font-weight: 600;
}

.dw-lib-main small {
  display: block;
  margin-top: 3px;
  color: #8a9994;
  font-size: 12px;
}

.dw-lib-actions {
  display: flex;
  gap: 8px;
}

.dw-lib-actions button {
  padding: 5px 12px;
  border: 1px solid rgba(47, 74, 69, 0.16);
  border-radius: 999px;
  background: transparent;
  color: #2f7a52;
  font-size: 12px;
  cursor: pointer;
}

.dw-lib-actions button:hover {
  border-color: rgba(47, 122, 82, 0.45);
  background: rgba(47, 122, 82, 0.08);
}

.dw-lib-actions button.danger {
  color: #b84a30;
}

.dw-lib-actions button.danger:hover {
  border-color: rgba(184, 74, 48, 0.4);
  background: rgba(184, 74, 48, 0.07);
}

.dw-lib-empty {
  margin: 14px 0 0;
  color: #8a9994;
  font-size: 12.5px;
  line-height: 1.7;
}

/* ---------- 校验分组与时限提示 ---------- */
.dw-check-group {
  margin-top: 14px;
}

.dw-check-group h4 {
  margin: 0 0 8px;
  color: #7b8b86;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.dw-deadline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  padding: 8px 12px;
  border-left: 3px solid #c98a2b;
  border-radius: 0 8px 8px 0;
  background: rgba(201, 138, 43, 0.09);
  color: #8a5c15;
  font-size: 12.5px;
  line-height: 1.65;
}

.dw-deadline strong {
  color: #6f4a0f;
}

/* ---------- 上传改格式 ---------- */
.dw-normalize {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.dw-norm-intro h2 {
  margin: 4px 0 8px;
  font-size: 1.5rem;
  font-weight: 400;
  color: #172b2a;
}

.dw-norm-intro h2 em {
  font-style: normal;
  color: #397f72;
}

.dw-norm-lead {
  margin: 0;
  max-width: 68ch;
  color: #667572;
  line-height: 1.75;
}

.dw-norm-drop {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 30px 20px;
  border: 1.5px dashed #d8ded4;
  border-radius: 18px;
  background: #fffef8;
  color: #667572;
  cursor: pointer;
  text-align: center;
  transition: border-color .18s ease, background .18s ease;
}

.dw-norm-drop:hover,
.dw-norm-drop:focus-visible {
  border-color: #397f72;
  background: #f5f4eb;
  outline: none;
}

.dw-norm-drop.is-over {
  border-color: #397f72;
  background: #dfece5;
}

.dw-norm-drop.has-file {
  border-style: solid;
  border-color: #397f72;
}

.dw-norm-drop strong {
  font-size: 1rem;
  color: #172b2a;
  word-break: break-all;
}

.dw-norm-drop span {
  font-size: .82rem;
}

.dw-norm-input {
  display: none;
}

.dw-norm-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
}

.dw-norm-type {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: .82rem;
  color: #667572;
}

.dw-norm-type select {
  min-width: 160px;
  padding: 10px 12px;
  border: 1px solid #d8ded4;
  border-radius: 10px;
  background: #fffef8;
  color: #172b2a;
  font: inherit;
}

.dw-norm-notice {
  margin: 0;
  padding: 10px 14px;
  border-left: 3px solid #397f72;
  border-radius: 0 10px 10px 0;
  background: #f5f4eb;
  color: #172b2a;
  font-size: .88rem;
  line-height: 1.6;
}

.dw-norm-summary,
.dw-norm-checks,
.dw-norm-changes,
.dw-norm-warnings {
  padding: 18px 20px;
  border: 1px solid #d8ded4;
  border-radius: 18px;
  background: #fffef8;
}

.dw-norm-summary header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dw-norm-summary h3 {
  margin: 2px 0 0;
  font-size: 1.25rem;
  color: #172b2a;
}

.dw-norm-cats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}

.dw-norm-cats li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 11px;
  border-radius: 999px;
  background: #dfece5;
  color: #173f43;
  font-size: .8rem;
}

.dw-norm-cats strong {
  font-size: .95rem;
}

.dw-norm-standard {
  margin: 12px 0 0;
  font-size: .78rem;
  line-height: 1.6;
  color: #667572;
}

.dw-norm-checks h3,
.dw-norm-changes h3,
.dw-norm-warnings h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 12px;
  font-size: .95rem;
  color: #172b2a;
}

.dw-norm-checks ul,
.dw-norm-warnings ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.dw-norm-checks li {
  display: flex;
  align-items: baseline;
  gap: 7px;
  font-size: .86rem;
  line-height: 1.55;
  color: #b63d3d;
}

.dw-norm-checks li.ok {
  color: #397f72;
}

.dw-norm-checks li em {
  font-style: normal;
  font-size: .78rem;
  color: #667572;
}

.dw-norm-warnings {
  border-color: #e8cfc9;
  background: #fdf6f4;
}

.dw-norm-warnings li {
  font-size: .86rem;
  line-height: 1.6;
  color: #8a3d30;
}

.dw-norm-table {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-x: auto;
}

.dw-norm-row {
  display: grid;
  grid-template-columns: minmax(120px, 1.1fr) 88px minmax(120px, 1fr) minmax(140px, 1.2fr) minmax(150px, 1.4fr);
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: .8rem;
  line-height: 1.5;
  color: #172b2a;
}

.dw-norm-row:nth-child(even) {
  background: #f5f4eb;
}

.dw-norm-row-head {
  background: transparent;
  font-weight: 700;
  font-size: .74rem;
  letter-spacing: .04em;
  color: #667572;
}

.dw-norm-tag {
  justify-self: start;
  padding: 2px 8px;
  border-radius: 999px;
  background: #e7e9f4;
  color: #3b4470;
  font-size: .72rem;
  white-space: nowrap;
}

.dw-norm-before {
  color: #8a6a3d;
  text-decoration: line-through;
  text-decoration-color: #d6a849;
}

.dw-norm-after {
  color: #1f5a4e;
  font-weight: 600;
}

.dw-norm-basis {
  color: #667572;
  font-size: .74rem;
}

@media (max-width: 900px) {
  .dw-norm-row {
    grid-template-columns: 1fr;
    gap: 3px;
    padding: 10px;
    border-bottom: 1px solid #e6e9e0;
  }

  .dw-norm-row-head {
    display: none;
  }
}
</style>
