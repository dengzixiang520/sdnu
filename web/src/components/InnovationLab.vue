<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { PhArrowSquareOut, PhFilePlus, PhFunnel, PhLightbulb, PhMagnifyingGlass, PhNewspaper, PhRocketLaunch, PhUsersThree, PhTrophy, PhCalendar, PhUsers, PhStar } from '@phosphor-icons/vue'
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

// 导入竞赛数据
async function importCompetitions() {
  try {
    const response = await fetch('/api/v1/competitions/import', { method: 'POST' })
    const data = await response.json()
    if (data.success) {
      await fetchCompetitions()
      submitMessage.value = data.message
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '导入失败'
  }
}

// 过滤后的竞赛
const filteredCompetitions = computed(() => {
  return competitions.value
})

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

onMounted(() => {
  fetchCompetitions()
})
</script>

<template>
  <section class="innovation-page">
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
        <article v-for="comp in filteredCompetitions" :key="comp.id" class="competition-card">
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
              <span v-for="skill in comp.skills" :key="skill" class="skill-tag">{{ skill }}</span>
            </div>
            <div class="awards-list" v-if="comp.awards.length">
              <strong>奖项设置：</strong>
              <span v-for="award in comp.awards" :key="award" class="award-tag">{{ award }}</span>
            </div>
            <div class="tips" v-if="comp.tips">
              <strong>参赛建议：</strong>{{ comp.tips }}
            </div>
          </div>
          <a v-if="comp.website" :href="comp.website" target="_blank" rel="noreferrer" class="website-link">
            官网 <PhArrowSquareOut :size="14" />
          </a>
        </article>
        
        <div v-if="loading" class="feed-empty">加载中...</div>
        <div v-else-if="!filteredCompetitions.length" class="feed-empty">
          没有找到匹配内容。试试更短的关键词。
          <button v-if="competitions.length === 0" @click="importCompetitions" class="import-btn">
            导入竞赛数据
          </button>
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
  </section>
</template>