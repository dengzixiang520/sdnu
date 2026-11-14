<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import {
  PhTrophy, PhStar, PhMedal, PhChartBar, PhChartLine, PhCalendar, PhGift,
  PhUsers, PhCoins, PhTrendUp, PhArrowRight, PhInfo, PhSealCheck, PhSparkle,
} from '@phosphor-icons/vue'
import { useIdentity } from '../identity'
import { loadFiveDimensions, requestJson } from '../api'
import type { FiveDimensionSummary } from '../api'
import ExchangeShop from './ExchangeShop.vue'

interface UserPoints {
  user_id: string
  user_name: string
  total_points: number
  competition_points: number
  checkin_points: number
  activity_points: number
  badges: string[]
  level: string
}

interface Badge {
  id: string
  name: string
  description: string
  icon: string
  requirement: number
  category: string
}

interface PointsRecord {
  id: string
  user_id: string
  user_name: string
  points: number
  source: string
  source_detail: string
  created_at: string
}

interface ExchangeProduct {
  id: string
  name: string
  description: string
  category: string
  points: number
  stock: number
  image: string
  location: string
}

const { identity } = useIdentity()
const activeTab = ref('overview')
const userPoints = ref<UserPoints | null>(null)
const leaderboard = ref<UserPoints[]>([])
const badges = ref<Badge[]>([])
const records = ref<PointsRecord[]>([])
const products = ref<ExchangeProduct[]>([])
const loading = ref(false)
const loadError = ref('')
/* 记录流水的加载状态：曲线和徽章解锁日期都依赖它，失败要能单独提示并重试 */
const recordsState = ref<'loading' | 'ready' | 'error'>('loading')
const recordsError = ref('')

const currentUserId = computed(() => identity.value.userId)
const currentUserName = computed(() => identity.value.displayName)

/* 等级阶梯与后端 points_service.LEVELS 保持一致 */
const LEVEL_STEPS = [
  { name: '新手', min: 0 },
  { name: '入门', min: 100 },
  { name: '进阶', min: 300 },
  { name: '熟练', min: 500 },
  { name: '精通', min: 1000 },
  { name: '大师', min: 2000 },
]

const totalPoints = computed(() => userPoints.value?.total_points ?? 0)

const levelState = computed(() => {
  const total = totalPoints.value
  let index = 0
  LEVEL_STEPS.forEach((step, i) => { if (total >= step.min) index = i })
  const cur = LEVEL_STEPS[index]
  const next = LEVEL_STEPS[index + 1] ?? null
  if (!next) return { cur, next: null, need: 0, pct: 100 }
  const span = next.min - cur.min
  const pct = Math.max(0, Math.min(100, Math.round(((total - cur.min) / span) * 100)))
  return { cur, next, need: next.min - total, pct }
})

const nextBadge = computed(() => {
  const earned = new Set(userPoints.value?.badges ?? [])
  return badges.value
    .filter(badge => badge.requirement > 0 && !earned.has(badge.id))
    .sort((a, b) => a.requirement - b.requirement)[0] ?? null
})

const affordableCount = computed(
  () => products.value.filter(p => p.stock > 0 && p.points <= totalPoints.value).length,
)

const productRange = computed(() => {
  if (products.value.length === 0) return null
  const costs = products.value.map(p => p.points)
  return { min: Math.min(...costs), max: Math.max(...costs) }
})

/* ==================== 记录时间解析 ==================== */
/*
 * 后端用 datetime.now().isoformat() 落库，形如 "2026-11-13T22:33:00"：本地时间、无时区后缀。
 * 直接交给 new Date() 在各浏览器上对「无时区的日期时间」解释一致（按本地时区），
 * 但为了不依赖这一约定、也为了绕开 6 位小数秒的兼容差异，这里自己按字段解析。
 */
function parseRecordTime(value: string | undefined | null): number {
  if (!value) return Number.NaN
  const matched = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/.exec(value)
  if (matched) {
    const stamp = new Date(
      Number(matched[1]), Number(matched[2]) - 1, Number(matched[3]),
      Number(matched[4]), Number(matched[5]), Number(matched[6] || '0'),
    ).getTime()
    return Number.isNaN(stamp) ? Number.NaN : stamp
  }
  const fallback = Date.parse(value)
  return Number.isNaN(fallback) ? Number.NaN : fallback
}

/** 本地自然日的 YYYY-MM-DD，和后端 created_at 前缀口径一致 */
function dateKeyOf(stamp: number): string {
  const date = new Date(stamp)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

function shortDateLabel(stamp: number): string {
  const date = new Date(stamp)
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function formatRecordDate(value: string): string {
  const stamp = parseRecordTime(value)
  if (Number.isNaN(stamp)) return ''
  return dateKeyOf(stamp)
}

interface DatedRecord { record: PointsRecord; index: number; stamp: number }

/** 记录按时间升序，时间相同的保持后端原始顺序（后端按 created_at 倒序返回） */
const datedRecords = computed<DatedRecord[]>(() =>
  records.value
    .map((record, index) => ({ record, index, stamp: parseRecordTime(record.created_at) }))
    .filter(item => !Number.isNaN(item.stamp))
    .sort((a, b) => (a.stamp === b.stamp ? a.index - b.index : a.stamp - b.stamp)),
)

/* ==================== 积分成长曲线（概览） ==================== */
/* 记录条数超过这个值时按天聚合，避免点太密看不出走势 */
const GROWTH_MAX_POINTS = 30

interface GrowthSample { stamp: number; total: number }

const growthSeries = computed<GrowthSample[]>(() => {
  const items = datedRecords.value
  if (items.length === 0) return []
  const running: GrowthSample[] = []
  let total = 0
  for (const item of items) {
    total += item.record.points
    running.push({ stamp: item.stamp, total })
  }
  if (running.length <= GROWTH_MAX_POINTS) return running
  // 按天聚合：Map 覆盖写入 + 升序遍历，天然得到「每天结束时的累计值」
  const byDay = new Map<string, GrowthSample>()
  for (const point of running) byDay.set(dateKeyOf(point.stamp), point)
  const daily = Array.from(byDay.values())
  // 一天里塞了 30 多条记录时聚合完只剩 1 个点，画不出线，退回逐笔
  return daily.length >= 2 ? daily : running
})

const growthAggregated = computed(
  () => datedRecords.value.length > GROWTH_MAX_POINTS && growthSeries.value.length < datedRecords.value.length,
)

const CHART_HEIGHT = 208
const CHART_PAD_TOP = 28
const CHART_PAD_BOTTOM = 28
const CHART_PAD_X = 16

const chartWrap = ref<HTMLElement | null>(null)
const chartWidth = ref(760)
let chartObserver: ResizeObserver | null = null
/* 同一页面可能出现多个实例，渐变 id 加随机后缀避免互相覆盖 */
const chartFillId = `ptsx-curve-fill-${Math.random().toString(36).slice(2, 8)}`

interface ChartPoint { x: number; y: number; value: number; stamp: number }
interface ChartTick { key: string; x: number; label: string; anchor: string }

const chartGeometry = computed(() => {
  const series = growthSeries.value
  const width = Math.max(280, Math.round(chartWidth.value) || 760)
  const height = CHART_HEIGHT
  const innerWidth = Math.max(1, width - CHART_PAD_X * 2)
  const innerHeight = Math.max(1, height - CHART_PAD_TOP - CHART_PAD_BOTTOM)
  const baseY = CHART_PAD_TOP + innerHeight
  const values = series.map(point => point.total)
  // 纵轴从 0 起，累计曲线的「涨」才不会被放大成锯齿
  const low = values.length > 0 ? Math.min(0, ...values) : 0
  const highRaw = values.length > 0 ? Math.max(...values) : 0
  const high = highRaw === low ? low + 1 : highRaw
  const span = high - low || 1
  const xAt = (index: number) =>
    series.length <= 1
      ? CHART_PAD_X + innerWidth / 2
      : CHART_PAD_X + (index / (series.length - 1)) * innerWidth
  const yAt = (value: number) => CHART_PAD_TOP + (1 - (value - low) / span) * innerHeight
  const points: ChartPoint[] = series.map((point, index) => ({
    x: xAt(index),
    y: yAt(point.total),
    value: point.total,
    stamp: point.stamp,
  }))
  const drawable = points.length >= 2
  const linePath = drawable
    ? points
        .map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)},${point.y.toFixed(2)}`)
        .join(' ')
    : ''
  const first: ChartPoint = drawable ? points[0] : { x: 0, y: baseY, value: 0, stamp: 0 }
  const last: ChartPoint = drawable ? points[points.length - 1] : { x: 0, y: baseY, value: 0, stamp: 0 }
  const areaPath = drawable
    ? `${linePath} L${last.x.toFixed(2)},${baseY.toFixed(2)} L${first.x.toFixed(2)},${baseY.toFixed(2)} Z`
    : ''
  // 横轴刻度：首、中、尾；点足够多时补到 4 个
  const tickIndexes: number[] = []
  if (drawable) {
    const lastIndex = points.length - 1
    const candidates = points.length >= 12
      ? [0, Math.round(lastIndex / 3), Math.round((lastIndex * 2) / 3), lastIndex]
      : points.length >= 3
        ? [0, Math.round(lastIndex / 2), lastIndex]
        : [0, lastIndex]
    for (const index of candidates) {
      if (!tickIndexes.includes(index)) tickIndexes.push(index)
    }
  }
  const ticks: ChartTick[] = tickIndexes.map(index => ({
    key: `tick-${index}`,
    x: points[index].x,
    label: shortDateLabel(points[index].stamp),
    anchor: index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle',
  }))
  // 末尾数值标签：贴右边时改为右对齐，贴着顶部时挪到点下方
  const endAnchor = last.x > width - 58 ? 'end' : 'start'
  const endLabelX = endAnchor === 'end' ? last.x - 8 : last.x + 8
  const endLabelY = last.y < CHART_PAD_TOP + 18 ? last.y + 16 : last.y - 10
  const gridLines = [0, 0.5, 1].map(ratio => ({
    key: `grid-${ratio}`,
    y: CHART_PAD_TOP + innerHeight * ratio,
  }))
  return {
    width, height, innerWidth, innerHeight, baseY,
    points, linePath, areaPath, ticks, gridLines,
    first, last, endAnchor, endLabelX, endLabelY, drawable, low, high,
  }
})

const canDrawCurve = computed(() => chartGeometry.value.drawable)

const growthStats = computed(() => {
  const now = new Date()
  const monthPrefix = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  let monthEarned = 0
  let earnedTotal = 0
  let earnCount = 0
  for (const record of records.value) {
    if (!(record.points > 0)) continue
    earnedTotal += record.points
    earnCount += 1
    const stamp = parseRecordTime(record.created_at)
    if (!Number.isNaN(stamp) && dateKeyOf(stamp).startsWith(monthPrefix)) monthEarned += record.points
  }
  const average = earnCount > 0 ? earnedTotal / earnCount : 0
  return {
    monthEarned,
    earnedTotal,
    earnCount,
    averageText: average.toFixed(1),
  }
})

const growthHeadHint = computed(() => {
  if (recordsState.value === 'error') return '数据读取失败'
  const series = growthSeries.value
  if (series.length === 0) return '暂无记录'
  if (series.length < 2) return '仅 1 条记录'
  return `${growthAggregated.value ? '按天聚合' : '逐笔累加'} · ${series.length} 个点`
})

/* ==================== 徽章墙 ==================== */
interface BadgeRow {
  badge: Badge
  earned: boolean
  earnedAt: string
  condition: string
  trackable: boolean
  current: number
  requirement: number
  progressPct: number
  remain: number
}

/*
 * 解锁日期：在升序流水上逐笔累加，只有「上一笔还没到、这一笔跨过门槛」的那条才认作解锁时刻。
 * 门槛在可见记录之前就已满足（流水被 200 条截断）时不猜日期，卡片上只显示「已获得」。
 */
const badgeUnlockDates = computed(() => {
  const dates = new Map<string, string>()
  const trackable = badges.value.filter(badge => badge.requirement > 0)
  if (trackable.length === 0) return dates
  let running = 0
  for (const item of datedRecords.value) {
    const before = running
    running += item.record.points
    for (const badge of trackable) {
      if (dates.has(badge.id)) continue
      if (before < badge.requirement && running >= badge.requirement) {
        const label = formatRecordDate(item.record.created_at)
        if (label) dates.set(badge.id, label)
      }
    }
  }
  return dates
})

const badgeRows = computed<BadgeRow[]>(() => {
  const earnedSet = new Set(userPoints.value?.badges ?? [])
  const current = Math.max(0, totalPoints.value)
  const rows: BadgeRow[] = badges.value.map(badge => {
    const earned = earnedSet.has(badge.id)
    const trackable = badge.requirement > 0
    const description = (badge.description ?? '').trim()
    return {
      badge,
      earned,
      earnedAt: earned ? (badgeUnlockDates.value.get(badge.id) ?? '') : '',
      condition: description || (trackable ? `累计 ${badge.requirement} 分` : '完成指定成就'),
      trackable,
      current,
      requirement: badge.requirement,
      progressPct: trackable
        ? Math.max(0, Math.min(100, Math.round((current / badge.requirement) * 100)))
        : 0,
      remain: trackable ? Math.max(0, badge.requirement - current) : 0,
    }
  })
  /*
   * 未获得的排前面，按门槛升序（下一个最容易拿到的排最前）；已获得的排后面。
   * 门槛为 0 的专项徽章（连续打卡、参赛次数等）没有分数进度可算，排在未获得组末尾，
   * 不抢「下一个最容易拿到」的位置。
   */
  return rows.sort((a, b) => {
    if (a.earned !== b.earned) return a.earned ? 1 : -1
    const rankA = a.trackable ? a.badge.requirement : Number.MAX_SAFE_INTEGER
    const rankB = b.trackable ? b.badge.requirement : Number.MAX_SAFE_INTEGER
    if (rankA !== rankB) return rankA - rankB
    return a.badge.name.localeCompare(b.badge.name, 'zh-Hans-CN')
  })
})

const badgeSummary = computed(() => {
  const total = badgeRows.value.length
  const earned = badgeRows.value.filter(row => row.earned).length
  return {
    total,
    earned,
    locked: total - earned,
    pct: total > 0 ? Math.round((earned / total) * 100) : 0,
  }
})

const nextBadgeRow = computed(() => badgeRows.value.find(row => !row.earned && row.trackable) ?? null)

/* 容器实测宽度：SVG 用真实像素坐标，文字和线宽不会被非等比缩放拉变形 */
watch(chartWrap, element => {
  chartObserver?.disconnect()
  chartObserver = null
  if (!element) return
  if (typeof ResizeObserver === 'undefined') {
    chartWidth.value = element.clientWidth || chartWidth.value
    return
  }
  chartObserver = new ResizeObserver(entries => {
    const measured = entries[0]?.contentRect?.width ?? 0
    if (measured > 0) chartWidth.value = measured
  })
  chartObserver.observe(element)
}, { flush: 'post' })

onUnmounted(() => {
  chartObserver?.disconnect()
  chartObserver = null
})

async function fetchUserPoints() {
  try {
    const data = await requestJson<{ success: boolean; data: { user: UserPoints } }>(
      `/api/v1/points/user/${currentUserId.value}`, {}, '获取积分失败')
    if (data.success && data.data.user) {
      userPoints.value = data.data.user
    }
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '获取积分失败'
  }
}

async function fetchLeaderboard() {
  try {
    const data = await requestJson<{ success: boolean; data: { leaderboard: UserPoints[] } }>(
      '/api/v1/points/leaderboard?limit=20', {}, '获取排行榜失败')
    if (data.success) leaderboard.value = data.data.leaderboard
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '获取排行榜失败'
  }
}

async function fetchBadges() {
  try {
    const data = await requestJson<{ success: boolean; data: { badges: Badge[] } }>(
      '/api/v1/points/badges', {}, '获取徽章失败')
    if (data.success) badges.value = data.data.badges
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '获取徽章失败'
  }
}

async function fetchRecords() {
  recordsState.value = 'loading'
  recordsError.value = ''
  try {
    const data = await requestJson<{ success: boolean; data: { records: PointsRecord[] } }>(
      `/api/v1/points/user/${currentUserId.value}/records?limit=200`, {}, '获取记录失败')
    if (data.success) {
      records.value = data.data.records ?? []
      recordsState.value = 'ready'
      checkTodayChecked()
    } else {
      recordsState.value = 'error'
      recordsError.value = '获取记录失败'
    }
  } catch (err) {
    recordsState.value = 'error'
    recordsError.value = err instanceof Error ? err.message : '获取记录失败'
    loadError.value = recordsError.value
  }
}

async function fetchProducts() {
  try {
    const data = await requestJson<{ success: boolean; data: { products: ExchangeProduct[] } }>(
      '/api/v1/exchange/products', {}, '获取兑换商品失败')
    if (data.success) products.value = data.data.products
  } catch {
    // 兑换商品只是概览里的补充信息，失败时静默降级，不打断页面
    products.value = []
  }
}

const todayChecked = ref(false)

function checkTodayChecked() {
  // 后端按服务器本地自然日判定，前端也用本地日期；用 toISOString() 在 UTC+8 早八点前会差一天
  const today = dateKeyOf(Date.now())
  todayChecked.value = records.value.some(record =>
    record.source === 'checkin' && (record.created_at ?? '').startsWith(today)
  )
}

async function addCheckinPoints() {
  if (todayChecked.value) {
    alert('今天已经打过卡了，明天再来吧！')
    return
  }
  loading.value = true
  try {
    const data = await requestJson<{ success: boolean; message?: string }>(
      `/api/v1/points/checkin/${currentUserId.value}?user_name=${encodeURIComponent(currentUserName.value)}`,
      { method: 'POST' }, '打卡失败')
    if (data.success) {
      todayChecked.value = true
      await fetchUserPoints()
      await fetchRecords()
    } else {
      loadError.value = data.message || '打卡失败'
    }
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '打卡失败'
  }
  finally { loading.value = false }
}

function getSourceLabel(source: string) {
  switch (source) {
    case 'competition': return '竞赛获奖'
    case 'checkin': return '每日打卡'
    case 'activity': return '活动参与'
    case 'exchange': return '积分兑换'
    default: return source
  }
}

function getRankIcon(index: number) {
  if (index === 0) return '🥇'
  if (index === 1) return '🥈'
  if (index === 2) return '🥉'
  return `${index + 1}`
}

function goTab(tab: string) {
  activeTab.value = tab
}

/* 五育分布：把单一积分数字拆成德智体美劳，对应教育部「全要素横向评价」。
   认不出的积分进「未归类」，不硬塞——比假装每笔都能归类诚实。 */
const fiveDimensions = ref<FiveDimensionSummary | null>(null)
const fiveError = ref('')

async function fetchFiveDimensions() {
  fiveError.value = ''
  try {
    fiveDimensions.value = await loadFiveDimensions(identity.value.userId)
  } catch (reason) {
    fiveDimensions.value = null
    fiveError.value = reason instanceof Error ? reason.message : '读不到五育分布'
  }
}

onMounted(async () => {
  await fetchUserPoints()
  fetchLeaderboard()
  fetchBadges()
  await fetchRecords()
  checkTodayChecked()
  fetchProducts()
  void fetchFiveDimensions()
})
</script>

<template>
  <section class="points-page">
    <header class="points-header">
      <div>
        <h1><PhTrophy :size="28" weight="duotone" /> 积分中心</h1>
        <p>把竞赛获奖、每日打卡、活动参与换算成可累计的积分，再兑换成实物或校园服务</p>
      </div>
    </header>

    <div v-if="loadError" class="inline-error dismissible-error page-error" role="alert">
      <span>{{ loadError }}</span>
      <button type="button" @click="loadError = ''">知道了</button>
    </div>

    <!-- 积分概览卡片 -->
    <div class="points-overview">
      <div class="overview-card main">
        <div class="card-icon"><PhStar :size="32" weight="duotone" /></div>
        <div class="card-content">
          <span class="card-label">当前积分</span>
          <span class="card-value">{{ userPoints?.total_points ?? 0 }}</span>
        </div>
        <div class="card-level">{{ userPoints?.level ?? '新手' }}</div>
      </div>
      <div class="overview-card">
        <div class="card-icon"><PhTrophy :size="24" /></div>
        <div class="card-content">
          <span class="card-label">竞赛积分</span>
          <span class="card-value small">{{ userPoints?.competition_points ?? 0 }}</span>
        </div>
      </div>
      <div class="overview-card">
        <div class="card-icon"><PhCalendar :size="24" /></div>
        <div class="card-content">
          <span class="card-label">打卡积分</span>
          <span class="card-value small">{{ userPoints?.checkin_points ?? 0 }}</span>
        </div>
      </div>
      <div class="overview-card">
        <div class="card-icon"><PhMedal :size="24" /></div>
        <div class="card-content">
          <span class="card-label">徽章数</span>
          <span class="card-value small">{{ userPoints?.badges?.length ?? 0 }}</span>
        </div>
      </div>
    </div>

    <!-- 每日打卡 -->
    <div class="checkin-section">
      <button class="checkin-btn" @click="addCheckinPoints" :disabled="loading || todayChecked">
        <PhCalendar :size="20" /> {{ todayChecked ? '今日已打卡' : loading ? '打卡中...' : '每日打卡 +5积分' }}
      </button>
      <span class="checkin-note">
        {{ todayChecked ? '今天的 5 分已经到账，明天再来' : '每天只能打一次卡，服务端按自然日判定' }}
      </span>
    </div>

    <!-- 标签页 -->
    <div class="points-tabs">
      <button :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">概览</button>
      <button :class="{ active: activeTab === 'leaderboard' }" @click="activeTab = 'leaderboard'">排行榜</button>
      <button :class="{ active: activeTab === 'badges' }" @click="activeTab = 'badges'">徽章</button>
      <button :class="{ active: activeTab === 'records' }" @click="activeTab = 'records'">积分记录</button>
      <button :class="{ active: activeTab === 'rules' }" @click="activeTab = 'rules'">积分规则</button>
      <button :class="{ active: activeTab === 'exchange' }" @click="activeTab = 'exchange'">积分兑换</button>
    </div>

    <!-- ==================== 概览 ==================== -->
    <div v-if="activeTab === 'overview'" class="overview-section">

      <!-- 1. 成长进度 -->
      <section class="overview-panel">
        <div class="panel-head">
          <h3><PhTrendUp :size="20" weight="duotone" /> 成长进度</h3>
          <span class="panel-hint">等级由累计积分自动晋升，不需要申请</span>
        </div>

        <!-- 当前等级 → 下一等级 -->
        <div class="ptsx-level-flow">
          <div class="ptsx-level-chip is-current">
            <span class="ptsx-level-chip-label">当前等级</span>
            <strong>{{ levelState.cur.name }}</strong>
            <span class="ptsx-level-chip-min ptsx-num">{{ totalPoints }} 分</span>
          </div>
          <PhArrowRight :size="16" class="ptsx-level-arrow" />
          <div v-if="levelState.next" class="ptsx-level-chip">
            <span class="ptsx-level-chip-label">下一等级</span>
            <strong>{{ levelState.next.name }}</strong>
            <span class="ptsx-level-chip-min ptsx-num">{{ levelState.next.min }} 分</span>
          </div>
          <div v-else class="ptsx-level-chip is-max">
            <PhSealCheck :size="17" weight="fill" />
            <strong>已达最高等级</strong>
            <span class="ptsx-level-chip-min">大师</span>
          </div>
        </div>

        <div class="level-track">
          <div class="level-bar">
            <div class="level-bar-fill" :style="{ width: levelState.pct + '%' }"></div>
          </div>
          <div class="level-meta">
            <span>当前等级 <b>{{ levelState.cur.name }}</b> · 累计 <b class="ptsx-num">{{ totalPoints }}</b> 分</span>
            <span v-if="levelState.next" class="ptsx-level-need">
              还差 <b class="ptsx-num">{{ levelState.need }}</b> 分升级「{{ levelState.next.name }}」
            </span>
            <span v-else class="ptsx-level-need">已达最高等级，积分继续累加</span>
            <span class="ptsx-level-pct ptsx-num">{{ levelState.pct }}%</span>
          </div>
        </div>

        <div class="level-steps">
          <div
            v-for="step in LEVEL_STEPS"
            :key="step.name"
            class="level-step"
            :class="{ done: totalPoints >= step.min, current: levelState.cur.name === step.name }"
          >
            <span class="step-name">{{ step.name }}</span>
            <span class="step-min">{{ step.min }} 分</span>
          </div>
        </div>

        <p v-if="nextBadge" class="badge-hint">
          <PhMedal :size="15" />
          下一个徽章「{{ nextBadge.name }}」需要累计 {{ nextBadge.requirement }} 分，还差
          {{ Math.max(0, nextBadge.requirement - totalPoints) }} 分
        </p>
        <p v-else-if="badges.length > 0" class="badge-hint">
          <PhMedal :size="15" /> 积分类徽章已全部集齐，可在「徽章」页查看
        </p>
      </section>

      <!-- 2. 积分成长曲线 -->
      <section class="overview-panel">
        <div class="panel-head">
          <h3><PhChartLine :size="20" weight="duotone" /> 积分成长曲线</h3>
          <span class="panel-hint">{{ growthHeadHint }}</span>
        </div>

        <!-- 读取失败：给文案 + 重试，不留白屏 -->
        <div v-if="recordsState === 'error'" class="ptsx-curve-state is-error">
          <p>曲线数据没取到：{{ recordsError }}</p>
          <button type="button" class="ptsx-retry" @click="fetchRecords">重新加载</button>
        </div>

        <template v-else>
          <!-- 记录不足 2 条，不画曲线 -->
          <div v-if="!canDrawCurve" class="ptsx-curve-state">
            <p v-if="recordsState === 'loading'">正在读取积分记录…</p>
            <p v-else-if="records.length === 0">
              还没有积分记录。打个卡或参加一次活动，曲线会从第一条记录开始往上走。
            </p>
            <p v-else>再获得 1 次积分就能看到成长曲线</p>
          </div>

          <!-- 折线 + 面积填充 + 末尾圆点，全部由 computed 出坐标 -->
          <div v-else ref="chartWrap" class="ptsx-curve-canvas">
            <svg
              :viewBox="`0 0 ${chartGeometry.width} ${chartGeometry.height}`"
              :width="chartGeometry.width"
              :height="chartGeometry.height"
              role="img"
              aria-label="累计积分随时间变化的折线图"
            >
              <defs>
                <linearGradient :id="chartFillId" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#397f72" stop-opacity="0.32" />
                  <stop offset="65%" stop-color="#397f72" stop-opacity="0.09" />
                  <stop offset="100%" stop-color="#397f72" stop-opacity="0" />
                </linearGradient>
              </defs>

              <line
                v-for="grid in chartGeometry.gridLines"
                :key="grid.key"
                :x1="CHART_PAD_X"
                :x2="chartGeometry.width - CHART_PAD_X"
                :y1="grid.y"
                :y2="grid.y"
                class="ptsx-curve-grid"
              />

              <path :d="chartGeometry.areaPath" :fill="`url(#${chartFillId})`" />
              <path
                :d="chartGeometry.linePath"
                fill="none"
                stroke="#2d6659"
                stroke-width="2.4"
                stroke-linejoin="round"
                stroke-linecap="round"
              />

              <circle
                :cx="chartGeometry.last.x"
                :cy="chartGeometry.last.y"
                r="8.5"
                fill="#2d6659"
                opacity="0.12"
              />
              <circle
                :cx="chartGeometry.last.x"
                :cy="chartGeometry.last.y"
                r="4.2"
                fill="#2d6659"
                stroke="#fffef8"
                stroke-width="1.6"
              />
              <text
                :x="chartGeometry.endLabelX"
                :y="chartGeometry.endLabelY"
                :text-anchor="chartGeometry.endAnchor"
                class="ptsx-curve-endlabel"
              >{{ chartGeometry.last.value }} 分</text>

              <text
                v-for="tick in chartGeometry.ticks"
                :key="tick.key"
                :x="tick.x"
                :y="chartGeometry.height - 9"
                :text-anchor="tick.anchor"
                class="ptsx-curve-tick"
              >{{ tick.label }}</text>
            </svg>
          </div>

          <div v-if="records.length > 0" class="ptsx-curve-stats">
            <div class="ptsx-curve-stat">
              <span>本月获得</span>
              <b class="ptsx-num">{{ growthStats.monthEarned }}</b>
            </div>
            <div class="ptsx-curve-stat">
              <span>累计获得</span>
              <b class="ptsx-num">{{ growthStats.earnedTotal }}</b>
            </div>
            <div class="ptsx-curve-stat">
              <span>平均每次</span>
              <b class="ptsx-num">{{ growthStats.averageText }}</b>
            </div>
          </div>
          <p v-if="records.length > 0" class="ptsx-curve-note">
            曲线按全部记录累加，兑换扣分会让曲线回落；「获得」只统计加分记录，不含消耗。
          </p>
        </template>
      </section>

      <!-- 3. 积分从哪来 -->
      <section class="overview-panel">
        <div class="panel-head">
          <h3><PhCoins :size="20" weight="duotone" /> 积分从哪来</h3>
          <button type="button" class="panel-link" @click="goTab('rules')">
            完整规则 <PhArrowRight :size="13" />
          </button>
        </div>
        <p class="panel-desc">
          三条通道互不冲突，最终都累加进「当前积分」；兑换消耗后，「竞赛积分」「打卡积分」作为累计贡献记录保持不变。
        </p>

        <div class="source-grid">
          <div class="source-card">
            <div class="source-head">
              <PhTrophy :size="20" weight="duotone" />
              <span class="source-title">竞赛获奖</span>
            </div>
            <span class="source-amount">3 – 100 分 / 次</span>
            <p class="source-desc">
              参加学校认定的竞赛并获奖后按等级核定：国家级 A1 100 分、A2 80、A3 60；B1 50、B2 40、B3 30；
              省级 C1 20、C2 15、C3 10；校级 D1 8、D2 5、D3 3，共 12 档。
            </p>
            <p class="source-note">由管理员按获奖证书核定发放，学生端只读，不能自助加分。</p>
          </div>

          <div class="source-card">
            <div class="source-head">
              <PhCalendar :size="20" weight="duotone" />
              <span class="source-title">每日打卡</span>
            </div>
            <span class="source-amount">+5 分 / 天</span>
            <p class="source-desc">
              每天一次心情打卡 +5 分；连续 7 天额外 +20 分，连续 30 天额外 +100 分。坚持本身就是最稳的积分来源。
            </p>
            <p class="source-note">服务端按自然日去重，换设备、清缓存都不能重复领取。</p>
          </div>

          <div class="source-card">
            <div class="source-head">
              <PhUsers :size="20" weight="duotone" />
              <span class="source-title">活动参与</span>
            </div>
            <span class="source-amount">按活动核定</span>
            <p class="source-desc">
              参与校内讲座、志愿服务、朋辈互助等活动，由组织方登记后发放；也用于人工补录其他经认定的加分项。
            </p>
            <p class="source-note">与竞赛、打卡分开记账，在明细里能看清每一笔的来源。</p>
          </div>
        </div>
      </section>

      <!-- 4. 五育分布 -->
      <section class="overview-panel">
        <div class="panel-head">
          <h3><PhChartBar :size="20" weight="duotone" /> 五育分布</h3>
          <button type="button" class="panel-link" @click="fetchFiveDimensions">
            刷新 <PhArrowRight :size="13" />
          </button>
        </div>
        <p class="panel-desc">
          把积分拆成德智体美劳五育，对应教育部《「人工智能+教育」行动计划》里的「德智体美劳全要素横向评价」。
          这一层只看你自己的分布，不是评优依据。
        </p>

        <p v-if="fiveError" class="five-error">{{ fiveError }}</p>

        <template v-else-if="fiveDimensions">
          <p class="five-summary">{{ fiveDimensions.summary }}</p>

          <ul class="five-bars">
            <li v-for="item in fiveDimensions.dimensions" :key="item.id">
              <span class="five-label">{{ item.label }}</span>
              <div class="five-track">
                <i :style="{ width: `${Math.max(item.share, item.points > 0 ? 4 : 0)}%` }" />
              </div>
              <span class="five-value">{{ item.points }}<em>{{ item.share }}%</em></span>
              <span class="five-note">{{ item.note }}</span>
            </li>
          </ul>

          <p v-if="fiveDimensions.unclassified > 0" class="five-unclassified">
            另有 {{ fiveDimensions.unclassified }} 分（{{ fiveDimensions.unclassified_share }}%）还没归类：
            来源说明里没有可识别的关键词，所以没硬塞进某一育。
          </p>
          <p class="five-foot">{{ fiveDimensions.note }}</p>
        </template>
      </section>

      <!-- 5. 积分花到哪 -->
      <section class="overview-panel">
        <div class="panel-head">
          <h3><PhGift :size="20" weight="duotone" /> 积分花到哪</h3>
          <button type="button" class="panel-link" @click="goTab('exchange')">
            去兑换 <PhArrowRight :size="13" />
          </button>
        </div>
        <p class="panel-desc">
          积分可以兑换实物奖品、校园服务和优先权益。兑换成功后生成 8 位兑换码，凭码到指定地点领取，虚拟权益由系统自动发放。
        </p>

        <div v-if="productRange" class="spend-stats">
          <div class="spend-stat">
            <span>在架兑换品</span>
            <b>{{ products.length }} <small>件</small></b>
          </div>
          <div class="spend-stat">
            <span>当前积分可兑换</span>
            <b>{{ affordableCount }} <small>件</small></b>
          </div>
          <div class="spend-stat">
            <span>兑换门槛</span>
            <b>{{ productRange.min }} <small>– {{ productRange.max }} 分</small></b>
          </div>
        </div>
        <p v-else class="panel-desc panel-desc-muted">兑换商品列表暂未取到，可切到「积分兑换」页重试。</p>
      </section>

      <!-- 5. 记账口径 -->
      <section class="overview-panel">
        <div class="panel-head">
          <h3><PhInfo :size="20" weight="duotone" /> 记账口径</h3>
          <span class="panel-hint">四条硬规则，避免分数算不清</span>
        </div>
        <ul class="rule-list">
          <li>
            <strong>兑换只扣总分</strong>
            <span>兑换会让「当前积分」减少，但「竞赛积分」「打卡积分」作为累计贡献记录保持不变，不随消费回退。</span>
          </li>
          <li>
            <strong>徽章只增不减</strong>
            <span>已经拿到的徽章不会因为兑换消耗积分而被回收，成就记录保持完整。</span>
          </li>
          <li>
            <strong>打卡一天一次，服务端判定</strong>
            <span>按钮变灰只是前端提示，真正的重复校验在服务端按自然日完成，重复请求会被拒绝。</span>
          </li>
          <li>
            <strong>竞赛积分需核定</strong>
            <span>加分接口只对管理员开放，学生端只能查看，避免出现自助刷分。</span>
          </li>
        </ul>
      </section>
    </div>

    <!-- 排行榜 -->
    <div v-if="activeTab === 'leaderboard'" class="leaderboard-section">
      <div v-for="(user, index) in leaderboard" :key="user.user_id" class="leaderboard-item" :class="{ 'is-me': user.user_id === currentUserId }">
        <span class="rank">{{ getRankIcon(index) }}</span>
        <span class="name">{{ user.user_name }}</span>
        <span class="level">{{ user.level }}</span>
        <span class="points">{{ user.total_points }} 积分</span>
      </div>
      <div v-if="leaderboard.length === 0" class="empty-state">暂无排行数据</div>
    </div>

    <!-- 徽章墙 -->
    <div v-if="activeTab === 'badges'" class="ptsx-badges">
      <div v-if="badgeSummary.total > 0" class="ptsx-badge-summary">
        <div class="ptsx-badge-summary-head">
          <div>
            <strong>
              已解锁 <span class="ptsx-num">{{ badgeSummary.earned }}</span> /
              共 <span class="ptsx-num">{{ badgeSummary.total }}</span> 枚
            </strong>
            <p>积分类徽章按累计积分自动发放；专项徽章需要达成对应成就，兑换不会回收已得徽章。</p>
          </div>
          <span class="ptsx-badge-summary-pct ptsx-num">{{ badgeSummary.pct }}%</span>
        </div>
        <div class="ptsx-progress">
          <div class="ptsx-progress-fill" :style="{ width: badgeSummary.pct + '%' }"></div>
        </div>
        <p v-if="nextBadgeRow" class="ptsx-badge-next">
          <PhSparkle :size="14" weight="duotone" />
          下一个最容易拿到的是「{{ nextBadgeRow.badge.name }}」，还差
          <b class="ptsx-num">{{ nextBadgeRow.remain }}</b> 分
        </p>
        <p v-else-if="badgeSummary.locked === 0" class="ptsx-badge-next">
          <PhSealCheck :size="14" weight="fill" /> 全部徽章已集齐
        </p>
      </div>

      <div v-if="badges.length === 0" class="ptsx-curve-state">
        <p>徽章列表暂未取到，可能是后端暂时不可用。</p>
        <button type="button" class="ptsx-retry" @click="fetchBadges">重新加载</button>
      </div>

      <div v-else class="ptsx-badge-grid">
        <article
          v-for="row in badgeRows"
          :key="row.badge.id"
          class="ptsx-badge-card"
          :class="row.earned ? 'is-earned' : 'is-locked'"
        >
          <div class="ptsx-badge-top">
            <span class="ptsx-badge-emoji">{{ row.badge.icon || '🎖️' }}</span>
            <div class="ptsx-badge-title">
              <strong>{{ row.badge.name }}</strong>
              <small>{{ row.condition }}</small>
            </div>
            <span class="ptsx-badge-tag" :class="row.earned ? 'is-earned' : 'is-locked'">
              <PhSealCheck v-if="row.earned" :size="11" weight="fill" />{{ row.earned ? '已获得' : '未解锁' }}
            </span>
          </div>

          <div v-if="row.earned" class="ptsx-badge-foot">
            <span v-if="row.earnedAt" class="ptsx-badge-date">获得于 {{ row.earnedAt }}</span>
            <span v-else class="ptsx-badge-date is-muted">已获得（更早解锁）</span>
          </div>

          <div v-else class="ptsx-badge-foot">
            <div v-if="row.trackable" class="ptsx-progress ptsx-progress-sm">
              <div class="ptsx-progress-fill" :style="{ width: row.progressPct + '%' }"></div>
            </div>
            <span class="ptsx-badge-progress-text">
              <template v-if="row.trackable">
                当前 <b class="ptsx-num">{{ row.current }}</b> / 需要 <b class="ptsx-num">{{ row.requirement }}</b>
              </template>
              <template v-else>需达成专项成就（打卡连续天数、参赛次数等）</template>
            </span>
          </div>
        </article>
      </div>
    </div>

    <!-- 积分记录 -->
    <div v-if="activeTab === 'records'" class="records-section">
      <div v-for="record in records" :key="record.id" class="record-item">
        <div class="record-info">
          <span class="record-source">{{ getSourceLabel(record.source) }}</span>
          <span class="record-detail">{{ record.source_detail }}</span>
        </div>
        <span class="record-points" :class="{ minus: record.points < 0 }">
          {{ record.points > 0 ? '+' : '' }}{{ record.points }}
        </span>
      </div>
      <div v-if="records.length === 0" class="empty-state">暂无积分记录</div>
    </div>

    <!-- 积分规则 -->
    <div v-if="activeTab === 'rules'" class="rules-section">
      <div class="rules-card">
        <h3>🏆 竞赛获奖积分</h3>
        <p>参加学校认定的各类竞赛并获奖，可获得相应积分：</p>
        <div class="rules-table">
          <div class="rules-row header"><span>奖项等级</span><span>获得积分</span><span>说明</span></div>
          <div class="rules-row"><span>A1（国家级特等）</span><span class="points-val">100分</span><span>A类竞赛最高奖</span></div>
          <div class="rules-row"><span>A2（国家级一等）</span><span class="points-val">80分</span><span>A类竞赛一等奖</span></div>
          <div class="rules-row"><span>A3（国家级二等）</span><span class="points-val">60分</span><span>A类竞赛二等奖</span></div>
          <div class="rules-row"><span>B1（国家级一等）</span><span class="points-val">50分</span><span>B类竞赛一等奖</span></div>
          <div class="rules-row"><span>B2（国家级二等）</span><span class="points-val">40分</span><span>B类竞赛二等奖</span></div>
          <div class="rules-row"><span>B3（国家级三等）</span><span class="points-val">30分</span><span>B类竞赛三等奖</span></div>
          <div class="rules-row"><span>C1（省级一等）</span><span class="points-val">20分</span><span>省级竞赛一等奖</span></div>
          <div class="rules-row"><span>C2（省级二等）</span><span class="points-val">15分</span><span>省级竞赛二等奖</span></div>
          <div class="rules-row"><span>C3（省级三等）</span><span class="points-val">10分</span><span>省级竞赛三等奖</span></div>
          <div class="rules-row"><span>D1（校级一等）</span><span class="points-val">8分</span><span>校级竞赛一等奖</span></div>
          <div class="rules-row"><span>D2（校级二等）</span><span class="points-val">5分</span><span>校级竞赛二等奖</span></div>
          <div class="rules-row"><span>D3（校级三等）</span><span class="points-val">3分</span><span>校级竞赛三等奖</span></div>
        </div>
      </div>

      <div class="rules-card">
        <h3>📅 日常打卡积分</h3>
        <p>坚持每日心情打卡，养成良好习惯：</p>
        <div class="rules-table">
          <div class="rules-row header"><span>行为</span><span>获得积分</span><span>说明</span></div>
          <div class="rules-row"><span>每日打卡</span><span class="points-val">5分</span><span>每天首次心情打卡</span></div>
          <div class="rules-row"><span>连续7天打卡</span><span class="points-val">20分</span><span>额外奖励</span></div>
          <div class="rules-row"><span>连续30天打卡</span><span class="points-val">100分</span><span>额外奖励</span></div>
        </div>
      </div>

      <div class="rules-card">
        <h3>⭐ 等级说明</h3>
        <p>根据累计积分自动晋升等级：</p>
        <div class="rules-table">
          <div class="rules-row header"><span>等级</span><span>所需积分</span><span>说明</span></div>
          <div class="rules-row"><span>🌱 新手</span><span class="points-val">0分</span><span>初始等级</span></div>
          <div class="rules-row"><span>⭐ 入门</span><span class="points-val">100分</span><span>开始积累</span></div>
          <div class="rules-row"><span>🔥 进阶</span><span class="points-val">300分</span><span>持续参与</span></div>
          <div class="rules-row"><span>💪 熟练</span><span class="points-val">500分</span><span>活跃分子</span></div>
          <div class="rules-row"><span>🏆 精通</span><span class="points-val">1000分</span><span>竞赛达人</span></div>
          <div class="rules-row"><span>👑 大师</span><span class="points-val">2000分</span><span>顶尖水平</span></div>
        </div>
      </div>
    </div>

    <!-- 积分兑换 -->
    <div v-if="activeTab === 'exchange'" class="exchange-section">
      <ExchangeShop />
    </div>
  </section>
</template>

<style scoped>
/* 数字统一等宽，数值变化时列宽不抖 */
.ptsx-num {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
}

/* ==================== 等级流（概览） ==================== */
.ptsx-level-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.ptsx-level-chip {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 104px;
  padding: 9px 13px;
  border-radius: 12px;
  border: 1px solid #d8ded4;
  background: #f7f8f3;
}

.ptsx-level-chip.is-current {
  border-color: #397f72;
  background: #e8f4f0;
}

.ptsx-level-chip.is-max {
  flex-direction: row;
  align-items: center;
  gap: 7px;
  border-color: #dcc78a;
  background: #fdf6e3;
  color: #8a6a1f;
}

.ptsx-level-chip-label {
  font-size: 11px;
  letter-spacing: 0.04em;
  color: #8b9794;
}

.ptsx-level-chip strong {
  font-size: 15px;
  font-weight: 700;
  color: #172b2a;
}

.ptsx-level-chip.is-current strong {
  color: #2d6659;
}

.ptsx-level-chip.is-max strong {
  color: #8a6a1f;
}

.ptsx-level-chip-min {
  font-size: 11px;
  color: #8b9794;
}

.ptsx-level-arrow {
  flex: none;
  color: #b0b9b6;
}

.ptsx-level-need b {
  color: #2d6659;
  font-size: 15px;
}

.ptsx-level-pct {
  padding: 2px 9px;
  border-radius: 999px;
  background: #eef4ef;
  font-size: 12px;
  font-weight: 700;
  color: #397f72;
}

/* ==================== 成长曲线 ==================== */
.ptsx-curve-canvas {
  width: 100%;
  padding: 2px 0 0;
  border-radius: 14px;
  border: 1px solid #e4e9df;
  background: linear-gradient(180deg, #f8faf5, #fffef8);
  overflow: hidden;
}

.ptsx-curve-canvas svg {
  display: block;
  width: 100%;
  height: auto;
}

.ptsx-curve-grid {
  stroke: #dfe5d8;
  stroke-width: 1;
  stroke-dasharray: 3 5;
}

.ptsx-curve-tick {
  font-size: 10.5px;
  fill: #93a09c;
  font-variant-numeric: tabular-nums;
}

.ptsx-curve-endlabel {
  font-size: 12px;
  font-weight: 700;
  fill: #2d6659;
  font-variant-numeric: tabular-nums;
}

.ptsx-curve-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.ptsx-curve-stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid #e4e9df;
  background: #f7f8f3;
}

.ptsx-curve-stat span {
  font-size: 11.5px;
  color: #8b9794;
}

.ptsx-curve-stat b {
  font-size: 18px;
  font-weight: 700;
  color: #172b2a;
}

.ptsx-curve-note {
  margin: 10px 0 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: #98a3a0;
}

.ptsx-curve-state {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 10px;
  padding: 20px 18px;
  border-radius: 14px;
  border: 1px dashed #d8ded4;
  background: #f9faf5;
}

.ptsx-curve-state p {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: #667572;
}

.ptsx-curve-state.is-error {
  border-color: #e8bcb4;
  background: #fff7f4;
}

.ptsx-curve-state.is-error p {
  color: #9e3030;
}

.ptsx-retry {
  padding: 6px 14px;
  border: 1px solid #cdd8cd;
  border-radius: 9px;
  background: #fffef8;
  font-size: 12px;
  font-weight: 700;
  color: #397f72;
  cursor: pointer;
  transition: background 0.18s ease;
}

.ptsx-retry:hover {
  background: #eef4ef;
}

/* ==================== 徽章墙 ==================== */
.ptsx-badges {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ptsx-badge-summary {
  padding: 18px 20px;
  border-radius: 16px;
  border: 1px solid #d8ded4;
  background: rgba(255, 254, 248, 0.98);
}

.ptsx-badge-summary-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.ptsx-badge-summary-head strong {
  font-size: 15px;
  color: #172b2a;
}

.ptsx-badge-summary-head p {
  margin: 5px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: #8b9794;
}

.ptsx-badge-summary-pct {
  flex: none;
  font-size: 22px;
  font-weight: 700;
  color: #397f72;
}

.ptsx-progress {
  height: 9px;
  margin-top: 12px;
  border-radius: 999px;
  background: #eef1ea;
  overflow: hidden;
}

.ptsx-progress-sm {
  height: 6px;
  margin-top: 0;
  background: #e6eade;
}

.ptsx-progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #397f72, #74c2ab);
  transition: width 0.5s ease;
}

.ptsx-badge-next {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  padding-top: 11px;
  border-top: 1px dashed #e2e7dd;
  font-size: 12.5px;
  color: #667572;
}

.ptsx-badge-next b {
  color: #2d6659;
  font-size: 14px;
}

.ptsx-badge-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(268px, 1fr));
  gap: 14px;
}

.ptsx-badge-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-radius: 14px;
  border: 1px solid #d8ded4;
  background: rgba(255, 254, 248, 0.98);
}

.ptsx-badge-card.is-earned {
  border-color: #8ec3b0;
  background: linear-gradient(150deg, #f2faf6, #e6f4ee);
  box-shadow: 0 3px 12px rgba(45, 102, 89, 0.1);
}

/* 未获得：整体灰度 + 压暗，进度条仍靠深色填充保持可读 */
.ptsx-badge-card.is-locked {
  filter: grayscale(1);
  opacity: 0.55;
}

.ptsx-badge-top {
  display: flex;
  align-items: flex-start;
  gap: 11px;
}

.ptsx-badge-emoji {
  flex: none;
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  border-radius: 12px;
  background: #f5f4eb;
}

.ptsx-badge-card.is-earned .ptsx-badge-emoji {
  background: #dcefe6;
}

.ptsx-badge-title {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ptsx-badge-title strong {
  font-size: 14px;
  color: #172b2a;
}

.ptsx-badge-title small {
  font-size: 11.5px;
  line-height: 1.6;
  color: #7c8a86;
}

.ptsx-badge-tag {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.ptsx-badge-tag.is-earned {
  background: #d7ece2;
  color: #2d6659;
}

.ptsx-badge-tag.is-locked {
  background: #f0f0e8;
  color: #8b9794;
}

.ptsx-badge-foot {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ptsx-badge-date {
  font-size: 11.5px;
  color: #397f72;
}

.ptsx-badge-date.is-muted {
  color: #93a09c;
}

.ptsx-badge-progress-text {
  font-size: 11.5px;
  color: #7c8a86;
}

.ptsx-badge-progress-text b {
  color: #4c5a57;
}

@media (max-width: 680px) {
  .ptsx-level-flow {
    gap: 8px;
  }

  .ptsx-level-chip {
    min-width: 88px;
    padding: 8px 11px;
  }

  .ptsx-curve-stats {
    grid-template-columns: 1fr;
  }

  .ptsx-badge-grid {
    grid-template-columns: 1fr;
  }
}

/* ==================== 五育分布 ==================== */
.five-summary {
  margin: 0 0 14px;
  font-size: .88rem;
  line-height: 1.7;
  color: #172b2a;
}

.five-bars {
  display: grid;
  gap: 9px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.five-bars li {
  display: grid;
  grid-template-columns: 28px 1fr 84px 1fr;
  align-items: center;
  gap: 10px;
}

.five-label {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  background: #dfece5;
  color: #173f43;
  font-size: .86rem;
  font-weight: 700;
}

.five-track {
  height: 8px;
  border-radius: 999px;
  background: #eef1ea;
  overflow: hidden;
}

.five-track i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #397f72, #6aa899);
  transition: width .3s ease;
}

.five-value {
  font-size: .86rem;
  font-weight: 700;
  color: #172b2a;
  font-variant-numeric: tabular-nums;
}

.five-value em {
  margin-left: 4px;
  font-style: normal;
  font-size: .72rem;
  font-weight: 600;
  color: #667572;
}

.five-note {
  font-size: .74rem;
  color: #667572;
}

.five-unclassified,
.five-foot {
  margin: 12px 0 0;
  font-size: .76rem;
  line-height: 1.65;
  color: #667572;
}

.five-unclassified {
  color: #8a6a3d;
}

.five-error {
  margin: 0;
  font-size: .82rem;
  color: #b63d3d;
}

@media (max-width: 720px) {
  .five-bars li {
    grid-template-columns: 28px 1fr 76px;
  }

  .five-note {
    display: none;
  }
}
</style>
