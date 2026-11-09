<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, computed } from 'vue'
import { 
  PhBookOpenText, PhChatCircleDots, PhFirstAid, PhFlowerLotus, PhLockKey, 
  PhPaperPlaneTilt, PhWind, PhWarning, PhCalendarCheck, PhNotebook,
  PhChartLine, PhUsers, PhExport, PhPhoneCall, PhConfetti, PhImage, PhHeart
} from '@phosphor-icons/vue'
import { command } from '../api'
import { useIdentity } from '../identity'
import WellbeingUtilityRail from './WellbeingUtilityRail.vue'

type Weather = 'sunny' | 'cloudy' | 'rainy' | 'stormy'
interface WallMessage { message_id: string; content: string; topic?: string }
interface AlertItem { student_id: string; level: string; reason_codes: string[]; created_at: string }
interface TalkEntry { student_id: string; student_name: string; counselor_name: string; meeting_at: string; location: string; topic_summary: string; agreed_actions: string; follow_up_at?: string; overall_assessment: string }

const { identity } = useIdentity()

// 学生入口切换：有人只想记录自己，有人只想看大家的分享
type SpaceTab = 'self' | 'share'
const activeTab = ref<SpaceTab>('self')

// 学生功能相关
const weather = ref<Weather>('sunny')
const reflection = ref('')
const response = ref('')
const level = ref('')
const loading = ref(false)
const error = ref('')
const wall = ref<WallMessage[]>([])
const journal = ref(localStorage.getItem('zhq-private-journal') ?? '')
const journalSaved = ref(false)
const breathing = ref(false)
const breathPhase = ref('准备开始')
const breathSeconds = ref(60)
let breathTimer: number | undefined

// 开心分享墙
interface HappyShare { share_id: string; author_name: string; content: string; image_data_url?: string | null; cheer_count: number; created_at: string }
const shares = ref<HappyShare[]>([])
const shareContent = ref('')
const shareImage = ref<string | null>(null)
const shareAnonymous = ref(false)
const shareStatus = ref('')
const shareError = ref('')
const shareRedirect = ref('')
const shareLoading = ref(false)
const shareLoaded = ref(false)
const cheeredIds = ref<string[]>([])


// 辅导员功能相关
const alerts = ref<AlertItem[]>([])
const talkEntries = ref<TalkEntry[]>([])
const talkSearch = ref('')

const filteredTalkEntries = computed(() => {
  if (!talkSearch.value) return talkEntries.value
  const search = talkSearch.value.toLowerCase()
  return talkEntries.value.filter(e => 
    e.student_id.toLowerCase().includes(search) ||
    e.topic_summary.toLowerCase().includes(search) ||
    e.counselor_name.toLowerCase().includes(search)
  )
})
const showNewTalk = ref(false)
const newTalk = ref<TalkEntry>({
  student_id: '', student_name: '', counselor_name: '', meeting_at: '', location: '',
  topic_summary: '', agreed_actions: '', follow_up_at: '', overall_assessment: ''
})

// 寄语墙
const wallTopic = ref('今日寄语')
const wallContent = ref('')
const wallStatus = ref('')

// 权限判断
const isStudent = computed(() => identity.value.role === 'student')
const isCounselor = computed(() => identity.value.role === 'counselor')
const isAdmin = computed(() => identity.value.role === 'administrator')
const isStaff = computed(() => isCounselor.value || isAdmin.value)

const weatherOptions: Array<{ id: Weather; mark: string; label: string; copy: string }> = [
  { id: 'sunny', mark: '晴', label: '轻松', copy: '今天还不错' },
  { id: 'cloudy', mark: '云', label: '一般', copy: '有点提不起劲' },
  { id: 'rainy', mark: '雨', label: '低落', copy: '需要一点空间' },
  { id: 'stormy', mark: '雷', label: '难熬', copy: '希望有人陪我' },
]

// 学生功能
async function fetchWall() {
  try { wall.value = ((await command('wellbeing', 'wall_messages')).data.messages ?? []) as WallMessage[] } catch { wall.value = [] }
}

async function checkIn() {
  loading.value = true; error.value = ''
  try {
    const result = await command('wellbeing', 'mood_checkin', '', { check_in: { weather: weather.value, reflection: reflection.value } })
    response.value = result.message
    level.value = String(result.data.alert_level ?? '')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '记录失败，请稍后再试。'
  } finally { loading.value = false }
}

function saveJournal() {
  localStorage.setItem('zhq-private-journal', journal.value)
  journalSaved.value = true
  window.setTimeout(() => { journalSaved.value = false }, 1800)
}

function openGuide() { window.dispatchEvent(new Event('zhq-open-guide')) }

/** 校内心理支持 QQ 号：桌面浏览器无法直接唤起 QQ，提供复制更可靠。 */
const counselorQQ = '2645256823'
const qqCopied = ref(false)
async function copyCounselorQQ() {
  try {
    await navigator.clipboard.writeText(counselorQQ)
    qqCopied.value = true
    window.setTimeout(() => { qqCopied.value = false }, 2000)
  } catch {
    // 剪贴板被浏览器策略拒绝时，退回到选中提示，至少让用户能手动复制。
    window.prompt('复制下面的 QQ 号：', counselorQQ)
  }
}

// ---------- 开心分享墙 ----------

async function fetchShares() {
  try {
    const result = await command('wellbeing', 'happy_shares')
    shares.value = (result.data.shares ?? []) as HappyShare[]
    shareLoaded.value = true
  } catch (reason) {
    shareError.value = reason instanceof Error ? reason.message : '分享墙加载失败'
  }
}

function switchTab(tab: SpaceTab) {
  activeTab.value = tab
  if (tab === 'share' && !shareLoaded.value) fetchShares()
}

/**
 * 压缩后转 data URL。
 * 现场用手机拍的照片动辄 4-8MB，直接塞进请求会超时；统一缩到长边 1280、JPEG 0.82。
 */
async function readAndCompress(file: File): Promise<string> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('图片读取失败'))
    reader.readAsDataURL(file)
  })
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('图片格式不支持'))
    img.src = dataUrl
  })
  const maxSide = 1280
  const scale = Math.min(1, maxSide / Math.max(image.width, image.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(image.width * scale))
  canvas.height = Math.max(1, Math.round(image.height * scale))
  const context = canvas.getContext('2d')
  if (!context) return dataUrl
  context.drawImage(image, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL('image/jpeg', 0.82)
}

async function pickShareImage(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  shareError.value = ''
  if (!file.type.startsWith('image/')) {
    shareError.value = '只能选图片文件（jpg / png / webp）'
    return
  }
  try {
    const compressed = await readAndCompress(file)
    if (compressed.length > 1_300_000) {
      shareError.value = '这张图压完还是太大，换一张或先截图裁一下'
      return
    }
    shareImage.value = compressed
  } catch (reason) {
    shareError.value = reason instanceof Error ? reason.message : '图片处理失败'
  } finally {
    input.value = ''
  }
}

async function publishShare() {
  shareError.value = ''
  shareStatus.value = ''
  shareRedirect.value = ''
  if (!shareContent.value.trim()) {
    shareError.value = '先写一句今天值得高兴的事'
    return
  }
  shareLoading.value = true
  try {
    const result = await command('wellbeing', 'publish_happy_share', '', {
      author_name: identity.value.displayName,
      share: {
        content: shareContent.value.trim(),
        image_data_url: shareImage.value,
        anonymous: shareAnonymous.value,
      },
    })
    shareContent.value = ''
    shareImage.value = null
    shareAnonymous.value = false
    shareStatus.value = result.message
    await fetchShares()
  } catch (reason) {
    // 后端拒绝时给的是可操作的话术 + 该去哪个入口，不是一句"发布失败"
    shareError.value = reason instanceof Error ? reason.message : '发布失败，请稍后再试'
  } finally {
    shareLoading.value = false
  }
}

async function cheerShare(share: HappyShare) {
  if (cheeredIds.value.includes(share.share_id)) return
  try {
    const result = await command('wellbeing', 'cheer_happy_share', '', { share_id: share.share_id })
    const updated = result.data.share as HappyShare | undefined
    if (updated) {
      shares.value = shares.value.map(item => item.share_id === updated.share_id ? updated : item)
      cheeredIds.value = [...cheeredIds.value, share.share_id]
    }
  } catch {
    // 鼓励是弱交互，失败不打断浏览
  }
}

function formatShareTime(value: string) {
  try {
    return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return value
  }
}

function startBreathing() {
  if (breathing.value) { stopBreathing(); return }
  breathing.value = true; breathSeconds.value = 60
  const phases = ['吸气 4 秒', '停留 4 秒', '呼气 6 秒']; let index = 0; breathPhase.value = phases[0]
  breathTimer = window.setInterval(() => {
    breathSeconds.value -= 1
    if (breathSeconds.value <= 0) { stopBreathing(); breathPhase.value = '完成了，慢慢回到当下'; return }
    if (breathSeconds.value % 5 === 0) { index = (index + 1) % phases.length; breathPhase.value = phases[index] }
  }, 1000)
}

function stopBreathing() {
  window.clearInterval(breathTimer); breathing.value = false
  if (breathSeconds.value > 0) breathPhase.value = '随时可以重新开始'
}

// 辅导员功能
async function fetchAlerts() {
  if (!isStaff.value) return
  try {
    const result = await command('wellbeing', 'list_alerts')
    alerts.value = (result.data.alerts ?? []) as AlertItem[]
  } catch { alerts.value = [] }
}

async function publishWallMessage() {
  if (!wallContent.value.trim()) { wallStatus.value = '请先填写寄语内容。'; return }
  loading.value = true
  try {
    await command('wellbeing', 'publish_wall_message', '', { message: { topic: wallTopic.value, content: wallContent.value } })
    wallContent.value = ''; wallStatus.value = '寄语已发布。'; await fetchWall()
  } catch (reason) {
    wallStatus.value = reason instanceof Error ? reason.message : '发布失败。'
  } finally { loading.value = false }
}

function addTalkEntry() {
  if (!newTalk.value.student_id || !newTalk.value.topic_summary) return
  talkEntries.value.push({ ...newTalk.value })
  newTalk.value = { student_id: '', student_name: '', counselor_name: '', meeting_at: '', location: '', topic_summary: '', agreed_actions: '', follow_up_at: '', overall_assessment: '' }
  showNewTalk.value = false
  try {
    localStorage.setItem('zhq-talk-ledger', JSON.stringify(talkEntries.value))
  } catch {
    // Keep in-memory ledger if storage quota is exceeded.
  }
}

function exportLedger(format: string = 'json') {
  const date = new Date().toISOString().split('T')[0]
  let content = ''
  let mimeType = ''
  let fileName = ''
  
  if (format === 'json') {
    content = JSON.stringify(talkEntries.value, null, 2)
    mimeType = 'application/json'
    fileName = 'talk_ledger_' + date + '.json'
  } else if (format === 'csv') {
    const headers = ['student_id', 'counselor_name', 'meeting_at', 'location', 'topic_summary', 'agreed_actions', 'follow_up_at']
    const rows = talkEntries.value.map(e => [e.student_id, e.counselor_name, e.meeting_at, e.location, e.topic_summary, e.agreed_actions, e.follow_up_at || ''])
    content = headers.join(',') + '\n' + rows.map(r => r.join(',')).join('\n')
    mimeType = 'text/csv'
    fileName = 'talk_ledger_' + date + '.csv'
  } else if (format === 'txt') {
    const lines = ['=== Talk Ledger ===', 'Export: ' + new Date().toLocaleString(), '']
    talkEntries.value.forEach((e, i) => {
      lines.push('[' + (i + 1) + '] ' + e.student_id)
      lines.push('  Counselor: ' + e.counselor_name)
      lines.push('  Time: ' + e.meeting_at)
      lines.push('  Location: ' + e.location)
      lines.push('  Topic: ' + e.topic_summary)
      lines.push('  Actions: ' + e.agreed_actions)
      if (e.follow_up_at) lines.push('  Follow-up: ' + e.follow_up_at)
      lines.push('')
    })
    content = lines.join('\n')
    mimeType = 'text/plain'
    fileName = 'talk_ledger_' + date + '.txt'
  } else if (format === 'pdf') {
    generatePDF()
    return
  }
  
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = fileName
  a.click(); URL.revokeObjectURL(url)
}

/** Escape text before it is concatenated into the print document's HTML. */
function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function generatePDF() {
  const printWindow = window.open('', '_blank')
  if (!printWindow) return
  
  const date = new Date().toLocaleString('zh-CN')
  let html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Talk Ledger</title>'
  html += '<style>'
  html += 'body { font-family: SimSun, serif; padding: 40px; color: #333; }'
  html += 'h1 { text-align: center; font-size: 22px; margin-bottom: 5px; }'
  html += '.subtitle { text-align: center; color: #666; margin-bottom: 25px; font-size: 14px; }'
  html += '.record { border: 1px solid #ccc; padding: 15px; margin-bottom: 15px; page-break-inside: avoid; }'
  html += '.record-header { background: #f0f0f0; padding: 8px; margin: -15px -15px 12px; font-weight: bold; font-size: 14px; }'
  html += '.row { display: flex; margin-bottom: 6px; font-size: 13px; }'
  html += '.label { width: 90px; font-weight: bold; color: #555; }'
  html += '.value { flex: 1; }'
  html += '.section { margin-top: 12px; padding-top: 10px; border-top: 1px dashed #ddd; }'
  html += '.section-title { font-weight: bold; color: #173f43; margin-bottom: 6px; font-size: 13px; }'
  html += '.footer { margin-top: 30px; text-align: center; color: #999; font-size: 11px; }'
  html += '@media print { body { padding: 20px; } }'
  html += '</style></head><body>'
  html += '<h1>SDNU Talk Ledger</h1>'
  html += '<p class="subtitle">Shandong Normal University - Export Time: ' + escapeHtml(date) + '</p>'
  
  talkEntries.value.forEach((entry, i) => {
    html += '<div class="record">'
    html += '<div class="record-header">Record ' + (i + 1) + '</div>'
    html += '<div class="row"><span class="label">Student ID:</span><span class="value">' + escapeHtml(entry.student_id) + '</span></div>'
    html += '<div class="row"><span class="label">Name:</span><span class="value">' + escapeHtml(entry.student_name || 'N/A') + '</span></div>'
    html += '<div class="row"><span class="label">Counselor:</span><span class="value">' + escapeHtml(entry.counselor_name) + '</span></div>'
    html += '<div class="row"><span class="label">Time:</span><span class="value">' + escapeHtml(entry.meeting_at) + '</span></div>'
    html += '<div class="row"><span class="label">Location:</span><span class="value">' + escapeHtml(entry.location) + '</span></div>'
    html += '<div class="section"><div class="section-title">Topic</div><p>' + escapeHtml(entry.topic_summary) + '</p></div>'
    html += '<div class="section"><div class="section-title">Agreed Actions</div><p>' + escapeHtml(entry.agreed_actions) + '</p></div>'
    if (entry.overall_assessment) {
      html += '<div class="section"><div class="section-title">Assessment</div><p>' + escapeHtml(entry.overall_assessment) + '</p></div>'
    }
    if (entry.follow_up_at) {
      html += '<div class="section"><div class="section-title">Follow-up</div><p>' + escapeHtml(entry.follow_up_at) + '</p></div>'
    }
    html += '</div>'
  })
  
  html += '<div class="footer"><p>Total: ' + talkEntries.value.length + ' records</p>'
  html += '<p>Generated by SDNU Smart Campus Platform</p></div>'
  html += '</body></html>'
  
  printWindow.document.write(html)
  printWindow.document.close()
  setTimeout(() => printWindow.print(), 500)
}

onMounted(() => {
  fetchWall()
  if (isStaff.value) {
    fetchAlerts()
    const stored = localStorage.getItem('zhq-talk-ledger')
    if (stored) {
      try {
        talkEntries.value = JSON.parse(stored)
      } catch {
        talkEntries.value = []
      }
    }
  }
})

onBeforeUnmount(() => window.clearInterval(breathTimer))
</script>

<template>
  <section class="wellbeing-page">
    <div class="wellbeing-main">
      <header class="wellbeing-hero">
        <div>
          <span>{{ isStaff ? '辅导员工作台' : '给自己留十分钟' }}</span>
          <h1>{{ isStaff ? '关注学生状态，' : '今天的你，' }}<br><em>{{ isStaff ? '及时给予关怀。' : '不必急着变好。' }}</em></h1>
          <p>{{ isStaff ? '查看预警、发布寄语、记录谈心台账。' : '先辨认感受，再决定是聊一聊、写下来，还是安静呼吸一会儿。' }}</p>
        </div>
        <button v-if="isStudent" type="button" class="talk-callout" @click="openGuide">
          <PhChatCircleDots :size="27" weight="duotone" />
          <span><strong>和小齐聊聊</strong><small>右下角的引导员支持多轮对话</small></span>
          <PhPaperPlaneTilt :size="18" />
        </button>
      </header>

      <!-- 学生专属：两个入口。有人只想记录自己，有人只想看大家的开心事 -->
      <nav v-if="isStudent" class="space-tabs" aria-label="暖心空间入口">
        <button type="button" :class="{ active: activeTab === 'self' }" @click="switchTab('self')">
          <PhWind :size="17" weight="duotone" />
          <span>记录自己<small>仅你与辅导员可见</small></span>
        </button>
        <button type="button" :class="{ active: activeTab === 'share' }" @click="switchTab('share')">
          <PhConfetti :size="17" weight="duotone" />
          <span>开心分享<small>全校可见的积极小事</small></span>
        </button>
      </nav>

      <!-- 开心分享墙 -->
      <template v-if="isStudent && activeTab === 'share'">
        <article class="happy-compose">
          <header>
            <div><PhConfetti :size="24" weight="duotone" /><h2>今天有什么值得高兴的？</h2></div>
            <span>公开可见</span>
          </header>
          <p class="compose-hint">
            这里只收积极的内容：一件小确幸、一张好看的天空、一句想分享的话。
            如果今天不太好受，请用「记录自己」——那条不会公开。
          </p>
          <textarea v-model="shareContent" maxlength="500" placeholder="例如：答辩过了，出门看到晚霞是粉色的。"></textarea>

          <div v-if="shareImage" class="share-image-preview">
            <img :src="shareImage" alt="待发布的图片预览">
            <button type="button" @click="shareImage = null">移除图片</button>
          </div>

          <div class="compose-actions">
            <label class="share-upload">
              <PhImage :size="17" weight="duotone" />
              <span>{{ shareImage ? '换一张图' : '加一张图' }}</span>
              <input type="file" accept="image/*" @change="pickShareImage">
            </label>
            <label class="share-anon">
              <input v-model="shareAnonymous" type="checkbox">
              <span>匿名发布</span>
            </label>
            <button type="button" class="share-publish" :disabled="shareLoading" @click="publishShare">
              {{ shareLoading ? '正在发布' : '发布到分享墙' }}
            </button>
          </div>
          <p v-if="shareStatus" class="share-ok">{{ shareStatus }}</p>
          <p v-if="shareError" class="inline-error">{{ shareError }}</p>
        </article>

        <article class="happy-wall">
          <header class="section-header">
            <div><PhUsers :size="22" weight="duotone" /><h2>大家的开心事</h2></div>
            <button type="button" class="refresh-btn" @click="fetchShares">刷新</button>
          </header>
          <div v-if="!shareLoaded" class="empty-state"><p>正在加载…</p></div>
          <div v-else-if="shares.length === 0" class="empty-state">
            <p>还没有人分享，你可以是第一个。</p>
          </div>
          <div v-else class="share-grid">
            <article v-for="item in shares" :key="item.share_id" class="share-card">
              <img v-if="item.image_data_url" :src="item.image_data_url" alt="分享的图片" loading="lazy">
              <p>{{ item.content }}</p>
              <footer>
                <span class="share-author">{{ item.author_name }}</span>
                <span class="share-time">{{ formatShareTime(item.created_at) }}</span>
                <button
                  type="button"
                  class="cheer-btn"
                  :class="{ cheered: cheeredIds.includes(item.share_id) }"
                  :disabled="cheeredIds.includes(item.share_id)"
                  @click="cheerShare(item)"
                >
                  <PhHeart :size="15" :weight="cheeredIds.includes(item.share_id) ? 'fill' : 'regular'" />
                  {{ item.cheer_count }}
                </button>
              </footer>
            </article>
          </div>
        </article>
      </template>

      <!-- 记录自己 -->
      <template v-if="isStudent && activeTab === 'self'">
      <!-- 学生专属：心情打卡 -->
      <article v-if="isStudent" class="mood-checkin">
        <div class="checkin-title">
          <div><h2>此刻更像哪一种天气？</h2><p>这是日常状态记录，不是心理诊断。</p></div>
          <span>今日打卡</span>
        </div>
        <div class="weather-picker">
          <button v-for="item in weatherOptions" :key="item.id" :class="{ chosen: weather === item.id }" type="button" @click="weather = item.id">
            <b>{{ item.mark }}</b><span><strong>{{ item.label }}</strong><small>{{ item.copy }}</small></span>
          </button>
        </div>
        <label class="reflection-field">
          <span>想补充一点吗？ <small>可选，仅本人可见</small></span>
          <textarea v-model="reflection" maxlength="2000" placeholder="例如：今天汇报前有点紧张，但结束后松了一口气。"></textarea>
        </label>
        <div class="checkin-action">
          <p v-if="response" :class="['support-result', level]">{{ response }}</p>
          <p v-else>记录会进入你的短期记忆，7 天后按策略过期。</p>
          <button type="button" :disabled="loading" @click="checkIn">{{ loading ? '正在保存' : '保存今天的状态' }}</button>
        </div>
        <p v-if="error" class="inline-error">{{ error }}</p>
      </article>

      <!-- 学生专属：呼吸练习和日记 -->
      <div v-if="isStudent" class="wellbeing-tools">
        <article class="breathing-card">
          <div class="breath-orbit" :class="{ active: breathing }"><span>{{ breathSeconds }}</span></div>
          <div>
            <PhWind :size="24" weight="duotone" /><h2>一分钟呼吸</h2>
            <p>{{ breathPhase }}</p>
            <button type="button" @click="startBreathing">{{ breathing ? '结束练习' : '跟着节奏开始' }}</button>
          </div>
        </article>
        <article class="journal-card">
          <header>
            <div><PhBookOpenText :size="23" weight="duotone" /><h2>只写给自己</h2></div>
            <span><PhLockKey :size="14" /> 仅存本机</span>
          </header>
          <textarea v-model="journal" maxlength="4000" placeholder="不用完整，也不用正确。写下脑海里最响的那句话。"></textarea>
          <button type="button" @click="saveJournal">{{ journalSaved ? '已经保存' : '保存私人片段' }}</button>
        </article>
      </div>
      </template>

      <!-- 辅导员专属：预警总览 -->
      <article v-if="isStaff" class="alert-overview">
        <div class="section-header">
          <div><PhWarning :size="24" weight="duotone" /><h2>预警总览</h2></div>
          <button @click="fetchAlerts" class="refresh-btn">刷新</button>
        </div>
        <div v-if="alerts.length === 0" class="empty-state">
          <p>暂无预警信息</p>
        </div>
        <div v-else class="alert-list">
          <div v-for="alert in alerts" :key="alert.student_id" :class="['alert-item', alert.level]">
            <span class="alert-level">{{ alert.level }}</span>
            <span class="alert-student">{{ alert.student_id }}</span>
            <span class="alert-reason">{{ alert.reason_codes.join(', ') }}</span>
            <span class="alert-time">{{ alert.created_at }}</span>
          </div>
        </div>
      </article>

      <!-- 辅导员专属：谈心台账 -->
      <article v-if="isStaff" class="talk-ledger">
        <div class="section-header">
          <div><PhNotebook :size="24" weight="duotone" /><h2>谈心台账</h2></div>
          <div class="action-buttons">
            <button @click="showNewTalk = !showNewTalk" class="add-btn">
              {{ showNewTalk ? '取消' : '+ 新增记录' }}
            </button>
            <div class="export-dropdown">
              <button class="export-btn" :disabled="talkEntries.length === 0">
                <PhExport :size="16" /> 导出
              </button>
              <div class="export-options">
                <button @click="exportLedger('json')">JSON</button>
                <button @click="exportLedger('csv')">CSV</button>
                <button @click="exportLedger('txt')">TXT</button>
                <button @click="exportLedger('pdf')">PDF</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 新增谈心记录表单 -->
        <div v-if="showNewTalk" class="talk-form">
          <div class="form-row">
            <label>学生学号<input v-model="newTalk.student_id" placeholder="学号"></label>
            <label>学生姓名<input v-model="newTalk.student_name" placeholder="姓名"></label>
          </div>
          <div class="form-row">
            <label>辅导员<input v-model="newTalk.counselor_name" placeholder="姓名"></label>
            <label>访谈时间<input v-model="newTalk.meeting_at" type="datetime-local"></label>
          </div>
          <label>访谈地点<input v-model="newTalk.location" placeholder="如：心理咨询室"></label>
          <label>主要话题<textarea v-model="newTalk.topic_summary" placeholder="记录主要讨论的话题"></textarea></label>
          <label>商定事项<textarea v-model="newTalk.agreed_actions" placeholder="记录商定的后续行动"></textarea></label>
          <label>下次跟进<input v-model="newTalk.follow_up_at" type="date"></label>
          <label>整体概况评价<textarea v-model="newTalk.overall_assessment" placeholder="对学生整体情况的评价和建议"></textarea></label>
          <button @click="addTalkEntry" class="submit-btn">保存记录</button>
        </div>

        <!-- 搜索和统计 -->
        <div class="ledger-stats" v-if="talkEntries.length > 0">
          <span>Total: {{ filteredTalkEntries.length }} records</span>
          <input v-model="talkSearch" placeholder="Search..." class="search-input">
        </div>

        <!-- 谈心记录列表 -->
        <div v-if="filteredTalkEntries.length === 0" class="empty-state">
          <p>暂无谈心记录</p>
        </div>
        <div v-else class="talk-list">
          <div v-for="(entry, index) in filteredTalkEntries" :key="index" class="talk-item">
            <div class="talk-header">
              <span class="talk-student">{{ entry.student_id }}</span>
              <span class="talk-time">{{ entry.meeting_at }}</span>
            </div>
            <div class="talk-content">
              <p><strong>学生：</strong>{{ entry.student_name || '未填写' }}（{{ entry.student_id }}）</p>
              <p><strong>话题：</strong>{{ entry.topic_summary }}</p>
              <p><strong>商定：</strong>{{ entry.agreed_actions }}</p>
              <p v-if="entry.overall_assessment"><strong>评价：</strong>{{ entry.overall_assessment }}</p>
              <p v-if="entry.follow_up_at"><strong>跟进：</strong>{{ entry.follow_up_at }}</p>
            </div>
          </div>
        </div>
      </article>

      <!-- 紧急支持说明 -->
      <section class="support-entries">
        <h2>需要更多支持时</h2>
        <div>
          <article class="support-card">
            <PhFlowerLotus :size="24" weight="duotone" /><h3>校内心理支持</h3>
            <p>学校的心理支持渠道，可直接联系；本系统不代约、不转存你的对话内容。</p>
            <div class="support-links">
              <a href="tel:12356" class="support-link">
                <PhPhoneCall :size="17" weight="duotone" />
                <span><strong>12356</strong><small>24 小时心理援助热线</small></span>
              </a>
              <button type="button" class="support-link" @click="copyCounselorQQ">
                <PhChatCircleDots :size="17" weight="duotone" />
                <span><strong>2645256823</strong><small>山师心灵阳光使者 · QQ</small></span>
                <em>{{ qqCopied ? '已复制' : '复制' }}</em>
              </button>
            </div>
          </article>
          <article class="support-card">
            <PhFirstAid :size="24" weight="duotone" /><h3>紧急支持说明</h3>
            <p>当自己或他人可能立即受伤时，请优先联系身边可信任的人和当地紧急服务。</p>
            <div class="support-links">
              <a href="tel:120" class="support-link">
                <PhPhoneCall :size="17" weight="duotone" />
                <span><strong>120</strong><small>急救</small></span>
              </a>
              <a href="tel:110" class="support-link">
                <PhPhoneCall :size="17" weight="duotone" />
                <span><strong>110</strong><small>报警</small></span>
              </a>
            </div>
          </article>
        </div>
      </section>

      <!-- 寄语墙 -->
      <section class="counselor-wall">
        <header>
          <div><h2>辅导员寄语墙</h2><p>发布者身份在学生端匿名展示，内容先经过人工确认。</p></div>
        </header>
        <div v-if="isStaff" class="wall-publisher">
          <input v-model="wallTopic" maxlength="80" aria-label="寄语主题">
          <textarea v-model="wallContent" maxlength="1000" placeholder="写下一段简短、明确的支持。"></textarea>
          <div><span>{{ wallStatus }}</span><button type="button" :disabled="loading" @click="publishWallMessage">发布寄语</button></div>
        </div>
        <div class="wall-notes">
          <article v-for="note in wall" :key="note.message_id">
            <small>{{ note.topic || '今日寄语' }}</small><p>{{ note.content }}</p>
          </article>
          <article v-if="!wall.length">
            <small>等待一封寄语</small><p>辅导员还没有发布新内容。</p>
          </article>
        </div>
      </section>
    </div>
    <WellbeingUtilityRail />
  </section>
</template>