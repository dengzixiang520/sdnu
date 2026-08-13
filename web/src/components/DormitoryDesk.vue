<script setup lang="ts">
import { ref } from 'vue'
import { command } from '../api'

interface Event { 
  title: string
  starts_at: string
  ends_at: string
  location?: string
  day_of_week?: string
}

interface Transfer { 
  from_member_id: string
  to_member_id: string
  amount: string 
}

const timetable = ref('2026-09-01 08:00-09:40 高等数学 @ A101\n2026-09-01 14:00-15:40 数据结构 @ B202')
const events = ref<Event[]>([])
const parseMessage = ref('')
const amount = ref('36.00')
const payer = ref('我')
const members = ref('我, 小林, 小周')
const transfers = ref<Transfer[]>([])
const suggestion = ref('')
const observation = ref('阳台物品暂未归位')
const loading = ref(false)
const error = ref('')

// 文件上传相关
const fileInput = ref<HTMLInputElement | null>(null)
const uploadProgress = ref('')
const dragover = ref(false)

// 解析模式：text 或 file
const parseMode = ref<'text' | 'file'>('text')

async function importTimetable() {
  loading.value = true
  error.value = ''
  try {
    const result = await command('dormitory', 'parse_text_timetable', timetable.value)
    events.value = result.data.events as Event[]
    parseMessage.value = result.message
  } catch (err) {
    parseMessage.value = err instanceof Error ? err.message : '解析失败'
  } finally {
    loading.value = false
  }
}

async function parseWithAI() {
  loading.value = true
  error.value = ''
  try {
    const response = await fetch('/api/v1/timetable/parse-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: timetable.value })
    })
    const result = await response.json()
    if (result.success) {
      events.value = result.events
      parseMessage.value = result.message
    } else {
      error.value = result.message || '解析失败'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'AI解析失败'
  } finally {
    loading.value = false
  }
}

async function uploadFile(file: File) {
  loading.value = true
  error.value = ''
  uploadProgress.value = '正在上传和解析...'
  
  try {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await fetch('/api/v1/timetable/upload', {
      method: 'POST',
      body: formData
    })
    
    const result = await response.json()
    
    if (result.success) {
      events.value = result.events
      parseMessage.value = result.message
      uploadProgress.value = ''
    } else {
      error.value = result.message || '上传失败'
      uploadProgress.value = ''
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '上传失败'
    uploadProgress.value = ''
  } finally {
    loading.value = false
  }
}

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    uploadFile(input.files[0])
  }
}

function handleDrop(event: DragEvent) {
  event.preventDefault()
  dragover.value = false
  
  if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
    uploadFile(event.dataTransfer.files[0])
  }
}

function handleDragOver(event: DragEvent) {
  event.preventDefault()
  dragover.value = true
}

function handleDragLeave() {
  dragover.value = false
}

function triggerFileInput() {
  fileInput.value?.click()
}

async function settle() {
  const participant_ids = members.value.split(/[,，]/).map((item) => item.trim()).filter(Boolean)
  if (Number(amount.value) <= 0 || participant_ids.length < 2 || !participant_ids.includes(payer.value.trim())) {
    error.value = '请填写有效金额，并确保付款人在参与成员中'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const result = await command('dormitory', 'settle_expenses', '', {
      expenses: [{ 
        description: '宿舍公用支出', 
        amount: amount.value, 
        payer_id: payer.value, 
        participant_ids 
      }]
    })
    transfers.value = result.data.transfers as Transfer[]
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '分摊失败'
  } finally {
    loading.value = false
  }
}

async function improve() {
  if (!observation.value.trim()) {
    error.value = '请填写观察到的情况'
    return
  }
  try {
    const result = await command('dormitory', 'improvement_suggestion', '', {
      inspection: { 
        dormitory_label: '本宿舍', 
        observations: [observation.value], 
        strengths: ['共同维护的意识'] 
      }
    })
    suggestion.value = String(result.data.suggestion ?? result.message)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '生成失败'
  }
}

function formatTime(dateStr: string) {
  try {
    return new Date(dateStr).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } catch {
    return dateStr
  }
}

function getDayOfWeek(dateStr: string) {
  try {
    const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    return days[new Date(dateStr).getDay()]
  } catch {
    return ''
  }
}
</script>

<template>
  <section class="dorm-page">
    <header class="dorm-head">
      <div>
        <p class="eyebrow">生活协同 / 宿舍与日程</p>
        <h1>课表、账目、<em>值日安排。</em></h1>
      </div>
      <p>所有建议只生成草案，调班与转账仍由成员确认。</p>
    </header>
    
    <p v-if="error" class="inline-error page-error">{{ error }}</p>
    
    <div class="dorm-grid">
      <!-- 课表与行程 -->
      <article class="timetable-panel">
        <p class="micro">01 / 课表与行程</p>
        
        <!-- 解析模式切换 -->
        <div class="parse-mode-switch">
          <button 
            :class="{ active: parseMode === 'text' }" 
            @click="parseMode = 'text'"
          >
            文本输入
          </button>
          <button 
            :class="{ active: parseMode === 'file' }" 
            @click="parseMode = 'file'"
          >
            文件上传
          </button>
        </div>
        
        <!-- 文本输入模式 -->
        <div v-if="parseMode === 'text'">
          <textarea 
            v-model="timetable" 
            class="schedule-input" 
            aria-label="文本课表"
            placeholder="输入课表文本，格式：日期 时间 课程名 @ 地点"
          ></textarea>
          <div class="panel-action">
            <span>{{ parseMessage }}</span>
            <button class="ink-button" :disabled="loading" @click="importTimetable">
              {{ loading ? '解析中...' : '本地解析' }}
            </button>
            <button class="ink-button primary" :disabled="loading" @click="parseWithAI">
              {{ loading ? '解析中...' : 'AI 解析' }}
            </button>
          </div>
        </div>
        
        <!-- 文件上传模式 -->
        <div v-else class="file-upload-section">
          <div 
            class="upload-area"
            :class="{ dragover }"
            @drop="handleDrop"
            @dragover="handleDragOver"
            @dragleave="handleDragLeave"
            @click="triggerFileInput"
          >
            <input 
              ref="fileInput"
              type="file" 
              accept=".txt,.csv,.xlsx,.xls,.ics,.pdf"
              style="display: none"
              @change="handleFileSelect"
            >
            <div class="upload-icon">📁</div>
            <p class="upload-text">
              {{ uploadProgress || '点击或拖拽文件到此处上传' }}
            </p>
            <p class="upload-hint">支持 .txt .csv .xlsx .xls .ics .pdf 格式</p>
          </div>
        </div>
        
        <!-- 课表结果 -->
        <div v-if="events.length" class="event-list">
          <div v-for="event in events" :key="`${event.title}${event.starts_at}`" class="event-row">
            <div class="event-time">
              <time>{{ formatTime(event.starts_at) }}</time>
              <span class="event-day">{{ event.day_of_week || getDayOfWeek(event.starts_at) }}</span>
            </div>
            <div class="event-info">
              <b>{{ event.title }}</b>
              <span>{{ event.location || '地点待定' }}</span>
            </div>
          </div>
        </div>
      </article>

      <!-- 公用记账 -->
      <article class="split-panel">
        <p class="micro">02 / 公用记账</p>
        <h2>按分计算，生成清晰的转账建议。</h2>
        <label>金额<input v-model="amount" inputmode="decimal" /></label>
        <label>付款人<input v-model="payer" /></label>
        <label>参与成员<input v-model="members" /></label>
        <button class="ink-button" :disabled="loading" @click="settle">计算 AA 分摊</button>
        <ul v-if="transfers.length" class="transfer-list">
          <li v-for="transfer in transfers" :key="`${transfer.from_member_id}${transfer.to_member_id}`">
            {{ transfer.from_member_id }} <span>→</span> {{ transfer.to_member_id }} <strong>¥{{ transfer.amount }}</strong>
          </li>
        </ul>
        <p v-else class="empty-state">填写金额和成员后计算。</p>
      </article>

      <!-- 整改建议 -->
      <article class="suggestion-panel">
        <p class="micro">03 / 整改建议</p>
        <h2>把检查记录改写为可执行建议。</h2>
        <label>观察到的情况<input v-model="observation" /></label>
        <button class="soft-button" @click="improve">生成建议</button>
        <p v-if="suggestion" class="suggestion-copy">{{ suggestion }}</p>
      </article>
    </div>
  </section>
</template>