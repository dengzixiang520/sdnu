<script setup lang="ts">
/**
 * 沉浸式 AI 模拟复试。
 *
 * 进入即全屏，画面是一个 3D 教室：三位导师坐在长桌后，谁提问镜头就转向谁，
 * 导师语音由 Breeze Blue 流式合成（首字节约 2 秒），考生必须用语音回答，
 * 语速、停顿、音量、填充词、开口延迟全部现场实测，结束后换算成五维评分。
 *
 * 降级路径写得很明确：
 *   - WebGL 不可用 → 3D 场景显示占位，流程照走
 *   - 语音合成不可用 → 回落到浏览器 speechSynthesis
 *   - 语音识别不可用 → 弹出文字作答框（只在识别确实不可用时出现）
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  PhArrowDownRight,
  PhArrowLeft,
  PhArrowUpRight,
  PhArrowsOut,
  PhCaretDown,
  PhCaretUp,
  PhChartLine,
  PhCheckCircle,
  PhCircleNotch,
  PhClockCounterClockwise,
  PhDownloadSimple,
  PhFileCode,
  PhMicrophone,
  PhMicrophoneSlash,
  PhPlay,
  PhStop,
  PhTimer,
  PhTrash,
  PhVideoCamera,
  PhVideoCameraSlash,
  PhWaveform,
  PhX,
} from '@phosphor-icons/vue'
import { requestJson } from '../api'
import ClassroomScene from './interview/ClassroomScene.vue'
import { useSpeechLab, type AnswerMetricPayload } from './interview/useSpeechLab'

/* ------------------------------------------------------------------ 类型 */

interface Examiner {
  id: string
  name: string
  title: string
  role: string
  duty: string
  voice_name: string
  color: string
  seat: number
}

interface PlanStep {
  step: number
  examiner: string
  examiner_name: string
  intent: string
  language: string
  hard: boolean
}

interface Turn {
  step: number
  total: number
  examiner: string
  examiner_name: string
  examiner_title: string
  intent: string
  language: string
  hard: boolean
  question: string
  closing: boolean
  generated_by: string
}

interface TtsTicket {
  token: string
  url: string
  cached: boolean
}

interface Dimension {
  key: string
  label: string
  score: number
  evidence: string
  advice: string
}

interface SpeechSummary {
  total_seconds: number
  speech_seconds: number
  speech_ratio: number
  chars_per_min: number
  pause_count: number
  longest_pause_ms: number
  latency_ms: number
  filler_total: number
  filler_rate: number
  avg_volume: number
  volume_stability: number
  answered: number
  pace_source: 'transcript' | 'estimate' | 'none'
}

interface AnswerReview {
  index: number
  examiner_name: string
  question: string
  transcript: string
  seconds: number
  chars_per_min: number
  pause_count: number
  longest_pause_ms: number
  latency_ms: number
  filler_count: number
  verdict: string
}

interface InterviewReport {
  overall: number
  grade: string
  headline: string
  dimensions: Dimension[]
  speech: SpeechSummary
  answers: AnswerReview[]
  highlights: string[]
  fixes: string[]
}

/** 压进 localStorage 的历史场次，字段刻意收窄：只留对比用得上的数字。 */
interface HistoryEntry {
  at: string
  overall: number
  grade: string
  dimensions: Array<{ key: string; score: number }>
  speech: { chars_per_min: number; filler_rate: number; speech_ratio: number }
}

/** 语速曲线上的一个点：坐标在 computed 里一次算好，模板只负责画。 */
interface PacePoint {
  no: number
  rate: number
  x: number
  y: number
  tone: 'slow' | 'fit' | 'fast'
  labelY: number
  tagY: number
}

interface PaceChart {
  width: number
  height: number
  left: number
  right: number
  baseline: number
  single: boolean
  band: { y: number; height: number }
  refs: number[]
  ticks: Array<{ value: number; y: number }>
  points: PacePoint[]
  path: string
  /** 只有 1 题时画的那根竖条；多题时为 null。 */
  bar: { x: number; y: number; width: number; height: number } | null
}

/* ------------------------------------------------------------------ 状态 */

type Stage = 'lobby' | 'live' | 'report'
type Phase = 'idle' | 'question' | 'answer' | 'report'

const stage = ref<Stage>('lobby')
const phase = ref<Phase>('idle')
const major = ref('人工智能')
const minutes = ref(15)
const strictness = ref('常规')
const examiners = ref<Examiner[]>([])
const plan = ref<PlanStep[]>([])
const speechReady = ref(false)
/** 服务端语音识别是否可用（MiMo-ASR） */
const asrReady = ref(false)
const speechNote = ref('')

const turn = ref<Turn | null>(null)
const stepIndex = ref(0)
const answers = ref<AnswerMetricPayload[]>([])
const report = ref<InterviewReport | null>(null)
const transcriptLog = ref<Array<{ role: 'examiner' | 'me'; name: string; text: string }>>([])

const busy = ref(false)
const speaking = ref<string | null>(null)
/**
 * 导师语音正在路上。
 *
 * 云端合成首字节约 2 秒，这段等待是正常的，界面上必须显示成"准备中"，
 * 不能显示成失败——否则用户会看到"加载失败"和随后正常播放的语音并存。
 */
const speechLoading = ref(false)
const elapsed = ref(0)
const error = ref('')
const notice = ref('')
const manualAnswer = ref('')
const manualOpen = ref(false)
const manualTitle = ref('文字作答')
const manualHint = ref('当前浏览器无法做语音转写。文字模式只统计内容，不会测量语速与停顿。')
const pendingMetric = ref<AnswerMetricPayload | null>(null)
/** 正在等最后一句话的转写结果，按钮需要防重入 */
const submitting = ref(false)
const fullscreen = ref(false)
const startedAtMs = ref(0)
const promptEndedAtMs = ref(0)

const root = ref<HTMLDivElement | null>(null)
const selfView = ref<HTMLVideoElement | null>(null)
const lab = useSpeechLab(transcribeAudio)

/**
 * 把一段 WAV（已经是 base64）送给后端转写。
 *
 * 走服务端而不是浏览器 Web Speech API：后者依赖 Google 的在线识别服务，
 * 国内网络基本连不上，表现就是"麦克风有信号但一个字都不出"。
 */
async function transcribeAudio(base64: string, format: string): Promise<string> {
  const result = await requestJson<{ text: string; elapsed_ms: number }>(
    '/api/v1/interview/asr',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ audio: base64, format }),
    },
    '语音转写失败',
  )
  return result.text
}

let cameraStream: MediaStream | null = null
let timer: number | undefined
let audio: HTMLAudioElement | null = null

const cameraOn = ref(false)
const cameraError = ref('')
/** 大厅试音：麦克风电平是否已经证明能收到声音 */
const micChecked = ref(false)
const micChecking = ref(false)
const micSampleUrl = ref('')
const micSamplePlaying = ref(false)

/* ------------------------------------------------- 新增状态：计时 / 历史 / 导出 */

/**
 * 本题计时（毫秒）。
 *
 * 只读 phase 与 lab.recording，从不写它们——录音链路的控制权仍然完全在 useSpeechLab 手里。
 * 阶段一变或录音一停就清 interval，卸载时由 leave() 兜底。
 */
const answerClockMs = ref(0)
let answerClockTimer: number | undefined
let answerClockBase = 0

/** 历史场次：新→旧，最多 10 场。 */
const HISTORY_KEY = 'zhq-interview-history-v1'
const HISTORY_LIMIT = 10
/** 语速曲线的理想区间（需求口径 200–260；后端维度文案写的是 190–270）。 */
/* 与后端 interview_service.py 的语速评分区间保持一致，避免同一页出现
   「曲线标偏快、语速维度说舒适」的矛盾。 */
const PACE_BAND_LOW = 190
const PACE_BAND_HIGH = 270
/** 历史维度只有 key，没回 label 时用它兜底。 */
const DIM_LABELS: Record<string, string> = {
  pace: '语速节奏',
  pause: '停顿控制',
  fluency: '表达干净度',
  presence: '音量与气场',
  composure: '临场应变',
  content: '内容密度',
}

const historyEntries = ref<HistoryEntry[]>([])
const historyOpen = ref(false)
const historyExpandedAt = ref('')
const clearArmed = ref(false)
/** 同一份报告只入历史一次，避免重复渲染把一次成绩记成两场。 */
let historyRecorded = false
/** 导出用的 objectURL 回收定时器，卸载时要清掉。 */
let downloadUrlTimer: number | undefined
/** 「已导出 …」提示的自动消失定时器，同样要清。 */
let noticeTimer: number | undefined

/* ------------------------------------------------------------------ 派生 */

const activeExaminer = computed(() => examiners.value.find((item) => item.id === turn.value?.examiner) ?? examiners.value[0])

/** 写到 3D 教室后墙黑板上的内容：当前第几题、谁在问、问什么。 */
const boardContent = computed(() => {
  const current = turn.value
  if (!current) return null
  return {
    speaker: current.examiner_name,
    intent: current.intent,
    question: current.question,
    step: current.step + 1,
    total: current.total,
  }
})
const progress = computed(() => {
  const total = turn.value?.total ?? plan.value.length ?? 1
  return Math.min(100, Math.round((stepIndex.value / Math.max(1, total)) * 100))
})
const elapsedText = computed(() => {
  const total = elapsed.value
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
})
const budgetText = computed(() => `${minutes.value}:00`)
const liveRateHint = computed(() => {
  const rate = lab.liveCharsPerMin.value
  if (!rate) return '等待开口'
  if (rate < 190) return '偏慢'
  if (rate <= 270) return '合适'
  return '偏快'
})
const liveRateTone = computed(() => {
  const rate = lab.liveCharsPerMin.value
  if (!rate) return 'idle'
  if (rate < 190 || rate > 270) return 'warn'
  return 'good'
})
const canFinish = computed(() => answers.value.length > 0 && !busy.value)

/* ------------------------------------------------------------ 答题计时器 */

const answerClockVisible = computed(() => stage.value === 'live' && phase.value === 'answer')

const answerClockText = computed(() => {
  const total = Math.floor(answerClockMs.value / 1000)
  const mm = String(Math.floor(total / 60)).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  return `${mm}:${ss}`
})

/** 90 秒转黄、150 秒转红——和「建议控制在 2 分钟内」的提示配套。 */
const answerClockTone = computed(() => {
  const seconds = answerClockMs.value / 1000
  if (seconds > 150) return 'over'
  if (seconds > 90) return 'warn'
  return 'ok'
})

const answerClockHint = computed(() => (answerClockMs.value / 1000 > 150 ? '建议控制在 2 分钟内' : ''))

function tickAnswerClock(): void {
  answerClockMs.value = performance.now() - answerClockBase
}

function startAnswerClock(): void {
  stopAnswerClock()
  answerClockMs.value = 0
  answerClockBase = performance.now()
  answerClockTimer = window.setInterval(tickAnswerClock, 100)
}

function stopAnswerClock(): void {
  if (answerClockTimer !== undefined) {
    window.clearInterval(answerClockTimer)
    answerClockTimer = undefined
  }
}

/** 归零并停表：换题、离场、卸载都走这里，保证不会有 interval 活过组件。 */
function resetAnswerClock(): void {
  stopAnswerClock()
  answerClockMs.value = 0
}

/**
 * 计时器的开关逻辑：只有「答题阶段 + 正在收音」两个条件同时成立才走表。
 *
 * 单独抽出来是为了能脱离组件直接验证这张状态转移表：
 *   answer+录音  → 开始（已在走则不重复建 interval）
 *   answer+停录  → 停表、保留读数
 *   其他任何阶段 → 停表 + 归零
 */
function syncAnswerClock(nowPhase: Phase, recording: boolean): void {
  if (nowPhase === 'answer' && recording) {
    if (answerClockTimer === undefined) startAnswerClock()
    return
  }
  stopAnswerClock()
  if (nowPhase !== 'answer') answerClockMs.value = 0
}

/**
 * 计时器唯一的驱动源：phase 与 lab.recording。
 *
 * 只读这两个值，不写它们——录音链路的控制权仍然完全在 useSpeechLab 手里。
 */
watch(
  () => [phase.value, lab.recording.value] as const,
  ([nowPhase, recording]) => syncAnswerClock(nowPhase, recording),
)

/* ------------------------------------------------------------------ 面板 */

async function loadPanel(): Promise<void> {
  try {
    const data = await requestJson<{
      examiners: Examiner[]
      plan: PlanStep[]
      speech: { available: boolean; note: string }
      asr: { available: boolean; note: string; model: string }
    }>(`/api/v1/interview/panel?minutes=${minutes.value}`, {}, '考官信息加载失败')
    examiners.value = data.examiners
    plan.value = data.plan
    speechReady.value = data.speech.available
    speechNote.value = data.speech.note
    asrReady.value = data.asr.available
    if (!data.asr.available) {
      lab.recognitionIssue.value = data.asr.note
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '考官信息加载失败'
  }
}

/* ------------------------------------------------------------------ 摄像头 */

async function startCamera(): Promise<void> {
  cameraError.value = ''
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { width: 640, height: 480, facingMode: 'user' },
      audio: false,
    })
    cameraOn.value = true
    await nextTick()
    if (selfView.value) {
      selfView.value.srcObject = cameraStream
      await selfView.value.play().catch(() => undefined)
    }
  } catch {
    cameraOn.value = false
    cameraError.value = '摄像头未授权。面试仍可继续，但建议打开摄像头练习镜头感。'
  }
}

function stopCamera(): void {
  cameraStream?.getTracks().forEach((track) => track.stop())
  cameraStream = null
  cameraOn.value = false
  if (selfView.value) selfView.value.srcObject = null
}

/* ------------------------------------------------------------------ 麦克风自检 */

/**
 * 大厅阶段的试音。
 *
 * 报"听不到我声音"时，用户没法自己判断是哪一层出的问题：权限、设备、
 * 音频上下文、还是阈值。所以进房前先跑一遍：开麦 → 标定噪声底 → 显示实时电平，
 * 只要开口条子会跳，就说明链路是通的；再录 3 秒回放，能听见自己就彻底排除设备问题。
 */
async function runMicCheck(): Promise<void> {
  if (micChecking.value) return
  micChecking.value = true
  micSampleUrl.value = ''
  try {
    await lab.openMic()
    await lab.calibrate()
    lab.startMonitor()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '麦克风不可用'
  } finally {
    micChecking.value = false
  }
}

async function recordMicSample(): Promise<void> {
  if (micSamplePlaying.value) {
    micSamplePlaying.value = false
    return
  }
  try {
    const url = await lab.recordSample(3000)
    if (!url) {
      error.value = '没有录到音频，请确认麦克风设备与系统音量'
      return
    }
    micSampleUrl.value = url
    micSamplePlaying.value = true
    const player = new Audio(url)
    player.onended = () => {
      micSamplePlaying.value = false
    }
    await player.play().catch(() => {
      micSamplePlaying.value = false
      error.value = '浏览器拦截了回放，请再点一次'
    })
  } catch {
    error.value = '录音失败，请检查麦克风'
  }
}

/** 试音时只要电平明显超过阈值，就认为麦克风通了。 */
watch(
  () => lab.peakRms.value,
  (value) => {
    if (!micChecked.value && lab.calibrated.value && value > lab.voiceThreshold.value * 1.4) {
      micChecked.value = true
    }
  },
)

/* ------------------------------------------------------------------ 全屏 */

async function enterFullscreen(): Promise<void> {
  const element = root.value
  if (!element || document.fullscreenElement) return
  try {
    await element.requestFullscreen()
    fullscreen.value = true
  } catch {
    fullscreen.value = false
  }
}

async function exitFullscreen(): Promise<void> {
  if (document.fullscreenElement) {
    try {
      await document.exitFullscreen()
    } catch {
      // 用户可能已经手动退出
    }
  }
  fullscreen.value = false
}

function onFullscreenChange(): void {
  fullscreen.value = Boolean(document.fullscreenElement)
}

/* ------------------------------------------------------------------ 语音 */

/** 语音代次：每次 stopAudio 都 +1，用来作废还在下载中的旧请求。 */
let speechGeneration = 0
/** 已经建过、还没回收的 blob 地址 */
let speechObjectUrl: string | null = null

function releaseObjectUrl(): void {
  if (speechObjectUrl) {
    URL.revokeObjectURL(speechObjectUrl)
    speechObjectUrl = null
  }
}

function stopAudio(): void {
  speechGeneration += 1
  if (audio) {
    const player = audio
    audio = null
    // 回调全部摘干净：清空 src 会触发一次 error 事件，
    // 若上一段的 onerror 还挂着，就会在"新语音正在加载"时弹一句失败提示。
    player.onended = null
    player.onerror = null
    player.oncanplay = null
    player.onplaying = null
    try {
      player.pause()
      player.removeAttribute('src')
      player.load()
    } catch {
      // 元素已经不可用就忽略
    }
  }
  releaseObjectUrl()
  speaking.value = null
  speechLoading.value = false
}

/**
 * 先把 mp3 整个取回来，再交给 `<audio>` 播放。
 *
 * 不直接把 ``/tts/{token}.mp3`` 塞给 ``<audio>``：那个接口要等上游合成出首字节
 * 才响应，大约 2 秒。媒体元素在等待期间的失败语义和真实网络错误混在一起，
 * 分不清"还在路上"和"真的挂了"，界面上就会出现"显示加载失败但语音随后正常播放"。
 * 改成 fetch 之后，等待是明确的加载态，失败是明确的 HTTP 状态码。
 */
async function fetchSpeechBlob(url: string): Promise<string> {
  const response = await fetch(url)
  if (!response.ok) {
    let detail = ''
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // 不是 JSON 就按状态码说话
    }
    throw new Error(detail || `HTTP ${response.status}`)
  }
  const blob = await response.blob()
  if (blob.size < 1024) throw new Error('音频数据为空')
  return URL.createObjectURL(blob)
}

/** 播放导师语音；返回播放结束的时间戳（用于算开口延迟）。 */
async function playSpeech(url: string, examinerId: string): Promise<number> {
  stopAudio()
  const generation = speechGeneration
  speechLoading.value = true
  let objectUrl: string
  try {
    objectUrl = await fetchSpeechBlob(url)
  } catch (reason) {
    if (generation !== speechGeneration) return performance.now()
    speechLoading.value = false
    const detail = reason instanceof Error && reason.message ? `：${reason.message}` : ''
    notice.value = `导师语音加载失败${detail}，已切换为文字提问`
    return performance.now()
  }
  // 下载途中已经被停止（换题、重听、退出）
  if (generation !== speechGeneration) {
    URL.revokeObjectURL(objectUrl)
    return performance.now()
  }
  speechObjectUrl = objectUrl
  return await new Promise((resolve) => {
    const player = new Audio(objectUrl)
    audio = player
    let settled = false
    const finish = (): void => {
      if (settled) return
      settled = true
      speechLoading.value = false
      speaking.value = null
      resolve(performance.now())
    }
    player.onplaying = () => {
      speechLoading.value = false
      speaking.value = examinerId
    }
    player.onended = finish
    player.onerror = () => {
      notice.value = '导师语音播放失败，已切换为文字提问'
      finish()
    }
    player.play().catch((reason: unknown) => {
      const name = reason instanceof DOMException ? reason.name : ''
      notice.value =
        name === 'NotAllowedError'
          ? '浏览器拦截了自动播放，点击"重听"可以播放导师语音'
          : '导师语音播放失败，已切换为文字提问'
      finish()
    })
  })
}

function browserSpeak(text: string, language: string): Promise<number> {
  if (!('speechSynthesis' in window)) return Promise.resolve(performance.now())
  window.speechSynthesis.cancel()
  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = language === 'en' ? 'en-US' : 'zh-CN'
    utterance.rate = 0.98
    utterance.onend = () => resolve(performance.now())
    utterance.onerror = () => resolve(performance.now())
    window.speechSynthesis.speak(utterance)
  })
}

async function speakQuestion(text: string, examinerId: string, language: string): Promise<number> {
  // 上一题的语音提示不该留到这一题：这一题还没开始加载就先清掉，
  // 否则"失败"两个字会和正在正常合成的语音同时挂在屏幕上。
  notice.value = ''
  if (speechReady.value) {
    try {
      const ticket = await requestJson<TtsTicket>(
        '/api/v1/interview/tts',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, examiner: examinerId, language }),
        },
        '导师语音生成失败',
      )
      return await playSpeech(ticket.url, examinerId)
    } catch {
      notice.value = '导师语音服务暂不可用，已切换为浏览器语音'
    }
  }
  return await browserSpeak(text, language)
}

/* ------------------------------------------------------------------ 流程 */

async function begin(): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    // 大厅已经试音过就复用，否则这里补一次开麦 + 标定
    await lab.openMic()
    if (!lab.calibrated.value) await lab.calibrate()
    lab.stopMonitor()
    // 先切到 live 让 <video> 挂载，再开摄像头，否则 srcObject 赋给不存在的元素
    stage.value = 'live'
    await nextTick()
    await startCamera()
    await enterFullscreen()
    startedAtMs.value = performance.now()
    elapsed.value = 0
    timer = window.setInterval(() => {
      elapsed.value = Math.round((performance.now() - startedAtMs.value) / 1000)
    }, 1000)
    await nextTick()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法开始面试'
    stage.value = 'lobby'
    busy.value = false
    return
  }
  // askNext 自己会抢 busy 锁，所以必须先释放，否则第一题会被守卫吞掉
  busy.value = false
  await askNext()
}

async function askNext(): Promise<void> {
  if (busy.value) return
  busy.value = true
  phase.value = 'idle'
  stopAudio()
  lab.abortAnswer()
  try {
    const next = await requestJson<Turn>(
      '/api/v1/interview/turn',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          major: major.value,
          minutes: minutes.value,
          strictness: strictness.value,
          step: stepIndex.value,
          history: transcriptLog.value.slice(-6).map((item) => ({
            role: item.role === 'me' ? 'user' : 'assistant',
            speaker: item.name,
            content: item.text,
          })),
        }),
      },
      '提问服务暂时不可用',
    )
    turn.value = next
    phase.value = 'question'
    transcriptLog.value.push({ role: 'examiner', name: next.examiner_name, text: next.question })
    busy.value = false

    const endedAt = await speakQuestion(next.question, next.examiner, next.language)
    promptEndedAtMs.value = endedAt
    phase.value = 'answer'
    // 关键：不管语音识别是否可用都要开麦录音。
    // 语速、停顿、音量、开口延迟都不依赖识别结果，只有文字才依赖。
    // 识别挂了也照样测指标，最后让考生补一句文字即可。
    if (!lab.beginAnswer(endedAt, next.language)) {
      openManualFallback('mic')
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '提问失败'
    busy.value = false
  }
}

async function submitVoice(): Promise<void> {
  if (!turn.value || submitting.value) return
  const current = turn.value
  submitting.value = true
  let metric: AnswerMetricPayload
  try {
    // endAnswer 会把最后半句切出去并等服务端转写落地，所以是异步的
    metric = await lab.endAnswer({
      index: stepIndex.value,
      examiner: current.examiner,
      question: current.question,
      hard: current.hard,
    })
  } finally {
    submitting.value = false
  }
  // 没出字但确实说了话：指标有效，让考生补一句要点再合并
  if (!metric.transcript && metric.speech_ms > 1200) {
    pendingMetric.value = metric
    openManualFallback('fill')
    return
  }
  // 一点声音都没采到：不要静默地把空回答计进成绩，先让考生确认
  if (!metric.transcript && metric.speech_ms <= 1200) {
    pendingMetric.value = metric
    manualTitle.value = '这一题没收到声音'
    manualHint.value =
      lab.micState.value === 'nosignal'
        ? '麦克风采到的信号恒为 0：检查设备是否被会议软件占用、系统输入设备是否选对、物理静音键是否按下。也可以直接用文字补这一题。'
        : `麦克风没有采到有效人声（峰值 ${Math.round(lab.peakRms.value * 1000)}‰，阈值 ${Math.round(lab.voiceThreshold.value * 1000)}‰）。可以直接用文字补这一题。`
    manualAnswer.value = ''
    manualOpen.value = true
    return
  }
  finishAnswer(metric, metric.transcript)
}

/** 把补写的文字并入已测得的语音指标。 */
function submitPendingTranscript(): void {
  const base = pendingMetric.value
  if (!base) return
  const text = manualAnswer.value.trim()
  if (!text) return
  const merged: AnswerMetricPayload = {
    ...base,
    transcript: text,
    chars: text.replace(/[\s，。、！？；：""''（）()《》…—\-.,!?;:]/g, '').length,
  }
  pendingMetric.value = null
  manualAnswer.value = ''
  manualOpen.value = false
  finishAnswer(merged, text)
}

function submitManual(): void {
  if (pendingMetric.value) {
    submitPendingTranscript()
    return
  }
  if (!turn.value) return
  const text = manualAnswer.value.trim()
  if (!text) return
  manualOpen.value = false
  const current = turn.value
  const chars = text.replace(/[\s，。、！？；：""''（）()《》…—\-.,!?;:]/g, '').length
  // 手输没有语音样本，只上报字数；其余指标留 0，服务端会按缺失处理
  const metric: AnswerMetricPayload = {
    index: stepIndex.value,
    examiner: current.examiner,
    question: current.question,
    transcript: text,
    duration_ms: Math.max(1000, chars * 220),
    speech_ms: Math.max(1000, chars * 220),
    latency_ms: 0,
    pause_count: 0,
    longest_pause_ms: 0,
    avg_volume: 0,
    volume_stability: 0,
    filler_count: 0,
    chars,
    syllables: 0,
    hard: current.hard,
  }
  manualAnswer.value = ''
  finishAnswer(metric, text)
}

function finishAnswer(metric: AnswerMetricPayload, text: string): void {
  answers.value.push(metric)
  transcriptLog.value.push({ role: 'me', name: '我', text: text || '（本题未识别到语音内容）' })
  lab.abortAnswer()
  manualOpen.value = false
  pendingMetric.value = null
  const total = turn.value?.total ?? plan.value.length
  if (turn.value?.closing || stepIndex.value + 1 >= total) {
    void finishInterview()
    return
  }
  stepIndex.value += 1
  void askNext()
}

/**
 * 文字作答的兜底入口。
 *
 * 三种原因要分开说，否则用户会被误导：
 *   browser —— 浏览器根本没有语音转写接口（Firefox 默认不支持）
 *   mic     —— 麦克风链路没就绪（权限 / 占用 / 音频上下文）
 *   fill    —— 麦克风正常、语音指标已记录，只是没识别出文字，补一句要点即可
 */
function openManualFallback(kind: 'browser' | 'mic' | 'fill'): void {
  if (kind === 'fill') {
    manualTitle.value = '补一句文字要点'
    manualHint.value = '语音指标已经记录下来了（语速、停顿、音量都在），只差文字内容。把你刚才说的话补一句要点即可。'
  } else if (kind === 'browser') {
    manualTitle.value = '这一题改用文字'
    manualHint.value =
      lab.recognitionIssue.value || '当前浏览器没有语音转写接口，文字请手动补写。麦克风指标仍会记录。'
  } else {
    manualTitle.value = '麦克风没就绪，这一题用文字'
    manualHint.value =
      lab.error.value ||
      (lab.micState.value === 'nosignal'
        ? '麦克风采到的信号恒为 0：检查设备是否被会议软件占用、系统输入设备是否选对、物理静音键是否按下。'
        : '麦克风链路没有就绪，请回到大厅点「开启并试音」确认后再试。')
  }
  manualAnswer.value = ''
  manualOpen.value = true
}

/** 从文字弹窗回到语音：重试本题的收音。 */
function retryVoice(): void {
  manualOpen.value = false
  pendingMetric.value = null
  startAnswering()
}

function replayQuestion(): void {
  const current = turn.value
  if (!current) return
  void speakQuestion(current.question, current.examiner, current.language).then((endedAt) => {
    promptEndedAtMs.value = endedAt
    phase.value = 'answer'
    if (!lab.beginAnswer(endedAt, current.language)) openManualFallback('mic')
  })
}

/** 直接开始作答（不重放题目），用于自动播放被拦截或识别中断后的续答。 */
function startAnswering(): void {
  const current = turn.value
  if (!current) return
  promptEndedAtMs.value = performance.now()
  phase.value = 'answer'
  if (!lab.beginAnswer(promptEndedAtMs.value, current.language)) {
    openManualFallback('mic')
  }
}

async function finishInterview(): Promise<void> {
  busy.value = true
  phase.value = 'report'
  stopAudio()
  lab.abortAnswer()
  lab.closeMic()
  window.clearInterval(timer)
  resetAnswerClock()
  await exitFullscreen()
  try {
    const fresh = await requestJson<InterviewReport>(
      '/api/v1/interview/report',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ major: major.value, minutes: minutes.value, strictness: strictness.value, answers: answers.value }),
      },
      '复盘报告生成失败',
    )
    report.value = fresh
    recordHistory(fresh)
    stage.value = 'report'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '复盘报告生成失败'
    stage.value = 'report'
  } finally {
    busy.value = false
  }
}

async function finishEarly(): Promise<void> {
  if (!canFinish.value) return
  await finishInterview()
}

function restart(): void {
  stage.value = 'lobby'
  phase.value = 'idle'
  answers.value = []
  transcriptLog.value = []
  report.value = null
  turn.value = null
  stepIndex.value = 0
  elapsed.value = 0
  error.value = ''
  notice.value = ''
  manualOpen.value = false
  // 新一场要重新入历史；清空历史的二次确认也归位
  resetAnswerClock()
  historyRecorded = false
  clearArmed.value = false
  historyExpandedAt.value = ''
}

function leave(): void {
  stopAudio()
  lab.closeMic()
  stopCamera()
  window.clearInterval(timer)
  window.speechSynthesis?.cancel()
  // 计时器与导出用的 objectURL 定时器都在这里收尾，卸载后不留活着的 interval
  resetAnswerClock()
  if (downloadUrlTimer !== undefined) {
    window.clearTimeout(downloadUrlTimer)
    downloadUrlTimer = undefined
  }
  if (noticeTimer !== undefined) {
    window.clearTimeout(noticeTimer)
    noticeTimer = undefined
  }
  void exitFullscreen()
}

/* ------------------------------------------------- 语速曲线（SVG 手写） */

/**
 * 逐题语速曲线。
 *
 * 数据来源就是报告里的 report.answers[].chars_per_min（后端按「有效字数 / 有效说话时长」算的），
 * 不再自己重算一遍，保证曲线和逐题复盘卡片上的数字完全一致。
 * 0 字/分表示这题没测到人声，直接跳过——画在 0 上会读成「说得极慢」，是错的。
 */
const paceChart = computed<PaceChart | null>(() => {
  const rows = (report.value?.answers ?? [])
    .filter((item) => item.chars_per_min > 0)
    .map((item) => ({ no: item.index + 1, rate: item.chars_per_min }))
  if (!rows.length) return null

  const width = 680
  const height = 216
  const left = 46
  const right = 18
  const top = 26
  const bottom = 36
  const innerW = width - left - right
  const innerH = height - top - bottom
  const baseline = top + innerH
  const peak = Math.max(PACE_BAND_HIGH, ...rows.map((row) => row.rate))
  const yMax = Math.max(300, Math.ceil((peak + 40) / 50) * 50)
  /** 坐标保留两位：SVG 属性里不出现 79.89999999999999 这种浮点噪声。 */
  const round2 = (value: number): number => Math.round(value * 100) / 100
  const yOf = (rate: number): number => round2(top + innerH - (Math.min(yMax, Math.max(0, rate)) / yMax) * innerH)
  const toneOf = (rate: number): PacePoint['tone'] =>
    rate < PACE_BAND_LOW ? 'slow' : rate > PACE_BAND_HIGH ? 'fast' : 'fit'
  const single = rows.length === 1

  const points: PacePoint[] = rows.map((row, index) => {
    const x = round2(single ? left + innerW / 2 : left + (innerW * index) / (rows.length - 1))
    const y = yOf(row.rate)
    return {
      no: row.no,
      rate: row.rate,
      x,
      y,
      tone: toneOf(row.rate),
      labelY: Math.max(top - 8, y - 9),
      tagY: Math.max(12, y - 22),
    }
  })

  const ticks: Array<{ value: number; y: number }> = []
  for (let value = 0; value <= yMax; value += 100) ticks.push({ value, y: yOf(value) })

  return {
    width,
    height,
    left,
    right,
    baseline,
    single,
    band: { y: yOf(PACE_BAND_HIGH), height: round2(yOf(PACE_BAND_LOW) - yOf(PACE_BAND_HIGH)) },
    refs: [yOf(PACE_BAND_LOW), yOf(PACE_BAND_HIGH)],
    ticks,
    points,
    path: points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' '),
    bar: single
      ? {
          x: round2(points[0].x - 16),
          y: points[0].y,
          width: 32,
          height: Math.max(2, round2(baseline - points[0].y)),
        }
      : null,
  }
})

/** 图下那句自动结论：只挑最出格的一题说，别把七句话堆在一起。 */
const paceConclusion = computed(() => {
  const chart = paceChart.value
  if (!chart) return ''
  const fast = chart.points.filter((point) => point.rate > PACE_BAND_HIGH).sort((a, b) => b.rate - a.rate)[0]
  const slow = chart.points.filter((point) => point.rate < PACE_BAND_LOW).sort((a, b) => a.rate - b.rate)[0]
  const parts: string[] = []
  if (fast) parts.push(`第 ${fast.no} 题语速 ${fast.rate} 字/分明显偏快，建议放慢，句末留半拍再换气`)
  if (slow) parts.push(`第 ${slow.no} 题语速 ${slow.rate} 字/分偏慢，内容容易显得拖沓，可以稍微加快`)
  if (parts.length) return `${parts.join('；')}。`
  return `${chart.points.length} 题语速都落在 ${PACE_BAND_LOW}–${PACE_BAND_HIGH} 字/分的舒适区间，节奏控制得不错。`
})

/* ------------------------------------------------------ 历史场次对比 */

function isHistoryEntry(value: unknown): value is HistoryEntry {
  if (!value || typeof value !== 'object') return false
  const row = value as Partial<HistoryEntry>
  return (
    typeof row.at === 'string' &&
    typeof row.overall === 'number' &&
    typeof row.grade === 'string' &&
    Array.isArray(row.dimensions)
  )
}

function loadHistory(): void {
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY)
    if (!raw) {
      historyEntries.value = []
      return
    }
    const parsed: unknown = JSON.parse(raw)
    historyEntries.value = Array.isArray(parsed) ? parsed.filter(isHistoryEntry).slice(0, HISTORY_LIMIT) : []
  } catch {
    // 存储被禁用（隐私模式）或内容损坏：当作没有历史，报告本身照常看
    historyEntries.value = []
  }
}

/** 报告落地后立刻记一场。同一份报告只记一次。 */
function recordHistory(current: InterviewReport): void {
  if (historyRecorded) return
  historyRecorded = true
  const entry: HistoryEntry = {
    at: new Date().toISOString(),
    overall: current.overall,
    grade: current.grade,
    dimensions: (current.dimensions ?? []).map((dim) => ({ key: dim.key, score: dim.score })),
    speech: {
      chars_per_min: current.speech?.chars_per_min ?? 0,
      filler_rate: current.speech?.filler_rate ?? 0,
      speech_ratio: current.speech?.speech_ratio ?? 0,
    },
  }
  const next = [entry, ...historyEntries.value].slice(0, HISTORY_LIMIT)
  historyEntries.value = next
  try {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(next))
  } catch {
    // 配额满或被禁用：本次对比仍能在内存里显示，只是下次进来会丢
  }
}

const historyDelta = computed(() => {
  if (historyEntries.value.length < 2) return null
  const current = historyEntries.value[0]
  const previous = historyEntries.value[1]
  return { diff: current.overall - previous.overall, prev: previous.overall, at: previous.at }
})

/** 10 场总分的迷你折线：只有点和线，没有坐标轴。 */
const historySpark = computed(() => {
  const rows = [...historyEntries.value].reverse()
  if (rows.length < 2) return null
  const width = 240
  const height = 54
  const pad = 7
  const scores = rows.map((row) => row.overall)
  const min = Math.min(...scores)
  const max = Math.max(...scores)
  const span = max - min
  const points = rows.map((row, index) => ({
    x: pad + ((width - pad * 2) * index) / (rows.length - 1),
    y: span === 0 ? height / 2 : pad + (height - pad * 2) * (1 - (row.overall - min) / span),
    last: index === rows.length - 1,
  }))
  return {
    width,
    height,
    points,
    path: points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(' '),
  }
})

function dimLabel(key: string): string {
  const hit = report.value?.dimensions?.find((dim) => dim.key === key)
  return hit?.label ?? DIM_LABELS[key] ?? key
}

function toggleHistoryOpen(): void {
  historyOpen.value = !historyOpen.value
  if (!historyOpen.value) historyExpandedAt.value = ''
  clearArmed.value = false
}

function toggleHistoryEntry(at: string): void {
  historyExpandedAt.value = historyExpandedAt.value === at ? '' : at
}

/** 两段式清空：第一下改成确认，避免演示时误触把历史点没。 */
function clearHistory(): void {
  if (!clearArmed.value) {
    clearArmed.value = true
    return
  }
  clearArmed.value = false
  historyEntries.value = []
  historyOpen.value = false
  historyExpandedAt.value = ''
  try {
    window.localStorage.removeItem(HISTORY_KEY)
  } catch {
    // 存储不可用：内存里已经清空，界面表现一致
  }
}

/* ------------------------------------------------------------ 报告导出 */

function formatStamp(input: string | number | Date): string {
  const date = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(date.getTime())) return String(input)
  const pad = (value: number): string => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function stampForFilename(date: Date): string {
  const pad = (value: number): string => String(value).padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}`
}

/** Markdown 表格里不能有换行和裸竖线。 */
function mdEscape(text: string): string {
  return String(text ?? '')
    .replace(/\r?\n+/g, ' ')
    .replace(/\|/g, '\\|')
    .trim()
}

function buildReportMarkdown(current: InterviewReport, at: Date): string {
  const lines: string[] = []
  const speech = current.speech
  lines.push('# AI 模拟复试报告', '')
  lines.push(`时间：${formatStamp(at)}`)
  lines.push(`综合得分：${current.overall} / 100　等级：${current.grade}`)
  if (current.headline) lines.push(mdEscape(current.headline))
  lines.push('', '## 五维评估', '')
  lines.push('| 维度 | 得分 | 依据 | 建议 |')
  lines.push('|---|---|---|---|')
  for (const dim of current.dimensions ?? []) {
    lines.push(`| ${mdEscape(dim.label)} | ${dim.score} | ${mdEscape(dim.evidence)} | ${mdEscape(dim.advice)} |`)
  }
  lines.push('', '## 语音表现', '')
  lines.push(`- 总时长：${speech.total_seconds} 秒`)
  lines.push(`- 有效表达占比：${speech.speech_ratio}%`)
  lines.push(`- 平均语速：${speech.chars_per_min} 字/分`)
  lines.push(`- 填充词：${speech.filler_total} 次（占比 ${speech.filler_rate}%，按每百字计）`)
  lines.push(`- 最长停顿：${speech.longest_pause_ms} ms`)
  lines.push(`- 停顿次数：${speech.pause_count} 次`)
  lines.push(`- 开口延迟：${(speech.latency_ms / 1000).toFixed(1)} 秒`)
  lines.push(`- 平均音量：${speech.avg_volume} / 100（稳定性 ${speech.volume_stability} / 100）`)
  lines.push('', '## 逐题复盘', '')
  for (const item of current.answers ?? []) {
    lines.push(`### 第 ${item.index + 1} 题 · ${item.examiner_name}`, '')
    lines.push(`**问：** ${mdEscape(item.question)}`)
    lines.push(`**答：** ${item.transcript ? mdEscape(item.transcript) : '（本题没有识别到语音内容）'}`)
    lines.push(
      `**评：** ${item.verdict}（${item.chars_per_min} 字/分，停顿 ${item.pause_count} 次，最长 ${(item.longest_pause_ms / 1000).toFixed(1)} 秒）`,
    )
    lines.push('')
  }
  lines.push('## 亮点', '')
  if ((current.highlights ?? []).length) {
    for (const line of current.highlights) lines.push(`- ${mdEscape(line)}`)
  } else {
    lines.push('- （本场没有记录到亮点）')
  }
  lines.push('', '## 待改进', '')
  if ((current.fixes ?? []).length) {
    for (const line of current.fixes) lines.push(`- ${mdEscape(line)}`)
  } else {
    lines.push('- （本场没有待改进项）')
  }
  lines.push('')
  return lines.join('\n')
}

function downloadText(filename: string, text: string, mime: string): void {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
  // 立刻回收会让部分浏览器来不及取数据，延后一点并记住这个定时器
  if (downloadUrlTimer !== undefined) window.clearTimeout(downloadUrlTimer)
  downloadUrlTimer = window.setTimeout(() => {
    URL.revokeObjectURL(url)
    downloadUrlTimer = undefined
  }, 1200)
}

/** 提示只挂两秒多就走，不然会一直压在报告页顶上。 */
function flashNotice(text: string): void {
  notice.value = text
  if (noticeTimer !== undefined) window.clearTimeout(noticeTimer)
  noticeTimer = window.setTimeout(() => {
    noticeTimer = undefined
    if (notice.value === text) notice.value = ''
  }, 2600)
}

function exportReportMarkdown(): void {
  const current = report.value
  if (!current) return
  const now = new Date()
  const name = `复试报告-${stampForFilename(now)}.md`
  downloadText(name, buildReportMarkdown(current, now), 'text/markdown')
  flashNotice(`已导出 ${name}`)
}

function exportReportJson(): void {
  const current = report.value
  if (!current) return
  const name = `复试报告-${stampForFilename(new Date())}.json`
  downloadText(name, JSON.stringify(current, null, 2), 'application/json')
  flashNotice(`已导出 ${name}`)
}

/* ------------------------------------------------------------------ 生命周期 */

watch(minutes, () => {
  void loadPanel()
})

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  // 沉浸式页面：隐藏全局引导员并锁滚动，避免和 3D 场景抢视觉
  document.body.classList.add('iv-immersive')
  loadHistory()
  void loadPanel()
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.body.classList.remove('iv-immersive')
  leave()
})
</script>

<template>
  <div ref="root" class="iv-root" :class="[`is-${stage}`, { 'is-fullscreen': fullscreen }]">
    <!-- 3D 教室始终在渲染：大厅阶段就已经能看见教室，进入后直接接管全屏 -->
    <ClassroomScene class="iv-scene" :speaking="speaking" :phase="phase" :stage="stage" :board="boardContent" />

    <!-- 顶栏 -->
    <header class="iv-hud">
      <div class="iv-hud-left">
        <RouterLink v-if="stage !== 'live'" to="/academic" class="iv-exit" @click="leave">
          <PhArrowLeft :size="17" /> 返回
        </RouterLink>
        <button v-else type="button" class="iv-exit" @click="finishEarly">
          <PhX :size="16" /> 结束面试
        </button>
        <div v-if="stage === 'live'" class="iv-clock">
          <span class="iv-clock-now">{{ elapsedText }}</span>
          <span class="iv-clock-cap">/ {{ budgetText }}</span>
        </div>
        <div v-if="stage === 'live'" class="iv-progress">
          <i :style="{ width: `${progress}%` }" />
        </div>
        <span v-if="stage === 'live' && turn" class="iv-step">第 {{ stepIndex + 1 }} / {{ turn.total }} 题</span>
        <!-- 答题计时：只在答题阶段出现，贴在 HUD 里，不挡考官也不挡字幕 -->
        <div v-if="answerClockVisible" class="ivx-timer" :class="answerClockTone">
          <PhTimer :size="14" />
          <b>{{ answerClockText }}</b>
          <em v-if="answerClockHint">{{ answerClockHint }}</em>
        </div>
      </div>
      <div class="iv-hud-right">
        <span class="iv-flag" :class="{ on: cameraOn }">
          <component :is="cameraOn ? PhVideoCamera : PhVideoCameraSlash" :size="15" />
          {{ cameraOn ? '摄像头已开' : '摄像头关闭' }}
        </span>
        <span class="iv-flag" :class="{ on: lab.micGranted.value }">
          <component :is="lab.micGranted.value ? PhMicrophone : PhMicrophoneSlash" :size="15" />
          {{ lab.micGranted.value ? '麦克风已开' : '麦克风关闭' }}
        </span>
        <button v-if="stage === 'live' && !fullscreen" type="button" class="iv-ghost" @click="enterFullscreen">
          <PhArrowsOut :size="15" /> 全屏
        </button>
      </div>
    </header>

    <!-- 大厅：教室已经渲染好，上面盖一层设置卡 -->
    <div v-if="stage === 'lobby'" class="iv-lobby">
      <div class="iv-lobby-card">
        <span class="iv-lobby-mark">复试</span>
        <h1>把紧张留在教室外面，<br /><em>把从容带进复试现场。</em></h1>
        <p class="iv-lobby-lead">
          三位导师坐在长桌后依次提问，全程语音对话。你必须开口回答——系统会现场测量语速、停顿、音量与口头禅，
          结束后给出一份可复核的复盘报告。
        </p>

        <div class="iv-examiner-row">
          <article v-for="item in examiners" :key="item.id" class="iv-examiner-chip" :style="{ '--tone': item.color }">
            <strong>{{ item.name }}</strong>
            <span>{{ item.title }}</span>
            <small>{{ item.duty }}</small>
          </article>
        </div>

        <form class="iv-form" @submit.prevent="begin">
          <label class="iv-field">
            <span>目标专业</span>
            <input v-model="major" required maxlength="20" placeholder="例如：人工智能" />
          </label>
          <div class="iv-field-row">
            <label class="iv-field">
              <span>模拟时长</span>
              <select v-model.number="minutes">
                <option :value="5">5 分钟 · 快速热身</option>
                <option :value="15">15 分钟 · 标准复试</option>
                <option :value="30">30 分钟 · 完整流程</option>
              </select>
            </label>
            <label class="iv-field">
              <span>导师风格</span>
              <select v-model="strictness">
                <option>鼓励</option>
                <option>常规</option>
                <option>严格追问</option>
              </select>
            </label>
          </div>

          <ul class="iv-ready">
            <li :class="{ ok: lab.micGranted.value }">
              <component :is="lab.micGranted.value ? PhCheckCircle : PhMicrophone" :size="15" />
              麦克风（必开，用语音作答）
            </li>
            <li :class="{ ok: cameraOn }">
              <component :is="cameraOn ? PhCheckCircle : PhVideoCamera" :size="15" />
              摄像头（建议开启，用于镜头感练习）
            </li>
            <li :class="{ ok: speechReady }">
              <component :is="speechReady ? PhCheckCircle : PhWaveform" :size="15" />
              {{ speechReady ? '导师真人语音已就绪' : '导师语音将使用浏览器合成' }}
            </li>
            <li :class="{ ok: asrReady, warn: !asrReady }">
              <PhWaveform :size="15" />
              <template v-if="asrReady">语音转写已就绪（MiMo-ASR）</template>
              <template v-else>语音转写不可用，文字请手动补录</template>
            </li>
          </ul>

          <!-- 麦克风自检：把"听不到声音"拆成可判断的几层 -->
          <section class="iv-miccheck" :class="{ live: lab.calibrated.value }">
            <header>
              <strong>麦克风试音</strong>
              <span v-if="!lab.calibrated.value">先测一下，避免进教室后才发现没声音</span>
              <span v-else-if="micChecked" class="ok">已收到你的声音</span>
              <span v-else class="warn">还没听到声音，说句话试试</span>
            </header>
            <div class="iv-miccheck-bar">
              <i :style="{ width: `${Math.round(lab.liveVolume.value * 100)}%` }" />
              <b v-if="lab.calibrated.value" :style="{ left: `${Math.round((lab.voiceThreshold.value / Math.max(0.016, lab.voiceThreshold.value * 3)) * 100)}%` }" />
            </div>
            <div class="iv-miccheck-meta">
              <span>输入电平 {{ Math.round(lab.rawRms.value * 1000) }}‰</span>
              <span v-if="lab.calibrated.value">噪声底 {{ Math.round(lab.noiseFloor.value * 1000) }}‰ · 阈值 {{ Math.round(lab.voiceThreshold.value * 1000) }}‰</span>
              <span>峰值 {{ Math.round(lab.peakRms.value * 1000) }}‰</span>
            </div>
            <div class="iv-miccheck-actions">
              <button type="button" class="iv-ghost" :disabled="micChecking" @click="runMicCheck">
                <component :is="micChecking ? PhCircleNotch : PhMicrophone" :size="14" :class="{ spin: micChecking }" />
                {{ lab.calibrated.value ? '重新测一次' : '开启并试音' }}
              </button>
              <button v-if="lab.calibrated.value" type="button" class="iv-ghost" @click="recordMicSample">
                <component :is="micSamplePlaying ? PhCircleNotch : PhPlay" :size="14" :class="{ spin: micSamplePlaying }" />
                录 3 秒回放
              </button>
            </div>
            <p v-if="lab.micState.value === 'nosignal'" class="iv-miccheck-warn">
              采到的信号恒为 0。常见原因：麦克风被会议软件占用、系统输入设备选错、或笔记本的物理静音键按下了。
            </p>
            <p v-else-if="lab.micState.value === 'suspended'" class="iv-miccheck-warn">
              浏览器的音频上下文没能启动，请刷新页面后重新进入。
            </p>
            <p v-else-if="lab.micState.value === 'denied'" class="iv-miccheck-warn">
              麦克风权限被拒绝，请点地址栏左侧图标改成「允许」后刷新。
            </p>
            <p v-else-if="lab.recognitionIssue.value" class="iv-miccheck-warn">
              {{ lab.recognitionIssue.value }}
            </p>
          </section>

          <button type="submit" class="iv-primary" :disabled="busy">
            <component :is="busy ? PhCircleNotch : PhPlay" :size="18" :class="{ spin: busy }" />
            进入教室，开始面试
          </button>
          <p class="iv-lobby-note">
            进入后会请求全屏、摄像头与麦克风权限。语速、停顿、音量在你本机实时计算，不上传；
            <b>语音转写</b>会把切好的短句送到服务端（小米 MiMo-ASR）转成文字，用于内容评分与字幕。
            万一转写不可用，语速与停顿仍会照常测量，只需在每题结束后补一句文字要点。
          </p>
        </form>
      </div>
    </div>

    <!-- 进行中：底部字幕条 + 右侧实时指标 + 右下镜像小窗 -->
    <template v-if="stage === 'live'">
      <section class="iv-subtitle" :class="{ 'is-live': phase === 'question' }">
        <div class="iv-subtitle-head">
          <span class="iv-who" :style="{ '--tone': activeExaminer?.color }">{{ turn?.examiner_name ?? '导师' }}</span>
          <span class="iv-intent">{{ turn?.intent }}</span>
          <button type="button" class="iv-replay" :disabled="busy" @click="replayQuestion">
            <PhPlay :size="13" weight="fill" /> 重听
          </button>
        </div>
        <p class="iv-question">
          {{ turn?.question ?? '正在请考官提问…' }}
        </p>
        <p v-if="speechLoading" class="iv-speech-loading">
          <PhCircleNotch :size="13" class="spin" />
          {{ turn?.examiner_name ?? '导师' }}正在组织语言，约 2 秒出声…
        </p>
        <div class="iv-wave" :class="{ active: speaking, pending: speechLoading }">
          <i v-for="n in 26" :key="n" :style="{ animationDelay: `${n * 40}ms` }" />
        </div>
      </section>

      <aside class="iv-metrics">
        <h2><PhWaveform :size="15" weight="bold" /> 实时语音</h2>
        <div class="iv-meter">
          <span>语速</span>
          <strong>{{ lab.liveCharsPerMin.value || '—' }}<small>字/分</small></strong>
          <em :class="liveRateTone">{{ liveRateHint }}</em>
        </div>
        <div class="iv-meter">
          <span>停顿</span>
          <strong>{{ lab.livePauseCount.value }}<small>次</small></strong>
        </div>
        <div class="iv-meter">
          <span>已说</span>
          <strong>{{ lab.liveSeconds.value }}<small>秒</small></strong>
        </div>
        <div class="iv-volume">
          <span>音量 <b>{{ Math.round(lab.rawRms.value * 1000) }}‰</b></span>
          <div class="iv-volume-bar">
            <i :style="{ width: `${Math.round(lab.liveVolume.value * 100)}%` }" />
            <b class="iv-volume-threshold" />
          </div>
          <small class="iv-volume-hint">峰值 {{ Math.round(lab.peakRms.value * 1000) }}‰ · 阈值 {{ Math.round(lab.voiceThreshold.value * 1000) }}‰</small>
        </div>
        <p v-if="lab.recording.value && lab.silentMs.value > 5000" class="iv-metrics-silent">
          已经 {{ Math.round(lab.silentMs.value / 1000) }} 秒没收到声音了。检查一下麦克风，或者点「改用文字」。
        </p>
        <p class="iv-metrics-tip">
          中文面试的舒适语速是 <b>190–270 字/分</b>；单次停顿超过 2.5 秒会被听成卡壳。
        </p>
      </aside>

      <div class="iv-selfview" :class="{ off: !cameraOn }">
        <video ref="selfView" autoplay muted playsinline />
        <span v-if="!cameraOn" class="iv-selfview-off"><PhVideoCameraSlash :size="16" /> 未开摄像头</span>
        <em>你</em>
      </div>

      <div class="iv-transcript">
        <span class="iv-transcript-tag" :class="{ on: lab.recording.value }">
          <i /> {{ lab.recording.value ? (lab.asrBusy.value > 0 ? '正在转写…' : '正在收音') : '待回答' }}
        </span>
        <p v-if="lab.transcript.value">{{ lab.transcript.value }}</p>
        <p v-else-if="lab.recognitionIssue.value" class="iv-transcript-warn">
          {{ lab.recognitionIssue.value }}
        </p>
        <p v-else-if="lab.recording.value && lab.liveSeconds.value >= 4" class="iv-transcript-warn">
          已经录了 {{ lab.liveSeconds.value }} 秒还没出字。语音指标仍在正常记录（峰值
          {{ Math.round(lab.peakRms.value * 1000) }}‰）；说完一句停顿一下，字幕会在约 2 秒后出现。
        </p>
        <p v-else>开口说话，说完一句停顿一下，这里会出现你的回答文字…</p>
      </div>

      <footer class="iv-controls">
        <button
          v-if="!lab.recording.value"
          type="button"
          class="iv-primary"
          :disabled="busy || phase === 'question'"
          @click="startAnswering"
        >
          <PhMicrophone :size="18" /> 开始回答
        </button>
        <button
          v-else
          type="button"
          class="iv-primary danger"
          :disabled="submitting"
          @click="submitVoice"
        >
          <component :is="submitting ? PhCircleNotch : PhStop" :size="18" :weight="submitting ? 'regular' : 'fill'" :class="{ spin: submitting }" />
          {{ submitting ? '正在整理字幕…' : '回答完毕，下一题' }}
        </button>
        <button type="button" class="iv-ghost" @click="openManualFallback('browser')">改用文字</button>
        <button type="button" class="iv-ghost" :disabled="!canFinish" @click="finishEarly">提前结束并生成报告</button>
      </footer>

      <div v-if="manualOpen" class="iv-manual">
        <div class="iv-manual-card">
          <h3>{{ manualTitle }}</h3>
          <p>{{ manualHint }}</p>
          <textarea v-model="manualAnswer" rows="6" placeholder="把你的回答写在这里…" />
          <div class="iv-manual-actions">
            <button type="button" class="iv-ghost" @click="retryVoice">
              <PhMicrophone :size="14" /> 再试一次语音
            </button>
            <button type="button" class="iv-ghost" @click="manualOpen = false; pendingMetric = null">取消</button>
            <button type="button" class="iv-primary" :disabled="!manualAnswer.trim()" @click="submitManual">提交并继续</button>
          </div>
        </div>
      </div>
    </template>

    <!-- 报告 -->
    <div v-if="stage === 'report'" class="iv-report">
      <div class="iv-report-inner">
        <header class="iv-report-head">
          <div>
            <span class="iv-report-mark">复试复盘</span>
            <h1>
              <em>{{ report?.overall ?? 0 }}</em> 分
              <b>{{ report?.grade }}</b>
            </h1>
            <p>{{ report?.headline ?? '正在生成复盘…' }}</p>
          </div>
          <div class="iv-report-actions">
            <div class="ivx-export">
              <button type="button" class="iv-ghost" :disabled="!report" @click="exportReportMarkdown">
                <PhDownloadSimple :size="15" /> 导出 Markdown
              </button>
              <button type="button" class="iv-ghost" :disabled="!report" @click="exportReportJson">
                <PhFileCode :size="15" /> 导出 JSON
              </button>
            </div>
            <button type="button" class="iv-ghost" @click="restart">再练一次</button>
            <RouterLink to="/academic" class="iv-primary" @click="leave">返回功能选择</RouterLink>
          </div>
        </header>

        <template v-if="report">
          <!-- 历史对比：本次 vs 上次 + 近 10 场总分迷你折线 + 全部场次 -->
          <section class="ivx-history">
            <header class="ivx-history-head">
              <strong><PhClockCounterClockwise :size="15" /> 历史对比</strong>
              <div class="ivx-history-tools">
                <button v-if="historyEntries.length" type="button" class="ivx-link" @click="toggleHistoryOpen">
                  {{ historyOpen ? '收起场次' : '查看全部场次' }}
                  <component :is="historyOpen ? PhCaretUp : PhCaretDown" :size="12" />
                </button>
                <button v-if="historyEntries.length" type="button" class="ivx-link danger" @click="clearHistory">
                  <PhTrash :size="12" />
                  {{ clearArmed ? '再点一次确认清空' : '清空历史' }}
                </button>
              </div>
            </header>

            <p v-if="!historyEntries.length" class="ivx-history-empty">历史已清空，下次练完会重新记录。</p>

            <div v-else class="ivx-history-body">
              <div class="ivx-history-delta">
                <template v-if="historyDelta">
                  <span>本次 <b>{{ historyEntries[0].overall }}</b> 分</span>
                  <em :class="historyDelta.diff >= 0 ? 'up' : 'down'">
                    <component :is="historyDelta.diff >= 0 ? PhArrowUpRight : PhArrowDownRight" :size="14" />
                    {{ historyDelta.diff >= 0 ? '+' : '' }}{{ historyDelta.diff }}
                  </em>
                  <span class="ivx-history-prev">上次 {{ historyDelta.prev }} 分 · {{ formatStamp(historyDelta.at) }}</span>
                </template>
                <span v-else class="ivx-history-first">这是你的第 1 场，下次会在这里看到进步</span>
              </div>

              <svg
                v-if="historySpark"
                class="ivx-spark"
                :viewBox="`0 0 ${historySpark.width} ${historySpark.height}`"
                role="img"
                aria-label="最近场次总分走势"
              >
                <path :d="historySpark.path" class="ivx-spark-line" />
                <circle
                  v-for="(point, index) in historySpark.points"
                  :key="`spark${index}`"
                  :cx="point.x"
                  :cy="point.y"
                  r="3"
                  class="ivx-spark-dot"
                  :class="{ last: point.last }"
                />
              </svg>
              <span v-if="historySpark" class="ivx-history-count">最近 {{ historyEntries.length }} 场</span>
            </div>

            <ol v-if="historyOpen && historyEntries.length" class="ivx-history-list">
              <li v-for="(entry, index) in historyEntries" :key="`${entry.at}-${index}`">
                <button type="button" class="ivx-history-row" @click="toggleHistoryEntry(entry.at)">
                  <span class="ivx-history-at">{{ formatStamp(entry.at) }}</span>
                  <span class="ivx-history-score">{{ entry.overall }}<small>分</small></span>
                  <span class="ivx-history-grade">{{ entry.grade }}</span>
                  <em v-if="index === 0">本次</em>
                  <component :is="historyExpandedAt === entry.at ? PhCaretUp : PhCaretDown" :size="12" />
                </button>
                <div v-if="historyExpandedAt === entry.at" class="ivx-history-dims">
                  <span v-for="dim in entry.dimensions" :key="`${entry.at}-${dim.key}`">
                    {{ dimLabel(dim.key) }} <b>{{ dim.score }}</b>
                  </span>
                </div>
              </li>
            </ol>
          </section>

          <section class="iv-report-grid">
            <article v-for="dim in report.dimensions" :key="dim.key" class="iv-dim">
              <header>
                <span>{{ dim.label }}</span>
                <strong :class="{ low: dim.score < 70 }">{{ dim.score }}</strong>
              </header>
              <div class="iv-dim-bar"><i :style="{ width: `${dim.score}%` }" /></div>
              <p class="iv-dim-evidence">{{ dim.evidence }}</p>
              <p class="iv-dim-advice">{{ dim.advice }}</p>
            </article>
          </section>

          <section class="iv-report-speech">
            <h2>这场面试的语音实测</h2>
            <div class="iv-speech-grid">
              <div><span>有效说话</span><strong>{{ report.speech.speech_seconds }}<small>秒</small></strong></div>
              <div><span>平均语速</span><strong>{{ report.speech.chars_per_min }}<small>字/分</small></strong></div>
              <div><span>停顿次数</span><strong>{{ report.speech.pause_count }}<small>次</small></strong></div>
              <div><span>最长停顿</span><strong>{{ (report.speech.longest_pause_ms / 1000).toFixed(1) }}<small>秒</small></strong></div>
              <div><span>开口延迟</span><strong>{{ (report.speech.latency_ms / 1000).toFixed(1) }}<small>秒</small></strong></div>
              <div><span>口头禅</span><strong>{{ report.speech.filler_total }}<small>处</small></strong></div>
              <div><span>平均音量</span><strong>{{ report.speech.avg_volume }}<small>/100</small></strong></div>
              <div><span>作答题数</span><strong>{{ report.speech.answered }}<small>题</small></strong></div>
            </div>
            <p v-if="report.speech.pace_source === 'estimate'" class="iv-pace-note">
              语速按音量包络的音节峰估算（浏览器没返回转写文本），量级正确但会有 ±15% 偏差。
            </p>
            <p v-else-if="report.speech.pace_source === 'none'" class="iv-pace-note warn">
              没有测到有效人声，语速与内容均未评估。请确认麦克风可用后重练。
            </p>

            <!-- 逐题语速曲线：手写 SVG，不引入图表库 -->
            <div class="ivx-pace">
              <header class="ivx-pace-head">
                <strong><PhChartLine :size="15" /> 逐题语速曲线</strong>
                <span>浅色横带 = 理想区间 {{ PACE_BAND_LOW }}–{{ PACE_BAND_HIGH }} 字/分</span>
              </header>

              <svg
                v-if="paceChart"
                class="ivx-pace-svg"
                :viewBox="`0 0 ${paceChart.width} ${paceChart.height}`"
                role="img"
                aria-label="逐题语速曲线"
              >
                <rect
                  :x="paceChart.left"
                  :y="paceChart.band.y"
                  :width="paceChart.width - paceChart.left - paceChart.right"
                  :height="paceChart.band.height"
                  class="ivx-band"
                />
                <line
                  v-for="ref in paceChart.refs"
                  :key="`ref${ref}`"
                  :x1="paceChart.left"
                  :x2="paceChart.width - paceChart.right"
                  :y1="ref"
                  :y2="ref"
                  class="ivx-ref"
                />
                <line
                  v-for="tick in paceChart.ticks"
                  :key="`grid${tick.value}`"
                  :x1="paceChart.left"
                  :x2="paceChart.width - paceChart.right"
                  :y1="tick.y"
                  :y2="tick.y"
                  class="ivx-grid"
                />
                <text
                  v-for="tick in paceChart.ticks"
                  :key="`tick${tick.value}`"
                  :x="paceChart.left - 8"
                  :y="tick.y + 3"
                  class="ivx-axis"
                  text-anchor="end"
                >{{ tick.value }}</text>

                <!-- 只有 1 题：一根竖条 + 数值，不出折线 -->
                <rect
                  v-if="paceChart.bar"
                  :x="paceChart.bar.x"
                  :y="paceChart.bar.y"
                  :width="paceChart.bar.width"
                  :height="paceChart.bar.height"
                  rx="6"
                  class="ivx-bar"
                  :class="paceChart.points[0].tone"
                />
                <path v-else :d="paceChart.path" class="ivx-line" />

                <g v-for="point in paceChart.points" :key="`p${point.no}`">
                  <circle
                    v-if="!paceChart.single"
                    :cx="point.x"
                    :cy="point.y"
                    r="4.5"
                    class="ivx-dot"
                    :class="point.tone"
                  />
                  <text
                    v-if="point.tone !== 'fit'"
                    :x="point.x"
                    :y="point.tagY"
                    class="ivx-tag"
                    :class="point.tone"
                    text-anchor="middle"
                  >{{ point.tone === 'fast' ? '偏快' : '偏慢' }}</text>
                  <text :x="point.x" :y="point.labelY" class="ivx-value" :class="point.tone" text-anchor="middle">{{
                    point.rate
                  }}</text>
                  <text :x="point.x" :y="paceChart.height - 12" class="ivx-axis" text-anchor="middle"
                    >第{{ point.no }}题</text
                  >
                </g>
              </svg>

              <p v-else class="ivx-pace-empty">这一场没有测到有效语速（麦克风没采到人声），曲线无法生成。</p>
              <p v-if="paceChart" class="ivx-pace-conclusion">{{ paceConclusion }}</p>
            </div>
          </section>

          <section class="iv-report-list">
            <h2>逐题回看</h2>
            <article v-for="item in report.answers" :key="item.index" class="iv-answer-card">
              <header>
                <span class="iv-answer-no">Q{{ item.index + 1 }}</span>
                <span class="iv-answer-examiner">{{ item.examiner_name }}</span>
                <em :class="item.verdict === '好' ? 'good' : item.verdict === '稳' ? 'mid' : 'low'">{{ item.verdict }}</em>
              </header>
              <p class="iv-answer-q">{{ item.question }}</p>
              <p class="iv-answer-a">{{ item.transcript || '（本题没有识别到语音内容）' }}</p>
              <div class="iv-answer-stats">
                <span>{{ item.seconds }} 秒</span>
                <span>{{ item.chars_per_min }} 字/分</span>
                <span>停顿 {{ item.pause_count }} 次</span>
                <span>最长 {{ (item.longest_pause_ms / 1000).toFixed(1) }} 秒</span>
                <span>口头禅 {{ item.filler_count }} 处</span>
              </div>
            </article>
          </section>

          <section class="iv-report-tips">
            <div>
              <h3>这场做得好的</h3>
              <ul><li v-for="line in report.highlights" :key="line">{{ line }}</li></ul>
            </div>
            <div>
              <h3>下一场先改这两点</h3>
              <ul><li v-for="line in report.fixes" :key="line">{{ line }}</li></ul>
            </div>
          </section>
        </template>
        <p v-else-if="busy" class="iv-report-loading"><PhCircleNotch :size="18" class="spin" /> 正在换算语音指标…</p>
      </div>
    </div>

    <p v-if="error" class="iv-toast error">{{ error }}</p>
    <p v-else-if="notice" class="iv-toast">{{ notice }}</p>
    <p v-if="cameraError && stage === 'live'" class="iv-toast warn">{{ cameraError }}</p>
  </div>
</template>

<style scoped>
/* ============================================================================
   本组件新增块的样式。只在本组件生效，class 统一 ivx- 前缀，
   颜色沿用 .iv-root 上的 --iv-accent / --iv-warm / --iv-danger / --iv-line。
   ============================================================================ */

/* ---------------------------------------------------------------- 答题计时器 */
.ivx-timer {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  flex: 0 0 auto;
  padding: .24rem .6rem;
  font-size: .74rem;
  font-variant-numeric: tabular-nums;
  color: #dff3ec;
  background: rgba(255, 255, 255, .07);
  border: 1px solid var(--iv-line);
  border-radius: 999px;
  white-space: nowrap;
  transition: color .2s, background .2s, border-color .2s;
}
.ivx-timer b {
  font-size: .86rem;
  font-weight: 700;
  letter-spacing: .04em;
}
.ivx-timer em {
  font-style: normal;
  font-size: .66rem;
  color: inherit;
  opacity: .9;
}
.ivx-timer.ok { color: #bff0e2; }
.ivx-timer.warn {
  color: #f7e4bd;
  background: rgba(150, 116, 48, .32);
  border-color: rgba(232, 184, 119, .45);
}
.ivx-timer.over {
  color: #ffd6cd;
  background: rgba(160, 62, 48, .34);
  border-color: rgba(232, 112, 95, .5);
  animation: ivx-breathe 1.8s ease-in-out infinite;
}
@keyframes ivx-breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: .72; }
}

/* ---------------------------------------------------------------- 语速曲线 */
.ivx-pace {
  margin-top: .9rem;
  padding: .8rem .9rem .7rem;
  background: rgba(255, 255, 255, .035);
  border: 1px solid var(--iv-line);
  border-radius: 14px;
}
.ivx-pace-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: .6rem;
  flex-wrap: wrap;
  margin-bottom: .35rem;
}
.ivx-pace-head strong {
  display: inline-flex;
  align-items: center;
  gap: .34rem;
  font-size: .82rem;
  color: rgba(232, 240, 236, .9);
}
.ivx-pace-head span {
  font-size: .7rem;
  color: rgba(226, 236, 231, .5);
}
.ivx-pace-svg {
  display: block;
  width: 100%;
  height: auto;
}
.ivx-band { fill: rgba(127, 212, 189, .1); }
.ivx-ref {
  stroke: rgba(127, 212, 189, .42);
  stroke-width: 1;
  stroke-dasharray: 4 4;
}
.ivx-grid { stroke: rgba(255, 255, 255, .07); stroke-width: 1; }
.ivx-axis {
  font-size: 10px;
  fill: rgba(226, 236, 231, .45);
  font-variant-numeric: tabular-nums;
}
.ivx-line {
  fill: none;
  stroke: rgba(127, 212, 189, .72);
  stroke-width: 2;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.ivx-dot { stroke: #0e171b; stroke-width: 1.5; }
.ivx-dot.fit { fill: #7fd4bd; }
.ivx-dot.slow { fill: #8fb8e8; }
.ivx-dot.fast { fill: #e8b877; }
.ivx-bar.fit { fill: rgba(127, 212, 189, .42); }
.ivx-bar.slow { fill: rgba(143, 184, 232, .42); }
.ivx-bar.fast { fill: rgba(232, 184, 119, .42); }
.ivx-value {
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.ivx-value.fit { fill: #cdeee2; }
.ivx-value.slow { fill: #a8cbf2; }
.ivx-value.fast { fill: #f3d6a5; }
.ivx-tag {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: .04em;
}
.ivx-tag.slow { fill: #8fb8e8; }
.ivx-tag.fast { fill: #e8b877; }
.ivx-pace-conclusion {
  margin: .5rem 0 0;
  font-size: .76rem;
  line-height: 1.66;
  color: rgba(238, 245, 241, .86);
}
.ivx-pace-empty {
  margin: .5rem 0 0;
  font-size: .76rem;
  line-height: 1.66;
  color: rgba(226, 236, 231, .55);
}

/* ---------------------------------------------------------------- 历史对比 */
.ivx-history {
  margin-bottom: 1.1rem;
  padding: .8rem .95rem .85rem;
  background: rgba(255, 255, 255, .04);
  border: 1px solid var(--iv-line);
  border-radius: 14px;
}
.ivx-history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .6rem;
  flex-wrap: wrap;
}
.ivx-history-head strong {
  display: inline-flex;
  align-items: center;
  gap: .34rem;
  font-size: .82rem;
  color: rgba(232, 240, 236, .9);
}
.ivx-history-tools { display: flex; align-items: center; gap: .45rem; flex-wrap: wrap; }
.ivx-link {
  display: inline-flex;
  align-items: center;
  gap: .24rem;
  padding: .18rem .52rem;
  font-size: .7rem;
  font-weight: 600;
  color: #cfe9e0;
  background: rgba(255, 255, 255, .07);
  border: 1px solid var(--iv-line);
  border-radius: 999px;
  cursor: pointer;
  transition: background .18s, border-color .18s;
}
.ivx-link:hover { background: rgba(255, 255, 255, .14); border-color: rgba(255, 255, 255, .3); }
.ivx-link.danger { color: #ffd0c6; }
.ivx-history-empty {
  margin: .55rem 0 0;
  font-size: .76rem;
  color: rgba(226, 236, 231, .55);
}
.ivx-history-body {
  display: flex;
  align-items: center;
  gap: .8rem;
  flex-wrap: wrap;
  margin-top: .5rem;
}
.ivx-history-delta {
  display: flex;
  align-items: baseline;
  gap: .45rem;
  flex-wrap: wrap;
  font-size: .78rem;
  color: rgba(232, 240, 236, .8);
}
.ivx-history-delta b {
  font-size: 1.12rem;
  font-weight: 800;
  color: #f2f7f4;
  font-variant-numeric: tabular-nums;
}
.ivx-history-delta em {
  display: inline-flex;
  align-items: center;
  gap: .1rem;
  font-style: normal;
  font-size: .8rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.ivx-history-delta em.up { color: #8fe3c8; }
.ivx-history-delta em.down { color: #f39a89; }
.ivx-history-prev { font-size: .7rem; color: rgba(226, 236, 231, .5); }
.ivx-history-first { font-size: .76rem; color: rgba(226, 236, 231, .62); }
.ivx-spark { width: 190px; height: auto; flex: 0 0 auto; }
.ivx-spark-line {
  fill: none;
  stroke: rgba(127, 212, 189, .6);
  stroke-width: 1.6;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.ivx-spark-dot { fill: rgba(127, 212, 189, .72); }
.ivx-spark-dot.last { fill: var(--iv-warm); }
.ivx-history-count { font-size: .68rem; color: rgba(226, 236, 231, .42); }
.ivx-history-list {
  margin: .7rem 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: .3rem;
  max-height: 260px;
  overflow-y: auto;
}
.ivx-history-row {
  display: flex;
  align-items: center;
  gap: .55rem;
  width: 100%;
  padding: .4rem .55rem;
  font-size: .74rem;
  color: rgba(232, 240, 236, .8);
  text-align: left;
  background: rgba(255, 255, 255, .045);
  border: 1px solid var(--iv-line);
  border-radius: 10px;
  cursor: pointer;
  transition: background .18s;
}
.ivx-history-row:hover { background: rgba(255, 255, 255, .1); }
.ivx-history-at { font-variant-numeric: tabular-nums; color: rgba(226, 236, 231, .62); }
.ivx-history-score {
  margin-left: auto;
  font-size: .9rem;
  font-weight: 700;
  color: #f2f7f4;
  font-variant-numeric: tabular-nums;
}
.ivx-history-score small {
  margin-left: .1rem;
  font-size: .62rem;
  font-weight: 500;
  color: rgba(226, 236, 231, .5);
}
.ivx-history-grade {
  padding: .06rem .38rem;
  font-size: .66rem;
  font-weight: 700;
  color: #0f1a18;
  background: rgba(232, 184, 119, .9);
  border-radius: 5px;
}
.ivx-history-row em {
  font-style: normal;
  font-size: .64rem;
  color: #bff0e2;
}
.ivx-history-dims {
  display: flex;
  flex-wrap: wrap;
  gap: .3rem .5rem;
  padding: .4rem .55rem .15rem;
  font-size: .7rem;
  color: rgba(226, 236, 231, .6);
}
.ivx-history-dims span {
  padding: .1rem .42rem;
  background: rgba(255, 255, 255, .06);
  border-radius: 999px;
}
.ivx-history-dims b {
  color: #eaf5f0;
  font-variant-numeric: tabular-nums;
}

/* ---------------------------------------------------------------- 报告导出 */
.ivx-export { display: flex; gap: .5rem; flex-wrap: wrap; }

/* ---------------------------------------------------------------- 窄屏收敛 */
@media (max-width: 1180px) {
  .ivx-timer em { display: none; }
}
@media (max-width: 900px) {
  .ivx-spark { width: 140px; }
  .ivx-history-body { gap: .5rem; }
  .ivx-pace { padding: .7rem .7rem .6rem; }
}
</style>
