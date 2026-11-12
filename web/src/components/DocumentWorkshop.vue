<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
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

const activeTab = ref<'editor' | 'templates' | 'format'>('templates')
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
      <button :class="{ active: activeTab === 'format' }" @click="activeTab = 'format'">
        <PhEye :size="16" /> 格式细则
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
