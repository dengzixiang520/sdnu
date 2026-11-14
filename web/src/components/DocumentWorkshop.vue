<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { PhFileText, PhDownload, PhEye, PhCopy, PhTrash } from '@phosphor-icons/vue'
import { command, requestJson } from '../api'

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

const activeTab = ref<'templates' | 'editor' | 'preview' | 'format'>('templates')
const draft = ref('')
const elements = ref<DocumentElements | null>(null)
const message = ref('')
const loading = ref(false)
const selectedTemplate = ref('')
const documentHistory = ref<Array<{ name: string, date: string, type: string }>>([])

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

      documentHistory.value.unshift({
        name: elements.value.title || '未命名文档',
        date: new Date().toLocaleString('zh-CN'),
        type: `${currentTemplate.value?.name ?? '公文'} · DOCX`,
      })
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

/* ---------- 格式校验 ---------- */
interface FormatCheck {
  ok: boolean
  name: string
  detail: string
  /** error 表示细则硬性要求，warn 表示提醒 */
  level: 'error' | 'warn'
}

const formatChecks = ref<FormatCheck[]>([])
const formatChecked = ref(false)

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
      // 续行必须是缩进的条目编号，否则附件块结束
      if (cont && ATTACH_ITEM.test(cont) && /^\s/.test(line)) { attaches.push(cont); continue }
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

function checkFormat() {
  const title = previewTitle()
  const bodyText = previewBody()
  const dateText = (elements.value?.issue_date ?? '').trim()
  const rc = recipient.value.trim()
  const att = attachments.value.trim()
  const checks: FormatCheck[] = []

  checks.push({
    ok: title.includes('山东师范大学'),
    name: '标题标明发文机关',
    detail: title.includes('山东师范大学')
      ? '已包含「山东师范大学」'
      : '细则要求标题一般应标明发文机关，如「山东师范大学关于……的通知」',
    level: 'warn',
  })

  checks.push({
    ok: !rc || /[：:]$/.test(rc),
    name: '主送机关以冒号收尾',
    detail: !rc
      ? '未填主送机关；通知、请示类文种应当填写'
      : /[：:]$/.test(rc)
        ? '格式正确'
        : '主送机关应以全角冒号「：」结尾，且顶格书写',
    level: rc ? 'error' : 'warn',
  })

  checks.push({
    ok: bodyText.length >= 50,
    name: '正文不少于 50 字',
    detail: bodyText.length === 0 ? '正文为空' : `当前 ${bodyText.length} 字`,
    level: 'warn',
  })

  checks.push({
    ok: CHINESE_DATE.test(dateText),
    name: '成文日期用汉字标全',
    detail: !dateText
      ? '未填成文日期'
      : CHINESE_DATE.test(dateText)
        ? '格式正确'
        : DIGIT_DATE.test(dateText)
          ? '用了阿拉伯数字，细则要求写成「二○二六年十一月十三日」'
          : '日期格式无法识别，应形如「二○二六年十一月十三日」',
    level: dateText ? 'error' : 'warn',
  })

  checks.push({
    ok: title.length > 0 && title.length <= 40,
    name: '标题不超过 40 字',
    detail: title.length === 0 ? '标题为空' : `当前 ${title.length} 字${title.length > 40 ? '，建议精简' : ''}`,
    level: title.length > 40 ? 'error' : 'warn',
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
  })

  formatChecks.value = checks
  formatChecked.value = true
  const failed = checks.filter((item) => !item.ok).length
  message.value = failed === 0
    ? '格式检查全部通过，可以导出 DOCX'
    : `格式检查：${checks.length - failed} 项通过，${failed} 项待改`
}

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

onMounted(() => { loadTemplates() })
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
      <button :class="{ active: activeTab === 'editor' }" @click="activeTab = 'editor'">
        <PhFileText :size="16" /> 文档编辑
      </button>
      <button :class="{ active: activeTab === 'preview' }" @click="activeTab = 'preview'">
        <PhEye :size="16" /> A4 预览
      </button>
      <button :class="{ active: activeTab === 'format' }" @click="activeTab = 'format'">
        <PhCopy :size="16" /> 格式细则
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

        <textarea v-model="draft" class="document-draft" placeholder="输入公文内容，或用上方「文种模板」载入骨架…"></textarea>
        <div class="card-footer">
          <button class="ink-button" :disabled="loading || !draft.trim()" @click="parseDraft">
            {{ loading ? '解析中...' : '解析草稿' }}
          </button>
          <button class="ink-button primary" :disabled="loading || !elements" @click="exportDocx">
            <PhDownload :size="16" /> 导出 DOCX
          </button>
        </div>
        <p class="form-hint">{{ message || '选择文种与版头后解析草稿，导出的 DOCX 会带上版头红线、版记与页码' }}</p>
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
            ? `6 项检查全部通过`
            : `${formatChecks.filter((item) => item.ok).length} / ${formatChecks.length} 项通过` }}
        </p>
        <ul class="dw-check-list">
          <li v-for="item in formatChecks" :key="item.name" :class="[item.ok ? 'is-ok' : 'is-bad', item.level]">
            <span class="dw-check-mark">{{ item.ok ? '✓' : (item.level === 'error' ? '✕' : '!') }}</span>
            <div>
              <strong>{{ item.name }}</strong>
              <p>{{ item.detail }}</p>
            </div>
          </li>
        </ul>
      </div>
      <p v-else class="dw-check-idle">
        填好标题、正文与落款后点「检查格式」，会逐条列出通过项和待改项。
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
</style>
