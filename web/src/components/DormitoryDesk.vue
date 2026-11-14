<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
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
  loadDutyWeek()
  loadScheduleOwner()
  loadExpenseLog()
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

// 备份：记录只存在这台机器的浏览器里，换设备或清缓存就没了，所以给一份能带走的 JSON。
const memoryFileInput = ref<HTMLInputElement | null>(null)

function exportMemoryRecords() {
  if (!memoryRecords.value.length) {
    memoryNotice.value = '还没有记录可以导出。'
    return
  }
  const payload = {
    app: 'zhihui-qilu',
    kind: 'memory-records',
    version: 1,
    exportedAt: new Date().toISOString(),
    records: memoryRecords.value,
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
  link.href = url
  link.download = `美好记录-${stamp}.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  memoryNotice.value = `已导出 ${memoryRecords.value.length} 条记录。`
}

function chooseMemoryFile() {
  memoryFileInput.value?.click()
}

/**
 * 导入按 id 去重后并入，不会覆盖已有记录。
 * 也接受裸数组（手写的备份），字段缺什么就补默认值，坏条目直接跳过。
 */
async function importMemoryRecords(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  try {
    const parsed: unknown = JSON.parse(await file.text())
    const container = (typeof parsed === 'object' && parsed !== null ? parsed : {}) as { records?: unknown }
    const incoming: unknown = Array.isArray(parsed) ? parsed : container.records
    if (!Array.isArray(incoming)) {
      memoryNotice.value = '这个文件里没有记录。'
      return
    }
    const seen = new Set(memoryRecords.value.map((record) => record.id))
    const merged: MemoryRecord[] = []
    for (const raw of incoming) {
      if (!raw || typeof raw !== 'object') continue
      const record = raw as Partial<MemoryRecord>
      if (typeof record.id !== 'number' || typeof record.purpose !== 'string') continue
      if (seen.has(record.id)) continue
      seen.add(record.id)
      merged.push({
        id: record.id,
        createdAt: typeof record.createdAt === 'string' ? record.createdAt : new Date().toISOString(),
        purpose: record.purpose,
        amount: String(record.amount ?? '0'),
        payer: String(record.payer ?? ''),
        members: Array.isArray(record.members) ? record.members.map(String) : [],
        transfers: Array.isArray(record.transfers) ? (record.transfers as Transfer[]) : [],
        photos: Array.isArray(record.photos) ? record.photos.filter((item): item is string => typeof item === 'string') : [],
      })
    }
    if (!merged.length) {
      memoryNotice.value = '没有新记录，可能都已经导入过了。'
      return
    }
    memoryRecords.value = [...merged, ...memoryRecords.value].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
    persistMemoryRecords()
    memoryNotice.value = `已导入 ${merged.length} 条记录。`
  } catch {
    memoryNotice.value = '这个文件读不出来，确认是导出的 JSON 备份。'
  }
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

// 时间小工具：不引入 dayjs，统一用浏览器本地时区取「时:分」。
function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

function isoToHhmm(iso: string): string {
  try {
    const value = new Date(iso)
    if (Number.isNaN(value.getTime())) return '00:00'
    return `${pad2(value.getHours())}:${pad2(value.getMinutes())}`
  } catch {
    return '00:00'
  }
}

function isValidHhmm(value: string): boolean {
  return /^\d{1,2}:\d{2}$/.test(value)
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

// ── 课表时间重叠检测 ────────────────────────────────────────────────
// 同一门课的连续小节不是冲突；只有「两门不同课程时间相交」才标红。
interface CourseInterval {
  day: string
  title: string
  startTime: string
  endTime: string
  start: number
  end: number
}

interface ClashPair {
  key: string
  day: string
  first: string
  firstRange: string
  second: string
  secondRange: string
}

const courseIntervals = computed<CourseInterval[]>(() => {
  const list: CourseInterval[] = []
  for (const event of events.value) {
    const day = event.day_of_week && weekdays.includes(event.day_of_week)
      ? event.day_of_week
      : getDayOfWeek(event.starts_at)
    if (!weekdays.includes(day)) continue
    const startTime = isoToHhmm(event.starts_at)
    const endTime = isoToHhmm(event.ends_at)
    list.push({
      day,
      title: event.title,
      startTime,
      endTime,
      start: toMinutes(startTime),
      end: toMinutes(endTime)
    })
  }
  for (const event of customEvents.value) {
    list.push({
      day: event.day,
      title: event.title,
      startTime: event.startTime,
      endTime: event.endTime,
      start: toMinutes(event.startTime),
      end: toMinutes(event.endTime)
    })
  }
  return list
})

const clashInfo = computed(() => {
  const daySlots: Record<string, Set<string>> = {}
  const pairs: ClashPair[] = []
  const list = courseIntervals.value
  for (let i = 0; i < list.length; i += 1) {
    for (let j = i + 1; j < list.length; j += 1) {
      const first = list[i]
      const second = list[j]
      if (first.day !== second.day) continue
      if (first.title === second.title) continue
      if (Math.max(first.start, second.start) >= Math.min(first.end, second.end)) continue
      pairs.push({
        key: `${first.day}-${i}-${j}`,
        day: first.day,
        first: first.title,
        firstRange: `${first.startTime}-${first.endTime}`,
        second: second.title,
        secondRange: `${second.startTime}-${second.endTime}`
      })
      for (const interval of [first, second]) {
        const slots = slotsCoveredBy(interval.startTime, interval.endTime)
        if (!slots.length) continue
        if (!daySlots[interval.day]) daySlots[interval.day] = new Set<string>()
        slots.forEach((slot) => daySlots[interval.day].add(slot))
      }
    }
  }
  return { daySlots, pairs }
})

function hasClash(day: string, slot: string): boolean {
  return clashInfo.value.daySlots[day]?.has(slot) ?? false
}

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
  clash: boolean
}

function buildRenderCell(
  event: GridEvent | null,
  rowspan: 1 | 2,
  continuation: boolean,
  clash: boolean
): RenderCell {
  if (!event) {
    return {
      empty: true, rowspan, continuation: false,
      title: '', location: '', teacher: '',
      bg: 'transparent', border: 'transparent', text: 'inherit',
      customId: null, clash: false
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
    customId: event.type === 'custom' && typeof event.id === 'number' ? event.id : null,
    clash
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
        const mergedClash = hasClash(day, first) || hasClash(day, second)
        firstCells[day] = buildRenderCell(firstEvent, 2, prevTitle === firstEvent.title, mergedClash)
        continue
      }

      firstCells[day] = buildRenderCell(
        firstEvent,
        1,
        !!firstEvent && prevTitle === firstEvent.title,
        hasClash(day, first)
      )
      secondCells[day] = buildRenderCell(
        secondEvent,
        1,
        !!secondEvent && !!firstEvent && firstEvent.title === secondEvent.title,
        hasClash(day, second)
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
    balances.value = normalizeBalances(result.data.balances)
    // 记账顺手落一条月度流水，图表才能按描述粗分类。
    const logAmount = Math.round(Number(amount.value) * 100) / 100
    if (Number.isFinite(logAmount) && logAmount > 0) {
      appendExpenseLog({
        description: purpose.value.trim() || '宿舍公用支出',
        amount: logAmount,
        payer_id: payer.value.trim(),
        participant_ids,
        date: new Date().toISOString()
      })
    }
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

/* ==================================================================
 * 值日排班 + 冲突检测
 * ================================================================== */

interface DutySlot {
  member: string
  startTime: string
  endTime: string
}

interface DutyAssignmentDto {
  member_id: string
  starts_at: string
  ends_at: string
  duty_name: string
}

interface ScheduleEventDto {
  title: string
  starts_at: string
  ends_at: string
  location?: string
  source: 'ics' | 'spreadsheet' | 'ocr' | 'text'
}

interface DutyConflictDto {
  member_id: string
  duty: DutyAssignmentDto
  conflicting_event: ScheduleEventDto
}

interface DutySuggestionDto {
  original_member_id: string
  suggested_member_id: string
  duty: DutyAssignmentDto
  rationale: string
}

const DUTY_STORAGE_KEY = 'zhq-dorm-duty-v1'
const SCHEDULE_OWNER_KEY = 'zhq-dorm-schedule-owner-v1'
const EXPENSE_LOG_KEY = 'zhq-dorm-expense-log-v1'
const DUTY_DEFAULT_START = '20:00'
const DUTY_DEFAULT_END = '21:00'

function createEmptyDutyWeek(): Record<string, DutySlot> {
  const week: Record<string, DutySlot> = {}
  for (const day of weekdays) {
    week[day] = { member: '', startTime: DUTY_DEFAULT_START, endTime: DUTY_DEFAULT_END }
  }
  return week
}

const dutyWeek = ref<Record<string, DutySlot>>(createEmptyDutyWeek())
const dutyNotice = ref('')
const dutyChecking = ref(false)
const dutyChecked = ref(false)
const dutyConflicts = ref<DutyConflictDto[]>([])
const dutySuggestions = ref<DutySuggestionDto[]>([])

/**
 * 这份课表属于谁。
 *
 * 整页只有一份课表，它是「某一个人」的，不是全宿舍共享的。如果按成员逐个投影，
 * 值日时段一旦和课表重叠就会全员同时冲突，后端 suggest_swaps 找不到「该时段无冲突」
 * 的候选人，换班建议永远是空的。所以必须让用户声明归属人，只给归属人投影。
 */
const scheduleOwner = ref('')

function loadScheduleOwner() {
  try {
    const raw = localStorage.getItem(SCHEDULE_OWNER_KEY)
    if (raw) scheduleOwner.value = raw
  } catch {
    // 隐私模式读不到就保持为空，用户重新选一次即可。
  }
}

function persistScheduleOwner() {
  try {
    localStorage.setItem(SCHEDULE_OWNER_KEY, scheduleOwner.value)
  } catch {
    // 写不进去不影响本次分析。
  }
}

// 「参与成员」输入框是唯一的人员来源，值日面板只从它取名字。
const memberNames = computed(() =>
  members.value.split(/[,，、;；\s]+/).map((item) => item.trim()).filter(Boolean)
)

// 成员列表被改过之后，旧排班里的人名仍然要能在下拉里看到，否则会显示成空白。
const dutyMemberOptions = computed(() => {
  const names = [...memberNames.value]
  for (const day of weekdays) {
    const name = dutyWeek.value[day]?.member?.trim() ?? ''
    if (name && !names.includes(name)) names.push(name)
  }
  return names
})

function loadDutyWeek() {
  try {
    const raw = localStorage.getItem(DUTY_STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object') return
    const record = parsed as Record<string, unknown>
    const next = createEmptyDutyWeek()
    for (const day of weekdays) {
      const cell = record[day]
      if (!cell || typeof cell !== 'object') continue
      const slot = cell as Record<string, unknown>
      next[day] = {
        member: typeof slot.member === 'string' ? slot.member : '',
        startTime: isValidHhmm(String(slot.startTime ?? '')) ? String(slot.startTime) : DUTY_DEFAULT_START,
        endTime: isValidHhmm(String(slot.endTime ?? '')) ? String(slot.endTime) : DUTY_DEFAULT_END
      }
    }
    dutyWeek.value = next
  } catch {
    // 隐私模式或数据损坏：退回默认空排班，不影响其它面板。
  }
}

function persistDutyWeek() {
  try {
    localStorage.setItem(DUTY_STORAGE_KEY, JSON.stringify(dutyWeek.value))
  } catch {
    // 存不下就只在本次会话里生效。
  }
}

watch(dutyWeek, persistDutyWeek, { deep: true })

function clearDutyWeek() {
  dutyWeek.value = createEmptyDutyWeek()
  dutyConflicts.value = []
  dutySuggestions.value = []
  dutyChecked.value = false
  dutyNotice.value = ''
}

// 本地时刻 → 带时区的 ISO8601（toISOString 会转成 UTC 并带 Z，后端能直接解析）。
function isoAt(date: Date, hhmm: string): string {
  const [hours, minutes] = hhmm.split(':').map(Number)
  return new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
    Number.isFinite(hours) ? hours : 0,
    Number.isFinite(minutes) ? minutes : 0,
    0,
    0
  ).toISOString()
}

// 本周一 00:00（本地时区）。值日表按「本周」算，跨周后自动滚到新的一周。
function currentWeekMonday(): Date {
  const today = new Date()
  const weekday = today.getDay() // 0 = 周日
  const offset = weekday === 0 ? 6 : weekday - 1
  return new Date(today.getFullYear(), today.getMonth(), today.getDate() - offset)
}

function dateOfWeekIndex(monday: Date, index: number): Date {
  return new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + index)
}

const hasScheduleData = computed(() => events.value.length > 0 || customEvents.value.length > 0)

const WEEKDAY_NAMES = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function weekdayOfIso(iso: string): string {
  try {
    const value = new Date(iso)
    if (Number.isNaN(value.getTime())) return ''
    return WEEKDAY_NAMES[value.getDay()]
  } catch {
    return ''
  }
}

function hhmmRange(startIso: string, endIso: string): string {
  return `${isoToHhmm(startIso)}-${isoToHhmm(endIso)}`
}

function conflictText(item: DutyConflictDto): string {
  const day = weekdayOfIso(item.duty.starts_at)
  const course = item.conflicting_event.title
  const range = hhmmRange(item.conflicting_event.starts_at, item.conflicting_event.ends_at)
  return `${day} ${item.member_id} 值日与 ${course} ${range} 冲突`
}

function suggestionText(item: DutySuggestionDto): string {
  return `建议 ${item.original_member_id} ↔ ${item.suggested_member_id}，理由：${item.rationale}`
}

/**
 * 把课表/自定义行程重排到「本周」的日期上，只投影给课表的归属人。
 * 导入的课表可能来自任意一周，只有重新落到本周日期，才能和本周的值日时段比对。
 *
 * 只给归属人投影是刻意的：如果把同一份课表塞给每个成员，值日时段一旦落在课表里，
 * 全员同时冲突，后端就找不到可换班的人，黄色建议栏会永远空着。
 * 其他成员按「暂无课表数据」处理，换班建议才有意义。
 */
function buildMemberEvents(owner: string, monday: Date): Record<string, ScheduleEventDto[]> {
  const perDay: Record<string, ScheduleEventDto[]> = {}
  for (const day of weekdays) perDay[day] = []

  const push = (day: string, title: string, startTime: string, endTime: string, location?: string) => {
    const index = weekdays.indexOf(day)
    if (index < 0) return
    if (!isValidHhmm(startTime) || !isValidHhmm(endTime)) return
    const date = dateOfWeekIndex(monday, index)
    const startsAt = isoAt(date, startTime)
    const endsAt = isoAt(date, endTime)
    // 后端要求 ends_at > starts_at，倒挂的条目直接丢掉，别让整次分析 422。
    if (new Date(endsAt).getTime() <= new Date(startsAt).getTime()) return
    const item: ScheduleEventDto = { title, starts_at: startsAt, ends_at: endsAt, source: 'text' }
    if (location) item.location = location
    perDay[day].push(item)
  }

  for (const event of events.value) {
    const day = event.day_of_week && weekdays.includes(event.day_of_week)
      ? event.day_of_week
      : getDayOfWeek(event.starts_at)
    push(day, event.title, isoToHhmm(event.starts_at), isoToHhmm(event.ends_at), event.location)
  }
  for (const event of customEvents.value) {
    push(event.day, event.title, event.startTime, event.endTime, event.location || undefined)
  }

  const result: Record<string, ScheduleEventDto[]> = {}
  if (owner) result[owner] = weekdays.flatMap((day) => perDay[day])
  return result
}

async function checkDutyConflicts() {
  if (dutyChecking.value) return
  dutyChecking.value = true
  dutyNotice.value = ''
  dutyConflicts.value = []
  dutySuggestions.value = []
  dutyChecked.value = false
  try {
    const roster = memberNames.value
    if (!roster.length) {
      dutyNotice.value = '先在「参与成员」里填上宿舍成员，排班才有名字可选。'
      return
    }

    const monday = currentWeekMonday()
    const assignments: DutyAssignmentDto[] = []
    const invalidDays: string[] = []
    const unknownNames: string[] = []

    weekdays.forEach((day, index) => {
      const slot = dutyWeek.value[day]
      const member = slot?.member?.trim() ?? ''
      if (!member) return
      if (!roster.includes(member)) {
        unknownNames.push(member)
        return
      }
      const startTime = slot.startTime ?? ''
      const endTime = slot.endTime ?? ''
      if (!isValidHhmm(startTime) || !isValidHhmm(endTime) || toMinutes(endTime) <= toMinutes(startTime)) {
        invalidDays.push(day)
        return
      }
      const date = dateOfWeekIndex(monday, index)
      assignments.push({
        member_id: member,
        starts_at: isoAt(date, startTime),
        ends_at: isoAt(date, endTime),
        duty_name: `${day}值日`
      })
    })

    if (!assignments.length) {
      dutyNotice.value = '本周还没有安排值日：先在表格里给每天选人。'
      return
    }

    // 没有课表、或还没声明课表归属人时，只发 assignments，member_events 传 {}。
    const memberEvents = hasScheduleData.value && scheduleOwner.value
      ? buildMemberEvents(scheduleOwner.value, monday)
      : {}

    const result = await command('dormitory', 'analyze_schedule_conflicts', '', {
      assignments,
      member_events: memberEvents
    })

    dutyConflicts.value = Array.isArray(result.data.conflicts)
      ? (result.data.conflicts as DutyConflictDto[])
      : []
    dutySuggestions.value = Array.isArray(result.data.suggestions)
      ? (result.data.suggestions as DutySuggestionDto[])
      : []
    dutyChecked.value = true

    const notes: string[] = []
    if (invalidDays.length) notes.push(`${Array.from(new Set(invalidDays)).join('、')} 的结束时间不晚于开始时间，已跳过`)
    if (unknownNames.length) notes.push(`「${Array.from(new Set(unknownNames)).join('、')}」不在成员列表里，已跳过`)
    if (!hasScheduleData.value) notes.push('导入课表后可以检测时间冲突')
    else if (!scheduleOwner.value) notes.push('先在上面选一下「这份课表属于谁」，否则无法比对冲突')
    dutyNotice.value = notes.join('；')
  } catch (reason) {
    dutyNotice.value = reason instanceof Error ? reason.message : '冲突检测失败'
  } finally {
    dutyChecking.value = false
  }
}

/* ==================================================================
 * 结算净额 + 月度消费
 * ================================================================== */

interface MemberBalance {
  member: string
  amount: number
}

const balances = ref<MemberBalance[]>([])

// 后端 Decimal 在 JSON 里可能是字符串也可能是数字，统一收敛成两位小数。
function normalizeBalances(raw: unknown): MemberBalance[] {
  if (!raw || typeof raw !== 'object') return []
  const list: MemberBalance[] = []
  for (const [member, value] of Object.entries(raw as Record<string, unknown>)) {
    const amount = typeof value === 'number' ? value : Number(String(value ?? ''))
    if (!Number.isFinite(amount) || amount === 0) continue
    list.push({ member, amount: Math.round(amount * 100) / 100 })
  }
  return list.sort((a, b) => b.amount - a.amount)
}

function balanceText(amount: number): string {
  return amount >= 0 ? `应收 +${amount.toFixed(2)}` : `应付 ${amount.toFixed(2)}`
}

interface ExpenseLogEntry {
  description: string
  amount: number
  payer_id: string
  participant_ids: string[]
  date: string
}

const expenseLog = ref<ExpenseLogEntry[]>([])

function loadExpenseLog() {
  try {
    const raw = localStorage.getItem(EXPENSE_LOG_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return
    const list: ExpenseLogEntry[] = []
    for (const item of parsed) {
      if (!item || typeof item !== 'object') continue
      const entry = item as Record<string, unknown>
      const amountValue = Number(entry.amount)
      if (!Number.isFinite(amountValue)) continue
      list.push({
        description: typeof entry.description === 'string' ? entry.description : '',
        amount: amountValue,
        payer_id: typeof entry.payer_id === 'string' ? entry.payer_id : '',
        participant_ids: Array.isArray(entry.participant_ids) ? entry.participant_ids.map(String) : [],
        date: typeof entry.date === 'string' ? entry.date : new Date().toISOString()
      })
    }
    expenseLog.value = list
  } catch {
    // 读不出来就当没有历史，图表显示空态。
  }
}

function appendExpenseLog(entry: ExpenseLogEntry) {
  expenseLog.value = [...expenseLog.value, entry]
  try {
    localStorage.setItem(EXPENSE_LOG_KEY, JSON.stringify(expenseLog.value))
  } catch {
    // 配额满或隐私模式：只在本次会话里保留，图表仍然能更新。
  }
}

// 粗分类：按描述里的关键词，先命中先归类，匹配不到归「其他」。
const expenseCategories = [
  {
    key: '餐饮',
    color: '#d8614d',
    keywords: ['饭', '餐', '吃', '外卖', '食堂', '奶茶', '咖啡', '水果', '西瓜', '零食', '夜宵', '蛋糕', '烧烤', '火锅', '早餐', '午餐', '晚餐', '饮料', '可乐', '雪糕', '冰淇淋', '泡面', '补给']
  },
  {
    key: '日用',
    color: '#397f72',
    keywords: ['纸', '洗', '拖', '扫', '清洁', '垃圾', '沐浴', '牙膏', '毛巾', '日用', '消毒', '洁厕', '衣架', '插座', '灯泡', '收纳']
  },
  {
    key: '交通',
    color: '#2f6f9f',
    keywords: ['打车', '地铁', '公交', '出租', '高铁', '车票', '加油', '停车', '单车', '滴滴', '交通', '机票']
  },
  {
    key: '水电',
    color: '#d6a849',
    keywords: ['水费', '电费', '网费', '宽带', '燃气', '空调', '充值', '缴费', '物业', '水卡', '电卡']
  }
]

const OTHER_CATEGORY: { key: string; color: string } = { key: '其他', color: '#8b9a95' }

function categorizeExpense(description: string): string {
  const text = description ?? ''
  for (const category of expenseCategories) {
    if (category.keywords.some((keyword) => text.includes(keyword))) return category.key
  }
  return OTHER_CATEGORY.key
}

const monthlyExpenses = computed(() => {
  const now = new Date()
  return expenseLog.value.filter((entry) => {
    const value = new Date(entry.date)
    if (Number.isNaN(value.getTime())) return false
    return value.getFullYear() === now.getFullYear() && value.getMonth() === now.getMonth()
  })
})

const monthlyTotal = computed(() =>
  Math.round(monthlyExpenses.value.reduce((sum, entry) => sum + entry.amount, 0) * 100) / 100
)

const monthlyBars = computed(() => {
  const totals = new Map<string, number>()
  for (const entry of monthlyExpenses.value) {
    const key = categorizeExpense(entry.description)
    totals.set(key, (totals.get(key) ?? 0) + entry.amount)
  }
  const total = monthlyTotal.value
  const ordered: { key: string, color: string }[] = [
    ...expenseCategories.map((item) => ({ key: item.key as string, color: item.color as string })),
    OTHER_CATEGORY
  ]
  return ordered
    .map((item) => {
      const amount = Math.round((totals.get(item.key) ?? 0) * 100) / 100
      return {
        key: item.key,
        color: item.color,
        amount,
        percent: total > 0 ? Math.round((amount / total) * 1000) / 10 : 0
      }
    })
    .filter((item) => item.amount > 0)
})

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
      
      <!-- 时间重叠提醒：同一门课的连续小节不算冲突 -->
      <div v-if="clashInfo.pairs.length" class="dormx-clash-banner">
        <p class="dormx-clash-title">⚠ 检测到 {{ clashInfo.pairs.length }} 处时间重叠</p>
        <ul class="dormx-clash-list">
          <li v-for="pair in clashInfo.pairs.slice(0, 5)" :key="pair.key">
            {{ pair.day }} · {{ pair.first }} {{ pair.firstRange }} × {{ pair.second }} {{ pair.secondRange }}
          </li>
        </ul>
        <p v-if="clashInfo.pairs.length > 5" class="dormx-clash-more">另有 {{ clashInfo.pairs.length - 5 }} 处未展开。</p>
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
                  :class="{ 'has-event': !block.firstCells[day].empty, 'is-custom': block.firstCells[day].customId !== null, 'dormx-clash': block.firstCells[day].clash }"
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
                    :class="{ 'has-event': !block.secondCells[day].empty, 'is-custom': block.secondCells[day].customId !== null, 'dormx-clash': block.secondCells[day].clash }"
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

    <!-- 值日排班 + 冲突检测 -->
    <article class="timetable-panel">
      <p class="micro">02 / 值日排班</p>
      <h2>一周值日先排好，再让课表说话。</h2>
      <p class="panel-sub">默认时段 20:00–21:00；排班存在本机，检查冲突时会把值日与当天课表比对。</p>

      <label class="dormx-owner-row">
        <span class="dormx-owner-label">这份课表属于</span>
        <select v-model="scheduleOwner" @change="persistScheduleOwner">
          <option value="">未指定</option>
          <option v-for="name in dutyMemberOptions" :key="name" :value="name">{{ name }}</option>
        </select>
        <small class="dormx-owner-hint">
          整页只有一份课表，声明归属人后只比对这一个人的忙时；其他成员按「暂无课表」处理，
          换班建议才能给出候选人。
        </small>
      </label>

      <div class="dormx-duty-table">
        <table>
          <thead>
            <tr>
              <th>星期</th>
              <th>负责人</th>
              <th>开始</th>
              <th>结束</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="day in weekdays" :key="day">
              <th scope="row">{{ day }}</th>
              <td>
                <select v-model="dutyWeek[day].member" :aria-label="`${day}值日负责人`">
                  <option value="">未安排</option>
                  <option v-for="name in dutyMemberOptions" :key="name" :value="name">{{ name }}</option>
                </select>
              </td>
              <td><input v-model="dutyWeek[day].startTime" type="time" :aria-label="`${day}值日开始时间`"></td>
              <td><input v-model="dutyWeek[day].endTime" type="time" :aria-label="`${day}值日结束时间`"></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="dormx-duty-actions">
        <button class="ink-button primary" :disabled="dutyChecking" @click="checkDutyConflicts">
          {{ dutyChecking ? '检查中...' : '检查冲突' }}
        </button>
        <button class="soft-button" @click="clearDutyWeek">清空排班</button>
        <span class="dormx-duty-hint">
          {{ hasScheduleData ? '按本周一至周日，把值日时段和课表逐天比对。' : '导入课表后可以检测时间冲突' }}
        </span>
      </div>

      <p v-if="dutyNotice" class="dormx-duty-notice">{{ dutyNotice }}</p>

      <div v-if="dutyChecked" class="dormx-duty-result">
        <section class="dormx-column dormx-column-danger">
          <h3>冲突<span class="dormx-count">{{ dutyConflicts.length }}</span></h3>
          <p v-if="!dutyConflicts.length" class="dormx-ok">本周排班无冲突</p>
          <ul v-else class="dormx-conflict-list">
            <li v-for="(item, index) in dutyConflicts" :key="`conflict-${index}`">{{ conflictText(item) }}</li>
          </ul>
        </section>
        <section class="dormx-column dormx-column-warn">
          <h3>换班建议<span class="dormx-count">{{ dutySuggestions.length }}</span></h3>
          <p v-if="!dutySuggestions.length" class="dormx-muted">暂无换班建议。</p>
          <ul v-else class="dormx-suggest-list">
            <li v-for="(item, index) in dutySuggestions" :key="`suggest-${index}`">
              <span class="dormx-suggest-day">{{ weekdayOfIso(item.duty.starts_at) }}</span>
              {{ suggestionText(item) }}
            </li>
          </ul>
        </section>
      </div>
    </article>

    <!-- 公用记账 + 美好记录 -->
    <article class="split-panel">
      <p class="micro">03 / 公用记账 · 美好记录</p>
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

      <!-- 本宿舍净额：正数应收、负数应付，按金额从高到低排 -->
      <section v-if="balances.length" class="dormx-balance">
        <h3>本宿舍净额</h3>
        <ul class="dormx-balance-list">
          <li
            v-for="item in balances"
            :key="item.member"
            :class="item.amount >= 0 ? 'is-credit' : 'is-debt'"
          >
            <span class="dormx-balance-name">{{ item.member }}</span>
            <span class="dormx-balance-amount">{{ balanceText(item.amount) }}</span>
          </li>
        </ul>
      </section>

      <template v-if="transfers.length">
        <h3 class="dormx-transfer-title">最少转账方案：{{ transfers.length }} 笔</h3>
        <ul class="transfer-list">
          <li v-for="transfer in transfers" :key="`${transfer.from_member_id}${transfer.to_member_id}`">
            {{ transfer.from_member_id }} <span>→</span> {{ transfer.to_member_id }} <strong>¥{{ transfer.amount }}</strong>
          </li>
        </ul>
      </template>
      <p v-else class="empty-state">填写金额和成员后计算。</p>
      <p v-if="memoryNotice" class="memory-notice">{{ memoryNotice }}</p>

      <!-- 回忆时间线：最新的在最上面 -->
      <section class="memory-timeline">
        <header class="memory-timeline-head">
          <h3>美好记录</h3>
          <div class="memory-head-right">
            <span v-if="memoryRecords.length">共 {{ memoryRecords.length }} 条</span>
            <button type="button" class="memory-tool" :disabled="!memoryRecords.length" @click="exportMemoryRecords">导出备份</button>
            <button type="button" class="memory-tool" @click="chooseMemoryFile">导入恢复</button>
          </div>
        </header>
        <input ref="memoryFileInput" class="memory-import-input" type="file" accept="application/json,.json" @change="importMemoryRecords">
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

    <!-- 本月消费：纯 CSS 条形图，不引图表库 -->
    <article class="timetable-panel">
      <p class="micro">04 / 本月消费</p>
      <h2>这个月，钱花在哪一类。</h2>
      <p class="panel-sub">按记账时的描述粗分五类，只统计本月；每算一笔 AA 就自动多一条流水。</p>

      <div v-if="monthlyExpenses.length" class="dormx-month">
        <div class="dormx-month-head">
          <strong>本月总支出 ¥{{ monthlyTotal.toFixed(2) }}</strong>
          <span>{{ monthlyExpenses.length }} 笔</span>
        </div>
        <ul class="dormx-bars">
          <li v-for="bar in monthlyBars" :key="bar.key" class="dormx-bar-row">
            <span class="dormx-bar-label">{{ bar.key }}</span>
            <span class="dormx-bar-track">
              <span class="dormx-bar-fill" :style="{ width: bar.percent + '%', backgroundColor: bar.color }"></span>
            </span>
            <span class="dormx-bar-value">¥{{ bar.amount.toFixed(2) }} · {{ bar.percent }}%</span>
          </li>
        </ul>
      </div>
      <p v-else class="empty-state">记第一笔账后这里会出现分类统计</p>
    </article>

    <!-- 照片大图 -->
    <div v-if="previewPhoto" class="photo-lightbox" @click="previewPhoto = ''">
      <img :src="previewPhoto" alt="照片预览">
    </div>

    <!-- 整改建议 -->
    <article class="suggestion-panel">
      <p class="micro">05 / 整改建议</p>
      <h2>把检查记录改写为可执行建议。</h2>
      <label>观察到的情况<input v-model="observation" /></label>
      <button class="soft-button" @click="improve">生成建议</button>
      <p v-if="suggestion" class="suggestion-copy">{{ suggestion }}</p>
    </article>
  </section>
</template>

<style scoped>
/* ==================== 课表时间重叠 ==================== */
.dormx-clash-banner {
  margin-top: 18px;
  padding: 12px 14px;
  border: 1px solid #f0c4bd;
  border-left: 4px solid #d8614d;
  border-radius: 10px;
  background: #fdf2ef;
}

.dormx-clash-title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: #9e3030;
}

.dormx-clash-list {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.7;
  color: #8a3b2c;
}

.dormx-clash-more {
  margin: 4px 0 0;
  font-size: 12px;
  color: #a4715f;
}

/* 红边框用 inset 阴影，避免和 .timetable-grid td 的 border 打架 */
.dormx-clash {
  position: relative;
  box-shadow: inset 0 0 0 2px #d8614d;
}

.dormx-clash::after {
  content: '冲突';
  position: absolute;
  top: 2px;
  right: 2px;
  z-index: 3;
  padding: 1px 5px;
  border-radius: 999px;
  background: #d8614d;
  color: #fff;
  font-size: 10px;
  line-height: 1.5;
  letter-spacing: .04em;
  pointer-events: none;
}

/* ==================== 值日排班 ==================== */
.dormx-owner-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding: 10px 13px;
  border: 1px dashed rgba(47, 74, 69, 0.24);
  border-radius: 11px;
  background: rgba(255, 253, 248, 0.7);
}

.dormx-owner-label {
  flex: none;
  color: #3f5350;
  font-size: 13px;
  font-weight: 600;
}

.dormx-owner-row select {
  min-width: 128px;
  padding: 6px 9px;
  border: 1px solid rgba(47, 74, 69, 0.2);
  border-radius: 8px;
  background: #fff;
  color: #22302d;
  font-size: 13px;
  font-family: inherit;
}

.dormx-owner-hint {
  flex: 1 1 260px;
  color: #7b8b86;
  font-size: 11.5px;
  line-height: 1.6;
}

.dormx-duty-table {
  margin-top: 18px;
  overflow-x: auto;
}

.dormx-duty-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.dormx-duty-table th,
.dormx-duty-table td {
  border: 1px solid #e8e4dc;
  padding: 8px;
  text-align: center;
}

.dormx-duty-table thead th {
  background: #173f43;
  color: #fff;
  font-weight: 600;
  padding: 10px 8px;
}

.dormx-duty-table tbody th {
  width: 88px;
  background: #f5f4eb;
  color: #173f43;
  font-weight: 700;
  white-space: nowrap;
}

.dormx-duty-table select,
.dormx-duty-table input {
  width: 100%;
  max-width: 160px;
  padding: 7px 9px;
  border: 1px solid #d8ded4;
  border-radius: 8px;
  background: #fffef8;
  color: #172b2a;
  font-size: 13px;
}

.dormx-duty-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.dormx-duty-hint {
  font-size: 12px;
  color: #667572;
}

.dormx-duty-notice {
  margin: 12px 0 0;
  padding: 9px 12px;
  border: 1px solid #e8e4dc;
  border-radius: 10px;
  background: #f5f4eb;
  font-size: 12.5px;
  color: #4b5b57;
}

.dormx-duty-result {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
  margin-top: 16px;
}

.dormx-column {
  padding: 14px 16px;
  border: 1px solid #e8e4dc;
  border-radius: 12px;
  background: #fffef8;
}

.dormx-column h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 13.5px;
  letter-spacing: .02em;
}

.dormx-column-danger {
  border-color: #f0c4bd;
  background: #fdf2ef;
}

.dormx-column-danger h3 {
  color: #9e3030;
}

.dormx-column-warn {
  border-color: #eddfb6;
  background: #fdf7e6;
}

.dormx-column-warn h3 {
  color: #8a6a12;
}

.dormx-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: rgba(23, 43, 42, .08);
  font-size: 11px;
  font-weight: 700;
}

.dormx-ok {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid #bcdcc7;
  border-radius: 10px;
  background: #e4f1e8;
  color: #2e7d54;
  font-size: 13px;
  font-weight: 700;
}

.dormx-muted {
  margin: 0;
  font-size: 12.5px;
  color: #667572;
}

.dormx-conflict-list,
.dormx-suggest-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  line-height: 1.75;
}

.dormx-conflict-list {
  color: #5a3a33;
}

.dormx-suggest-list {
  color: #6b5518;
}

.dormx-suggest-day {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: 6px;
  background: rgba(214, 168, 73, .22);
  font-size: 11.5px;
  font-weight: 700;
}

/* ==================== 本宿舍净额 ==================== */
.dormx-balance {
  margin-top: 18px;
  padding: 14px 16px;
  border: 1px solid #e8e4dc;
  border-radius: 12px;
  background: #fbfaf3;
}

.dormx-balance h3 {
  margin: 0 0 10px;
  font-size: 13.5px;
  color: #173f43;
}

.dormx-balance-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.dormx-balance-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 10px;
  border: 1px solid #ece9df;
  border-radius: 8px;
  background: #fffef8;
  font-size: 13px;
}

.dormx-balance-name {
  color: #172b2a;
  font-weight: 600;
}

.dormx-balance-amount {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

.dormx-balance-list li.is-credit .dormx-balance-amount {
  color: #2e7d54;
}

.dormx-balance-list li.is-debt .dormx-balance-amount {
  color: #b63d3d;
}

.dormx-transfer-title {
  margin: 18px 0 8px;
  font-size: 13.5px;
  color: #173f43;
}

/* ==================== 本月消费 ==================== */
.dormx-month {
  margin-top: 16px;
}

.dormx-month-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid #e8e4dc;
  border-radius: 10px;
  background: #f5f4eb;
  font-size: 13px;
  color: #172b2a;
}

.dormx-month-head strong {
  font-size: 15px;
}

.dormx-month-head span {
  font-size: 12.5px;
  color: #667572;
}

.dormx-bars {
  display: grid;
  gap: 10px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}

.dormx-bar-row {
  display: grid;
  grid-template-columns: 52px 1fr auto;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
}

.dormx-bar-label {
  color: #172b2a;
  font-weight: 700;
}

.dormx-bar-track {
  display: block;
  height: 12px;
  border-radius: 999px;
  background: #eeece2;
  overflow: hidden;
}

.dormx-bar-fill {
  display: block;
  height: 100%;
  min-width: 3px;
  border-radius: 999px;
  transition: width .28s ease;
}

.dormx-bar-value {
  color: #4b5b57;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

@media (max-width: 720px) {
  .dormx-bar-row {
    grid-template-columns: 44px 1fr;
  }

  .dormx-bar-value {
    grid-column: 1 / -1;
    justify-self: end;
  }
}
</style>