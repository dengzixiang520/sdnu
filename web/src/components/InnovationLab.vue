<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { PhArrowSquareOut, PhFilePlus, PhFunnel, PhLightbulb, PhMagnifyingGlass, PhNewspaper, PhRocketLaunch, PhUsersThree, PhTrophy, PhCalendar, PhUsers, PhStar, PhX, PhArrowLeft, PhTarget, PhMedal, PhClock, PhBookOpen } from '@phosphor-icons/vue'
import { command } from '../api'
import { useIdentity } from '../identity'

type Tool = 'submit' | 'team' | 'proposal' | 'review'
interface Competition {
  id: string
  name: string
  category: string
  level: string
  organizer: string
  website: string
  description: string
  teamSize: string
  time: string
  registrationDeadline: string
  difficulty: string
  skills: string[]
  awards: string[]
  tips: string
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

const name = ref('')
const edition = ref('')
const url = ref('')
const submitMessage = ref('')
const project = ref('')
const outline = ref<string[]>([])
const matches = ref<Array<{ display_name: string; score: number; matched_skills: string[] }>>([])

async function fetchCompetitions() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams()
    if (category.value !== '全部') params.append('category', category.value)
    if (search.value) params.append('keyword', search.value)
    const response = await fetch(`/api/v1/competitions?${params}`)
    const data = await response.json()
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

function viewDetail(comp: Competition) {
  selectedCompetition.value = comp
}

function backToList() {
  selectedCompetition.value = null
}

function difficultyColor(difficulty: string) {
  switch (difficulty) {
    case '低': return '#52c41a'
    case '中': return '#1890ff'
    case '中高': return '#faad14'
    case '高': return '#ff7a45'
    case '极高': return '#ff4d4f'
    default: return '#666'
  }
}

function difficultyDesc(difficulty: string) {
  switch (difficulty) {
    case '低': return '入门级，适合新手'
    case '中': return '需要一定基础'
    case '中高': return '建议有相关经验'
    case '高': return '需要较强专业能力'
    case '极高': return '需要深厚专业功底'
    default: return '难度未知'
  }
}

function getHighlights(comp: Competition): string[] {
  const highlights = []
  if (comp.level === '国家级' || comp.level === '国际级') highlights.push('权威认证，含金量高')
  if (comp.difficulty === '高' || comp.difficulty === '极高') highlights.push('高难度挑战')
  if (comp.teamSize.includes('-')) highlights.push('团队协作')
  if (comp.skills.length > 3) highlights.push('多技能综合')
  return highlights.slice(0, 3)
}

onMounted(() => { fetchCompetitions() })
</script>

<template>
  <section class="innovation-page" :class="{ 'detail-mode': selectedCompetition }">
    <!-- 竞赛详情视图 - 横向排版 -->
    <div v-if="selectedCompetition" class="competition-detail">
      <!-- 顶部：返回按钮 + 竞赛名称 -->
      <div class="detail-top-bar">
        <button class="back-btn" @click="backToList">
          <PhArrowLeft :size="18" /> 返回列表
        </button>
        <div class="detail-title-row">
          <h1>{{ selectedCompetition.name }}</h1>
          <div class="detail-tags-inline">
            <span class="category-tag">{{ selectedCompetition.category }}</span>
            <span class="level-tag">{{ selectedCompetition.level }}</span>
          </div>
        </div>
        <a v-if="selectedCompetition.website" :href="selectedCompetition.website" target="_blank" rel="noreferrer" class="website-btn">
          访问官网 <PhArrowSquareOut :size="14" />
        </a>
      </div>
      
      <!-- 横向信息卡片行 -->
      <div class="detail-info-row">
        <div class="info-card-horizontal">
          <div class="info-icon"><PhCalendar :size="24" /></div>
          <div class="info-content">
            <span class="info-label">比赛时间</span>
            <span class="info-value">{{ selectedCompetition.time || '待更新' }}</span>
          </div>
        </div>
        
        <div class="info-card-horizontal">
          <div class="info-icon"><PhClock :size="24" /></div>
          <div class="info-content">
            <span class="info-label">报名截止</span>
            <span class="info-value highlight">{{ selectedCompetition.registrationDeadline || '待更新' }}</span>
          </div>
        </div>
        
        <div class="info-card-horizontal">
          <div class="info-icon"><PhUsers :size="24" /></div>
          <div class="info-content">
            <span class="info-label">团队规模</span>
            <span class="info-value">{{ selectedCompetition.teamSize }}</span>
          </div>
        </div>
        
        <div class="info-card-horizontal">
          <div class="info-icon"><PhStar :size="24" /></div>
          <div class="info-content">
            <span class="info-label">难度等级</span>
            <span class="info-value" :style="{ color: difficultyColor(selectedCompetition.difficulty) }">{{ selectedCompetition.difficulty }}</span>
          </div>
        </div>
        
        <div class="info-card-horizontal">
          <div class="info-icon"><PhTarget :size="24" /></div>
          <div class="info-content">
            <span class="info-label">竞赛级别</span>
            <span class="info-value">{{ selectedCompetition.level }}</span>
          </div>
        </div>
      </div>
      
      <!-- 横向内容区域 -->
      <div class="detail-content-row">
        <!-- 左侧：竞赛介绍 -->
        <div class="detail-main-content">
          <div class="content-section">
            <h3><PhBookOpen :size="20" /> 竞赛介绍</h3>
            <p class="description-text">{{ selectedCompetition.description }}</p>
            <p class="organizer-text">主办单位：{{ selectedCompetition.organizer || '待更新' }}</p>
          </div>
          
          <div v-if="selectedCompetition.tips" class="content-section tips-section">
            <h3><PhLightbulb :size="20" /> 参赛建议</h3>
            <p>{{ selectedCompetition.tips }}</p>
          </div>
        </div>
        
        <!-- 右侧：技能和奖项 -->
        <div class="detail-sidebar">
          <div class="sidebar-card">
            <h4><PhMedal :size="18" /> 所需技能</h4>
            <div class="skills-horizontal">
              <span v-for="skill in selectedCompetition.skills" :key="skill" class="skill-chip">{{ skill }}</span>
            </div>
          </div>
          
          <div class="sidebar-card">
            <h4><PhTrophy :size="18" /> 奖项设置</h4>
            <div class="awards-horizontal">
              <div v-for="(award, index) in selectedCompetition.awards" :key="award" class="award-chip" :class="{ 'gold': index === 0, 'silver': index === 1, 'bronze': index === 2 }">
                {{ award }}
              </div>
            </div>
          </div>
          
          <div class="sidebar-card">
            <h4><PhStar :size="18" /> 难度评估</h4>
            <div class="difficulty-horizontal">
              <div class="difficulty-level-text" :style="{ color: difficultyColor(selectedCompetition.difficulty) }">
                {{ selectedCompetition.difficulty }}
              </div>
              <div class="difficulty-bar-horizontal">
                <div class="difficulty-fill-horizontal" :style="{ width: selectedCompetition.difficulty === '低' ? '20%' : selectedCompetition.difficulty === '中' ? '40%' : selectedCompetition.difficulty === '中高' ? '60%' : selectedCompetition.difficulty === '高' ? '80%' : '100%', backgroundColor: difficultyColor(selectedCompetition.difficulty) }"></div>
              </div>
              <p class="difficulty-desc-horizontal">{{ difficultyDesc(selectedCompetition.difficulty) }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 竞赛列表视图 -->
    <template v-else>
      <main class="innovation-feed">
        <header class="innovation-masthead">
          <div>
            <span><PhNewspaper :size="18" /> 竞赛信息中心</span>
            <h1>发现适合你的竞赛，<br><em>提前规划参赛之路。</em></h1>
            <p>收录 {{ competitions.length }} 个竞赛，{{ categories.length - 1 }} 个类别</p>
          </div>
          <div class="launch-stamp">
            <PhTrophy :size="38" weight="duotone" />
            <strong>COMPETE<br>&<br>WIN</strong>
          </div>
        </header>
        
        <div class="feed-controls">
          <label>
            <PhMagnifyingGlass :size="19" />
            <input v-model="search" placeholder="搜索竞赛名称、技能或关键词" @input="fetchCompetitions">
          </label>
          <div>
            <PhFunnel :size="17" />
            <button v-for="item in categories" :key="item" :class="{ active: category === item }" type="button" @click="category = item; fetchCompetitions()">
              {{ item }}
            </button>
          </div>
        </div>
        
        <section class="notice-stream">
          <article v-for="comp in competitions" :key="comp.id" class="competition-card" @click="viewDetail(comp)">
            <div class="notice-kind">
              <span class="category-tag">{{ comp.category }}</span>
              <span class="level-tag">{{ comp.level }}</span>
            </div>
            <div class="competition-info">
              <h2>{{ comp.name }}</h2>
              <p class="description">{{ comp.description }}</p>
              <div class="competition-meta">
                <span><PhCalendar :size="14" /> {{ comp.time }}</span>
                <span><PhUsers :size="14" /> {{ comp.teamSize }}</span>
                <span :style="{ color: difficultyColor(comp.difficulty) }"><PhStar :size="14" /> {{ comp.difficulty }}</span>
              </div>
              <div class="skills-list">
                <span v-for="skill in comp.skills.slice(0, 3)" :key="skill" class="skill-tag">{{ skill }}</span>
                <span v-if="comp.skills.length > 3" class="skill-tag more">+{{ comp.skills.length - 3 }}</span>
              </div>
            </div>
            <div class="card-footer">
              <span class="view-detail">查看详情 →</span>
            </div>
          </article>
          
          <div v-if="loading" class="feed-empty">加载中...</div>
          <div v-else-if="!competitions.length" class="feed-empty">没有找到匹配内容</div>
        </section>
      </main>

      <aside class="innovation-rail">
        <header><h2>竞赛工具</h2></header>
        <nav aria-label="竞赛工具">
          <button :class="{ active: activeTool === 'submit' }" type="button" @click="activeTool = 'submit'">
            <PhFilePlus :size="20" weight="duotone" />
            <span><strong>提交竞赛</strong><small>添加新竞赛</small></span>
          </button>
          <button :class="{ active: activeTool === 'team' }" type="button" @click="activeTool = 'team'">
            <PhUsersThree :size="20" weight="duotone" />
            <span><strong>技能组队</strong><small>匹配队友</small></span>
          </button>
          <button :class="{ active: activeTool === 'proposal' }" type="button" @click="activeTool = 'proposal'">
            <PhLightbulb :size="20" weight="duotone" />
            <span><strong>申报大纲</strong><small>生成结构</small></span>
          </button>
        </nav>
        
        <section class="innovation-tool-panel">
          <div v-if="activeTool === 'submit'" class="submit-tool">
            <h3>提交竞赛信息</h3>
            <label>赛事名称<input v-model="name" placeholder="输入竞赛名称"></label>
            <label>届次<input v-model="edition" placeholder="例如：2026"></label>
            <button type="button" @click="submitMessage = '功能开发中...'">提交核验</button>
            <p>{{ submitMessage || '审核通过后公开' }}</p>
          </div>
          <div v-else-if="activeTool === 'team'" class="team-tool">
            <h3>寻找队友</h3>
            <label>项目名称<input v-model="project"></label>
            <button type="button" @click="submitMessage = '功能开发中...'">技能匹配</button>
          </div>
          <div v-else class="proposal-tool">
            <h3>申报书骨架</h3>
            <label>项目名称<input v-model="project"></label>
            <button type="button" @click="submitMessage = '功能开发中...'">生成大纲</button>
          </div>
        </section>
        
        <div class="stats-panel">
          <h3>竞赛统计</h3>
          <div class="stat-item"><span>总竞赛数</span><span class="stat-value">{{ competitions.length }}</span></div>
          <div class="stat-item"><span>竞赛类别</span><span class="stat-value">{{ categories.length - 1 }}</span></div>
        </div>
      </aside>
    </template>
  </section>
</template>