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
  PhArrowLeft,
  PhArrowsOut,
  PhCheckCircle,
  PhCircleNotch,
  PhMicrophone,
  PhMicrophoneSlash,
  PhPlay,
  PhStop,
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

/* ------------------------------------------------------------------ 派生 */

const activeExaminer = computed(() => examiners.value.find((item) => item.id === turn.value?.examiner) ?? examiners.value[0])
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
  await exitFullscreen()
  try {
    report.value = await requestJson<InterviewReport>(
      '/api/v1/interview/report',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ major: major.value, minutes: minutes.value, strictness: strictness.value, answers: answers.value }),
      },
      '复盘报告生成失败',
    )
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
}

function leave(): void {
  stopAudio()
  lab.closeMic()
  stopCamera()
  window.clearInterval(timer)
  window.speechSynthesis?.cancel()
  void exitFullscreen()
}

/* ------------------------------------------------------------------ 生命周期 */

watch(minutes, () => {
  void loadPanel()
})

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  // 沉浸式页面：隐藏全局引导员并锁滚动，避免和 3D 场景抢视觉
  document.body.classList.add('iv-immersive')
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
    <ClassroomScene class="iv-scene" :speaking="speaking" :phase="phase" />

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
            <button type="button" class="iv-ghost" @click="restart">再练一次</button>
            <RouterLink to="/academic" class="iv-primary" @click="leave">返回功能选择</RouterLink>
          </div>
        </header>

        <template v-if="report">
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
