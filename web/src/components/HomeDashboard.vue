<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  PhArrowRight,
  PhCalendarDots,
  PhCheckCircle,
  PhCircle,
  PhClock,
  PhGraduationCap,
  PhHeart,
  PhListChecks,
  PhStar,
} from '@phosphor-icons/vue'
import { command, requestJson } from '../api'
import { useIdentity } from '../identity'

const router = useRouter()
const { identity } = useIdentity()

const greeting = ref('需要聊聊、整理日程或准备复试，都可以从这里开始。')
const loading = ref(false)
const error = ref('')

const now = ref(new Date())
/** 只在跨天时更新：驾驶舱里所有「今天」的判断都挂在它上面，避免每秒重算整块。 */
const todayStamp = ref(new Date())
let timer: number | undefined

const weekDays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
const weekDaysEn = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
const months = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
const monthsEn = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

/** 课表 / 计划里的星期一律用中文「周一…周日」；顺序与后端 _WEEKDAYS 一致。 */
const WEEK_ORDER = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
/** 与 points_service.LEVELS 保持一致的等级阶梯。 */
const LEVEL_LADDER = [
  { name: '新手', min: 0 },
  { name: '入门', min: 100 },
  { name: '进阶', min: 300 },
  { name: '熟练', min: 500 },
  { name: '精通', min: 1000 },
  { name: '大师', min: 2000 },
]
const PLAN_STORAGE_KEY = 'zhq-study-plan-v2'

interface TimetableEvent {
  title: string
  starts_at?: string
  ends_at?: string
  location?: string
  day_of_week?: string
  teacher?: string
}

interface PointsUser {
  user_id?: string
  total_points?: number
  level?: string
  badges?: string[]
}

interface HappyShare {
  share_id?: string
  id?: string
  author_id?: string
  author_name?: string
  content: string
  cheer_count?: number
  created_at?: string
}

interface PlanTask { title?: string; minutes?: number; kind?: string }
interface PlanDay { day?: string; date?: string; focus?: string; minutes?: number; tasks?: PlanTask[] }
interface StudyPlan {
  week_start?: string
  week_end?: string
  total_minutes?: number
  summary?: string
  days?: PlanDay[]
  checkpoint?: string
}

// ---------------------------------------------------------------- 时间工具

function pad2(value: number): string {
  return value.toString().padStart(2, '0')
}

function formatTime(date: Date): string {
  const hours = date.getHours().toString().padStart(2, '0')
  const minutes = date.getMinutes().toString().padStart(2, '0')
  return `${hours}:${minutes}`
}

function formatDate(date: Date) {
  return {
    day: date.getDate().toString(),
    month: months[date.getMonth()],
    monthEn: monthsEn[date.getMonth()],
    weekDay: weekDays[date.getDay()],
    weekDayEn: weekDaysEn[date.getDay()],
    year: date.getFullYear().toString()
  }
}

/** 本地日期键：2026-11-14。用于「今天」的跨天判断与分享归属判断。 */
function isoDayKey(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`
}

/** 学习计划里 day.date 的格式是 %m-%d（如 11-14），必须同格式才能对齐 done 的键。 */
function monthDayKey(date: Date): string {
  return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`
}

/**
 * 从 "2026-09-01T10:10:00" 这类无时区字符串里直接抠时分。
 * 不用 new Date()：课表里 starts_at 的日期是历史锚点（全是 2026-09-01），
 * 一旦走时区换算就会把「周五」的课算到别的日子上。
 */
function clockParts(value?: string): { clock: string; minutes: number } {
  if (!value) return { clock: '', minutes: -1 }
  const matched = String(value).match(/(\d{1,2}):(\d{2})/)
  if (!matched) return { clock: '', minutes: -1 }
  const hours = Number(matched[1])
  const minutes = Number(matched[2])
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return { clock: '', minutes: -1 }
  return { clock: `${pad2(hours)}:${pad2(minutes)}`, minutes: hours * 60 + minutes }
}

/** 星期归一：'周一' / '星期一' / '礼拜一' / '1' 都能落到「周一…周日」。 */
function normalizeWeekday(raw?: string): string | null {
  if (raw === undefined || raw === null) return null
  const text = String(raw).trim()
  if (!text) return null
  if (/^[1-7]$/.test(text)) return WEEK_ORDER[Number(text) - 1]
  const unified = text.replace(/^(星期|礼拜)/, '周')
  return WEEK_ORDER.includes(unified) ? unified : null
}

function getGreeting(date: Date): string {
  const hour = date.getHours()
  if (hour < 6) return '夜深了，注意休息'
  if (hour < 9) return '早上好'
  if (hour < 12) return '上午好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  if (hour < 22) return '晚上好'
  return '夜深了，注意休息'
}

const capabilities = [
  { path: '/wellbeing', no: '01', title: '记录心情', detail: '心情打卡、环境音与辅导员寄语', status: '可用' },
  { path: '/dormitory', no: '02', title: '协调宿舍', detail: '课表导入、AA 分摊、值日冲突', status: '可用' },
  { path: '/academic', no: '03', title: '准备复试', detail: '模拟提问、五维评估、笔记整理', status: '可用' },
  { path: '/innovation', no: '04', title: '推进竞赛', detail: '赛事提交、组队匹配、申报大纲', status: '可用' },
]

async function wakeGuide() {
  loading.value = true
  error.value = ''
  try {
    greeting.value = (await command('wellbeing', 'greeting')).message
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法连接后端服务'
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------- 今日锚点

const dayKey = computed(() => isoDayKey(todayStamp.value))
const todayWeekday = computed(() => weekDays[todayStamp.value.getDay()])
const todayMmDd = computed(() => monthDayKey(todayStamp.value))
const nowMinutes = computed(() => now.value.getHours() * 60 + now.value.getMinutes())

// ---------------------------------------------------------------- 数据源 1：今天课程

const courses = ref<TimetableEvent[]>([])
const coursesState = ref<'loading' | 'ready' | 'error'>('loading')

async function loadCourses() {
  try {
    const result = await requestJson<{ success?: boolean; events?: TimetableEvent[]; message?: string }>(
      '/api/v1/timetable/saved', {}, '课表读取失败')
    courses.value = Array.isArray(result?.events) ? result.events : []
    coursesState.value = 'ready'
  } catch {
    // 没导入过课表时后端也返回 200 + 空数组，走到这里就是真的读不到。
    courses.value = []
    coursesState.value = 'error'
  }
}

interface TodayCourse { title: string; clock: string; minutes: number; endMinutes: number; location: string }

/**
 * 只按 day_of_week 过滤。starts_at 里的日期是 2026-09-01 的历史锚点，
 * 用它推星期会把所有课都算到同一天，所以这里刻意不碰 new Date(starts_at)。
 */
const todayCourses = computed<TodayCourse[]>(() => {
  const weekday = todayWeekday.value
  const list: TodayCourse[] = []
  for (const event of courses.value) {
    if (!event || typeof event.title !== 'string' || !event.title.trim()) continue
    if (normalizeWeekday(event.day_of_week) !== weekday) continue
    const start = clockParts(event.starts_at)
    const end = clockParts(event.ends_at)
    list.push({
      title: event.title,
      clock: start.clock,
      minutes: start.minutes,
      endMinutes: end.minutes > start.minutes ? end.minutes : start.minutes + 45,
      location: typeof event.location === 'string' ? event.location : '',
    })
  }
  return list.sort((a, b) => a.minutes - b.minutes)
})

/** 一周有多少节有效课程：day_of_week 认不出来的一律不计，宁可少算也不按锚点日期瞎猜。 */
const weekCourseCount = computed(() => {
  let count = 0
  for (const event of courses.value) {
    if (!event || typeof event.title !== 'string' || !event.title.trim()) continue
    if (!normalizeWeekday(event.day_of_week)) continue
    count += 1
  }
  return count
})

// ---------------------------------------------------------------- 数据源 2：积分等级

const pointsUser = ref<PointsUser | null>(null)
const pointsState = ref<'loading' | 'ready' | 'error'>('loading')

async function loadPoints() {
  try {
    const userId = identity.value.userId || 'demo-student'
    const result = await requestJson<{ success?: boolean; data?: { user?: PointsUser | null } }>(
      `/api/v1/points/user/${encodeURIComponent(userId)}`, {}, '积分读取失败')
    pointsUser.value = result?.data?.user ?? null
    pointsState.value = 'ready'
  } catch {
    pointsUser.value = null
    pointsState.value = 'error'
  }
}

function levelOf(total: number) {
  let index = 0
  for (let cursor = 0; cursor < LEVEL_LADDER.length; cursor += 1) {
    if (total >= LEVEL_LADDER[cursor].min) index = cursor
  }
  return { current: LEVEL_LADDER[index], next: LEVEL_LADDER[index + 1] ?? null }
}

// ---------------------------------------------------------------- 数据源 3：本周计划（localStorage）

const planData = ref<StudyPlan | null>(null)
const doneMap = ref<Record<string, boolean>>({})
const planNotice = ref('')

function loadPlan() {
  planNotice.value = ''
  try {
    const raw = localStorage.getItem(PLAN_STORAGE_KEY)
    if (!raw) {
      planData.value = null
      doneMap.value = {}
      return
    }
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      planData.value = null
      doneMap.value = {}
      return
    }
    const record = parsed as Record<string, unknown>
    const plan = record.plan
    planData.value = plan && typeof plan === 'object' && !Array.isArray(plan) ? (plan as StudyPlan) : null
    const storedDone = record.done
    doneMap.value = storedDone && typeof storedDone === 'object' && !Array.isArray(storedDone)
      ? { ...(storedDone as Record<string, boolean>) }
      : {}
  } catch {
    // 旧版本或损坏的缓存直接当作没有计划，不让整页崩掉。
    planData.value = null
    doneMap.value = {}
  }
}

/**
 * 只改 done 字段，其余（goal/hours/major/deadline/weak/plan）原样写回，
 * 这样学习计划页读到的结构与它自己 persist() 写出来的完全一致。
 */
function writeStoredDone(done: Record<string, boolean>): boolean {
  try {
    const raw = localStorage.getItem(PLAN_STORAGE_KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : null
    const base = parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? { ...(parsed as Record<string, unknown>) }
      : {}
    base.done = done
    localStorage.setItem(PLAN_STORAGE_KEY, JSON.stringify(base))
    return true
  } catch {
    return false
  }
}

interface DashTask { key: string; title: string; minutes: number; done: boolean }

/** 今天那一格：先按日期精确命中，日期对不上再退回星期（兼容只存了 day 的旧计划）。 */
const todayPlanDay = computed<PlanDay | null>(() => {
  const days = planData.value?.days
  if (!Array.isArray(days) || !days.length) return null
  const byDate = days.find((day) => day && typeof day.date === 'string' && day.date === todayMmDd.value)
  if (byDate) return byDate
  return days.find((day) => day && normalizeWeekday(day.day) === todayWeekday.value) ?? null
})

const todayPlanTasks = computed<DashTask[]>(() => {
  const day = todayPlanDay.value
  const tasks = day?.tasks
  if (!day || !Array.isArray(tasks)) return []
  const date = typeof day.date === 'string' ? day.date : ''
  const list: DashTask[] = []
  for (const task of tasks) {
    if (!task || typeof task.title !== 'string' || !task.title.trim()) continue
    // 与 StudyPlan.vue 的 taskKey() 完全一致：`${day.date}|${task.title}`
    const key = `${date}|${task.title}`
    list.push({
      key,
      title: task.title,
      minutes: typeof task.minutes === 'number' ? task.minutes : 0,
      done: Boolean(doneMap.value[key]),
    })
  }
  return list
})

const todayTasks = computed(() => todayPlanTasks.value.slice(0, 3))
const todayDoneCount = computed(() => todayPlanTasks.value.filter((task) => task.done).length)

function toggleTask(key: string) {
  if (!key) return
  const next: Record<string, boolean> = { ...doneMap.value, [key]: !doneMap.value[key] }
  doneMap.value = next
  planNotice.value = writeStoredDone(next) ? '' : '浏览器存储写不进去，这次勾选只在本次会话有效。'
}

const planStats = computed<{ total: number; done: number; percent: number } | null>(() => {
  const days = planData.value?.days
  if (!Array.isArray(days) || !days.length) return null
  let total = 0
  let done = 0
  for (const day of days) {
    if (!day || !Array.isArray(day.tasks)) continue
    const date = typeof day.date === 'string' ? day.date : ''
    for (const task of day.tasks) {
      if (!task || typeof task.title !== 'string') continue
      total += 1
      if (doneMap.value[`${date}|${task.title}`]) done += 1
    }
  }
  if (!total) return null
  return { total, done, percent: Math.round((done / total) * 100) }
})

// ---------------------------------------------------------------- 数据源 4：美好记录

const shares = ref<HappyShare[]>([])
const sharePick = ref<HappyShare | null>(null)

async function loadShares() {
  try {
    const result = await command('wellbeing', 'happy_shares')
    const raw = result.data?.shares
    const list = Array.isArray(raw) ? (raw as HappyShare[]) : []
    const usable = list.filter((item) => item && typeof item.content === 'string' && item.content.trim())
    shares.value = usable
    sharePick.value = usable.length ? usable[Math.floor(Math.random() * usable.length)] : null
  } catch {
    // 分享墙是可选的锦上添花：读不到就整张卡不渲染，不占位、不报错。
    shares.value = []
    sharePick.value = null
  }
}

interface TodayShare extends HappyShare { clock: string; order: number }

const todayShares = computed<TodayShare[]>(() => {
  const list: TodayShare[] = []
  for (const share of shares.value) {
    if (!share || typeof share.content !== 'string') continue
    if (!share.created_at) continue
    const stamp = new Date(share.created_at)
    if (Number.isNaN(stamp.getTime())) continue
    if (isoDayKey(stamp) !== dayKey.value) continue
    list.push({ ...share, clock: formatTime(stamp), order: stamp.getHours() * 60 + stamp.getMinutes() })
  }
  return list.sort((a, b) => b.order - a.order)
})

// ---------------------------------------------------------------- 驾驶舱指标

const courseMetric = computed(() => {
  if (coursesState.value === 'error') {
    return { value: '—', unit: '', caption: '课表暂时读不到', empty: true }
  }
  if (coursesState.value === 'loading') {
    return { value: '—', unit: '', caption: '正在读今天的课表', empty: true }
  }
  const list = todayCourses.value
  const weekCount = weekCourseCount.value
  if (!list.length) {
    // 周末和空档日不该显示成「0 节」的灰卡，改报本周总量，信息量更大。
    return {
      value: String(weekCount),
      unit: '节',
      caption: weekCount ? `今天没课 · 本周共 ${weekCount} 节` : '课表里还没有课程',
      empty: weekCount === 0,
    }
  }
  const nowAt = nowMinutes.value
  const live = list.find((item) => item.minutes <= nowAt && item.endMinutes > nowAt)
  const next = list.find((item) => item.minutes >= nowAt)
  const focus = live ?? next ?? list[list.length - 1]
  const prefix = live ? '正在上' : next ? '下一节' : '最后一节'
  const where = focus.location ? ` · ${focus.location}` : ''
  const when = focus.clock ? ` ${focus.clock}` : ''
  return {
    value: String(weekCount),
    unit: '节',
    caption: `今天 ${list.length} 节 · ${prefix} ${focus.title}${when}${where}`,
    empty: false,
  }
})

const planMetric = computed(() => {
  const stats = planStats.value
  if (!stats) return { value: '—', unit: '', caption: '还没排本周计划', empty: true }
  return {
    value: `${stats.percent}%`,
    unit: '',
    caption: `${stats.done}/${stats.total} 项完成`,
    empty: false,
  }
})

const pointsMetric = computed(() => {
  if (pointsState.value === 'loading') {
    return { value: '—', unit: '', caption: '正在读积分', empty: true }
  }
  if (pointsState.value === 'error') {
    return { value: '—', unit: '', caption: '积分暂时读不到', empty: true }
  }
  const user = pointsUser.value
  if (!user) {
    // 后端对没有积分记录的用户返回 user: null；不要显示成 0 分。
    return { value: '—', unit: '', caption: '暂无积分记录，去积分中心看看', empty: true }
  }
  const total = Number(user.total_points ?? 0)
  const ladder = levelOf(total)
  const levelName = (user.level ?? '').trim() || ladder.current.name
  const caption = ladder.next
    ? `${levelName} · 距${ladder.next.name}还差 ${Math.max(0, ladder.next.min - total)} 分`
    : `${levelName} · 已经到顶了`
  return { value: total.toLocaleString('zh-CN'), unit: '分', caption, empty: false }
})

const shareMetric = computed(() => {
  const pick = sharePick.value
  if (!pick) return null
  const text = pick.content.trim().replace(/\s+/g, ' ')
  if (!text) return null
  const clipped = text.length > 20 ? `${text.slice(0, 20)}…` : text
  const author = (pick.author_name ?? '').trim() || '同学'
  const cheers = typeof pick.cheer_count === 'number' ? pick.cheer_count : 0
  return {
    value: clipped,
    caption: cheers > 0 ? `${author} · ${cheers} 次鼓励` : author,
  }
})

// ---------------------------------------------------------------- 今日动态轴

interface TimelineItem { id: string; time: string; text: string; kind: 'course' | 'share' | 'plan'; order: number }

const timeline = computed<TimelineItem[]>(() => {
  const items: TimelineItem[] = []

  // id 里带上序号：同一门课同一天可能有多条记录，重复 key 会让 Vue 报警。
  todayCourses.value.forEach((course, index) => {
    items.push({
      id: `course-${index}-${course.clock}-${course.title}`,
      time: course.clock || '今天',
      text: course.location ? `${course.title} · ${course.location}` : course.title,
      kind: 'course',
      order: course.minutes,
    })
  })

  todayShares.value.forEach((share, index) => {
    const content = share.content.trim().replace(/\s+/g, ' ')
    if (!content) return
    const clipped = content.length > 28 ? `${content.slice(0, 28)}…` : content
    const author = (share.author_name ?? '').trim() || '同学'
    const mine = Boolean(share.author_id) && share.author_id === identity.value.userId
    items.push({
      id: `share-${index}-${share.share_id ?? share.id ?? share.clock}`,
      time: share.clock,
      text: mine ? `你记录了：${clipped}` : `${author} 分享了：${clipped}`,
      kind: 'share',
      order: share.order,
    })
  })

  if (todayDoneCount.value > 0) {
    items.push({
      id: 'plan-today',
      time: '今日',
      text: `今天已完成 ${todayDoneCount.value} 项计划`,
      kind: 'plan',
      // 没有具体时刻的汇总条目固定排在最下面。
      order: -1,
    })
  }

  return items.sort((a, b) => b.order - a.order).slice(0, 5)
})

// ---------------------------------------------------------------- 生命周期

onMounted(() => {
  timer = window.setInterval(() => {
    const tick = new Date()
    now.value = tick
    // 跨天时刷新「今天」，驾驶舱会自己换到新的一天。
    if (isoDayKey(tick) !== isoDayKey(todayStamp.value)) todayStamp.value = tick
  }, 1000)

  // 四个数据源各自独立失败，互不阻塞：任何一块挂掉都只影响它自己那张卡。
  loadPlan()
  void loadCourses()
  void loadPoints()
  void loadShares()
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <section class="dashboard-page">
    <header class="dashboard-heading entrance entrance-top">
      <!-- 主要位置：问候语 -->
      <div class="greeting-main">
        <p class="section-kicker">{{ formatDate(now).year }} / SDNU</p>
        <h1>{{ getGreeting(now) }}，<br />今天要处理什么？</h1>
        <p class="greeting-desc">选择一个具体任务，系统会调用对应 Skill。没有虚构数据，也不会自动执行高风险操作。</p>
      </div>

      <!-- 次要位置：时间日期 -->
      <div class="date-block-side">
        <div class="time-display">{{ formatTime(now) }}</div>
        <div class="date-info">
          <strong>{{ formatDate(now).day }}</strong>
          <span>{{ formatDate(now).monthEn }}<br />{{ formatDate(now).weekDayEn }}</span>
        </div>
        <div class="date-chinese">{{ formatDate(now).month }} {{ formatDate(now).weekDay }}</div>
      </div>
    </header>

    <!-- ① 驾驶舱指标行 -->
    <section class="dash-metrics entrance entrance-top" aria-label="今日指标">
      <article class="dash-metric is-course" :class="{ 'is-empty': courseMetric.empty }">
        <span class="dash-metric-label"><PhGraduationCap :size="15" weight="duotone" />本周课程</span>
        <span class="dash-metric-value">{{ courseMetric.value }}<em v-if="courseMetric.unit" class="dash-metric-unit">{{ courseMetric.unit }}</em></span>
        <span class="dash-metric-caption">{{ courseMetric.caption }}</span>
      </article>

      <article class="dash-metric is-plan" :class="{ 'is-empty': planMetric.empty }">
        <span class="dash-metric-label"><PhListChecks :size="15" weight="duotone" />本周计划</span>
        <span class="dash-metric-value">{{ planMetric.value }}</span>
        <span class="dash-metric-caption">{{ planMetric.caption }}</span>
      </article>

      <button
        type="button"
        class="dash-metric dash-metric-link is-points"
        :class="{ 'is-empty': pointsMetric.empty }"
        @click="router.push('/points')"
      >
        <span class="dash-metric-label"><PhStar :size="15" weight="duotone" />积分</span>
        <span class="dash-metric-value">{{ pointsMetric.value }}<em v-if="pointsMetric.unit" class="dash-metric-unit">{{ pointsMetric.unit }}</em></span>
        <span class="dash-metric-caption">{{ pointsMetric.caption }}</span>
        <PhArrowRight class="dash-metric-arrow" :size="14" />
      </button>

      <!-- 没有美好记录时整张卡不渲染，指标行自动变成 3 列 -->
      <button
        v-if="shareMetric"
        type="button"
        class="dash-metric dash-metric-link is-share"
        @click="router.push('/wellbeing')"
      >
        <span class="dash-metric-label"><PhHeart :size="15" weight="duotone" />美好记录</span>
        <span class="dash-metric-value is-text">{{ shareMetric.value }}</span>
        <span class="dash-metric-caption">{{ shareMetric.caption }}</span>
        <PhArrowRight class="dash-metric-arrow" :size="14" />
      </button>
    </section>

    <!-- ② 今日待办 + ③ 今日动态 -->
    <section class="dash-lower entrance entrance-top">
      <article class="dash-card dash-todo">
        <header class="dash-card-head">
          <span class="dash-card-kicker">今日待办</span>
          <span class="dash-card-meta">
            {{ todayWeekday }}
            <template v-if="todayPlanTasks.length"> · 已完成 {{ todayDoneCount }}/{{ todayPlanTasks.length }}</template>
          </span>
        </header>

        <ul v-if="todayTasks.length" class="dash-task-list">
          <li v-for="task in todayTasks" :key="task.key">
            <button
              type="button"
              class="dash-check"
              :aria-pressed="task.done"
              :aria-label="task.done ? `取消完成：${task.title}` : `标记完成：${task.title}`"
              @click="toggleTask(task.key)"
            >
              <PhCheckCircle v-if="task.done" :size="21" weight="fill" />
              <PhCircle v-else :size="21" />
            </button>
            <span class="dash-task-title" :class="{ 'is-done': task.done }">{{ task.title }}</span>
            <em v-if="task.minutes > 0" class="dash-task-min">{{ task.minutes }}′</em>
          </li>
        </ul>

        <p v-else class="dash-empty">
          <PhCalendarDots :size="18" weight="duotone" />
          <span>{{ planData ? '今天这一格是空的，留点余地也挺好。' : '还没有排本周计划，先把大目标拆成一周。' }}</span>
          <button type="button" class="dash-ghost" @click="router.push('/academic/plan')">
            去排计划<PhArrowRight :size="13" />
          </button>
        </p>

        <p v-if="planNotice" class="dash-notice">{{ planNotice }}</p>
      </article>

      <article v-if="timeline.length" class="dash-card dash-timeline">
        <header class="dash-card-head">
          <span class="dash-card-kicker">今日动态</span>
          <span class="dash-card-meta"><PhClock :size="12" weight="bold" /> 最近 {{ timeline.length }} 条</span>
        </header>
        <ol class="dash-axis">
          <li v-for="item in timeline" :key="item.id" :class="`is-${item.kind}`">
            <time>{{ item.time }}</time>
            <p>{{ item.text }}</p>
          </li>
        </ol>
      </article>
    </section>

    <section class="dashboard-grid">
      <article class="agent-console entrance entrance-left">
        <div class="console-head"><span>SUPER AGENT</span><i></i></div>
        <div class="agent-copy"><small>当前响应</small><h2>{{ greeting }}</h2><p v-if="error" class="inline-error">{{ error }}</p></div>
        <div class="console-actions"><button class="primary-action" type="button" :disabled="loading" @click="wakeGuide">{{ loading ? '连接中' : '唤醒引导员' }}</button><button class="text-action" type="button" @click="router.push('/wellbeing')">进入暖心空间</button></div>
      </article>

      <div class="capability-list entrance entrance-center">
        <button v-for="item in capabilities" :key="item.path" class="capability-row" type="button" @click="router.push(item.path)">
          <span>{{ item.no }}</span><div><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></div><em>{{ item.status }}</em><b>↗</b>
        </button>
      </div>

      <aside class="system-panel entrance entrance-right">
        <div><span class="panel-label">系统状态</span><strong>6</strong><small>业务 Skill 已注册</small></div>
        <dl><div><dt>记忆后端</dt><dd>SQLite / 可切换</dd></div><div><dt>安全网关</dt><dd>常驻</dd></div><div><dt>生产认证</dt><dd class="pending">待接 SSO</dd></div></dl>
        <button class="system-link" type="button" @click="router.push('/documents')">打开文档工坊 <span>05</span></button>
      </aside>
    </section>
  </section>
</template>

<style scoped>
/* ==================== 驾驶舱指标行 ==================== */
/* auto-fit：美好记录缺失时整行自动收成 3 列，不会留一个空位。 */
.dash-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
  margin: 0 0 18px;
}

.dash-metric {
  position: relative;
  display: grid;
  gap: .3rem;
  align-content: start;
  padding: 1rem 1.1rem 1.05rem 1.2rem;
  text-align: left;
  color: var(--ink);
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: 0 10px 26px rgba(42, 59, 53, .06);
  overflow: hidden;
}

.dash-metric::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--green);
  opacity: .8;
}

.dash-metric.is-course::before { background: #2f6f8f; }
.dash-metric.is-plan::before { background: var(--green); }
.dash-metric.is-points::before { background: var(--gold); }
.dash-metric.is-share::before { background: var(--coral); }

.dash-metric-label {
  display: flex;
  align-items: center;
  gap: .34rem;
  color: var(--muted);
  font-size: .74rem;
  font-weight: 700;
  letter-spacing: .04em;
}

.dash-metric-value {
  display: block;
  color: var(--navy);
  font-family: 'Noto Sans SC Variable', 'Microsoft YaHei', sans-serif;
  font-size: 2.1rem;
  font-weight: 800;
  line-height: 1.06;
  letter-spacing: -.02em;
  font-variant-numeric: tabular-nums;
}

.dash-metric-value.is-text {
  display: -webkit-box;
  font-family: 'LXGW WenKai', cursive;
  font-size: 1.02rem;
  font-weight: 400;
  line-height: 1.5;
  letter-spacing: 0;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.dash-metric-unit {
  margin-left: .16rem;
  color: var(--muted);
  font-size: .9rem;
  font-style: normal;
  font-weight: 700;
}

.dash-metric-caption {
  display: -webkit-box;
  color: var(--muted);
  font-size: .78rem;
  line-height: 1.5;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.dash-metric.is-empty .dash-metric-value { color: #aab5b1; }

.dash-metric-link {
  cursor: pointer;
  transition: transform .16s ease, border-color .16s ease, box-shadow .16s ease;
}

.dash-metric-link:hover {
  transform: translateY(-2px);
  border-color: #9cb6aa;
  box-shadow: 0 16px 34px rgba(42, 59, 53, .12);
}

.dash-metric-arrow {
  position: absolute;
  top: .95rem;
  right: .95rem;
  color: var(--muted);
  opacity: .45;
  transition: transform .16s ease, opacity .16s ease;
}

.dash-metric-link:hover .dash-metric-arrow {
  opacity: .85;
  transform: translateX(2px);
}

/* ==================== 今日待办 / 今日动态 ==================== */
.dash-lower {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 18px;
  margin: 0 0 18px;
}

.dash-card {
  padding: 1.1rem 1.2rem 1.2rem;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: 0 14px 34px rgba(42, 59, 53, .08);
}

.dash-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: .8rem;
  margin-bottom: .8rem;
}

.dash-card-kicker {
  color: var(--coral);
  font-size: .78rem;
  font-weight: 750;
  letter-spacing: .05em;
}

.dash-card-meta {
  display: flex;
  align-items: center;
  gap: .25rem;
  color: var(--muted);
  font-size: .74rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.dash-task-list {
  display: grid;
  gap: .2rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.dash-task-list li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: .55rem;
  padding: .34rem .3rem;
  border-radius: 11px;
  transition: background .15s ease;
}

.dash-task-list li:hover { background: #f3f6ef; }

.dash-check {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  padding: 0;
  color: var(--green);
  background: transparent;
  border: 0;
  border-radius: 9px;
  transition: background .15s ease, color .15s ease;
}

.dash-check:hover { background: var(--green-soft); }

.dash-task-title {
  min-width: 0;
  color: var(--ink);
  font-size: .89rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.dash-task-title.is-done {
  color: #99a5a1;
  text-decoration: line-through;
  text-decoration-thickness: 1px;
}

.dash-task-min {
  color: var(--muted);
  font-size: .74rem;
  font-style: normal;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.dash-empty {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: .55rem;
  margin: .2rem 0 0;
  color: var(--muted);
  font-size: .85rem;
  line-height: 1.6;
}

.dash-empty > span { flex: 1 1 12rem; }

.dash-ghost {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  padding: .44rem .8rem;
  color: var(--navy);
  background: var(--green-soft);
  border: 0;
  border-radius: 10px;
  font-size: .8rem;
  font-weight: 700;
  transition: background .15s ease;
}

.dash-ghost:hover { background: #cfe3d9; }

.dash-notice {
  margin: .6rem 0 0;
  color: #9e3030;
  font-size: .76rem;
  line-height: 1.5;
}

/* ==================== 今日动态轴 ==================== */
.dash-axis {
  position: relative;
  display: grid;
  gap: .72rem;
  margin: 0;
  padding: 0 0 0 1.05rem;
  list-style: none;
}

.dash-axis::before {
  content: '';
  position: absolute;
  left: .26rem;
  top: .38rem;
  bottom: .38rem;
  width: 1px;
  background: linear-gradient(var(--line), rgba(216, 222, 212, 0));
}

.dash-axis li {
  position: relative;
  display: grid;
  gap: .1rem;
}

.dash-axis li::before {
  content: '';
  position: absolute;
  left: -.97rem;
  top: .42rem;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--line);
  box-shadow: 0 0 0 3px var(--paper);
}

.dash-axis li.is-course::before { background: #2f6f8f; }
.dash-axis li.is-share::before { background: var(--gold); }
.dash-axis li.is-plan::before { background: var(--green); }

.dash-axis time {
  color: var(--muted);
  font-size: .72rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: .04em;
}

.dash-axis p {
  margin: 0;
  color: var(--ink);
  font-size: .85rem;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

/* ==================== 响应式 ==================== */
@media (max-width: 620px) {
  .dash-lower { grid-template-columns: 1fr; }
  .dash-card { padding: 1rem; }
  .dash-metric { padding: .9rem 1rem 1rem 1.05rem; }
}
</style>
