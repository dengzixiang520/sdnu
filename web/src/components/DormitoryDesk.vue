<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { command, requestJson } from '../api'

// 课程颜色映射
const courseColors: Record<string, { bg: string, border: string, text: string }> = {
  '数字图像处理': { bg: '#e3f2fd', border: '#2196f3', text: '#1565c0' },
  '计算机网络原理': { bg: '#e8f5e9', border: '#4caf50', text: '#2e7d32' },
  '大学生就业指导': { bg: '#fff3e0', border: '#ff9800', text: '#e65100' },
  '计算机图形学': { bg: '#f3e5f5', border: '#9c27b0', text: '#7b1fa2' },
  '现代优化理论与应用': { bg: '#e0f7fa', border: '#00bcd4', text: '#00838f' },
  '世界电影艺术赏析与多元文化理解': { bg: '#fce4ec', border: '#e91e63', text: '#c2185b' },
  '世界电影艺术赏析': { bg: '#fce4ec', border: '#e91e63', text: '#c2185b' },
  '机器学习': { bg: '#f1f8e9', border: '#8bc34a', text: '#558b2f' },
  '算法分析与设计': { bg: '#ede7f6', border: '#673ab7', text: '#4527a0' },
  '形势与政策': { bg: '#fff8e1', border: '#ffc107', text: '#f57f17' },
}

// 默认颜色（当课程不在映射中时使用）
const defaultColors = [
  { bg: '#e3f2fd', border: '#2196f3', text: '#1565c0' },
  { bg: '#e8f5e9', border: '#4caf50', text: '#2e7d32' },
  { bg: '#fff3e0', border: '#ff9800', text: '#e65100' },
  { bg: '#f3e5f5', border: '#9c27b0', text: '#7b1fa2' },
  { bg: '#e0f7fa', border: '#00bcd4', text: '#00838f' },
  { bg: '#fce4ec', border: '#e91e63', text: '#c2185b' },
  { bg: '#f1f8e9', border: '#8bc34a', text: '#558b2f' },
  { bg: '#ede7f6', border: '#673ab7', text: '#4527a0' },
]

// 获取课程颜色
function getCourseColor(title: string, index: number): { bg: string, border: string, text: string } {
  // 先查找精确匹配
  if (courseColors[title]) {
    return courseColors[title]
  }
  
  // 查找部分匹配
  for (const [key, value] of Object.entries(courseColors)) {
    if (title.includes(key) || key.includes(title)) {
      return value
    }
  }
  
  // 使用默认颜色（根据索引循环）
  return defaultColors[index % defaultColors.length]
}

// 课程颜色缓存
const colorCache = new Map<string, { bg: string, border: string, text: string }>()
let colorIndex = 0

function getOrAssignColor(title: string): { bg: string, border: string, text: string } {
  if (!colorCache.has(title)) {
    colorCache.set(title, getCourseColor(title, colorIndex++))
  }
  return colorCache.get(title)!
}

// 加载已保存的课表
async function loadSavedTimetable() {
  try {
    const result = await requestJson<{ success: boolean; events: TimetableEvent[] }>(
      '/api/v1/timetable/saved', {}, '读取已保存课表失败')
    if (result.success && result.events.length > 0) {
      events.value = result.events
      parseMessage.value = `已加载保存的课表（${result.events.length}个课程）`
    }
  } catch (err) {
    // 首次运行没有课表属于正常状态，不打扰用户；真正的故障才提示。
    const message = err instanceof Error ? err.message : ''
    if (message && !message.includes('不存在') && !message.includes('为空')) {
      parseMessage.value = message
    }
  }
}

// 页面加载时读取已保存的课表与回忆记录
onMounted(() => {
  loadSavedTimetable()
  loadMemoryRecords()
})

interface TimetableEvent { 
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

interface CustomScheduleEvent {
  id: number
  title: string
  day: string
  startTime: string
  endTime: string
  location: string
}

const timetable = ref('周一 08:00-09:40 高等数学 A101 张教授\n周一 14:00-15:40 数据结构 B202 李老师\n周二 10:00-11:40 英语听说 C305 王老师\n周三 14:00-15:40 Python程序设计 D401 赵教授')
const events = ref<TimetableEvent[]>([])
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
const customEvents = ref<CustomScheduleEvent[]>([])
const showAddForm = ref(false)
const newEvent = ref<CustomScheduleEvent>({
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

// 记账 + 美好记录
interface MemoryRecord {
  id: number
  createdAt: string
  purpose: string
  amount: string
  payer: string
  members: string[]
  transfers: Transfer[]
  photos: string[]
}

const MEMORY_STORAGE_KEY = 'zhq-memory-records'
const MAX_PHOTOS_PER_RECORD = 6

const purpose = ref('宿舍一起买的东西')
const photos = ref<string[]>([])
const photoInput = ref<HTMLInputElement | null>(null)
const memoryRecords = ref<MemoryRecord[]>([])
const previewPhoto = ref('')
const memoryNotice = ref('')

function loadMemoryRecords() {
  try {
    const raw = localStorage.getItem(MEMORY_STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      memoryRecords.value = parsed as MemoryRecord[]
    }
  } catch {
    // 本地存储损坏或不可用时不打扰用户，只是回忆列表为空。
  }
}

function persistMemoryRecords() {
  try {
    localStorage.setItem(MEMORY_STORAGE_KEY, JSON.stringify(memoryRecords.value))
    return true
  } catch {
    // 照片占空间，配额满了就退化成「只保留文字」，不能让整条记录丢掉。
    try {
      const textOnly = memoryRecords.value.map((record) => ({ ...record, photos: [] }))
      localStorage.setItem(MEMORY_STORAGE_KEY, JSON.stringify(textOnly))
      memoryNotice.value = '本地存储空间不足，照片没有写入磁盘；文字记录已保存。'
    } catch {
      memoryNotice.value = '本地存储不可用，记录只保留在本次会话中。'
    }
    return false
  }
}

// 浏览器端压到 720px / JPEG 0.72：只用于回忆展示，够清楚又能塞进 localStorage。
function compressImage(file: File, maxSide = 720): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const image = new Image()
      image.onload = () => {
        const scale = Math.min(1, maxSide / Math.max(image.width, image.height))
        const canvas = document.createElement('canvas')
        canvas.width = Math.max(1, Math.round(image.width * scale))
        canvas.height = Math.max(1, Math.round(image.height * scale))
        const context = canvas.getContext('2d')
        if (!context) {
          reject(new Error('当前浏览器不支持图片压缩'))
          return
        }
        context.drawImage(image, 0, 0, canvas.width, canvas.height)
        resolve(canvas.toDataURL('image/jpeg', 0.72))
      }
      image.onerror = () => reject(new Error('这张图片读不出来'))
      image.src = String(reader.result)
    }
    reader.onerror = () => reject(new Error('这张图片读不出来'))
    reader.readAsDataURL(file)
  })
}

async function handlePhotoSelect(event: globalThis.Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  memoryNotice.value = ''
  for (const file of files) {
    if (photos.value.length >= MAX_PHOTOS_PER_RECORD) {
      memoryNotice.value = `一条记录最多 ${MAX_PHOTOS_PER_RECORD} 张照片`
      break
    }
    if (!file.type.startsWith('image/')) continue
    try {
      photos.value.push(await compressImage(file))
    } catch (reason) {
      memoryNotice.value = reason instanceof Error ? reason.message : '照片读取失败'
    }
  }
  // 允许重复选同一张图
  input.value = ''
}

function removePhoto(index: number) {
  photos.value.splice(index, 1)
}

function saveMemoryRecord(withSettlement: boolean) {
  const label = purpose.value.trim() || '宿舍公用支出'
  const memberList = members.value.split(/[,，]/).map((item) => item.trim()).filter(Boolean)
  memoryRecords.value.unshift({
    id: Date.now(),
    createdAt: new Date().toISOString(),
    purpose: label,
    amount: amount.value.trim() || '—',
    payer: payer.value.trim(),
    members: memberList,
    transfers: withSettlement ? [...transfers.value] : [],
    photos: [...photos.value]
  })
  persistMemoryRecords()
  photos.value = []
}

// 「只记美好」：不涉及钱、也不需要分摊，纯记录当下这件事。
function saveMemoryOnly() {
  if (!purpose.value.trim() && photos.value.length === 0) {
    error.value = '至少写一句这次是干啥，或者放一张照片'
    return
  }
  error.value = ''
  memoryNotice.value = ''
  saveMemoryRecord(false)
  memoryNotice.value = '已经记下来了，往下翻就能看到。'
}

function removeMemoryRecord(id: number) {
  memoryRecords.value = memoryRecords.value.filter((record) => record.id !== id)
  persistMemoryRecords()
}

function formatMemoryTime(iso: string) {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return iso
  }
}

// 时间段（支持单节和双节课程）
const timeSlots = [
  '08:20', '09:10', '10:10', '11:00',
  '14:00', '14:50', '15:50', '16:40',
  '19:00', '19:50'
]

// 节次信息（与后端 SLOT_TIMES、教务系统原始课表完全一致）
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

// 山师的课是「一个大课 = 两个小课」：每小课 45 分钟，大课内部间隔 5 分钟，
// 大课之间间隔 15 分钟。所以网格按大课分行，每行下面再挂两个小节的时刻。
const bigSlots: { label: string, tag: string, slots: [string, string] }[] = [
  { label: '第一大课', tag: '上午', slots: ['08:20', '09:10'] },
  { label: '第二大课', tag: '上午', slots: ['10:10', '11:00'] },
  { label: '第三大课', tag: '下午', slots: ['14:00', '14:50'] },
  { label: '第四大课', tag: '下午', slots: ['15:50', '16:40'] },
  { label: '晚间大课', tag: '晚上', slots: ['19:00', '19:50'] }
]

// 星期
const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

// 查找最接近的时间段（自定义行程用：用户从下拉里选的时刻一定落在某个小节附近）
function findClosestSlot(timeStr: string): string | null {
  const time = timeStr.substring(0, 5)
  const [hours, minutes] = time.split(':').map(Number)
  const timeMinutes = hours * 60 + minutes
  
  let closestSlot = null
  let minDiff = Infinity
  
  for (const slot of timeSlots) {
    const [slotHours, slotMinutes] = slot.split(':').map(Number)
    const slotTimeMinutes = slotHours * 60 + slotMinutes
    const diff = Math.abs(timeMinutes - slotTimeMinutes)
    
    if (diff < minDiff && diff <= 30) { // 允许30分钟的误差
      minDiff = diff
      closestSlot = slot
    }
  }
  
  return closestSlot
}

function toMinutes(time: string): number {
  const [hours, minutes] = time.split(':').map(Number)
  return hours * 60 + minutes
}

// 每小节的真实起止（分钟）。课程按「区间重叠」落到小节上，
// 而不是按「开始时刻最接近」——否则 11:45 这种结束时刻会因为差 45 分钟被丢掉，
// 一门 3-4 节的课就只剩第 3 节有格子。
const slotBounds = timeSlots.map((slot) => ({
  slot,
  start: toMinutes(slot),
  end: toMinutes(slotInfo[slot]?.end ?? slot)
}))

function slotsCoveredBy(startTime: string, endTime: string): string[] {
  const start = toMinutes(startTime)
  const end = toMinutes(endTime)
  const safeEnd = end > start ? end : start + 1
  const covered = slotBounds
    .filter((bounds) => start < bounds.end && safeEnd > bounds.start)
    .map((bounds) => bounds.slot)
  if (covered.length > 0) return covered
  const fallback = findClosestSlot(startTime)
  return fallback ? [fallback] : []
}

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
    if (!grid[day]) return
    const startTime = formatTime(event.starts_at)
    const endTime = formatTime(event.ends_at)
    const covered = slotsCoveredBy(startTime, endTime)

    covered.forEach((slot, index) => {
      if (grid[day][slot] !== null) return
      grid[day][slot] = {
        title: event.title,
        location: event.location,
        teacher: event.teacher,
        startTime,
        endTime,
        type: 'course',
        // 该格不是这门课的第一小节时，说明课程从上一节延续过来。
        isContinuation: index > 0
      }
    })
  })
  
  // 填充自定义行程
  customEvents.value.forEach(event => {
    if (!grid[event.day]) return
    const covered = slotsCoveredBy(event.startTime, event.endTime)
    covered.forEach((slot, index) => {
      if (grid[event.day][slot] !== null) return
      grid[event.day][slot] = {
        id: event.id,
        title: event.title,
        location: event.location,
        startTime: event.startTime,
        endTime: event.endTime,
        type: 'custom',
        isContinuation: index > 0
      }
    })
  })
  
  return grid
})

interface GridEvent {
  id?: number
  title: string
  location?: string
  teacher?: string
  endTime?: string
  type: 'course' | 'custom'
  isMultiSlot?: boolean
}

// 渲染用的单元格：把「有没有课 / 跨几行 / 是不是续节 / 配色」都在脚本里算好，
// 模板只负责摆位置，避免在模板里写一堆可选链和断言。
interface RenderCell {
  empty: boolean
  rowspan: 1 | 2
  continuation: boolean
  title: string
  location: string
  teacher: string
  bg: string
  border: string
  text: string
  customId: number | null
}

function buildRenderCell(
  event: GridEvent | null,
  rowspan: 1 | 2,
  continuation: boolean
): RenderCell {
  if (!event) {
    return {
      empty: true, rowspan, continuation: false,
      title: '', location: '', teacher: '',
      bg: 'transparent', border: 'transparent', text: 'inherit',
      customId: null
    }
  }
  const color = getOrAssignColor(event.title)
  return {
    empty: false,
    rowspan,
    continuation,
    title: event.title,
    location: event.location ?? '',
    teacher: event.teacher ?? '',
    bg: color.bg,
    border: color.border,
    text: color.text,
    customId: event.type === 'custom' && typeof event.id === 'number' ? event.id : null
  }
}

// 把「每小节一格」的网格重新组织成「每大课一行」：一个大课内的两小节如果是同一门课，
// 就合成一个跨两行的单元格，和教务系统原图一致；跨大课边界的课在下一行标「续」。
const mergedBlocks = computed(() => {
  return bigSlots.map((block, blockIndex) => {
    const [first, second] = block.slots
    const prevSlot = blockIndex > 0 ? bigSlots[blockIndex - 1].slots[1] : null
    const firstCells: Record<string, RenderCell> = {}
    const secondCells: Record<string, RenderCell> = {}

    for (const day of weekdays) {
      const firstEvent = (timetableGrid.value[day]?.[first] ?? null) as GridEvent | null
      const secondEvent = (timetableGrid.value[day]?.[second] ?? null) as GridEvent | null
      const prevTitle = prevSlot ? (timetableGrid.value[day]?.[prevSlot]?.title ?? null) : null

      if (firstEvent && secondEvent && firstEvent.title === secondEvent.title && firstEvent.type === secondEvent.type) {
        firstCells[day] = buildRenderCell(firstEvent, 2, prevTitle === firstEvent.title)
        continue
      }

      firstCells[day] = buildRenderCell(firstEvent, 1, !!firstEvent && prevTitle === firstEvent.title)
      secondCells[day] = buildRenderCell(
        secondEvent,
        1,
        !!secondEvent && !!firstEvent && firstEvent.title === secondEvent.title
      )
    }

    return {
      label: block.label,
      tag: block.tag,
      firstSlot: first,
      secondSlot: second,
      range: `${first}-${slotInfo[second]?.end ?? ''}`,
      firstCells,
      secondCells
    }
  })
})

async function importTimetable() {
  loading.value = true
  error.value = ''
  try {
    const result = await requestJson<{ success: boolean; events: TimetableEvent[]; message?: string }>(
      '/api/v1/timetable/parse-text',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: timetable.value })
      },
      '课表解析失败')
    if (result.success) {
      events.value = result.events
      parseMessage.value = result.message ?? ''
    } else {
      error.value = result.message || '未能识别出任何课程，请检查格式'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '课表解析失败'
  } finally {
    loading.value = false
  }
}

async function uploadFile(file: File) {
  loading.value = true
  error.value = ''
  // 截图识别要跑推理，实测 15–30 秒；先把预期说清楚，免得用户以为卡死又点一次。
  const isImage = /\.(png|jpe?g|bmp|gif)$/i.test(file.name)
  uploadProgress.value = isImage ? '正在识别截图，约需 15–30 秒，请不要重复点击…' : '正在上传和解析...'

  try {
    const formData = new FormData()
    formData.append('file', file)

    const result = await requestJson<{ success: boolean; events: TimetableEvent[]; message?: string }>(
      '/api/v1/timetable/upload', { method: 'POST', body: formData }, '上传失败')

    if (result.success) {
      events.value = result.events
      parseMessage.value = result.message ?? ''
    } else {
      error.value = result.message || '未能从文件中识别出课程'
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    uploadProgress.value = ''
    loading.value = false
  }
}

function handleFileSelect(event: globalThis.Event) {
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
  memoryNotice.value = ''
  try {
    const result = await command('dormitory', 'settle_expenses', '', {
      expenses: [{ 
        // 「这次是干啥」既写进分摊记录，也存进回忆列表。
        description: purpose.value.trim() || '宿舍公用支出', 
        amount: amount.value, 
        payer_id: payer.value, 
        participant_ids 
      }]
    })
    transfers.value = result.data.transfers as Transfer[]
    // 算完账自动落一条回忆记录，不用用户再点保存。
    saveMemoryRecord(true)
    memoryNotice.value = '分摊结果已算好，这条也存进回忆里了。'
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
          <input ref="fileInput" type="file" accept=".txt,.csv,.xlsx,.xls,.ics,.png,.jpg,.jpeg,.bmp" style="display: none" @change="handleFileSelect">
          <div class="upload-icon">📁</div>
          <p class="upload-text">{{ uploadProgress || '点击或拖拽文件到此处上传' }}</p>
          <p class="upload-hint">支持 .txt .csv .xlsx .xls .ics .png .jpg（PDF 解析尚未接入）</p>
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
      
      <!-- 课表表格：按「大课」分行，每大课下挂两个小节的时刻 -->
      <div class="timetable-grid">
        <table>
          <thead>
            <tr>
              <th class="big-slot-header">大课</th>
              <th class="time-header">小节</th>
              <th v-for="day in weekdays" :key="day">{{ day }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="block in mergedBlocks" :key="block.firstSlot">
              <tr>
                <td rowspan="2" class="big-slot-cell">
                  <div class="big-slot-label">{{ block.label }}</div>
                  <div class="big-slot-range">{{ block.range }}</div>
                  <div class="big-slot-tag">{{ block.tag }} · 两小节</div>
                </td>
                <td class="time-cell">
                  <div class="slot-label">{{ slotInfo[block.firstSlot]?.name }}</div>
                  <div class="slot-range">{{ block.firstSlot }}-{{ slotInfo[block.firstSlot]?.end }}</div>
                </td>
                <td
                  v-for="day in weekdays"
                  :key="day"
                  :class="{ 'has-event': !block.firstCells[day].empty, 'is-custom': block.firstCells[day].customId !== null }"
                  :rowspan="block.firstCells[day].rowspan === 2 ? 2 : undefined"
                >
                  <div
                    v-if="!block.firstCells[day].empty"
                    class="event-cell"
                    :style="{ backgroundColor: block.firstCells[day].bg, borderLeft: '4px solid ' + block.firstCells[day].border }"
                  >
                    <div class="event-title" :style="{ color: block.firstCells[day].text }">
                      {{ block.firstCells[day].title }}<span v-if="block.firstCells[day].continuation" class="event-continued">（续）</span>
                    </div>
                    <div class="event-info">
                      <span v-if="block.firstCells[day].location">📍{{ block.firstCells[day].location }}</span>
                      <span v-if="block.firstCells[day].teacher">👨‍🏫{{ block.firstCells[day].teacher }}</span>
                    </div>
                    <button
                      v-if="block.firstCells[day].customId !== null && !block.firstCells[day].continuation"
                      class="remove-btn"
                      @click="removeCustomEvent(block.firstCells[day].customId)"
                    >×</button>
                  </div>
                  <div v-else class="empty-cell">空档</div>
                </td>
              </tr>
              <tr>
                <td class="time-cell">
                  <div class="slot-label">{{ slotInfo[block.secondSlot]?.name }}</div>
                  <div class="slot-range">{{ block.secondSlot }}-{{ slotInfo[block.secondSlot]?.end }}</div>
                </td>
                <template v-for="day in weekdays" :key="day">
                  <!-- 上一行已经跨两行合并时，这一行不再输出该列的单元格 -->
                  <td
                    v-if="block.firstCells[day].rowspan !== 2"
                    :class="{ 'has-event': !block.secondCells[day].empty, 'is-custom': block.secondCells[day].customId !== null }"
                  >
                    <div
                      v-if="!block.secondCells[day].empty"
                      class="event-cell"
                      :style="{ backgroundColor: block.secondCells[day].bg, borderLeft: '4px solid ' + block.secondCells[day].border }"
                    >
                      <div class="event-title" :style="{ color: block.secondCells[day].text }">
                        {{ block.secondCells[day].title }}<span v-if="block.secondCells[day].continuation" class="event-continued">（续）</span>
                      </div>
                      <div class="event-info">
                        <span v-if="block.secondCells[day].location">📍{{ block.secondCells[day].location }}</span>
                        <span v-if="block.secondCells[day].teacher">👨‍🏫{{ block.secondCells[day].teacher }}</span>
                      </div>
                      <button
                        v-if="block.secondCells[day].customId !== null && !block.secondCells[day].continuation"
                        class="remove-btn"
                        @click="removeCustomEvent(block.secondCells[day].customId)"
                      >×</button>
                    </div>
                    <div v-else class="empty-cell">空档</div>
                  </td>
                </template>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <p class="timetable-legend">每小课 45 分钟；同一大课内的两小节连上，中间休息 5 分钟，大课之间休息 15 分钟。</p>
    </article>

    <!-- 公用记账 + 美好记录 -->
    <article class="split-panel">
      <p class="micro">02 / 公用记账 · 美好记录</p>
      <h2>算清每一笔，也记下当时的美好。</h2>
      <p class="panel-sub">记账只是顺手的事；真正想留下的是「那天我们为什么花这笔钱」。</p>

      <div class="form-row">
        <label>这次是干啥<input v-model="purpose" placeholder="如：一起买的西瓜 / 生日蛋糕 / 熬夜补给" /></label>
        <label>金额<input v-model="amount" inputmode="decimal" /></label>
      </div>
      <div class="form-row">
        <label>付款人<input v-model="payer" /></label>
        <label>参与成员<input v-model="members" /></label>
      </div>

      <div class="memory-photo-row">
        <button class="soft-button" @click="photoInput?.click()">📷 添加照片</button>
        <input ref="photoInput" type="file" accept="image/*" multiple class="memory-photo-input" @change="handlePhotoSelect">
        <span class="photo-hint">最多 {{ MAX_PHOTOS_PER_RECORD }} 张，自动压缩后存在本机</span>
      </div>

      <div v-if="photos.length" class="memory-photo-grid pending">
        <div v-for="(photo, index) in photos" :key="index" class="memory-photo-thumb">
          <img :src="photo" alt="待保存的照片" @click="previewPhoto = photo">
          <button class="remove-btn" @click="removePhoto(index)">×</button>
        </div>
      </div>

      <div class="panel-actions-row">
        <button class="ink-button primary" :disabled="loading" @click="settle">{{ loading ? '计算中...' : '计算 AA 分摊' }}</button>
        <button class="soft-button" @click="saveMemoryOnly">只记美好，不算账</button>
      </div>

      <ul v-if="transfers.length" class="transfer-list">
        <li v-for="transfer in transfers" :key="`${transfer.from_member_id}${transfer.to_member_id}`">
          {{ transfer.from_member_id }} <span>→</span> {{ transfer.to_member_id }} <strong>¥{{ transfer.amount }}</strong>
        </li>
      </ul>
      <p v-else class="empty-state">填写金额和成员后计算。</p>
      <p v-if="memoryNotice" class="memory-notice">{{ memoryNotice }}</p>

      <!-- 回忆时间线：最新的在最上面 -->
      <section class="memory-timeline">
        <header class="memory-timeline-head">
          <h3>美好记录</h3>
          <span v-if="memoryRecords.length">共 {{ memoryRecords.length }} 条</span>
        </header>
        <p v-if="!memoryRecords.length" class="empty-state">还没有记录。算完一笔账、或者点「只记美好」，它就会自动存到这里。</p>
        <article v-for="record in memoryRecords" :key="record.id" class="memory-record">
          <header>
            <strong>{{ record.purpose }}</strong>
            <span class="memory-when">{{ formatMemoryTime(record.createdAt) }}</span>
          </header>
          <p class="memory-meta">¥{{ record.amount }} · {{ record.payer }} 付 · {{ record.members.join('、') }}</p>
          <p v-if="record.transfers.length" class="memory-settle">
            结算：{{ record.transfers.map((t) => `${t.from_member_id}→${t.to_member_id} ¥${t.amount}`).join('；') }}
          </p>
          <div v-if="record.photos.length" class="memory-photo-grid">
            <div v-for="(photo, index) in record.photos" :key="index" class="memory-photo-thumb">
              <img :src="photo" :alt="record.purpose" @click="previewPhoto = photo">
            </div>
          </div>
          <button class="memory-delete" @click="removeMemoryRecord(record.id)">删除这条</button>
        </article>
      </section>
    </article>

    <!-- 照片大图 -->
    <div v-if="previewPhoto" class="photo-lightbox" @click="previewPhoto = ''">
      <img :src="previewPhoto" alt="照片预览">
    </div>

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