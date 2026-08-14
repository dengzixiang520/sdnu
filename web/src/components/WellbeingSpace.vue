<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, computed } from 'vue'
import { 
  PhBookOpenText, PhChatCircleDots, PhFirstAid, PhFlowerLotus, PhLockKey, 
  PhPaperPlaneTilt, PhWind, PhWarning, PhCalendarCheck, PhNotebook,
  PhChartLine, PhUsers, PhExport
} from '@phosphor-icons/vue'
import { command } from '../api'
import { useIdentity } from '../identity'
import WellbeingUtilityRail from './WellbeingUtilityRail.vue'

type Weather = 'sunny' | 'cloudy' | 'rainy' | 'stormy'
interface WallMessage { message_id: string; content: string; topic?: string }
interface AlertItem { student_id: string; level: string; reason_codes: string[]; created_at: string }
interface TalkEntry { student_id: string; counselor_name: string; meeting_at: string; location: string; topic_summary: string; agreed_actions: string; follow_up_at?: string }

const { identity } = useIdentity()

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
  student_id: '', counselor_name: '', meeting_at: '', location: '',
  topic_summary: '', agreed_actions: '', follow_up_at: ''
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
  newTalk.value = { student_id: '', counselor_name: '', meeting_at: '', location: '', topic_summary: '', agreed_actions: '', follow_up_at: '' }
  showNewTalk.value = false
  localStorage.setItem('zhq-talk-ledger', JSON.stringify(talkEntries.value))
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
  }
  
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = fileName
  a.click(); URL.revokeObjectURL(url)
}

onMounted(() => {
  fetchWall()
  if (isStaff.value) {
    fetchAlerts()
    const stored = localStorage.getItem('zhq-talk-ledger')
    if (stored) talkEntries.value = JSON.parse(stored)
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
              </div>
            </div>
          </div>
        </div>

        <!-- 新增谈心记录表单 -->
        <div v-if="showNewTalk" class="talk-form">
          <div class="form-row">
            <label>学生ID<input v-model="newTalk.student_id" placeholder="学号"></label>
            <label>辅导员<input v-model="newTalk.counselor_name" placeholder="姓名"></label>
          </div>
          <div class="form-row">
            <label>时间<input v-model="newTalk.meeting_at" type="datetime-local"></label>
            <label>地点<input v-model="newTalk.location" placeholder="如：心理咨询室"></label>
          </div>
          <label>主要话题<textarea v-model="newTalk.topic_summary" placeholder="记录主要讨论的话题"></textarea></label>
          <label>商定事项<textarea v-model="newTalk.agreed_actions" placeholder="记录商定的后续行动"></textarea></label>
          <label>下次跟进<input v-model="newTalk.follow_up_at" type="date"></label>
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
              <p><strong>话题：</strong>{{ entry.topic_summary }}</p>
              <p><strong>商定：</strong>{{ entry.agreed_actions }}</p>
              <p v-if="entry.follow_up_at"><strong>跟进：</strong>{{ entry.follow_up_at }}</p>
            </div>
          </div>
        </div>
      </article>

      <!-- 紧急支持说明 -->
      <section class="support-entries">
        <h2>需要更多支持时</h2>
        <div>
          <article>
            <PhFlowerLotus :size="24" weight="duotone" /><h3>校园心理资源</h3>
            <p>展示校内心理中心、预约方式与值班安排。当前尚未接入学校预约系统。</p>
            <button type="button" disabled>等待官方接口</button>
          </article>
          <article>
            <PhFirstAid :size="24" weight="duotone" /><h3>紧急支持说明</h3>
            <p>当自己或他人可能立即受伤时，请优先联系身边可信任的人和当地紧急服务。</p>
            <a href="tel:120">拨打 120</a>
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