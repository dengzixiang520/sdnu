<script setup lang="ts">
import { ref, computed } from 'vue'
import { command } from '../api'

interface Event { 
  title: string
  starts_at: string
  ends_at: string
  location?: string
  day_of_week?: string
  teacher?: string
}

interface Transfer { 
  from_member_id: string
  to_member_id: string
  amount: string 
}

interface CustomEvent {
  id: number
  title: string
  day: string
  startTime: string
  endTime: string
  location: string
}

const timetable = ref('周一 08:00-09:40 高等数学 A101 张教授\n周一 14:00-15:40 数据结构 B202 李老师\n周二 10:00-11:40 英语听说 C305 王老师\n周三 14:00-15:40 Python程序设计 D401 赵教授')
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

// 自定义行程
const customEvents = ref<CustomEvent[]>([])
const showAddForm = ref(false)
const newEvent = ref<CustomEvent>({
  id: 0,
  title: '',
  day: '周一',
  startTime: '08:00',
  endTime: '09:00',
  location: ''
})

// 文件上传相关
const fileInput = ref<HTMLInputElement | null>(null)
const uploadProgress = ref('')
const dragover = ref(false)
const parseMode = ref<'text' | 'file'>('text')

// 时间段（学校实际上课时间）
const timeSlots = [
  '08:20', '09:10', '10:10', '11:00',
  '14:00', '14:50', '15:50', '16:40',
  '19:00', '19:50'
]

// 节次信息
const slotInfo: Record<string, { name: string, end: string }> = {
  '08:20': { name: '第1节', end: '09:05' },
  '09:10': { name: '第2节', end: '09:55' },
  '10:10': { name: '第3节', end: '10:55' },
  '11:00': { name: '第4节', end: '11:45' },
  '14:00': { name: '第5节', end: '14:45' },
  '14:50': { name: '第6节', end: '15:35' },
  '15:50': { name: '第7节', end: '16:35' },
  '16:40': { name: '第8节', end: '17:25' },
  '19:00': { name: '第9节', end: '19:45' },
  '19:50': { name: '第10节', end: '20:35' }
}

// 星期
const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

// 将事件转换为表格数据
const timetableGrid = computed(() => {
  const grid: Record<string, Record<string, any>> = {}
  
  weekdays.forEach(day => {
    grid[day] = {}
    timeSlots.forEach(time => {
      grid[day][time] = null
    })
  })
  
  // 填充解析的事件
  events.value.forEach(event => {
    const day = event.day_of_week || getDayOfWeek(event.starts_at)
    const startTime = formatTime(event.starts_at)
    const timeKey = startTime.substring(0, 5)
    
    if (grid[day] && grid[day][timeKey] !== undefined) {
      grid[day][timeKey] = {
        title: event.title,
        location: event.location,
        teacher: event.teacher,
        endTime: formatTime(event.ends_at),
        type: 'course'
      }
    }
  })
  
  // 填充自定义行程
  customEvents.value.forEach(event => {
    const timeKey = event.startTime.substring(0, 5)
    if (grid[event.day] && grid[event.day][timeKey] !== undefined) {
      grid[event.day][timeKey] = {
        title: event.title,
        location: event.location,
        endTime: event.endTime,
        type: 'custom'
      }
    }
  })
  
  return grid
})

async function importTimetable() {
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

function addCustomEvent() {
  if (!newEvent.value.title) {
    error.value = '请输入行程名称'
    return
  }
  
  customEvents.value.push({
    ...newEvent.value,
    id: Date.now()
  })
  
  // 重置表单
  newEvent.value = {
    id: 0,
    title: '',
    day: '周一',
    startTime: '08:00',
    endTime: '09:00',
    location: ''
  }
  showAddForm.value = false
}

function removeCustomEvent(id: number) {
  customEvents.value = customEvents.value.filter(e => e.id !== id)
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
    return '周一'
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
    
    <!-- 课表与行程 -->
    <article class="timetable-panel">
      <p class="micro">01 / 课表与行程</p>
      
      <!-- 解析模式切换 -->
      <div class="parse-mode-switch">
        <button :class="{ active: parseMode === 'text' }" @click="parseMode = 'text'">文本输入</button>
        <button :class="{ active: parseMode === 'file' }" @click="parseMode = 'file'">文件上传</button>
      </div>
      
      <!-- 文本输入模式 -->
      <div v-if="parseMode === 'text'" class="parse-section">
        <textarea v-model="timetable" class="schedule-input" aria-label="文本课表" placeholder="输入课表文本，格式：星期 时间 课程名 地点 教师"></textarea>
        <div class="panel-action">
          <span>{{ parseMessage }}</span>
          <button class="ink-button primary" :disabled="loading" @click="importTimetable">
            {{ loading ? '解析中...' : 'AI 解析课表' }}
          </button>
        </div>
      </div>
      
      <!-- 文件上传模式 -->
      <div v-else class="file-upload-section">
        <div class="upload-area" :class="{ dragover }" @drop="handleDrop" @dragover="handleDragOver" @dragleave="handleDragLeave" @click="triggerFileInput">
          <input ref="fileInput" type="file" accept=".txt,.csv,.xlsx,.xls,.ics,.pdf" style="display: none" @change="handleFileSelect">
          <div class="upload-icon">📁</div>
          <p class="upload-text">{{ uploadProgress || '点击或拖拽文件到此处上传' }}</p>
          <p class="upload-hint">支持 .txt .csv .xlsx .xls .ics .pdf 格式</p>
        </div>
      </div>
      
      <!-- 添加行程按钮 -->
      <div class="add-event-section">
        <button class="ink-button" @click="showAddForm = !showAddForm">
          {{ showAddForm ? '取消添加' : '+ 添加自定义行程' }}
        </button>
      </div>
      
      <!-- 添加行程表单 -->
      <div v-if="showAddForm" class="add-event-form">
        <h3>添加新行程</h3>
        <div class="form-row">
          <label>名称<input v-model="newEvent.title" placeholder="如：社团活动"></label>
          <label>星期<select v-model="newEvent.day">
            <option v-for="day in weekdays" :key="day" :value="day">{{ day }}</option>
          </select></label>
        </div>
        <div class="form-row">
          <label>开始时间<select v-model="newEvent.startTime">
            <option v-for="time in timeSlots" :key="time" :value="time">{{ slotInfo[time]?.name }} {{ time }}</option>
          </select></label>
          <label>结束时间<select v-model="newEvent.endTime">
            <option v-for="time in timeSlots" :key="time" :value="time">{{ slotInfo[time]?.end }}</option>
          </select></label>
          <label>地点<input v-model="newEvent.location" placeholder="选填"></label>
        </div>
        <button class="ink-button primary" @click="addCustomEvent">确认添加</button>
      </div>
      
      <!-- 课表表格 -->
      <div class="timetable-grid">
        <table>
          <thead>
            <tr>
              <th class="time-header">时间</th>
              <th v-for="day in weekdays" :key="day">{{ day }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="time in timeSlots" :key="time">
              <td class="time-cell"><div class="slot-name">{{ slotInfo[time]?.name }}</div><div class="slot-time">{{ time }}</div></td>
              <td v-for="day in weekdays" :key="day" :class="{ 'has-event': timetableGrid[day]?.[time], 'is-custom': timetableGrid[day]?.[time]?.type === 'custom' }">
                <div v-if="timetableGrid[day]?.[time]" class="event-cell">
                  <div class="event-title">{{ timetableGrid[day][time].title }}</div>
                  <div class="event-info">
                    <span v-if="timetableGrid[day][time].location">📍{{ timetableGrid[day][time].location }}</span>
                    <span v-if="timetableGrid[day][time].teacher">👨‍🏫{{ timetableGrid[day][time].teacher }}</span>
                  </div>
                  <button v-if="timetableGrid[day][time].type === 'custom'" class="remove-btn" @click="removeCustomEvent(timetableGrid[day][time].id)">×</button>
                </div>
                <div v-else class="empty-cell">空档</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>

    <!-- 公用记账 -->
    <article class="split-panel">
      <p class="micro">02 / 公用记账</p>
      <h2>按分计算，生成清晰的转账建议。</h2>
      <div class="form-row">
        <label>金额<input v-model="amount" inputmode="decimal" /></label>
        <label>付款人<input v-model="payer" /></label>
        <label>参与成员<input v-model="members" /></label>
      </div>
      <button class="ink-button primary" :disabled="loading" @click="settle">计算 AA 分摊</button>
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
  </section>
</template>