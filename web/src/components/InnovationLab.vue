<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { PhArrowSquareOut, PhFilePlus, PhFunnel, PhLightbulb, PhMagnifyingGlass, PhNewspaper, PhRocketLaunch, PhUsersThree, PhTrophy, PhCalendar, PhUsers, PhStar, PhArrowLeft, PhTarget, PhMedal, PhClock, PhBookOpen, PhUpload, PhChartBar } from '@phosphor-icons/vue'
import { command, requestJson } from '../api'
import { useIdentity } from '../identity'

type Tool = 'submit' | 'team' | 'proposal' | 'review' | 'upload'
interface CompetitionDoc {
  title: string
  url: string
  kind: string
}
interface CompetitionValue {
  score: number
  rating: string
  schoolTier: string
  summary: string
  uses: string[]
  nationalAwards: number
  provincialAwards: number
  schoolLevelAwards: number
  totalAwards: number
  rarityNote: string
}
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
  intro?: string
  audience?: string
  value?: CompetitionValue
  website?: string
  registration?: string
  schedule?: string
  fee?: string
  tracks?: string[]
  documents?: CompetitionDoc[]
  highlights?: string[]
  prep?: string
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

/* 含金量五档配色，与后端 rating_of() 的阈值一致 */
const RATING_STYLE: Record<string, { fg: string; bg: string }> = {
  '极高': { fg: '#a8071a', bg: '#fff1f0' },
  '高': { fg: '#d4380d', bg: '#fff7e6' },
  '中高': { fg: '#ad6800', bg: '#fffbe6' },
  '中': { fg: '#237804', bg: '#f6ffed' },
  '一般': { fg: '#595959', bg: '#f5f5f5' },
}

function ratingColor(rating?: string) {
  return (rating && RATING_STYLE[rating]?.fg) || '#595959'
}

function ratingBg(rating?: string) {
  return (rating && RATING_STYLE[rating]?.bg) || '#f5f5f5'
}

const sortBy = ref<'value' | 'awards' | 'default'>('value')

const sortedCompetitions = computed(() => {
  const list = [...competitions.value]
  if (sortBy.value === 'value') {
    list.sort((a, b) => (b.value?.score ?? 0) - (a.value?.score ?? 0))
  } else if (sortBy.value === 'awards') {
    list.sort((a, b) => getTotalAwards(b.awards) - getTotalAwards(a.awards))
  }
  return list
})

const ratingSummary = computed(() => {
  const buckets: Record<string, number> = {}
  for (const c of competitions.value) {
    const r = c.value?.rating
    if (r) buckets[r] = (buckets[r] ?? 0) + 1
  }
  return ['极高', '高', '中高', '中', '一般']
    .filter(r => buckets[r])
    .map(r => ({ rating: r, count: buckets[r] }))
})

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
          <div><span class="info-label">建议队伍人数</span><span class="info-val">{{ selectedCompetition.teamSize }} 人</span></div>
        </div>
        <div class="info-card-h">
          <div class="info-icon"><PhStar :size="22" /></div>
          <div><span class="info-label">难度</span><span class="info-val" :style="{color: difficultyColor(selectedCompetition.difficulty)}">{{ selectedCompetition.difficulty }}</span></div>
        </div>
        <div class="info-card-h">
          <div class="info-icon"><PhTarget :size="22" /></div>
          <div><span class="info-label">学校认定类别</span><span class="info-val">{{ selectedCompetition.level }}</span></div>
        </div>
        <div class="info-card-h">
          <div class="info-icon"><PhTrophy :size="22" /></div>
          <div><span class="info-label">校内获奖总数</span><span class="info-val">{{ getTotalAwards(selectedCompetition.awards) }} 项</span></div>
        </div>
      </div>

      <!-- 含金量 -->
      <div v-if="selectedCompetition.value" class="value-block">
        <div class="value-head">
          <div class="value-score-box" :style="{ backgroundColor: ratingBg(selectedCompetition.value.rating), borderColor: ratingColor(selectedCompetition.value.rating) }">
            <span class="value-score" :style="{ color: ratingColor(selectedCompetition.value.rating) }">{{ selectedCompetition.value.score }}</span>
            <span class="value-score-unit">/ 100</span>
          </div>
          <div class="value-head-text">
            <div class="value-title-row">
              <h3><PhChartBar :size="20" weight="duotone" /> 含金量</h3>
              <span class="value-rating" :style="{ color: ratingColor(selectedCompetition.value.rating), backgroundColor: ratingBg(selectedCompetition.value.rating), borderColor: ratingColor(selectedCompetition.value.rating) }">
                {{ selectedCompetition.value.rating }}
              </span>
              <span class="value-tier">学校认定 {{ selectedCompetition.value.schoolTier }}</span>
            </div>
            <p class="value-summary">{{ selectedCompetition.value.summary }}</p>
          </div>
        </div>

        <div class="value-bar">
          <div class="value-bar-fill" :style="{ width: selectedCompetition.value.score + '%', background: ratingColor(selectedCompetition.value.rating) }"></div>
        </div>

        <div class="value-meta">
          <span><b>{{ selectedCompetition.value.nationalAwards }}</b> 项国家级认定</span>
          <span><b>{{ selectedCompetition.value.provincialAwards }}</b> 项省级认定</span>
          <span><b>{{ selectedCompetition.value.schoolLevelAwards }}</b> 项校级</span>
          <span class="value-rarity">{{ selectedCompetition.value.rarityNote }}</span>
        </div>

        <div class="value-uses">
          <span class="value-uses-label">这个奖项能用在</span>
          <span v-for="use in selectedCompetition.value.uses" :key="use" class="value-use-chip">{{ use }}</span>
        </div>
      </div>

      <!-- 简介 + 官网 -->
      <div class="detail-body">
        <div class="detail-desc-block">
          <h3><PhBookOpen :size="20" /> 竞赛简介</h3>
          <p v-if="selectedCompetition.intro" class="competition-intro">{{ selectedCompetition.intro }}</p>
          <p><strong>主办单位：</strong>{{ selectedCompetition.organizer || '以当年通知为准' }}</p>
          <p v-if="selectedCompetition.audience" class="audience-line">
            <strong>适合谁：</strong>{{ selectedCompetition.audience }}
          </p>
          <p class="detail-links-row">
            <a v-if="selectedCompetition.website" :href="selectedCompetition.website" target="_blank" rel="noopener noreferrer" class="official-link">
              <PhArrowSquareOut :size="15" /> 访问官网
            </a>
            <span v-if="selectedCompetition.registration" class="detail-inline-note">
              报名参考：{{ selectedCompetition.registration }}
            </span>
          </p>
        </div>
      </div>

      <!-- 赛事亮点 -->
      <div v-if="selectedCompetition.highlights?.length" class="detail-highlights">
        <h3><PhLightbulb :size="20" /> 赛事亮点与注意事项</h3>
        <ul>
          <li v-for="item in selectedCompetition.highlights" :key="item">{{ item }}</li>
        </ul>
      </div>

      <!-- 关键信息：报名、赛程、费用、赛道 -->
      <div class="detail-keyfacts">
        <div class="keyfact">
          <span class="keyfact-label"><PhCalendar :size="15" /> 大致报名时间</span>
          <p>{{ selectedCompetition.registration || '以当年通知为准' }}</p>
        </div>
        <div class="keyfact">
          <span class="keyfact-label"><PhClock :size="15" /> 赛程安排</span>
          <p>{{ selectedCompetition.schedule || '以当年通知为准' }}</p>
        </div>
        <div class="keyfact">
          <span class="keyfact-label">💰 大致费用</span>
          <p>{{ selectedCompetition.fee || '以当年通知为准' }}</p>
        </div>
        <div class="keyfact">
          <span class="keyfact-label"><PhFunnel :size="15" /> 赛道 / 组别</span>
          <div class="chip-wrap tight">
            <span v-for="track in selectedCompetition.tracks" :key="track" class="chip">{{ track }}</span>
            <span v-if="!selectedCompetition.tracks?.length" class="keyfact-empty">以当年通知为准</span>
          </div>
        </div>
      </div>
      <p class="keyfacts-note">报名时间、赛程与费用为往年规律整理，用于提前规划；具体以主办方当年通知为准。</p>

      <!-- 需要学什么 -->
      <div class="detail-bottom-row">
        <div class="bottom-card">
          <h4><PhMedal :size="18" /> 主要需要学习的内容</h4>
          <div class="chip-wrap">
            <span v-for="s in selectedCompetition.skills" :key="s" class="chip green">{{ s }}</span>
            <span v-if="!selectedCompetition.skills?.length" class="keyfact-empty">暂无</span>
          </div>
        </div>
        <div class="bottom-card">
          <h4><PhLightbulb :size="18" /> 备赛建议</h4>
          <p class="tips-copy">{{ selectedCompetition.tips || '暂无' }}</p>
        </div>
      </div>

      <!-- 备赛路线 -->
      <div v-if="selectedCompetition.prep" class="detail-prep">
        <h3><PhRocketLaunch :size="20" /> 备赛路线（从零到参赛）</h3>
        <p>{{ selectedCompetition.prep }}</p>
      </div>

      <!-- 获奖情况 -->
      <div class="awards-detail">
        <h3><PhTrophy :size="20" /> 校内获奖情况</h3>
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
          <p>校级 / 不入级 = 校级竞赛奖项，或省级以上三等奖未达到学校认定等级</p>
        </div>
      </div>

      <!-- 文档与资源 -->
      <div class="detail-docs">
        <h3><PhBookOpen :size="20" /> 直达链接</h3>
        <div class="doc-list">
          <a v-for="doc in selectedCompetition.documents" :key="doc.url" :href="doc.url" target="_blank" rel="noopener noreferrer" class="doc-link" :class="{ 'is-official': doc.kind === 'official' }">
            <PhArrowSquareOut :size="15" />
            <span>{{ doc.title }}</span>
          </a>
        </div>
        <p class="keyfacts-note">链接均指向官网或官方通知页，点击在新标签页打开。</p>
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
          <span>获奖数据为 2024-2025 学年学校统计结果；含金量评分综合学校认定类别、国家级获奖突破与赛事行业认可度换算，仅供参考；报名时间、赛程与费用为往年规律整理，具体以主办方当年通知为准。</span>
        </div>
        
        <div class="feed-controls">
          <label><PhMagnifyingGlass :size="19" /><input v-model="search" placeholder="搜索竞赛" @input="fetchCompetitions"></label>
          <div><PhFunnel :size="17" /><button v-for="item in categories" :key="item" :class="{active:category===item}" @click="category=item;fetchCompetitions()">{{ item }}</button></div>
        </div>

        <div class="sort-row">
          <span class="sort-label">排序</span>
          <button :class="{ active: sortBy === 'value' }" @click="sortBy = 'value'">按含金量</button>
          <button :class="{ active: sortBy === 'awards' }" @click="sortBy = 'awards'">按校内获奖数</button>
          <button :class="{ active: sortBy === 'default' }" @click="sortBy = 'default'">按录入顺序</button>
          <span class="sort-legend">
            <span v-for="item in ratingSummary" :key="item.rating" class="sort-legend-item">
              <i :style="{ backgroundColor: ratingColor(item.rating) }"></i>{{ item.rating }} {{ item.count }}
            </span>
          </span>
        </div>

        <section class="notice-stream">
          <article v-for="comp in sortedCompetitions" :key="comp.id" class="competition-card" @click="viewDetail(comp)">
            <div class="notice-kind">
              <span class="category-tag">{{ comp.category }}</span>
              <span
                v-if="comp.value"
                class="value-badge"
                :style="{ color: ratingColor(comp.value.rating), backgroundColor: ratingBg(comp.value.rating), borderColor: ratingColor(comp.value.rating) }"
                :title="`含金量 ${comp.value.score}/100 · ${comp.value.rating}`"
              >含金量 {{ comp.value.score }}</span>
            </div>
            <div class="competition-info">
              <h2>{{ comp.name }}</h2>
              <p v-if="comp.intro" class="card-intro">{{ comp.intro }}</p>
              <div class="competition-meta">
                <span><PhUsers :size="14" /> {{ comp.teamSize }} 人</span>
                <span :style="{color:difficultyColor(comp.difficulty)}"><PhStar :size="14" /> 难度 {{ comp.difficulty }}</span>
                <span v-if="comp.level"><PhTarget :size="14" /> {{ comp.level }}</span>
                <span><PhTrophy :size="14" /> {{ getTotalAwards(comp.awards) }} 项获奖</span>
              </div>
              <div class="competition-meta muted">
                <span v-if="comp.registration"><PhCalendar :size="14" /> 报名：{{ comp.registration }}</span>
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
          <div class="stat-item"><span>校内获奖记录</span><span class="stat-value">{{ competitions.reduce((s, c) => s + getTotalAwards(c.awards), 0) }}</span></div>
          <div v-if="ratingSummary.length" class="stat-ratings">
            <span v-for="item in ratingSummary" :key="item.rating" class="stat-rating" :style="{ color: ratingColor(item.rating), backgroundColor: ratingBg(item.rating) }">
              {{ item.rating }} {{ item.count }}
            </span>
          </div>
        </div>
      </aside>
    </template>
  </section>
</template>