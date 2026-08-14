<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { PhTrophy, PhStar, PhMedal, PhChartLine, PhUser, PhCalendar, PhGift } from '@phosphor-icons/vue'
import { useIdentity } from '../identity'

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

const { identity } = useIdentity()
const activeTab = ref<'overview' | 'leaderboard' | 'badges' | 'records'>('overview')
const userPoints = ref<UserPoints | null>(null)
const leaderboard = ref<UserPoints[]>([])
const badges = ref<Badge[]>([])
const records = ref<PointsRecord[]>([])
const loading = ref(false)

const currentUserId = computed(() => identity.value.userId)
const currentUserName = computed(() => identity.value.displayName)

async function fetchUserPoints() {
  try {
    const response = await fetch(`/api/v1/points/user/${currentUserId.value}`)
    const data = await response.json()
    if (data.success && data.data.user) {
      userPoints.value = data.data.user
    }
  } catch (err) {
    console.log('获取用户积分失败')
  }
}

async function fetchLeaderboard() {
  try {
    const response = await fetch('/api/v1/points/leaderboard?limit=20')
    const data = await response.json()
    if (data.success) {
      leaderboard.value = data.data.leaderboard
    }
  } catch (err) {
    console.log('获取排行榜失败')
  }
}

async function fetchBadges() {
  try {
    const response = await fetch('/api/v1/points/badges')
    const data = await response.json()
    if (data.success) {
      badges.value = data.data.badges
    }
  } catch (err) {
    console.log('获取徽章失败')
  }
}

async function fetchRecords() {
  try {
    const response = await fetch(`/api/v1/points/user/${currentUserId.value}/records`)
    const data = await response.json()
    if (data.success) {
      records.value = data.data.records
    }
  } catch (err) {
    console.log('获取记录失败')
  }
}

async function addCheckinPoints() {
  loading.value = true
  try {
    const response = await fetch(`/api/v1/points/checkin/${currentUserId.value}?user_name=${encodeURIComponent(currentUserName.value)}`, { method: 'POST' })
    const data = await response.json()
    if (data.success) {
      await fetchUserPoints()
      await fetchRecords()
    }
  } catch (err) {
    console.log('打卡积分失败')
  } finally {
    loading.value = false
  }
}

function getSourceLabel(source: string) {
  switch (source) {
    case 'competition': return '竞赛获奖'
    case 'checkin': return '每日打卡'
    case 'activity': return '活动参与'
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

onMounted(() => {
  fetchUserPoints()
  fetchLeaderboard()
  fetchBadges()
  fetchRecords()
})
</script>

<template>
  <section class="points-page">
    <header class="points-header">
      <div>
        <h1><PhTrophy :size="28" weight="duotone" /> 积分中心</h1>
        <p>参与竞赛、完成打卡，积累积分兑换奖励</p>
      </div>
    </header>

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
      <button class="checkin-btn" @click="addCheckinPoints" :disabled="loading">
        <PhCalendar :size="20" /> {{ loading ? '打卡中...' : '每日打卡 +5积分' }}
      </button>
    </div>

    <!-- 标签页 -->
    <div class="points-tabs">
      <button :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">概览</button>
      <button :class="{ active: activeTab === 'leaderboard' }" @click="activeTab = 'leaderboard'">排行榜</button>
      <button :class="{ active: activeTab === 'badges' }" @click="activeTab = 'badges'">徽章</button>
      <button :class="{ active: activeTab === 'records' }" @click="activeTab = 'records'">积分记录</button>
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
        <span class="record-points">+{{ record.points }}</span>
      </div>
      <div v-if="records.length === 0" class="empty-state">暂无积分记录</div>
    </div>
  </section>
</template>