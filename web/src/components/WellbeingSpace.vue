<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, computed, nextTick } from 'vue'
import { 
  PhBookOpenText, PhChatCircleDots, PhFirstAid, PhFlowerLotus, PhLockKey, 
  PhPaperPlaneTilt, PhWind, PhWarning, PhNotebook,
  PhChartLine, PhUsers, PhExport, PhPhoneCall, PhConfetti, PhImage, PhHeart, PhClipboardText
} from '@phosphor-icons/vue'
import { command } from '../api'
import { useIdentity } from '../identity'
import GuideChat from './GuideChat.vue'
import WellbeingUtilityRail from './WellbeingUtilityRail.vue'
import LyricStage from './lyric/LyricStage.vue'

type Weather = 'sunny' | 'cloudy' | 'rainy' | 'stormy'
/** 后端 mood_history 的一条打卡记录；checked_at 是带时区的 ISO 字符串。 */
interface MoodPoint { weather: string; checked_at: string; reflection: string }
interface MoodCell { key: string; weekday: string; label: string; weather: string; score: number; reflection: string; isToday: boolean }
interface TrendPoint { x: number; y: number; cell: MoodCell }
interface WallMessage { message_id: string; content: string; topic?: string }
interface AlertItem { student_id: string; level: string; reason_codes: string[]; created_at: string }
interface BookingItem { booking_id: string; user_id: string; slot: string; note: string; alert_level: string; requested_at: string; status: string }
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

/** localStorage 在隐私模式或配额满时会直接抛错，读写一律走这两层包装。 */
function readStoredText(key: string): string {
  try {
    return localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

function writeStoredText(key: string, value: string): boolean {
  try {
    localStorage.setItem(key, value)
    return true
  } catch {
    return false
  }
}

const journal = ref(readStoredText('zhq-private-journal'))
const journalSaved = ref(false)

// 呼吸练习：多节奏（4-7-8 / 方箱 / 均匀），用 conic-gradient 圆环推进
type BreathStageKind = 'inhale' | 'hold' | 'exhale'
interface BreathStage { kind: BreathStageKind; seconds: number }
interface BreathPattern { id: string; label: string; hint: string; cycles: number; stages: BreathStage[] }

const breathPatterns: BreathPattern[] = [
  {
    id: '478',
    label: '4-7-8 放松',
    hint: '吸气 4 秒 · 屏住 7 秒 · 呼气 8 秒',
    cycles: 4,
    stages: [{ kind: 'inhale', seconds: 4 }, { kind: 'hold', seconds: 7 }, { kind: 'exhale', seconds: 8 }],
  },
  {
    id: 'box',
    label: '方箱呼吸',
    hint: '吸 4 秒 · 屏 4 秒 · 呼 4 秒 · 屏 4 秒',
    cycles: 4,
    stages: [
      { kind: 'inhale', seconds: 4 },
      { kind: 'hold', seconds: 4 },
      { kind: 'exhale', seconds: 4 },
      { kind: 'hold', seconds: 4 },
    ],
  },
  {
    id: 'even',
    label: '均匀呼吸',
    hint: '吸气 4 秒 · 呼气 4 秒',
    cycles: 6,
    stages: [{ kind: 'inhale', seconds: 4 }, { kind: 'exhale', seconds: 4 }],
  },
]

const BREATH_TICK_MS = 100
const breathing = ref(false)
const breathDone = ref(false)
const breathPatternId = ref(breathPatterns[0].id)
const breathStageIndex = ref(0)
const breathStageElapsed = ref(0)
const breathCycle = ref(0)
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
const bookings = ref<BookingItem[]>([])
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

// ---------- 情绪趋势 / 心情日历（共用一份 mood_history，只请求一次） ----------

/** weather → 1-5 分，只用来把打卡画成折线与色块，不是任何心理量表。 */
const MOOD_SCORE: Record<string, number> = { sunny: 5, cloudy: 3, rainy: 2, stormy: 1 }
const WEATHER_MARK: Record<string, string> = { sunny: '晴', cloudy: '云', rainy: '雨', stormy: '雷' }
const WEATHER_LABEL: Record<string, string> = { sunny: '轻松', cloudy: '一般', rainy: '低落', stormy: '难熬' }
const WEEKDAY_LABEL = ['日', '一', '二', '三', '四', '五', '六']
/** 短期记忆只保留 7 天，趋势和热力图都按这个窗口做。 */
const MOOD_WINDOW_DAYS = 7

// 折线图坐标系：viewBox 固定 320x140，容器按同一比例缩放，悬停提示才能对得上。
const CHART_W = 320
const CHART_H = 140
const CHART_PAD_X = 18
const CHART_PAD_TOP = 16
const CHART_PAD_BOTTOM = 26
const CHART_BASE_Y = CHART_H - CHART_PAD_BOTTOM

const moodHistory = ref<MoodPoint[]>([])
const moodLoaded = ref(false)
const moodLoading = ref(false)
const moodError = ref('')
const moodHover = ref<number | null>(null)

function chartX(index: number): number {
  return CHART_PAD_X + (index / (MOOD_WINDOW_DAYS - 1)) * (CHART_W - CHART_PAD_X * 2)
}

function chartY(score: number): number {
  const clamped = Math.min(5, Math.max(1, score))
  return CHART_PAD_TOP + ((5 - clamped) / 4) * (CHART_H - CHART_PAD_TOP - CHART_PAD_BOTTOM)
}

/** 用本地日期做键，避免 UTC 与东八区跨日错位。 */
function localDateKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

const recentDays = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  // 用 setDate 逐日回退，跨夏令时也不会落到前一天 23 点。
  return Array.from({ length: MOOD_WINDOW_DAYS }, (_, index) => {
    const date = new Date(today)
    date.setDate(date.getDate() - (MOOD_WINDOW_DAYS - 1 - index))
    return date
  })
})

const todayKey = computed(() => localDateKey(recentDays.value[recentDays.value.length - 1]))

/** 同一天多次打卡只保留最后一次，一格日历只显示一个状态。 */
const moodByDay = computed(() => {
  const map = new Map<string, MoodPoint>()
  for (const item of moodHistory.value) {
    const when = new Date(item.checked_at)
    if (Number.isNaN(when.getTime())) continue
    map.set(localDateKey(when), item)
  }
  return map
})

const calendarCells = computed<MoodCell[]>(() => recentDays.value.map((date) => {
  const key = localDateKey(date)
  const item = moodByDay.value.get(key)
  return {
    key,
    weekday: WEEKDAY_LABEL[date.getDay()],
    label: `${date.getMonth() + 1}/${date.getDate()}`,
    weather: item?.weather ?? '',
    score: item ? MOOD_SCORE[item.weather] ?? 0 : 0,
    reflection: item?.reflection ?? '',
    isToday: key === todayKey.value,
  }
}))

const trendPoints = computed<TrendPoint[]>(() => {
  const points: TrendPoint[] = []
  calendarCells.value.forEach((cell, index) => {
    if (!cell.score) return
    points.push({ x: chartX(index), y: chartY(cell.score), cell })
  })
  return points
})

const trendLine = computed(() => (
  trendPoints.value.length >= 2
    ? trendPoints.value.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
    : ''
))

const trendArea = computed(() => {
  const points = trendPoints.value
  if (points.length < 2) return ''
  const base = CHART_BASE_Y + 4
  const first = points[0]
  const last = points[points.length - 1]
  return [
    `${first.x.toFixed(1)},${base}`,
    ...points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`),
    `${last.x.toFixed(1)},${base}`,
  ].join(' ')
})

const trendGuides = computed(() => [5, 3, 1].map((score) => ({ score, y: chartY(score) })))

const hoverPoint = computed(() => {
  const index = moodHover.value
  if (index === null) return null
  const point = trendPoints.value[index]
  if (!point) return null
  const reflection = point.cell.reflection.trim()
  return {
    left: `${Math.min(88, Math.max(12, (point.x / CHART_W) * 100))}%`,
    top: `${(point.y / CHART_H) * 100}%`,
    flip: point.y < 44,
    date: point.cell.label,
    weekday: point.cell.weekday,
    weatherLabel: `${WEATHER_MARK[point.cell.weather] ?? '·'} · ${WEATHER_LABEL[point.cell.weather] ?? '未记录'}`,
    text: reflection ? (reflection.length > 20 ? `${reflection.slice(0, 20)}…` : reflection) : '那天没有写备注',
  }
})

/* ---------- 打卡后的「照镜子」：对比上次 / 本周分布 / 最该注意的 ---------- */
const insight = ref<{ compare: string; spread: string; focus: string } | null>(null)

/** 连续偏低（雨/雷，分 ≤ 2）的最长区间；不足 2 天不算「连续」。 */
function lowRunText(cells: MoodCell[]): string {
  let best: { start: number; len: number } | null = null
  let run = 0
  for (let index = 0; index < cells.length; index += 1) {
    const cell = cells[index]
    if (cell.score > 0 && cell.score <= 2) {
      run += 1
      if (!best || run > best.len) best = { start: index - run + 1, len: run }
    } else {
      run = 0
    }
  }
  if (!best || best.len < 2) return ''
  const head = cells[best.start]
  const tail = cells[best.start + best.len - 1]
  const span = best.len === 2 ? `${head.label} 和 ${tail.label}` : `${head.label}～${tail.label}`
  return `${span} 连续 ${best.len} 天偏低落，值得留意`
}

/** 7 天窗口里每个星期几只出现一次，所以不做「按星期聚合」——那是假信号。
    真正有意义的是工作日 / 周末的对比。 */
const weekdaySplit = computed(() => {
  const filled = calendarCells.value.filter((cell) => cell.score > 0)
  const workday = filled.filter((cell) => cell.weekday !== '六' && cell.weekday !== '日')
  const weekend = filled.filter((cell) => cell.weekday === '六' || cell.weekday === '日')
  const average = (rows: MoodCell[]) => (rows.length ? rows.reduce((sum, cell) => sum + cell.score, 0) / rows.length : 0)
  return {
    workday: { count: workday.length, avg: average(workday) },
    weekend: { count: weekend.length, avg: average(weekend) },
  }
})

/** 这一周的结论，趋势卡和打卡后的「照镜子」共用同一段判断，避免两处口径打架。 */
const reviewSummary = computed(() => {
  const filled = calendarCells.value.filter((cell) => cell.score > 0)
  if (!filled.length) return '还没有打卡记录，先记一次今天的状态。'
  if (filled.length === 1) return '目前只有 1 天记录，多记几天才能看出走势。'

  const run = lowRunText(calendarCells.value)
  if (run) return run

  const { workday, weekend } = weekdaySplit.value
  if (workday.count && weekend.count) {
    const gap = workday.avg - weekend.avg
    if (Math.abs(gap) >= 0.5) {
      return gap > 0
        ? `周末比工作日平均高 ${gap.toFixed(1)} 分，课表带来的压力可能比你以为的大`
        : `工作日反而比周末平均高 ${(-gap).toFixed(1)} 分`
    }
  }

  const ordered = [...filled].sort((left, right) => left.score - right.score)
  const lowest = ordered[0]
  const best = ordered[ordered.length - 1]
  if (lowest.score === best.score) return `这几天状态都在「${WEATHER_LABEL[best.weather] ?? ''}」，很平稳`
  return `最好的是 ${best.label}（${WEATHER_LABEL[best.weather] ?? ''}），最低的是 ${lowest.label}（${WEATHER_LABEL[lowest.weather] ?? ''}）`
})

/** 打卡后的即时反馈：和上一次比，比「周总结」更贴身。 */
function buildInsight() {
  const cells = calendarCells.value
  const filled = cells.filter((cell) => cell.score > 0)
  if (!filled.length) {
    insight.value = null
    return
  }

  const today = filled[filled.length - 1]
  const previous = filled.length >= 2 ? filled[filled.length - 2] : null

  let compare = `这是这个窗口的第 1 次记录（今天 ${WEATHER_MARK[today.weather] ?? '·'}）`
  if (previous) {
    const delta = today.score - previous.score
    const trend = delta > 0 ? `转好 ${delta} 档` : delta < 0 ? `回落 ${-delta} 档` : '和上次一样'
    compare = `上次 ${previous.label} ${WEATHER_MARK[previous.weather] ?? '·'} → 今天 ${WEATHER_MARK[today.weather] ?? '·'}，${trend}`
    if (delta > 0) {
      let streak = 1
      for (let index = filled.length - 1; index > 0; index -= 1) {
        if (filled[index].score > filled[index - 1].score) streak += 1
        else break
      }
      if (streak >= 2) compare += `，连转 ${streak} 天`
    }
  }

  const counts = new Map<string, number>()
  for (const cell of filled) counts.set(cell.weather, (counts.get(cell.weather) ?? 0) + 1)
  const spread = `${MOOD_WINDOW_DAYS} 天里记了 ${filled.length} 天：` + [...counts.entries()]
    .sort((left, right) => (MOOD_SCORE[right[0]] ?? 0) - (MOOD_SCORE[left[0]] ?? 0))
    .map(([weather, count]) => `${count} ${WEATHER_MARK[weather] ?? '·'}`)
    .join(' / ')

  insight.value = { compare, spread, focus: reviewSummary.value }
}

/* ---------- 主动约谈心：把后端算出的 booking_suggested 接上 ---------- */
const bookingSuggested = ref(false)
const followUpRequested = ref(false)
const bookingSlot = ref('')
const bookingNote = ref('')
const bookingNotice = ref('')
const bookingDone = ref(false)

/** 从明天起找 3 个工作日时段，作为可约选项。 */
const bookingSlots = computed(() => {
  const slots: string[] = []
  const cursor = new Date()
  cursor.setHours(0, 0, 0, 0)
  let guard = 0
  while (slots.length < 3 && guard < 14) {
    guard += 1
    cursor.setDate(cursor.getDate() + 1)
    const weekday = cursor.getDay()
    if (weekday === 0 || weekday === 6) continue
    slots.push(`${cursor.getMonth() + 1}/${cursor.getDate()} 周${WEEKDAY_LABEL[weekday]} 15:00-15:30`)
  }
  return slots
})

async function requestBooking() {
  if (!bookingSlot.value) {
    bookingNotice.value = '先选一个时段'
    return
  }
  try {
    const result = await command('wellbeing', 'request_booking', '', {
      slot: bookingSlot.value,
      note: bookingNote.value,
      alert_level: level.value,
    })
    bookingDone.value = true
    bookingNotice.value = result.message
  } catch (reason) {
    bookingNotice.value = reason instanceof Error ? reason.message : '提交失败，请稍后再试'
  }
}

/* ---------- 4 题极简自评（PHQ-2 + GAD-2） ----------
   题目由后端给（wellbeing/self_check_items），前端不硬编码，改题库只改一处。
   结果只提示「要不要找专业的人聊聊」，不做诊断、不打标签。 */
interface SelfCheckItem { id: string; text: string; group: string }
interface SelfCheckOption { value: number; label: string }
interface SelfCheckMeta { window: string; items: SelfCheckItem[]; options: SelfCheckOption[]; disclaimer: string }
interface SelfCheckResult {
  level: 'green' | 'yellow' | 'orange'
  phq2: number
  gad2: number
  total: number
  focus: string
  advice: string
  recommend_booking: boolean
  hotline: string
  window: string
  disclaimer: string
}

const selfCheckMeta = ref<SelfCheckMeta | null>(null)
const selfCheckAnswers = ref<Record<string, number>>({})
const selfCheckResult = ref<SelfCheckResult | null>(null)
const selfCheckBusy = ref(false)
const selfCheckNotice = ref('')

async function loadSelfCheck() {
  if (selfCheckMeta.value) return
  try {
    const response = await command('wellbeing', 'self_check_items')
    selfCheckMeta.value = response.data as unknown as SelfCheckMeta
  } catch (reason) {
    selfCheckNotice.value = reason instanceof Error ? reason.message : '题目加载失败'
  }
}

function pickSelfCheck(id: string, value: number) {
  selfCheckAnswers.value = { ...selfCheckAnswers.value, [id]: value }
}

const selfCheckReady = computed(() => {
  const items = selfCheckMeta.value?.items ?? []
  return items.length > 0 && items.every((item) => typeof selfCheckAnswers.value[item.id] === 'number')
})

async function submitSelfCheck() {
  if (!selfCheckReady.value) {
    selfCheckNotice.value = '四道题都要选一个'
    return
  }
  selfCheckBusy.value = true
  selfCheckNotice.value = ''
  try {
    const response = await command('wellbeing', 'submit_self_check', '', { answers: selfCheckAnswers.value })
    selfCheckResult.value = response.data as unknown as SelfCheckResult
    // 自评建议预约时直接打开上面那张预约卡：别让人拿到建议还得自己找入口
    if (selfCheckResult.value.recommend_booking) {
      bookingSuggested.value = true
      bookingNotice.value = '自评结果建议约一次，选一个时段就行'
      await nextTick()
      document.querySelector('.wbx-booking')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  } catch (reason) {
    selfCheckNotice.value = reason instanceof Error ? reason.message : '提交失败'
  } finally {
    selfCheckBusy.value = false
  }
}

function resetSelfCheck() {
  selfCheckAnswers.value = {}
  selfCheckResult.value = null
  selfCheckNotice.value = ''
}

/* ---------- 心情不好时的疏导动作 ---------- */
interface SootheAction { id: string; title: string; detail: string; why: string; target: string }
interface SootheGroup { id: string; label: string; actions: SootheAction[] }

const SOOTHE_LOG_KEY = 'zhq-wellbeing-soothe-log'
/** 跳转锚点：每条建议都能落到页面上一个真实入口，不用用户自己找 */
const SOOTHE_ANCHORS: Record<string, string> = {
  chat: '.gcx-card',
  journal: '.journal-card',
  breath: '.wbx-breath-card',
  music: '.wellbeing-rail',
}

const sootheGroups = ref<SootheGroup[]>([])
const sootheShow = ref(false)
const sootheRound = ref(0)
/** 本轮已经标记过的动作 id，只影响显示，不影响累计日志 */
const sootheDone = ref<string[]>([])
const sootheLog = ref<Array<{ id: string; at: string }>>([])

function readSootheLog(): Array<{ id: string; at: string }> {
  try {
    const raw = localStorage.getItem(SOOTHE_LOG_KEY)
    const rows = raw ? (JSON.parse(raw) as Array<{ id: string; at: string }>) : []
    return Array.isArray(rows) ? rows.filter((row) => row && typeof row.id === 'string' && typeof row.at === 'string') : []
  } catch {
    return []
  }
}

function persistSootheLog() {
  try {
    localStorage.setItem(SOOTHE_LOG_KEY, JSON.stringify(sootheLog.value.slice(-120)))
  } catch {
    // 配额满时丢历史，不影响本次使用
  }
}

async function fetchSoothe() {
  if (!isStudent.value) return
  try {
    const result = await command('wellbeing', 'soothe_suggestions')
    const data = result.data as { show?: boolean; groups?: SootheGroup[] }
    sootheGroups.value = Array.isArray(data.groups) ? data.groups : []
    sootheShow.value = Boolean(data.show)
  } catch {
    sootheGroups.value = []
    sootheShow.value = false
  }
}

/** 每组各取一条，「换一批」整体往后挪一位 */
const soothePicks = computed(() => sootheGroups.value
  .map((group) => (group.actions.length
    ? { id: group.id, label: group.label, action: group.actions[sootheRound.value % group.actions.length] }
    : null))
  .filter((item): item is { id: string; label: string; action: SootheAction } => item !== null))

const sootheWeekCount = computed(() => {
  const cutoff = Date.now() - 7 * 86400000
  return sootheLog.value.filter((row) => {
    const at = new Date(row.at).getTime()
    return Number.isFinite(at) && at >= cutoff
  }).length
})

function rotateSoothe() {
  sootheRound.value += 1
  sootheDone.value = []
}

/** 标记「做了」只就地置灰，不轮换——否则条目会在手指底下消失 */
function markSootheDone(action: SootheAction) {
  sootheLog.value = [...sootheLog.value, { id: action.id, at: new Date().toISOString() }]
  persistSootheLog()
  if (!sootheDone.value.includes(action.id)) sootheDone.value = [...sootheDone.value, action.id]
}

function jumpSoothe(action: SootheAction) {
  const selector = SOOTHE_ANCHORS[action.target]
  if (!selector) return
  const node = document.querySelector<HTMLElement>(selector)
  node?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  if (action.target === 'chat') {
    window.setTimeout(() => node?.querySelector('input')?.focus(), 420)
  }
}

/* ---------- 呼吸练习累计 ---------- */
const BREATH_LOG_KEY = 'zhq-wellbeing-breath-log'
interface BreathLogRow { at: string; pattern: string; minutes: number }

const breathLog = ref<BreathLogRow[]>([])
/** 用户手动选过节奏后，就不再按打卡状态自动改默认值 */
const breathTouched = ref(false)

function readBreathLog(): BreathLogRow[] {
  try {
    const raw = localStorage.getItem(BREATH_LOG_KEY)
    const rows = raw ? (JSON.parse(raw) as BreathLogRow[]) : []
    return Array.isArray(rows) ? rows.filter((row) => row && typeof row.at === 'string') : []
  } catch {
    return []
  }
}

function persistBreathLog() {
  try {
    localStorage.setItem(BREATH_LOG_KEY, JSON.stringify(breathLog.value.slice(-60)))
  } catch {
    // 配额满时只丢历史，不影响本次练习
  }
}

function logBreathSession() {
  const seconds = activePattern.value.stages.reduce((sum, stage) => sum + stage.seconds, 0) * activePattern.value.cycles
  breathLog.value = [
    ...breathLog.value,
    { at: new Date().toISOString(), pattern: activePattern.value.label, minutes: Math.round((seconds / 60) * 10) / 10 },
  ]
  persistBreathLog()
}

const breathSummary = computed(() => {
  const cutoff = Date.now() - 7 * 86400000
  const recent = breathLog.value.filter((row) => {
    const at = new Date(row.at).getTime()
    return Number.isFinite(at) && at >= cutoff
  })
  const minutes = recent.reduce((sum, row) => sum + (Number(row.minutes) || 0), 0)
  return { count: recent.length, minutes: Math.round(minutes * 10) / 10, total: breathLog.value.length }
})

/** 读一次 mood_history，趋势和热力图共用，不重复请求。 */
async function fetchMoodHistory() {
  moodLoading.value = true
  moodError.value = ''
  try {
    const result = await command('wellbeing', 'mood_history', '', { days: MOOD_WINDOW_DAYS })
    const items = result.data.items
    moodHistory.value = Array.isArray(items)
      ? (items as MoodPoint[]).filter((item) => item && typeof item.checked_at === 'string')
      : []
    // 按最近一次打卡自动选呼吸节奏：低落给 4-7-8，轻松给均匀，其余方箱
    const latest = moodHistory.value[moodHistory.value.length - 1]
    if (!breathTouched.value && latest) {
      breathPatternId.value = latest.weather === 'rainy' || latest.weather === 'stormy'
        ? '478'
        : latest.weather === 'sunny' ? 'even' : 'box'
    }
  } catch (reason) {
    moodHistory.value = []
    moodError.value = reason instanceof Error ? reason.message : '心情记录暂时读不到'
  } finally {
    moodLoading.value = false
    moodLoaded.value = true
  }
}

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
    // 后端算出了「建议预约 / 需要人工关怀」，之前这两个字段被丢掉了，现在接到界面上
    bookingSuggested.value = Boolean(result.data.booking_suggested)
    followUpRequested.value = Boolean(result.data.human_follow_up_requested)
    bookingSlot.value = ''
    bookingNote.value = ''
    bookingNotice.value = ''
    bookingDone.value = false
    // 刚打完卡就让趋势跟上；fetchMoodHistory 自带 try/catch，不会反过来影响打卡结果。
    await fetchMoodHistory()
    // 拿刷新后的数据做「照镜子」对比
    buildInsight()
    // 心情变化后疏导建议也要跟着重算
    void fetchSoothe()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '记录失败，请稍后再试。'
  } finally { loading.value = false }
}

// ---------- 日记「那年今日」 ----------
const JOURNAL_DAYS_KEY = 'zhq-private-journal-days'
const JOURNAL_KEEP_DAYS = 30

/** 读回按日期归档的日记；坏数据当作没有，不让它卡住整页。 */
function readJournalDays(): Record<string, string> {
  try {
    const raw = localStorage.getItem(JOURNAL_DAYS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const days: Record<string, string> = {}
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === 'string' && value.trim()) days[key] = value
    }
    return days
  } catch {
    return {}
  }
}

function saveJournal() {
  writeStoredText('zhq-private-journal', journal.value)
  // 顺手留一份按日期归档的副本，七天后「那年今日」才有东西可对照。
  try {
    if (journal.value.trim()) {
      const days = readJournalDays()
      days[localDateKey(new Date())] = journal.value
      const keys = Object.keys(days).sort()
      for (const key of keys.slice(0, Math.max(0, keys.length - JOURNAL_KEEP_DAYS))) delete days[key]
      writeStoredText(JOURNAL_DAYS_KEY, JSON.stringify(days))
    }
  } catch {
    // 归档失败不影响本次保存
  }
  journalSaved.value = true
  window.setTimeout(() => { journalSaved.value = false }, 1800)
}

const journalMemory = ref('')
const journalMemoryDate = ref('')

/** 找出 7 天前同一天写的日记；没有就整块不渲染。 */
function loadJournalMemory() {
  try {
    const target = new Date()
    target.setHours(0, 0, 0, 0)
    target.setDate(target.getDate() - 7)
    const key = localDateKey(target)
    const text = (readJournalDays()[key] ?? '').trim()
    journalMemory.value = text
    journalMemoryDate.value = text ? key : ''
  } catch {
    journalMemory.value = ''
    journalMemoryDate.value = ''
  }
}

const journalMemoryPreview = computed(() => (
  journalMemory.value.length > 90 ? `${journalMemory.value.slice(0, 90)}…` : journalMemory.value
))

/** 首次进入时把已有日记补记到今天，否则七天后没有可对照的存档。 */
function seedJournalToday() {
  try {
    if (!journal.value.trim()) return
    const days = readJournalDays()
    const key = localDateKey(new Date())
    if (days[key]) return
    days[key] = journal.value
    writeStoredText(JOURNAL_DAYS_KEY, JSON.stringify(days))
  } catch {
    // 存档失败不阻塞页面
  }
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

// ---------- 呼吸多节奏 ----------

const activePattern = computed(() => breathPatterns.find((pattern) => pattern.id === breathPatternId.value) ?? breathPatterns[0])

const activeStage = computed<BreathStage>(() => {
  const stages = activePattern.value.stages
  return stages[Math.min(breathStageIndex.value, stages.length - 1)]
})

/** 圆环进度：当前阶段已经走过的比例，0..1，交给 CSS 的 conic-gradient 用。 */
const breathProgress = computed(() => {
  const total = activeStage.value.seconds * 1000
  return total > 0 ? Math.min(1, Math.max(0, breathStageElapsed.value / total)) : 0
})

const breathCountdown = computed(() => Math.max(1, Math.ceil((activeStage.value.seconds * 1000 - breathStageElapsed.value) / 1000)))

const breathPhaseLabel = computed(() => {
  if (breathDone.value) return '完成'
  if (!breathing.value && breathStageElapsed.value === 0 && breathCycle.value === 0) return '准备'
  return activeStage.value.kind === 'inhale' ? '吸气' : activeStage.value.kind === 'hold' ? '屏住' : '呼气'
})

const breathRoundLabel = computed(() => (
  breathDone.value
    ? '这一轮结束了'
    : `第 ${Math.min(breathCycle.value + 1, activePattern.value.cycles)} / ${activePattern.value.cycles} 轮`
))

const breathHint = computed(() => {
  if (breathDone.value) return '慢慢回到当下的感觉，需要时再来一轮。'
  if (!breathing.value && breathStageElapsed.value === 0 && breathCycle.value === 0) return activePattern.value.hint
  if (!breathing.value) return '已暂停，随时可以继续。'
  return `跟着圆环走：${breathPhaseLabel.value} ${breathCountdown.value} 秒`
})

function clearBreathTimer() {
  if (breathTimer !== undefined) {
    window.clearInterval(breathTimer)
    breathTimer = undefined
  }
}

function resetBreathSession() {
  clearBreathTimer()
  breathing.value = false
  breathDone.value = false
  breathStageIndex.value = 0
  breathStageElapsed.value = 0
  breathCycle.value = 0
}

/** 每 100ms 推进一次，跨过阶段末尾就换阶段，走完所有轮次自动收尾。 */
function tickBreathing() {
  breathStageElapsed.value += BREATH_TICK_MS
  if (breathStageElapsed.value < activeStage.value.seconds * 1000) return
  breathStageElapsed.value = 0
  if (breathStageIndex.value + 1 < activePattern.value.stages.length) {
    breathStageIndex.value += 1
    return
  }
  breathStageIndex.value = 0
  breathCycle.value += 1
  if (breathCycle.value >= activePattern.value.cycles) {
    clearBreathTimer()
    breathing.value = false
    breathDone.value = true
    logBreathSession()
  }
}

function toggleBreathing() {
  if (breathing.value) {
    clearBreathTimer()
    breathing.value = false
    return
  }
  if (breathDone.value) resetBreathSession()
  clearBreathTimer()
  breathing.value = true
  breathTimer = window.setInterval(tickBreathing, BREATH_TICK_MS)
}

function selectBreathPattern(id: string) {
  if (breathPatternId.value === id) return
  breathPatternId.value = id
  breathTouched.value = true
  resetBreathSession()
}

// 辅导员功能
async function fetchAlerts() {
  if (!isStaff.value) return
  try {
    const result = await command('wellbeing', 'list_alerts')
    alerts.value = (result.data.alerts ?? []) as AlertItem[]
  } catch { alerts.value = [] }
}

/** 学生主动约的谈心：辅导员侧能看到，和系统判定的预警分开列。 */
async function fetchBookings() {
  if (!isStaff.value) return
  try {
    const result = await command('wellbeing', 'list_bookings')
    bookings.value = (result.data.bookings ?? []) as BookingItem[]
  } catch { bookings.value = [] }
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
  breathLog.value = readBreathLog()
  sootheLog.value = readSootheLog()
  if (isStudent.value) {
    // 趋势和热力图共用这一次请求；日记存档在本地，读不到就整块不渲染。
    fetchMoodHistory()
    fetchSoothe()
    seedJournalToday()
    loadJournalMemory()
    void loadSelfCheck()
  }
  if (isStaff.value) {
    fetchAlerts()
    fetchBookings()
    const stored = readStoredText('zhq-talk-ledger')
    if (stored) {
      try {
        talkEntries.value = JSON.parse(stored)
      } catch {
        talkEntries.value = []
      }
    }
  }
})

onBeforeUnmount(() => clearBreathTimer())
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
      <!-- 独立聊天面板：进页面由小齐先说第一句 -->
      <GuideChat />
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

        <!-- 打卡后的「照镜子」：对比上次 / 本周分布 / 最该注意的 -->
        <div v-if="insight" class="wbx-insight">
          <p class="wbx-insight-row"><span>对比上次</span>{{ insight.compare }}</p>
          <p class="wbx-insight-row"><span>本周分布</span>{{ insight.spread }}</p>
          <p class="wbx-insight-row is-focus"><span>值得注意</span>{{ insight.focus }}</p>
        </div>

        <!-- 后端判定「建议预约」时才出现：橙/红等级 -->
        <div v-if="bookingSuggested" class="wbx-booking" :class="{ 'is-urgent': followUpRequested }">
          <header>
            <strong>{{ followUpRequested ? '已发出人工关怀提醒' : '建议约一次谈心' }}</strong>
            <span v-if="followUpRequested">辅导员会主动联系你</span>
            <span v-else>选一个时段，辅导员会在谈心台账里看到</span>
          </header>
          <div v-if="!bookingDone" class="wbx-booking-body">
            <div class="wbx-booking-slots">
              <button
                v-for="slot in bookingSlots"
                :key="slot"
                type="button"
                :class="{ chosen: bookingSlot === slot }"
                @click="bookingSlot = slot"
              >{{ slot }}</button>
            </div>
            <label class="wbx-booking-note">
              <span>想聊什么（可选）</span>
              <input v-model="bookingNote" maxlength="200" placeholder="例如：最近复习压力有点大">
            </label>
            <button type="button" class="wbx-booking-submit" @click="requestBooking">提交预约</button>
          </div>
          <p class="wbx-booking-result">{{ bookingNotice }}</p>
        </div>

        <p v-if="error" class="inline-error">{{ error }}</p>
      </article>

      <!-- 心情不好时的疏导动作：三组各推一条，可换一批、可标记做过、可跳到对应板块 -->
      <article v-if="isStudent && sootheShow && soothePicks.length" class="wbx-soothe">
        <header class="wbx-soothe-head">
          <div><PhHeart :size="22" weight="duotone" /><h2>现在可以先做一件</h2></div>
          <div class="wbx-soothe-actions">
            <span v-if="sootheWeekCount" class="wbx-soothe-count">本周做过 {{ sootheWeekCount }} 次</span>
            <button type="button" class="wbx-ghost-btn" @click="rotateSoothe">换一批</button>
          </div>
        </header>
        <p class="wbx-soothe-hint">情绪越压反弹越强，先让它有个出口，缓解才有落脚的地方。挑一件就够，不用都做。</p>
        <ul class="wbx-soothe-list">
          <li v-for="pick in soothePicks" :key="pick.action.id">
            <span class="wbx-soothe-group">{{ pick.label }}</span>
            <div class="wbx-soothe-body">
              <strong>{{ pick.action.title }}</strong>
              <p>{{ pick.action.detail }}</p>
              <small>{{ pick.action.why }}</small>
              <div class="wbx-soothe-buttons">
                <button v-if="pick.action.target" type="button" class="wbx-mini-btn" @click="jumpSoothe(pick.action)">
                  去这里
                </button>
                <button
                  type="button"
                  class="wbx-mini-btn is-done"
                  :class="{ 'is-marked': sootheDone.includes(pick.action.id) }"
                  :disabled="sootheDone.includes(pick.action.id)"
                  @click="markSootheDone(pick.action)"
                >{{ sootheDone.includes(pick.action.id) ? '已做过' : '做了' }}</button>
              </div>
            </div>
          </li>
        </ul>
      </article>

      <!-- 4 题极简自评：PHQ-2 + GAD-2，只提示要不要找专业人聊，不做诊断 -->
      <article class="wbx-selfcheck">
        <header class="wbx-card-head">
          <div><PhClipboardText :size="22" weight="duotone" /><h2>四道题，看看要不要找人聊聊</h2></div>
          <span class="wbx-selfcheck-window">{{ selfCheckMeta?.window ?? '最近两周' }}</span>
        </header>

        <template v-if="!selfCheckResult">
          <p class="wbx-selfcheck-hint">
            PHQ-2 与 GAD-2 是高校心理普测里常用的超短筛查工具。答案只进你自己的记录，辅导员看不到题目和选项。
          </p>
          <p v-if="!selfCheckMeta" class="wbx-note">{{ selfCheckNotice || '正在读取题目…' }}</p>
          <ul v-else class="wbx-selfcheck-list">
            <li v-for="(item, index) in selfCheckMeta.items" :key="item.id">
              <p class="wbx-selfcheck-q"><b>{{ index + 1 }}</b>{{ item.text }}</p>
              <div class="wbx-selfcheck-options">
                <button
                  v-for="option in selfCheckMeta.options"
                  :key="option.value"
                  type="button"
                  :class="{ chosen: selfCheckAnswers[item.id] === option.value }"
                  @click="pickSelfCheck(item.id, option.value)"
                >{{ option.label }}</button>
              </div>
            </li>
          </ul>
          <div v-if="selfCheckMeta" class="wbx-selfcheck-foot">
            <button
              type="button"
              class="wbx-selfcheck-submit"
              :disabled="selfCheckBusy || !selfCheckReady"
              @click="submitSelfCheck"
            >{{ selfCheckBusy ? '正在算…' : '看结果' }}</button>
            <span>{{ Object.keys(selfCheckAnswers).length }} / {{ selfCheckMeta.items.length }} 题已选</span>
          </div>
          <p class="wbx-selfcheck-note">{{ selfCheckMeta?.disclaimer ?? '这是筛查工具，不是诊断。' }}</p>
        </template>

        <template v-else>
          <div class="wbx-selfcheck-result" :class="`is-${selfCheckResult.level}`">
            <strong>{{ selfCheckResult.advice }}</strong>
            <div class="wbx-selfcheck-scores">
              <span>情绪 {{ selfCheckResult.phq2 }} / 6</span>
              <span>紧张担忧 {{ selfCheckResult.gad2 }} / 6</span>
              <span>合计 {{ selfCheckResult.total }} / 12</span>
            </div>
          </div>
          <p v-if="selfCheckResult.recommend_booking" class="wbx-selfcheck-hotline">
            现在就能约：<b>学校心理中心</b>；夜里不方便的话可以打 {{ selfCheckResult.hotline }}。
          </p>
          <p class="wbx-selfcheck-note">{{ selfCheckResult.disclaimer }}</p>
          <div class="wbx-selfcheck-foot">
            <button type="button" class="wbx-selfcheck-submit" @click="resetSelfCheck">再测一次</button>
          </div>
        </template>
      </article>

      <!-- 学生专属：情绪复盘（原来的「走势图 + 心情日历」是同一份数据的两种画法，合并成一块） -->
      <article v-if="isStudent" class="wbx-review-card">
        <header class="wbx-card-head">
          <div><PhChartLine :size="22" weight="duotone" /><h2>这一周的情绪复盘</h2></div>
          <button type="button" class="wbx-ghost-btn" :disabled="moodLoading" @click="fetchMoodHistory">
            {{ moodLoading ? '读取中' : '刷新' }}
          </button>
        </header>

        <p v-if="!moodLoaded" class="wbx-note">正在读取最近 7 天的心情记录…</p>
        <p v-else-if="moodError" class="wbx-note">趋势暂时读不到：{{ moodError }}</p>
        <template v-else>
          <div class="wbx-trend-plot">
            <svg viewBox="0 0 320 140" role="img" aria-label="最近 7 天情绪走势折线图">
              <defs>
                <linearGradient id="wbxTrendFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#397f72" stop-opacity="0.26" />
                  <stop offset="100%" stop-color="#397f72" stop-opacity="0" />
                </linearGradient>
              </defs>
              <line
                v-for="guide in trendGuides"
                :key="guide.score"
                class="wbx-trend-guide"
                x1="18" x2="302" :y1="guide.y" :y2="guide.y"
              />
              <polygon v-if="trendArea" class="wbx-trend-area" :points="trendArea" />
              <polyline v-if="trendLine" class="wbx-trend-line" :points="trendLine" />
              <g v-for="(point, index) in trendPoints" :key="point.cell.key">
                <circle
                  class="wbx-trend-hit"
                  :cx="point.x" :cy="point.y" r="11"
                  @mouseenter="moodHover = index"
                  @mouseleave="moodHover = null"
                />
                <circle
                  class="wbx-trend-dot"
                  :cx="point.x" :cy="point.y" :r="moodHover === index ? 6 : 4.5"
                />
              </g>
              <text
                v-for="(cell, index) in calendarCells"
                :key="cell.key"
                class="wbx-trend-axis"
                :x="chartX(index)" y="134"
              >{{ cell.weekday }}</text>
            </svg>
            <div
              v-if="hoverPoint"
              class="wbx-trend-tip"
              :class="{ below: hoverPoint.flip }"
              :style="{ left: hoverPoint.left, top: hoverPoint.top }"
            >
              <strong>{{ hoverPoint.date }} 周{{ hoverPoint.weekday }} · {{ hoverPoint.weatherLabel }}</strong>
              <span>{{ hoverPoint.text }}</span>
            </div>
          </div>

          <!-- 7 天里每个星期几只出现一次，所以做工作日 / 周末对比，而不是按星期聚合 -->
          <div class="wbx-review-split">
            <div class="wbx-review-bar">
              <span>工作日<small>{{ weekdaySplit.workday.count }} 天</small></span>
              <div class="wbx-review-track">
                <i :style="{ width: `${(weekdaySplit.workday.avg / 5) * 100}%` }" />
              </div>
              <em>{{ weekdaySplit.workday.count ? weekdaySplit.workday.avg.toFixed(1) : '—' }}</em>
            </div>
            <div class="wbx-review-bar">
              <span>周末<small>{{ weekdaySplit.weekend.count }} 天</small></span>
              <div class="wbx-review-track">
                <i :class="'is-weekend'" :style="{ width: `${(weekdaySplit.weekend.avg / 5) * 100}%` }" />
              </div>
              <em>{{ weekdaySplit.weekend.count ? weekdaySplit.weekend.avg.toFixed(1) : '—' }}</em>
            </div>
          </div>

          <p class="wbx-review-summary">{{ reviewSummary }}</p>
          <p class="wbx-note">分数只为可视化，不代表心理评估；折线断开的地方就是那天没打卡。</p>
        </template>
      </article>

      <!-- 学生专属：呼吸练习和日记 -->
      <div v-if="isStudent" class="wellbeing-tools">
        <article class="breathing-card wbx-breath-card">
          <div
            class="wbx-breath-ring"
            :class="{ active: breathing }"
            :style="{ '--wbx-progress': breathProgress }"
          >
            <div class="wbx-breath-core">
              <strong>{{ breathPhaseLabel }}</strong>
              <span>{{ breathCountdown }}</span>
              <small>{{ breathRoundLabel }}</small>
            </div>
          </div>
          <div class="wbx-breath-body">
            <PhWind :size="24" weight="duotone" /><h2>跟着节奏呼吸</h2>
            <p>{{ breathHint }}</p>
            <div class="wbx-breath-presets">
              <button
                v-for="pattern in breathPatterns"
                :key="pattern.id"
                type="button"
                :class="{ chosen: pattern.id === breathPatternId }"
                @click="selectBreathPattern(pattern.id)"
              >{{ pattern.label }}</button>
            </div>
            <button type="button" class="wbx-breath-toggle" @click="toggleBreathing">
              {{ breathing ? '暂停' : breathDone ? '再来一轮' : '开始' }}
            </button>
            <p class="wbx-breath-log">
              <template v-if="breathSummary.count">
                本周做了 {{ breathSummary.count }} 次 · 累计 {{ breathSummary.minutes }} 分钟
                <span v-if="breathSummary.total > breathSummary.count">（共 {{ breathSummary.total }} 次）</span>
              </template>
              <template v-else>做完一轮就会记一次，攒够几次能看出自己什么时候最需要它。</template>
            </p>
          </div>
        </article>
        <article class="journal-card">
          <header>
            <div><PhBookOpenText :size="23" weight="duotone" /><h2>只写给自己</h2></div>
            <span><PhLockKey :size="14" /> 仅存本机</span>
          </header>
          <textarea v-model="journal" maxlength="4000" placeholder="不用完整，也不用正确。写下脑海里最响的那句话。"></textarea>
          <button type="button" @click="saveJournal">{{ journalSaved ? '已经保存' : '保存私人片段' }}</button>
          <aside v-if="journalMemory" class="wbx-journal-echo">
            <small>{{ journalMemoryDate }} · 那年今日</small>
            <p>7 天前的今天你写道：{{ journalMemoryPreview }}</p>
          </aside>
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

        <!-- 学生主动约的谈心：和系统判定的预警分开列，避免把「求助」当「风险」 -->
        <div v-if="bookings.length" class="wbx-booking-queue">
          <p class="wbx-booking-queue-head">学生主动预约（{{ bookings.length }}）</p>
          <ul>
            <li v-for="row in bookings" :key="row.booking_id">
              <span class="wbx-booking-slot">{{ row.slot }}</span>
              <span class="wbx-booking-user">{{ row.user_id }}</span>
              <span v-if="row.alert_level" class="wbx-booking-level">{{ row.alert_level }}</span>
              <span v-if="row.note" class="wbx-booking-note-text">{{ row.note }}</span>
            </li>
          </ul>
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
    <LyricStage />
  </section>
</template>

<style scoped>
/* ===== 情绪复盘（原「走势 + 日历」合并） ===== */
.wbx-review-card { margin-top: 20px; padding: 22px; background: var(--paper); border-radius: 20px; box-shadow: var(--shadow); }
.wbx-card-head { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.wbx-card-head > div { display: flex; align-items: center; gap: .5rem; min-width: 0; }
.wbx-card-head h2 { margin: 0; font: 400 1.3rem "LXGW WenKai", cursive; }
.wbx-card-head svg { flex: none; color: var(--green); }
.wbx-badge { flex: none; padding: .25rem .55rem; color: #7c5a1e; background: #fff0c6; border-radius: 8px; font-size: .72rem; font-weight: 750; }
.wbx-ghost-btn { flex: none; padding: .35rem .7rem; color: var(--green); background: var(--green-soft); border: 0; border-radius: 9px; font-size: .78rem; font-weight: 700; }
.wbx-ghost-btn:hover { background: #cfe3d9; }
.wbx-note { margin: .7rem 0 0; color: var(--muted); font-size: .78rem; line-height: 1.65; }

.wbx-trend-plot { position: relative; margin-top: .5rem; }
.wbx-trend-plot svg { display: block; width: 100%; aspect-ratio: 320 / 140; overflow: visible; }
.wbx-trend-guide { stroke: rgba(23, 63, 67, .11); stroke-width: 1; stroke-dasharray: 3 5; }
.wbx-trend-area { fill: url(#wbxTrendFill); }
.wbx-trend-line { fill: none; stroke: var(--green); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.wbx-trend-hit { fill: transparent; cursor: pointer; }
.wbx-trend-dot { fill: var(--paper); stroke: var(--green); stroke-width: 2; pointer-events: none; transition: r .12s ease; }
.wbx-trend-axis { fill: var(--muted); font-size: 9px; text-anchor: middle; }
.wbx-trend-tip {
  position: absolute; z-index: 2; max-width: 190px; padding: .5rem .6rem;
  display: grid; gap: .15rem; pointer-events: none;
  color: #f7fff9; background: rgba(23, 63, 67, .94); border-radius: 10px;
  box-shadow: 0 10px 24px rgba(23, 63, 67, .22);
  transform: translate(-50%, calc(-100% - 10px));
}
.wbx-trend-tip.below { transform: translate(-50%, 12px); }
.wbx-trend-tip strong { font-size: .74rem; font-weight: 700; }
.wbx-trend-tip span { color: #d8e7e2; font-size: .74rem; line-height: 1.5; }

/* 工作日 / 周末对比：7 天窗口里每个星期一只出现一次，按星期聚合是假信号 */
.wbx-review-split { margin-top: .9rem; display: grid; gap: .45rem; }
.wbx-review-bar { display: grid; grid-template-columns: 5.5rem 1fr 2.2rem; align-items: center; gap: .6rem; }
.wbx-review-bar > span { display: grid; color: var(--ink); font-size: .8rem; line-height: 1.25; }
.wbx-review-bar small { color: var(--muted); font-size: .66rem; }
.wbx-review-track { height: 9px; border-radius: 999px; background: rgba(23, 63, 67, .07); overflow: hidden; }
.wbx-review-track i { display: block; height: 100%; border-radius: inherit; background: var(--green); transition: width .3s ease; }
.wbx-review-track i.is-weekend { background: var(--gold); }
.wbx-review-bar em { color: var(--muted); font-size: .78rem; font-style: normal; font-weight: 700; text-align: right; font-variant-numeric: tabular-nums; }
.wbx-review-summary {
  margin: .9rem 0 0; padding: .6rem .75rem;
  color: #24413d; background: var(--green-soft); border-left: 3px solid var(--green);
  border-radius: 0 10px 10px 0; font-size: .84rem; line-height: 1.7;
}

/* ===== 打卡后的「照镜子」 ===== */
.wbx-insight { margin-top: .8rem; display: grid; gap: .3rem; }
.wbx-insight-row { margin: 0; display: grid; grid-template-columns: 4.6rem 1fr; gap: .5rem; color: var(--ink); font-size: .82rem; line-height: 1.65; }
.wbx-insight-row > span { color: var(--muted); font-size: .74rem; font-weight: 700; letter-spacing: .02em; }
.wbx-insight-row.is-focus { padding: .5rem .65rem; background: var(--green-soft); border-radius: 9px; }

/* ===== 主动预约谈心 ===== */
.wbx-booking {
  margin-top: .9rem; padding: .8rem .9rem;
  display: grid; gap: .6rem;
  background: #fff8e8; border: 1px solid rgba(180, 132, 38, .28); border-radius: 13px;
}
.wbx-booking.is-urgent { background: #fdf0ee; border-color: rgba(158, 48, 48, .3); }
.wbx-booking header { display: grid; gap: .15rem; }
.wbx-booking header strong { color: #7c5a1e; font-size: .88rem; }
.wbx-booking.is-urgent header strong { color: #9e3030; }
.wbx-booking header span { color: var(--muted); font-size: .75rem; line-height: 1.55; }
.wbx-booking-body { display: grid; gap: .5rem; }
.wbx-booking-slots { display: flex; flex-wrap: wrap; gap: .4rem; }
.wbx-booking-slots button {
  padding: .35rem .6rem; color: var(--ink); background: #fff;
  border: 1px solid rgba(23, 63, 67, .14); border-radius: 9px;
  font-size: .76rem; font-weight: 650; cursor: pointer;
}
.wbx-booking-slots button:hover { border-color: var(--green); }
.wbx-booking-slots button.chosen { color: #fff; background: var(--green); border-color: var(--green); }
.wbx-booking-note { display: grid; gap: .2rem; }
.wbx-booking-note > span { color: var(--muted); font-size: .72rem; }
.wbx-booking-note input {
  padding: .4rem .55rem; color: var(--ink); background: #fff;
  border: 1px solid rgba(23, 63, 67, .14); border-radius: 9px; font-size: .8rem;
}
.wbx-booking-submit {
  justify-self: start; padding: .42rem .85rem; color: #fff;
  background: var(--navy); border: 0; border-radius: 9px;
  font-size: .8rem; font-weight: 700; cursor: pointer;
}
.wbx-booking-result { margin: 0; color: #2f5c33; font-size: .78rem; line-height: 1.6; }
.wbx-booking-result:empty { display: none; }

/* 辅导员侧：学生主动预约队列 */
.wbx-booking-queue { margin: .9rem 0; padding: .7rem .85rem; background: #fff8e8; border-radius: 12px; }
.wbx-booking-queue-head { margin: 0 0 .45rem; color: #7c5a1e; font-size: .8rem; font-weight: 750; }
.wbx-booking-queue ul { margin: 0; padding: 0; list-style: none; display: grid; gap: .35rem; }
.wbx-booking-queue li { display: flex; flex-wrap: wrap; align-items: baseline; gap: .5rem; font-size: .78rem; }
.wbx-booking-slot { color: var(--ink); font-weight: 700; }
.wbx-booking-user { color: var(--muted); }
.wbx-booking-level { padding: 0 .35rem; color: #9e3030; background: rgba(158, 48, 48, .1); border-radius: 6px; font-size: .68rem; font-weight: 700; }
.wbx-booking-note-text { color: #4d625f; font-size: .76rem; }

/* ===== 心情不好时的疏导动作 ===== */
.wbx-soothe {
  margin-top: 20px; padding: 20px 22px;
  background: var(--paper); border-radius: 20px; box-shadow: var(--shadow);
  border-left: 4px solid var(--gold);
}
.wbx-soothe-head { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
.wbx-soothe-head > div:first-child { display: flex; align-items: center; gap: .5rem; min-width: 0; }
.wbx-soothe-head svg { flex: none; color: var(--gold); }
.wbx-soothe-head h2 { margin: 0; font: 400 1.3rem "LXGW WenKai", cursive; }
.wbx-soothe-actions { display: flex; align-items: center; gap: .5rem; flex: none; }
.wbx-soothe-count { color: var(--muted); font-size: .74rem; font-variant-numeric: tabular-nums; }
.wbx-soothe-hint { margin: .5rem 0 0; color: var(--muted); font-size: .8rem; line-height: 1.7; }
.wbx-soothe-list { margin: .9rem 0 0; padding: 0; list-style: none; display: grid; gap: .6rem; }
.wbx-soothe-list li {
  display: grid; grid-template-columns: 6.2rem 1fr; gap: .7rem;
  padding: .7rem .8rem; border-radius: 12px;
  background: rgba(240, 236, 228, .55);
}
.wbx-soothe-group {
  align-self: start; padding: .2rem .45rem;
  color: #7c5a1e; background: #fff0c6; border-radius: 7px;
  font-size: .68rem; font-weight: 750; line-height: 1.5; text-align: center;
}
.wbx-soothe-body { min-width: 0; display: grid; gap: .18rem; }
.wbx-soothe-body strong { color: var(--ink); font-size: .88rem; }
.wbx-soothe-body p { margin: 0; color: #4d625f; font-size: .8rem; line-height: 1.65; }
.wbx-soothe-body small { color: var(--muted); font-size: .74rem; line-height: 1.6; }
.wbx-soothe-buttons { display: flex; gap: .4rem; margin-top: .35rem; }
.wbx-mini-btn {
  padding: .26rem .6rem; color: var(--green); background: var(--green-soft);
  border: 1px solid transparent; border-radius: 8px;
  font-size: .74rem; font-weight: 700; cursor: pointer;
}
.wbx-mini-btn:hover { border-color: var(--green); }
.wbx-mini-btn.is-done { color: #fff; background: var(--green); }
.wbx-mini-btn.is-done:hover { background: #2f6b60; }
.wbx-mini-btn.is-marked,
.wbx-mini-btn.is-marked:disabled {
  color: var(--muted); background: rgba(23, 63, 67, .07); cursor: default;
}

/* ===== 呼吸多节奏 ===== */
.wbx-breath-card { align-items: flex-start; }
.wbx-breath-ring {
  --wbx-progress: 0;
  position: relative; flex: 0 0 118px; width: 118px; height: 118px;
  display: grid; place-items: center; border-radius: 50%;
  background: conic-gradient(#397f72 calc(var(--wbx-progress) * 360deg), rgba(57, 127, 114, .16) 0);
  transition: background .12s linear;
}
.wbx-breath-core {
  width: 92px; height: 92px;
  display: grid; place-content: center; justify-items: center; gap: .05rem; text-align: center;
  background: #f7fbf8; border-radius: 50%;
  box-shadow: inset 0 0 0 1px rgba(57, 127, 114, .16);
  transition: box-shadow .2s ease;
}
.wbx-breath-core strong { color: var(--navy); font: 400 1.02rem "LXGW WenKai", cursive; }
.wbx-breath-core span { color: var(--green); font-size: 1.28rem; font-weight: 800; line-height: 1; }
.wbx-breath-core small { color: var(--muted); font-size: .62rem; }
.wbx-breath-ring.active .wbx-breath-core { box-shadow: inset 0 0 0 1px rgba(57, 127, 114, .32), 0 0 0 6px rgba(57, 127, 114, .09); }

.wbx-breath-body { min-width: 0; display: grid; justify-items: start; }
.wbx-breath-body h2 { margin: .35rem 0 .2rem; font: 400 1.3rem "LXGW WenKai", cursive; }
.wbx-breath-body p { margin: 0 0 .6rem; color: var(--muted); font-size: .82rem; line-height: 1.6; }
.wbx-breath-presets { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: .65rem; }
.wbx-breath-presets button {
  padding: .38rem .6rem;
  color: var(--navy); background: rgba(255, 255, 255, .72);
  border: 1px solid rgba(57, 127, 114, .24); border-radius: 9px;
  font-size: .76rem; font-weight: 700;
}
.wbx-breath-presets button:hover { background: #fff; }
.wbx-breath-presets button.chosen { color: #fff; background: var(--green); border-color: var(--green); }
.wbx-breath-body .wbx-breath-toggle {
  padding: .5rem .85rem;
  color: #fff; background: var(--navy); border: 0; border-radius: 9px; font-weight: 750;
}
.wbx-breath-body .wbx-breath-toggle:hover { background: #0f3235; }
.wbx-breath-log { margin: .55rem 0 0; color: var(--muted); font-size: .74rem; line-height: 1.6; }
.wbx-breath-log span { color: #8a9994; }

/* ===== 日记「那年今日」 ===== */
.wbx-journal-echo {
  margin-top: .7rem; padding: .65rem .8rem;
  background: #f7f3e6; border-left: 3px solid var(--gold); border-radius: 0 10px 10px 0;
}
.wbx-journal-echo small { color: #8a7433; font-size: .7rem; font-weight: 700; }
.wbx-journal-echo p { margin: .2rem 0 0; color: #5c5340; font-size: .8rem; line-height: 1.65; }

/* ===== 4 题极简自评 ===== */
.wbx-selfcheck {
  padding: 20px 22px;
  background: var(--paper);
  border-radius: 16px;
  box-shadow: var(--shadow);
}
.wbx-selfcheck-window {
  padding: .15rem .6rem; border-radius: 999px;
  background: rgba(47,74,69,.08); color: #5d726c; font-size: .72rem; font-weight: 700;
}
.wbx-selfcheck-hint {
  margin: .5rem 0 0; color: #6d7d78; font-size: .8rem; line-height: 1.7;
}
.wbx-selfcheck-list { display: grid; gap: .85rem; margin: .9rem 0 0; padding: 0; list-style: none; }
.wbx-selfcheck-q {
  display: flex; align-items: flex-start; gap: .45rem;
  margin: 0 0 .4rem; color: var(--ink); font-size: .86rem; line-height: 1.6;
}
.wbx-selfcheck-q b {
  flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center;
  width: 1.15rem; height: 1.15rem; margin-top: .1rem; border-radius: 50%;
  background: rgba(47,122,82,.12); color: #2f7a52; font-size: .7rem;
}
.wbx-selfcheck-options { display: flex; flex-wrap: wrap; gap: .35rem; padding-left: 1.6rem; }
.wbx-selfcheck-options button {
  padding: .3rem .7rem; border: 1px solid rgba(47,74,69,.16); border-radius: 999px;
  background: transparent; color: #5d726c; font-size: .76rem; font-family: inherit; cursor: pointer;
}
.wbx-selfcheck-options button:hover { border-color: rgba(47,122,82,.4); color: #2f7a52; }
.wbx-selfcheck-options button.chosen {
  border-color: #2f7a52; background: rgba(47,122,82,.12); color: #2f7a52; font-weight: 700;
}
.wbx-selfcheck-foot {
  display: flex; align-items: center; gap: .7rem; margin-top: 1rem;
  color: #8a9994; font-size: .75rem;
}
.wbx-selfcheck-submit {
  padding: .45rem 1.1rem; border: none; border-radius: 10px;
  background: #2f7a52; color: #fff; font-size: .82rem; font-family: inherit; cursor: pointer;
}
.wbx-selfcheck-submit:disabled { opacity: .55; cursor: default; }
.wbx-selfcheck-note { margin: .7rem 0 0; color: #a8b3af; font-size: .72rem; line-height: 1.65; }
.wbx-selfcheck-result {
  margin-top: .8rem; padding: .8rem .9rem;
  border-left: 3px solid #2f7a52; border-radius: 0 10px 10px 0;
  background: rgba(47,122,82,.07);
}
.wbx-selfcheck-result.is-yellow {
  border-left-color: #c98a2b; background: rgba(201,138,43,.09);
}
.wbx-selfcheck-result.is-orange {
  border-left-color: #b84a30; background: rgba(184,74,48,.08);
}
.wbx-selfcheck-result strong { display: block; color: var(--ink); font-size: .86rem; line-height: 1.7; }
.wbx-selfcheck-scores {
  display: flex; flex-wrap: wrap; gap: .5rem; margin-top: .5rem;
  color: #6d7d78; font-size: .74rem;
}
.wbx-selfcheck-scores span {
  padding: .1rem .5rem; border-radius: 999px; background: rgba(255,255,255,.7);
}
.wbx-selfcheck-hotline {
  margin: .7rem 0 0; padding: .55rem .8rem; border-radius: 9px;
  background: rgba(184,74,48,.07); color: #8c1d17; font-size: .78rem; line-height: 1.7;
}

@media (max-width: 720px) {
  .wbx-breath-card { align-items: center; }
  .wbx-review-bar { grid-template-columns: 4.6rem 1fr 1.8rem; }
  .wbx-insight-row { grid-template-columns: 1fr; gap: .1rem; }
}
</style>