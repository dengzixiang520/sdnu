<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { PhArrowSquareOut, PhFilePlus, PhFunnel, PhLightbulb, PhMagnifyingGlass, PhNewspaper, PhRocketLaunch, PhUsersThree, PhTrophy, PhCalendar, PhUsers, PhStar, PhArrowLeft, PhTarget, PhMedal, PhClock, PhBookOpen, PhUpload, PhChartBar } from '@phosphor-icons/vue'
import { command, requestJson } from '../api'
import { useIdentity } from '../identity'

type Tool = 'submit' | 'team' | 'proposal' | 'review' | 'upload'
interface Competition {
  id: string
  name: string
  category: string
  level: string
  organizer: string
  awards: Record<string, number>
  teamSize: string
  schoolParticipants: string
  difficulty: string
  skills: string[]
  tips: string
  isAlevel: boolean
  year: string
  note: string
}

const { identity } = useIdentity()
const activeTool = ref<Tool>('submit')
const search = ref('')
const category = ref('全部')
const competitions = ref<Competition[]>([])
const categories = ref<string[]>([])
const loading = ref(false)
const error = ref('')
const selectedCompetition = ref<Competition | null>(null)

const isStaff = computed(() => identity.value.role === 'counselor' || identity.value.role === 'administrator')

async function fetchCompetitions() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams()
    if (category.value !== '全部') params.append('category', category.value)
    if (search.value) params.append('keyword', search.value)
    const data = await requestJson<{ success: boolean; data: { competitions: Competition[]; categories: string[] } }>(
      `/api/v1/competitions?${params}`, {}, '竞赛库加载失败')
    if (data.success) {
      competitions.value = data.data.competitions
      categories.value = ['全部', ...data.data.categories]
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function viewDetail(comp: Competition) { selectedCompetition.value = comp }
function backToList() { selectedCompetition.value = null }

function difficultyColor(d: string) {
  switch (d) {
    case '低': return '#52c41a'
    case '中': return '#1890ff'
    case '中高': return '#faad14'
    case '高': return '#ff7a45'
    case '极高': return '#ff4d4f'
    default: return '#666'
  }
}

function awardLevelColor(level: string) {
  if (level.startsWith('A')) return '#ff4d4f'
  if (level.startsWith('B')) return '#ff7a45'
  if (level.startsWith('C')) return '#faad14'
  if (level.startsWith('D')) return '#52c41a'
  return '#999'
}

function awardLevelBg(level: string) {
  if (level.startsWith('A')) return '#fff1f0'
  if (level.startsWith('B')) return '#fff7e6'
  if (level.startsWith('C')) return '#fffbe6'
  if (level.startsWith('D')) return '#f6ffed'
  return '#f5f5f5'
}

function getTotalAwards(awards: Record<string, number>) {
  return Object.values(awards).reduce((sum, count) => sum + count, 0)
}

onMounted(() => { fetchCompetitions() })
</script>

<template>
  <section class="innovation-page" :class="{ 'detail-mode': selectedCompetition }">
    <!-- 竞赛详情 -->
    <div v-if="selectedCompetition" class="competition-detail">
      <div class="detail-top-bar">
        <button class="back-btn" @click="backToList"><PhArrowLeft :size="18" /> 返回列表</button>
        <div class="detail-title-row">
          <h1>{{ selectedCompetition.name }}</h1>
          <span class="category-tag">{{ selectedCompetition.category }}</span>
          <span class="level-tag">{{ selectedCompetition.level }}</span>
        </div>
      </div>
      
      <!-- 数据说明 -->
      <div class="data-notice">
        <PhClock :size="16" />
        <span>{{ selectedCompetition.note }}（{{ selectedCompetition.year }}学年）</span>
      </div>
      
      <!-- 信息卡片行 -->
      <div class="detail-info-row">
        <div class="info-card-h">
          <div class="info-icon"><PhUsers :size="22" /></div>
          <div><span class="info-label">参赛规模</span><span class="info-val">{{ selectedCompetition.teamSize }}</span></div>
        </div>
        <div class="info-card-h">
          <div class="info-icon"><PhStar :size="22" /></div>
          <div><span class="info-label">难度</span><span class="info-val" :style="{color: difficultyColor(selectedCompetition.difficulty)}">{{ selectedCompetition.difficulty }}</span></div>
        </div>
        <div class="info-card-h">
          <div class="info-icon"><PhTrophy :size="22" /></div>
          <div><span class="info-label">获奖总数</span><span class="info-val">{{ getTotalAwards(selectedCompetition.awards) }}项</span></div>
        </div>
      </div>
      
      <!-- 获奖详情 -->
      <div class="awards-detail">
        <h3><PhTrophy :size="20" /> 获奖情况</h3>
        <div class="awards-grid">
          <div v-for="(count, level) in selectedCompetition.awards" :key="level" class="award-item" :style="{backgroundColor: awardLevelBg(level), borderColor: awardLevelColor(level)}">
            <span class="award-level" :style="{color: awardLevelColor(level)}">{{ level }}</span>
            <span class="award-count">{{ count }}项</span>
          </div>
        </div>
        <div class="award-legend">
          <p><strong>等级说明：</strong></p>
          <p>A1/A2/A3 = A类竞赛国家级特等/一等/二等/三等</p>
          <p>B1/B2/B3 = B类竞赛国家级一等/二等/三等</p>
          <p>C1/C2/C3 = C类竞赛省级一等/二等/三等</p>
          <p>D1/D2/D3 = D类竞赛校级一等/二等/三等</p>
        </div>
      </div>
      
      <!-- 竞赛介绍 -->
      <div class="detail-body">
        <div class="detail-desc-block">
          <h3><PhBookOpen :size="20" /> 竞赛介绍</h3>
          <p>主办单位：{{ selectedCompetition.organizer }}</p>
          <p>{{ selectedCompetition.tips }}</p>
        </div>
      </div>
      
      <!-- 所需技能 -->
      <div class="detail-bottom-row">
        <div class="bottom-card">
          <h4><PhMedal :size="18" /> 所需技能</h4>
          <div class="chip-wrap">
            <span v-for="s in selectedCompetition.skills" :key="s" class="chip green">{{ s }}</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 竞赛列表 -->
    <template v-else>
      <main class="innovation-feed">
        <header class="innovation-masthead">
          <div>
            <span><PhNewspaper :size="18" /> 竞赛信息中心</span>
            <h1>山东师范大学竞赛成绩，<br><em>以赛促学，以赛促创。</em></h1>
            <p>收录 {{ competitions.length }} 个学校有参赛经验的竞赛，{{ categories.length - 1 }} 个类别</p>
          </div>
          <div class="launch-stamp"><PhTrophy :size="38" weight="duotone" /><strong>SDNU<br>COMPETE</strong></div>
        </header>
        
        <!-- 数据说明 -->
        <div class="data-notice-banner">
          <PhClock :size="16" />
          <span>当前数据为2024-2025学年学校统计结果，仅供参考。后续将上传更多年度数据。</span>
        </div>
        
        <div class="feed-controls">
          <label><PhMagnifyingGlass :size="19" /><input v-model="search" placeholder="搜索竞赛" @input="fetchCompetitions"></label>
          <div><PhFunnel :size="17" /><button v-for="item in categories" :key="item" :class="{active:category===item}" @click="category=item;fetchCompetitions()">{{ item }}</button></div>
        </div>
        
        <section class="notice-stream">
          <article v-for="comp in competitions" :key="comp.id" class="competition-card" @click="viewDetail(comp)">
            <div class="notice-kind">
              <span class="category-tag">{{ comp.category }}</span>
              
            </div>
            <div class="competition-info">
              <h2>{{ comp.name }}</h2>
              <div class="competition-meta">
                <span><PhUsers :size="14" /> {{ comp.teamSize }}</span>
                <span :style="{color:difficultyColor(comp.difficulty)}"><PhStar :size="14" /> {{ comp.difficulty }}</span>
                <span><PhTrophy :size="14" /> {{ getTotalAwards(comp.awards) }}项获奖</span>
              </div>
              <div class="awards-preview">
                <span v-for="(count, level) in comp.awards" :key="level" class="award-badge" :style="{backgroundColor: awardLevelBg(level), color: awardLevelColor(level), borderColor: awardLevelColor(level)}">
                  {{ level }}: {{ count }}
                </span>
              </div>
            </div>
            <div class="card-footer"><span class="view-detail">查看详情 →</span></div>
          </article>
          
          <div v-if="loading" class="feed-empty">加载中...</div>
          <div v-else-if="!competitions.length" class="feed-empty">没有找到匹配内容</div>
        </section>
      </main>

      <aside class="innovation-rail">
        <header><h2>竞赛工具</h2></header>
        <nav>
          <button :class="{active:activeTool==='submit'}" @click="activeTool='submit'"><PhFilePlus :size="20" weight="duotone" /><span><strong>提交竞赛</strong></span></button>
          <button v-if="isStaff" :class="{active:activeTool==='upload'}" @click="activeTool='upload'"><PhUpload :size="20" weight="duotone" /><span><strong>上传成果</strong></span></button>
        </nav>
        <section class="innovation-tool-panel">
          <div v-if="activeTool==='submit'"><h3>提交竞赛信息</h3><p>功能开发中...</p></div>
          <div v-if="activeTool==='upload' && isStaff">
            <h3>上传竞赛成果</h3>
            <p>一键导入全年竞赛获奖数据</p>
            <button class="ink-button primary" @click="error='功能开发中...'">导入竞赛数据</button>
          </div>
        </section>
        <div class="stats-panel">
          <h3>竞赛统计</h3>
          <div class="stat-item"><span>竞赛数</span><span class="stat-value">{{ competitions.length }}</span></div>
          <div class="stat-item"><span>类别数</span><span class="stat-value">{{ categories.length - 1 }}</span></div>
        </div>
      </aside>
    </template>
  </section>
</template>