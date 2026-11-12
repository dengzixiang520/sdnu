<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  PhTrophy, PhStar, PhMedal, PhChartLine, PhUser, PhCalendar, PhGift,
  PhUsers, PhCoins, PhTrendUp, PhArrowRight, PhInfo,
} from '@phosphor-icons/vue'
import { useIdentity } from '../identity'
import { requestJson } from '../api'
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
  try {
    const data = await requestJson<{ success: boolean; data: { records: PointsRecord[] } }>(
      `/api/v1/points/user/${currentUserId.value}/records`, {}, '获取记录失败')
    if (data.success) records.value = data.data.records
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : '获取记录失败'
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
  const today = new Date().toISOString().split('T')[0]
  todayChecked.value = records.value.some(r =>
    r.source === 'checkin' && r.created_at.startsWith(today)
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

function isEarned(badgeId: string) {
  return userPoints.value?.badges?.includes(badgeId) ?? false
}

function goTab(tab: string) {
  activeTab.value = tab
}

onMounted(async () => {
  await fetchUserPoints()
  fetchLeaderboard()
  fetchBadges()
  await fetchRecords()
  checkTodayChecked()
  fetchProducts()
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

        <div class="level-track">
          <div class="level-bar">
            <div class="level-bar-fill" :style="{ width: levelState.pct + '%' }"></div>
          </div>
          <div class="level-meta">
            <span>当前等级 <b>{{ levelState.cur.name }}</b> · 累计 {{ totalPoints }} 分</span>
            <span v-if="levelState.next">
              距「{{ levelState.next.name }}」还差 <b>{{ levelState.need }}</b> 分（{{ levelState.next.min }} 分解锁）
            </span>
            <span v-else>已到最高等级「大师」，继续保持</span>
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

      <!-- 2. 积分从哪来 -->
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

      <!-- 3. 积分花到哪 -->
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

      <!-- 4. 记账口径 -->
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

    <!-- 徽章展示 -->
    <div v-if="activeTab === 'badges'" class="badges-section">
      <div v-for="badge in badges" :key="badge.id" class="badge-item" :class="{ earned: isEarned(badge.id) }">
        <span class="badge-icon">{{ badge.icon }}</span>
        <div class="badge-info">
          <strong>{{ badge.name }}</strong>
          <small>{{ badge.description }}</small>
        </div>
        <span v-if="isEarned(badge.id)" class="badge-status earned">已获得</span>
        <span v-else class="badge-status locked">未解锁</span>
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
