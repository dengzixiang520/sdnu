<script setup lang="ts">
/**
 * 定向命题六：学术海报一键生成。
 *
 * 刻意不走「让模型画一张图」的路子：海报要打印出来贴墙上，位图放大就糊、
 * 改一个标点要整张重来、现场断网直接不可用。所以这里做成
 * **填表 → 生成可打印的 HTML → 浏览器另存为 PDF**，每个字都留在用户手里。
 *
 * 右边那列是「内容体检」：标题太长、缺结论栏、单栏正文超字数——
 * 只有做过海报的人才会提醒的事，这里自动说一遍。
 */
import { computed, ref } from 'vue'
import {
  PhArrowClockwise,
  PhCheckCircle,
  PhDownloadSimple,
  PhInfo,
  PhPlus,
  PhPrinter,
  PhTrash,
  PhWarning,
} from '@phosphor-icons/vue'
import { buildPoster } from '../api'
import type { PosterPlan } from '../api'
import AnswerFeedback from './AnswerFeedback.vue'

const SIZES = [
  { id: 'a0', label: 'A0 · 841 × 1189 mm（展板主用）' },
  { id: 'a1', label: 'A1 · 594 × 841 mm' },
  { id: 'a2', label: 'A2 · 420 × 594 mm' },
  { id: 'a3', label: 'A3 · 297 × 420 mm（打印最省）' },
]

interface SectionDraft {
  heading: string
  body: string
  bullets: string
}

interface FigureDraft {
  caption: string
  hint: string
}

const SAMPLE = {
  title: '智汇齐鲁·全域同频：一个技能底座驱动的校园智能助手',
  authors: '张三、李四、王五',
  affiliation: '山东师范大学 信息科学与工程学院',
  contact: 'zhangsan@sdnu.edu.cn',
  keywords: '多智能体、校园服务、可解释、离线可用',
  footer: '第一届人工智能创新应用大赛 · 2026-11-15',
  size: 'a0',
  sections: [
    {
      heading: '背景与问题',
      body:
        '校园服务分散在教务、学工、后勤等十余个系统里，学生每办一件事都要先找对入口。\n' +
        '现有问答工具只会聊天，没法把「查课表—改格式—报预警」这类多步事务真正做完。',
      bullets: '',
    },
    {
      heading: '方法',
      body: '以技能为最小单元组织能力，每个技能只做一件可验证的事。',
      bullets: '技能底座：六类能力共用一套安全网关与记忆层\n安全网关：角色鉴权、注入拦截、敏感信息脱敏\n记忆层：短期会话加长期偏好，跨技能复用',
    },
    {
      heading: '结果',
      body: '在五类高频事务上完成闭环，全部结论可追到规则出处。',
      bullets: '公文规范化：一份格式混乱的通知自动产出 40 处改动\n学业预警：直接命中学校 65% 学分线并给四步处置\n钓鱼识别：规则逐条可核对，纯离线不联网',
    },
    {
      heading: '结论',
      body: '把「能聊」变成「能办完」，关键不在模型大小，而在能力边界写不写得清。',
      bullets: '',
    },
  ] as SectionDraft[],
  figures: [
    { caption: '系统结构', hint: '在此处替换为系统结构图' },
    { caption: '关键指标', hint: '在此处替换为关键指标图' },
  ] as FigureDraft[],
}

const title = ref('')
const authors = ref('')
const affiliation = ref('')
const contact = ref('')
const keywords = ref('')
const footer = ref('')
const size = ref('a0')
const sections = ref<SectionDraft[]>([{ heading: '结论', body: '', bullets: '' }])
const figures = ref<FigureDraft[]>([])

const busy = ref(false)
const error = ref('')
const plan = ref<PosterPlan | null>(null)

/** 预览用缩放：A0 的 1mm ≈ 3.78 CSS px，按右栏宽度算一个 zoom。 */
const PREVIEW_WIDTH = 470
const previewScale = computed(() => {
  if (!plan.value) return 0.16
  const natural = plan.value.width_mm * 3.7795
  return Math.min(1, PREVIEW_WIDTH / natural)
})

/**
 * 预览文档 = 生成的 HTML + 一行预览专用缩放。
 * 只改预览这份，下载和打印用的还是原始 html，不带任何预览痕迹。
 */
const previewDoc = computed(() => {
  if (!plan.value) return ''
  return plan.value.html.replace(
    '</head>',
    `<style>html{zoom:${previewScale.value.toFixed(4)}}</style></head>`,
  )
})

const previewHeight = computed(() => {
  if (!plan.value) return 320
  return Math.round(plan.value.height_mm * 3.7795 * previewScale.value)
})

const failedItems = computed(() => (plan.value ? plan.value.checklist.filter((item) => !item.passed) : []))

function addSection() {
  sections.value.push({ heading: '', body: '', bullets: '' })
}

function removeSection(index: number) {
  sections.value.splice(index, 1)
}

function addFigure() {
  figures.value.push({ caption: '', hint: '在此处替换为你的图表' })
}

function removeFigure(index: number) {
  figures.value.splice(index, 1)
}

function fillSample() {
  title.value = SAMPLE.title
  authors.value = SAMPLE.authors
  affiliation.value = SAMPLE.affiliation
  contact.value = SAMPLE.contact
  keywords.value = SAMPLE.keywords
  footer.value = SAMPLE.footer
  size.value = SAMPLE.size
  sections.value = SAMPLE.sections.map((item) => ({ ...item }))
  figures.value = SAMPLE.figures.map((item) => ({ ...item }))
  plan.value = null
  error.value = ''
}

function toRequest() {
  return {
    title: title.value.trim(),
    authors: authors.value.trim(),
    affiliation: affiliation.value.trim(),
    contact: contact.value.trim(),
    keywords: keywords.value
      .split(/[、,，;；\s]+/)
      .map((item) => item.trim())
      .filter(Boolean),
    sections: sections.value
      .filter((item) => item.heading.trim())
      .map((item) => ({
        heading: item.heading.trim(),
        body: item.body.trim(),
        bullets: item.bullets
          .split('\n')
          .map((line) => line.trim())
          .filter(Boolean),
      })),
    figures: figures.value
      .filter((item) => item.caption.trim() || item.hint.trim())
      .map((item) => ({ caption: item.caption.trim(), hint: item.hint.trim() })),
    size: size.value,
    footer: footer.value.trim(),
  }
}

async function generate() {
  const request = toRequest()
  if (!request.title) {
    error.value = '先写标题。海报三米外只看得清标题，它比什么都重要。'
    return
  }
  if (!request.sections.length) {
    error.value = '至少写一栏内容，哪怕只有「结论」。'
    return
  }
  busy.value = true
  error.value = ''
  try {
    plan.value = await buildPoster(request)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '海报没生成出来'
    plan.value = null
  } finally {
    busy.value = false
  }
}

function download() {
  if (!plan.value) return
  const blob = new Blob([plan.value.html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `academic-poster-${plan.value.size}.html`
  document.body.appendChild(link)
  link.click()
  link.remove()
  // 立刻回收会让部分浏览器来不及开始下载，留一秒。
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function print() {
  if (!plan.value) return
  const blob = new Blob([plan.value.html], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank')
  window.setTimeout(() => URL.revokeObjectURL(url), 60000)
}
</script>

<template>
  <section class="poster-page">
    <header class="poster-head">
      <div>
        <p class="eyebrow">定向命题六 · 学术海报</p>
        <h1>填完这几栏，<em>直接拿去打印。</em></h1>
        <p class="poster-lead">
          生成的不是一张位图，而是一页可打印的 HTML：字号按纸张尺寸等比缩放，
          改一个字不用重新生成，断网也能打印。右边同时做内容体检——标题太长、缺结论栏、
          单栏正文超字数，都会当场说出来。
        </p>
      </div>
      <ul class="poster-facts">
        <li><strong>{{ plan ? plan.passed_count : '—' }}</strong><span>体检通过项</span></li>
        <li><strong>{{ plan ? plan.word_count : '—' }}</strong><span>正文字数</span></li>
        <li><strong>{{ plan ? `${plan.fonts.columns}` : '—' }}</strong><span>分栏数</span></li>
      </ul>
    </header>

    <div class="poster-grid">
      <!-- 左：填写 -->
      <div class="poster-form">
        <div class="pf-row pf-row-2">
          <label class="pf-field">
            <span>纸张尺寸</span>
            <select v-model="size" class="pf-input">
              <option v-for="item in SIZES" :key="item.id" :value="item.id">{{ item.label }}</option>
            </select>
          </label>
          <label class="pf-field">
            <span>页脚（会议 / 日期）</span>
            <input v-model="footer" class="pf-input" type="text" placeholder="第一届…大赛 · 2026-11-15">
          </label>
        </div>

        <label class="pf-field">
          <span>标题 <em>60 字以内</em></span>
          <input v-model="title" class="pf-input" type="text" placeholder="例：面向校园场景的多智能体协同助手">
        </label>

        <div class="pf-row pf-row-2">
          <label class="pf-field">
            <span>作者</span>
            <input v-model="authors" class="pf-input" type="text" placeholder="张三、李四">
          </label>
          <label class="pf-field">
            <span>联系方式</span>
            <input v-model="contact" class="pf-input" type="text" placeholder="you@sdnu.edu.cn">
          </label>
        </div>

        <label class="pf-field">
          <span>单位</span>
          <input v-model="affiliation" class="pf-input" type="text" placeholder="山东师范大学 信息科学与工程学院">
        </label>

        <label class="pf-field">
          <span>关键词 <em>3–5 个，顿号分隔</em></span>
          <input v-model="keywords" class="pf-input" type="text" placeholder="多智能体、校园服务、可解释">
        </label>

        <div class="pf-group">
          <div class="pf-group-head">
            <h2>栏目 <em>3–5 栏</em></h2>
            <button type="button" class="pf-mini" @click="addSection"><PhPlus :size="13" /> 加一栏</button>
          </div>
          <article v-for="(section, index) in sections" :key="index" class="pf-card">
            <div class="pf-card-head">
              <input v-model="section.heading" class="pf-input" type="text" placeholder="栏目名，例：结论">
              <button type="button" class="pf-trash" :aria-label="`删除第 ${index + 1} 栏`" @click="removeSection(index)">
                <PhTrash :size="14" />
              </button>
            </div>
            <textarea
              v-model="section.body"
              class="pf-area"
              rows="3"
              placeholder="一段话。换行就是分段。"
            />
            <textarea
              v-model="section.bullets"
              class="pf-area"
              rows="3"
              placeholder="要点，一行一条（可留空）"
            />
          </article>
        </div>

        <div class="pf-group">
          <div class="pf-group-head">
            <h2>图表位 <em>1–4 个</em></h2>
            <button type="button" class="pf-mini" @click="addFigure"><PhPlus :size="13" /> 加一个</button>
          </div>
          <article v-for="(figure, index) in figures" :key="index" class="pf-card pf-card-figure">
            <div class="pf-card-head">
              <input v-model="figure.caption" class="pf-input" type="text" placeholder="图注，例：系统结构">
              <button type="button" class="pf-trash" :aria-label="`删除第 ${index + 1} 个图表位`" @click="removeFigure(index)">
                <PhTrash :size="14" />
              </button>
            </div>
            <input v-model="figure.hint" class="pf-input" type="text" placeholder="占位说明，例：在此处替换为系统结构图">
          </article>
        </div>

        <div class="pf-actions">
          <button type="button" class="ink-button primary" :disabled="busy" @click="generate">
            <PhArrowClockwise :size="16" />
            {{ busy ? '正在排版…' : plan ? '重新生成' : '生成海报' }}
          </button>
          <button type="button" class="pf-ghost" @click="fillSample">填入示例</button>
        </div>

        <p v-if="error" class="pf-error"><PhWarning :size="15" />{{ error }}</p>
      </div>

      <!-- 右：预览 + 体检 -->
      <div class="poster-preview">
        <article v-if="plan" class="pv-card">
          <header class="pv-head">
            <div>
              <strong>{{ plan.size_label }}</strong>
              <span>
                标题 {{ plan.fonts.title_pt }}pt · 栏目 {{ plan.fonts.section_pt }}pt · 正文
                {{ plan.fonts.body_pt }}pt · {{ plan.fonts.columns }} 栏
              </span>
            </div>
            <div class="pv-actions">
              <button type="button" class="pf-mini" @click="download"><PhDownloadSimple :size="14" /> 下载 HTML</button>
              <button type="button" class="pf-mini is-strong" @click="print"><PhPrinter :size="14" /> 打印 / 存 PDF</button>
            </div>
          </header>

          <div class="pv-frame" :style="{ height: `${previewHeight}px` }">
            <iframe :srcdoc="previewDoc" title="海报预览" />
          </div>

          <p class="pv-hint"><PhInfo :size="14" />{{ plan.print_hint }}</p>
        </article>

        <p v-else class="pv-empty">
          还没生成。先点「填入示例」看看成品长什么样，再改成自己的内容。
        </p>

        <article v-if="plan" class="pv-check">
          <header>
            <h2>内容体检</h2>
            <span :class="{ 'is-warn': failedItems.length > 0 }">
              {{ plan.passed_count }} / {{ plan.checklist.length }} 通过
            </span>
          </header>
          <ul>
            <li v-for="item in plan.checklist" :key="item.id" :class="{ 'is-fail': !item.passed, 'is-info': item.level === 'info' }">
              <PhCheckCircle v-if="item.passed" :size="15" weight="fill" />
              <PhWarning v-else :size="15" />
              <div>
                <strong>{{ item.label }}</strong>
                <p>{{ item.passed ? '没问题' : item.advice }}</p>
              </div>
            </li>
          </ul>
          <p v-if="!failedItems.length" class="pv-clean">没有硬伤。可以直接打印了。</p>
        </article>

        <AnswerFeedback v-if="plan" target="poster_plan" hint="这张海报能用吗" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.poster-page {
  max-width: 1280px;
  margin: 0 auto;
  padding-bottom: 3rem;
}

.poster-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1.5rem;
  margin: 1.5rem 0 1.5rem;
}

.poster-head h1 {
  margin: .25rem 0 .6rem;
  font: 400 clamp(2rem, 4vw, 3.2rem)/1.1 "LXGW WenKai", cursive;
  letter-spacing: -.03em;
  color: #172b2a;
}

.poster-head h1 em {
  font-style: normal;
  color: #397f72;
}

.poster-lead {
  max-width: 66ch;
  margin: 0;
  color: #667572;
  line-height: 1.75;
}

.poster-facts {
  display: flex;
  gap: .6rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.poster-facts li {
  padding: .7rem 1rem;
  border: 1px solid #d8ded4;
  border-radius: 16px;
  background: #fffef8;
  text-align: right;
}

.poster-facts strong {
  display: block;
  font: 400 1.6rem/1 "LXGW WenKai", cursive;
  color: #173f43;
}

.poster-facts span {
  display: block;
  margin-top: .3rem;
  font-size: .72rem;
  color: #667572;
}

.poster-grid {
  display: grid;
  grid-template-columns: 420px minmax(0, 1fr);
  gap: 1.1rem;
  align-items: start;
}

/* ---------- 左：表单 ---------- */

.poster-form {
  display: grid;
  gap: .7rem;
  padding: 1rem 1.1rem 1.1rem;
  border: 1px solid #d8ded4;
  border-radius: 18px;
  background: #fffef8;
}

.pf-row {
  display: grid;
  gap: .6rem;
}

.pf-row-2 {
  grid-template-columns: 1fr 1fr;
}

.pf-field {
  display: grid;
  gap: .3rem;
  font-size: .78rem;
  color: #4c5b58;
}

.pf-field > span {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: .4rem;
  font-weight: 600;
  color: #173f43;
}

.pf-field > span em {
  font-style: normal;
  font-weight: 400;
  font-size: .7rem;
  color: #8f9c98;
}

.pf-input,
.pf-area {
  width: 100%;
  padding: .5rem .6rem;
  border: 1px solid #dfe3d8;
  border-radius: 9px;
  background: #fbfaf2;
  color: #172b2a;
  font: inherit;
  font-size: .82rem;
  line-height: 1.6;
}

.pf-area {
  resize: vertical;
}

.pf-input:focus-visible,
.pf-area:focus-visible {
  outline: 2px solid #397f72;
  outline-offset: 1px;
}

.pf-group {
  margin-top: .3rem;
  padding-top: .7rem;
  border-top: 1px dashed #e2e6dc;
}

.pf-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .5rem;
  margin-bottom: .5rem;
}

.pf-group-head h2 {
  margin: 0;
  font-size: .82rem;
  color: #173f43;
}

.pf-group-head h2 em {
  font-style: normal;
  font-weight: 400;
  font-size: .7rem;
  color: #8f9c98;
}

.pf-mini {
  display: inline-flex;
  align-items: center;
  gap: .28rem;
  padding: .3rem .6rem;
  border: 1px solid #d8ded4;
  border-radius: 999px;
  background: #fffef8;
  color: #2f4a45;
  font: inherit;
  font-size: .74rem;
  cursor: pointer;
  transition: border-color .16s ease, background .16s ease;
}

.pf-mini:hover {
  border-color: #397f72;
  background: #f0f5f1;
}

.pf-mini.is-strong {
  border-color: #173f43;
  background: #173f43;
  color: #fffef8;
}

.pf-mini.is-strong:hover {
  background: #397f72;
}

.pf-card {
  display: grid;
  gap: .4rem;
  margin-bottom: .55rem;
  padding: .6rem .65rem;
  border: 1px solid #e6e9df;
  border-radius: 12px;
  background: #fbfaf2;
}

.pf-card-head {
  display: flex;
  align-items: center;
  gap: .4rem;
}

.pf-card-head .pf-input {
  flex: 1;
}

.pf-trash {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 1px solid #e6e9df;
  border-radius: 8px;
  background: #fffef8;
  color: #9a6a5f;
  cursor: pointer;
}

.pf-trash:hover {
  border-color: #b63d3d;
  color: #b63d3d;
}

.pf-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .5rem;
  margin-top: .4rem;
}

.pf-ghost {
  padding: .42rem .8rem;
  border: 1px dashed #cfd7cb;
  border-radius: 999px;
  background: transparent;
  color: #4c5b58;
  font: inherit;
  font-size: .78rem;
  cursor: pointer;
}

.pf-ghost:hover {
  border-color: #397f72;
  color: #173f43;
}

.pf-error {
  display: flex;
  align-items: center;
  gap: .4rem;
  margin: 0;
  padding: .6rem .8rem;
  border-left: 3px solid #b63d3d;
  border-radius: 0 10px 10px 0;
  background: #fdf6f4;
  color: #8a3d30;
  font-size: .8rem;
}

/* ---------- 右：预览 ---------- */

.poster-preview {
  display: grid;
  gap: .8rem;
}

.pv-card,
.pv-check {
  padding: 1rem 1.1rem 1.1rem;
  border: 1px solid #d8ded4;
  border-radius: 18px;
  background: #fffef8;
}

.pv-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: .6rem;
  margin-bottom: .7rem;
}

.pv-head strong {
  display: block;
  font-size: .86rem;
  color: #173f43;
}

.pv-head span {
  display: block;
  margin-top: .2rem;
  font-size: .72rem;
  color: #8f9c98;
}

.pv-actions {
  display: flex;
  flex-wrap: wrap;
  gap: .4rem;
}

.pv-frame {
  overflow: hidden;
  border: 1px solid #e2e6dc;
  border-radius: 12px;
  background: #e9ece4;
}

.pv-frame iframe {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
}

.pv-hint {
  display: flex;
  align-items: flex-start;
  gap: .4rem;
  margin: .7rem 0 0;
  padding-top: .6rem;
  border-top: 1px dashed #e2e6dc;
  font-size: .74rem;
  line-height: 1.7;
  color: #8f9c98;
}

.pv-hint svg {
  flex: 0 0 auto;
  margin-top: .18rem;
}

.pv-empty {
  margin: 0;
  padding: 1.4rem 1.2rem;
  border: 1px dashed #d8ded4;
  border-radius: 16px;
  color: #667572;
  font-size: .84rem;
  line-height: 1.8;
}

.pv-check > header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: .6rem;
  margin-bottom: .6rem;
}

.pv-check h2 {
  margin: 0;
  font-size: .9rem;
  color: #173f43;
}

.pv-check > header span {
  font-size: .76rem;
  color: #397f72;
}

.pv-check > header span.is-warn {
  color: #b98b2e;
}

.pv-check ul {
  display: grid;
  gap: .45rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.pv-check li {
  display: flex;
  align-items: flex-start;
  gap: .45rem;
  padding: .45rem .6rem;
  border-radius: 10px;
  background: #f5f4eb;
  color: #397f72;
}

.pv-check li.is-fail {
  background: #fdfaf2;
  color: #b98b2e;
}

.pv-check li.is-info {
  color: #8f9c98;
}

.pv-check li > div {
  min-width: 0;
}

.pv-check li strong {
  display: block;
  font-size: .8rem;
  color: #172b2a;
}

.pv-check li p {
  margin: .15rem 0 0;
  font-size: .74rem;
  line-height: 1.65;
  color: #667572;
}

.pv-clean {
  margin: .6rem 0 0;
  font-size: .76rem;
  color: #397f72;
}

@media (max-width: 1080px) {
  .poster-grid {
    grid-template-columns: 1fr;
  }

  .poster-facts {
    width: 100%;
  }
}
</style>
