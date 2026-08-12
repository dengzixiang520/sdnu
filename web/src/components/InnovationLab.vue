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

// 选中的竞赛（用于详情视图）
const selectedCompetition = ref<Competition | null>(null)

// 表单数据
const name = ref('')
const edition = ref('')
const url = ref('')
const submitMessage = ref('')
const project = ref('')
const outline = ref<string[]>([])
const matches = ref<Array<{ display_name: string; score: number; matched_skills: string[] }>>([])

// 获取竞赛列表
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

// 查看竞赛详情
function viewDetail(comp: Competition) {
  selectedCompetition.value = comp
}

// 返回列表
function backToList() {
  selectedCompetition.value = null
}

// 难度颜色
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

// 难度描述
function difficultyDesc(difficulty: string) {
  switch (difficulty) {
    case '低': return '入门级竞赛，适合新手参与，获奖相对容易'
    case '中': return '中等难度，需要一定专业基础和准备时间'
    case '中高': return '中高难度，建议有相关项目经验或学习经历'
    case '高': return '高难度竞赛，需要较强的专业能力和团队协作'
    case '极高': return '顶级竞赛，需要深厚的专业功底和丰富的实战经验'
    default: return '难度未知'
  }
}

// 获取竞赛亮点
function getHighlights(comp: Competition): string[] {
  const highlights = []
  if (comp.level === '国家级' || comp.level === '国际级') {
    highlights.push('权威认证，含金量高')
  }
  if (comp.difficulty === '高' || comp.difficulty === '极高') {
    highlights.push('高难度挑战，获奖者备受认可')
  }
  if (comp.teamSize.includes('-') || comp.teamSize.includes('人')) {
    highlights.push('团队协作，培养合作能力')
  }
  if (comp.skills.length > 3) {
    highlights.push('多技能综合考察')
  }
  if (comp.awards.length > 2) {
    highlights.push('多层次奖项设置')
  }
  return highlights.slice(0, 3)
}

onMounted(() => {
  fetchCompetitions()
})
</script>

<template>
  <section class="innovation-page" :class="{ 'detail-mode': selectedCompetition }">
    <!-- 竞赛详情视图 -->
    <div v-if="selectedCompetition" class="competition-detail">
      <!-- 顶部导航栏 -->
      <div class="detail-nav">
        <button class="back-btn" @click="backToList">
          <PhArrowLeft :size="20" /> 返回竞赛列表
        </button>
        <div class="detail-actions">
          <a v-if="selectedCompetition.website" :href="selectedCompetition.website" target="_blank" rel="noreferrer" class="action-btn primary">
            访问官网 <PhArrowSquareOut :size="16" />
          </a>
        </div>
      </div>
      
      <!-- 主要内容区域 -->
      <div class="detail-main">
        <!-- 左侧：竞赛基本信息 -->
        <div class="detail-left">
          <div class="detail-header">
            <div class="detail-tags">
              <span class="category-tag large">{{ selectedCompetition.category }}</span>
              <span class="level-tag large">{{ selectedCompetition.level }}</span>
            </div>
            <h1>{{ selectedCompetition.name }}</h1>
            <p class="detail-subtitle">{{ selectedCompetition.description }}</p>
          </div>
          
          <!-- 竞赛亮点 -->
          <div class="highlights-section">
            <h3><PhTarget :size="20" /> 竞赛亮点</h3>
            <div class="highlights-grid">
              <div v-for="(highlight, index) in getHighlights(selectedCompetition)" :key="index" class="highlight-item">
                <div class="highlight-icon">{{ index + 1 }}</div>
                <span>{{ highlight }}</span>
              </div>
            </div>
          </div>
          
          <!-- 详细描述 -->
          <div class="detail-description-section">
            <h3><PhBookOpen :size="20" /> 竞赛介绍</h3>
            <div class="description-content">
              <p>{{ selectedCompetition.description }}</p>
              <p>该竞赛由<strong>{{ selectedCompetition.organizer || '相关机构' }}</strong>主办，面向全国大学生开放。</p>
              <p v-if="selectedCompetition.teamSize.includes('-')">参赛团队规模为<strong>{{ selectedCompetition.teamSize }}</strong>，需要组建团队共同完成项目。</p>
              <p v-else>该竞赛为<strong>{{ selectedCompetition.teamSize }}</strong>赛制。</p>
            </div>
          </div>
          
          <!-- 参赛建议 -->
          <div v-if="selectedCompetition.tips" class="tips-section">
            <h3><PhLightbulb :size="20" /> 参赛建议</h3>
            <div class="tips-content">
              <p>{{ selectedCompetition.tips }}</p>
            </div>
          </div>
        </div>
        
        <!-- 右侧：关键信息卡片 -->
        <div class="detail-right">
          <!-- 时间信息卡片 -->
          <div class="info-card">
            <h4><PhClock :size="18" /> 时间安排</h4>
            <div class="info-row">
              <span class="label">比赛时间</span>
              <span class="value">{{ selectedCompetition.time || '待更新' }}</span>
            </div>
            <div class="info-row">
              <span class="label">报名截止</span>
              <span class="value highlight">{{ selectedCompetition.registrationDeadline || '待更新' }}</span>
            </div>
          </div>
          
          <!-- 参赛信息卡片 -->
          <div class="info-card">
            <h4><PhUsers :size="18" /> 参赛信息</h4>
            <div class="info-row">
              <span class="label">团队规模</span>
              <span class="value">{{ selectedCompetition.teamSize }}</span>
            </div>
            <div class="info-row">
              <span class="label">竞赛级别</span>
              <span class="value">{{ selectedCompetition.level }}</span>
            </div>
            <div class="info-row">
              <span class="label">主办单位</span>
              <span class="value small">{{ selectedCompetition.organizer || '待更新' }}</span>
            </div>
          </div>
          
          <!-- 难度评估卡片 -->
          <div class="info-card difficulty-card">
            <h4><PhStar :size="18" /> 难度评估</h4>
            <div class="difficulty-visual">
              <div class="difficulty-level" :style="{ color: difficultyColor(selectedCompetition.difficulty) }">
                {{ selectedCompetition.difficulty }}
              </div>
              <div class="difficulty-bar">
                <div class="difficulty-fill" :style="{ width: selectedCompetition.difficulty === '低' ? '20%' : selectedCompetition.difficulty === '中' ? '40%' : selectedCompetition.difficulty === '中高' ? '60%' : selectedCompetition.difficulty === '高' ? '80%' : '100%', backgroundColor: difficultyColor(selectedCompetition.difficulty) }"></div>
              </div>
              <p class="difficulty-desc">{{ difficultyDesc(selectedCompetition.difficulty) }}</p>
            </div>
          </div>
          
          <!-- 所需技能卡片 -->
          <div class="info-card">
            <h4><PhMedal :size="18" /> 所需技能</h4>
            <div class="skills-grid">
              <span v-for="skill in selectedCompetition.skills" :key="skill" class="skill-badge">{{ skill }}</span>
            </div>
          </div>
          
          <!-- 奖项设置卡片 -->
          <div class="info-card">
            <h4><PhTrophy :size="18" /> 奖项设置</h4>
            <div class="awards-grid">
              <div v-for="(award, index) in selectedCompetition.awards" :key="award" class="award-item" :class="{ 'gold': index === 0, 'silver': index === 1, 'bronze': index === 2 }">
                <span class="award-rank">{{ index + 1 }}</span>
                <span class="award-name">{{ award }}</span>
              </div>
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
            <p>这里收录了 {{ competitions.length }} 个大学生常见竞赛，涵盖 {{ categories.length - 1 }} 个类别。</p>
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
            <button 
              v-for="item in categories" 
              :key="item" 
              :class="{ active: category === item }" 
              type="button" 
              @click="category = item; fetchCompetitions()"
            >
              {{ item }}
            </button>
          </div>
        </div>
        
        <section class="notice-stream">
          <article 
            v-for="comp in competitions" 
            :key="comp.id" 
            class="competition-card"
            @click="viewDetail(comp)"
          >
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
                <span :style="{ color: difficultyColor(comp.difficulty) }">
                  <PhStar :size="14" /> 难度: {{ comp.difficulty }}
                </span>
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
          <div v-else-if="!competitions.length" class="feed-empty">
            没有找到匹配内容。试试更短的关键词。
          </div>
        </section>
      </main>

      <aside class="innovation-rail">
        <header><h2>竞赛工具</h2><p>管理竞赛信息和参赛准备。</p></header>
        <nav aria-label="竞赛工具">
          <button :class="{ active: activeTool === 'submit' }" type="button" @click="activeTool = 'submit'">
            <PhFilePlus :size="20" weight="duotone" />
            <span><strong>提交竞赛</strong><small>添加新竞赛信息</small></span>
          </button>
          <button :class="{ active: activeTool === 'team' }" type="button" @click="activeTool = 'team'">
            <PhUsersThree :size="20" weight="duotone" />
            <span><strong>技能组队</strong><small>按项目需求匹配</small></span>
          </button>
          <button :class="{ active: activeTool === 'proposal' }" type="button" @click="activeTool = 'proposal'">
            <PhLightbulb :size="20" weight="duotone" />
            <span><strong>申报书大纲</strong><small>先搭结构再写作</small></span>
          </button>
        </nav>
        
        <section class="innovation-tool-panel">
          <div v-if="activeTool === 'submit'" class="submit-tool">
            <h3>提交一条竞赛信息</h3>
            <label>赛事名称<input v-model="name" placeholder="输入竞赛名称"></label>
            <label>届次<input v-model="edition" placeholder="例如：2026"></label>
            <label>官方链接 <small>可选</small><input v-model="url" type="url" placeholder="https://"></label>
            <button type="button" @click="submitMessage = '功能开发中...'">提交管理员核验</button>
            <p>{{ submitMessage || '审核通过后才会公开并计入积分。' }}</p>
          </div>
          
          <div v-else-if="activeTool === 'team'" class="team-tool">
            <h3>寻找互补队友</h3>
            <label>项目名称<input v-model="project" placeholder="输入项目名称"></label>
            <button type="button" @click="submitMessage = '功能开发中...'">执行技能匹配</button>
            <p>当前使用演示成员数据，接入真实学生技能档案前不会公开联系方式。</p>
          </div>
          
          <div v-else class="proposal-tool">
            <h3>搭建申报书骨架</h3>
            <label>项目名称<input v-model="project" placeholder="输入项目名称"></label>
            <button type="button" @click="submitMessage = '功能开发中...'">生成章节大纲</button>
            <p>大纲只组织结构，不编造团队成果或验证数据。</p>
          </div>
        </section>
        
        <div class="stats-panel">
          <h3>竞赛统计</h3>
          <div class="stat-item">
            <span class="stat-label">总竞赛数</span>
            <span class="stat-value">{{ competitions.length }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">竞赛类别</span>
            <span class="stat-value">{{ categories.length - 1 }}</span>
          </div>
        </div>
        
        <p v-if="error" class="rail-error">{{ error }}</p>
      </aside>
    </template>
  </section>
</template>