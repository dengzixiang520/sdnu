/**
 * 复试现场的语音采集：指标测量 + 准实时转写。
 *
 * 这里测量的每一项都是"可复核的原始量"，不做任何推断：
 *   - 音量包络：Web Audio 的 AnalyserNode，每 50ms 取一次时域 RMS
 *   - 停顿：连续 RMS 低于阈值的帧段，超过 800ms 才算一次停顿
 *   - 语速：转写文本字数 ÷ 有效说话时长
 *   - 填充词：在转写文本里直接数
 *   - 开口延迟：从考官语音播放结束到第一帧人声
 *
 * 为什么在浏览器侧测指标，而不是把音频传回服务端：
 *   1. 停顿与音量本质上是采样问题，本地算最准；
 *   2. 服务端只做换算与打分，避免"黑箱给分"。
 *
 * ---------------------------------------------------------------------------
 * 转写走服务端的小米 MiMo-ASR，不用浏览器 Web Speech API。
 *
 * 原因：Web Speech API 把音频送到 Google 的在线识别服务，国内网络基本连不上，
 * 表现就是"麦克风明明有信号，但一个字都不出"，而且报错还被浏览器吞掉。
 *
 * 但 MiMo-ASR 不是流式接口（实测固定开销 1.3–1.5s，与音频长短无关），
 * 所以这里自己做"准实时"：一边采集 PCM，一边用能量谷判断句子结束，
 * 每说完一句就把这段单独编码成 WAV 送出去，结果按顺序拼回字幕。
 * 2 秒以下的块会丢字甚至幻觉（0.6s 会被识别成 "Yeah."），
 * 因此切分规则是「≥1.2s 有声 + ≥450ms 静音」或「攒满 8s 强制切」。
 */

import { onBeforeUnmount, ref } from 'vue'

export interface AnswerMetricPayload {
  index: number
  examiner: string
  question: string
  transcript: string
  duration_ms: number
  speech_ms: number
  latency_ms: number
  pause_count: number
  longest_pause_ms: number
  avg_volume: number
  volume_stability: number
  filler_count: number
  chars: number
  /** 从音量包络数出来的音节峰数量；没有转写文本时用来估算语速 */
  syllables: number
  hard: boolean
}

/** 麦克风链路的状态，界面据此给出不同的提示文案。 */
export type MicState =
  | 'idle' // 还没申请
  | 'ready' // 权限、上下文、分析器都正常
  | 'denied' // 权限被拒 / 没有设备
  | 'suspended' // AudioContext 起不来
  | 'nosignal' // 一切就绪但采到的样本恒为 0（设备被占用或静音键）

const FILLERS = ['嗯', '呃', '那个', '就是', '然后', '这个', '反正', '其实吧', '怎么说']
/**
 * 采样周期 50 ms（20 Hz）。这个频率是按"数音节"倒推的：
 * 中文正常语速每秒 3–5 个字，音节间隔 200–330 ms，
 * 20 Hz 足以分辨，又不会让一次 2 分钟的回答堆出几万个采样点。
 */
const FRAME_MS = 50
const PAUSE_MIN_MS = 800
/** 阈值下限：低于这个值基本是电路底噪，再灵敏也没有意义。 */
const MIN_THRESHOLD = 0.004
/** 阈值上限：环境很吵时不让阈值高到把正常说话也判成静音。 */
const MAX_THRESHOLD = 0.05
/** 阈值相对噪声底的倍数。3 倍信噪比能干净地分开"人声"和"底噪"。 */
const NOISE_RATIO = 3
/** 标定用采样时长。 */
const CALIBRATE_MS = 1400
/** 识别用的目标采样率。16 kHz 单声道对语音足够，体积只有 48 kHz 的三分之一。 */
const ASR_SAMPLE_RATE = 16000
/** 切句规则：至少这么多有声，且紧跟这么长静音，才认为一句说完了。 */
const SEGMENT_MIN_VOICED_MS = 1200
const SEGMENT_END_SILENCE_MS = 450
/** 攒这么久还没等到停顿就强制切，避免长句一直不落盘。 */
const SEGMENT_MAX_MS = 8000
/** 同时最多几个转写请求在飞，避免网络抖动时堆积。 */
const ASR_MAX_INFLIGHT = 2
/** 统计字数时剔掉标点：识别结果里的逗号句号不该算进语速。 */
const PUNCTUATION = /[\s，。、！？；：""''（）()《》…—\-.,!?;:]/g

function spokenChars(text: string): number {
  return text.replace(PUNCTUATION, '').length
}

function percentile(list: number[], ratio: number): number {
  if (!list.length) return 0
  const sorted = [...list].sort((a, b) => a - b)
  const index = Math.min(sorted.length - 1, Math.max(0, Math.round((sorted.length - 1) * ratio)))
  return sorted[index]
}

/** 线性插值重采样。语音场景够用，比引入 resampler 库划算。 */
function resample(input: Float32Array, srcRate: number, dstRate: number): Float32Array {
  if (srcRate === dstRate) return input
  const ratio = srcRate / dstRate
  const length = Math.floor(input.length / ratio)
  const output = new Float32Array(length)
  for (let i = 0; i < length; i += 1) {
    const position = i * ratio
    const low = Math.floor(position)
    const high = Math.min(low + 1, input.length - 1)
    const weight = position - low
    output[i] = input[low] * (1 - weight) + input[high] * weight
  }
  return output
}

/** 把 Float32 单声道样本包成标准 16-bit PCM WAV。 */
function encodeWav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const writeText = (offset: number, text: string): void => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i))
  }
  writeText(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeText(8, 'WAVE')
  writeText(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeText(36, 'data')
  view.setUint32(40, samples.length * 2, true)
  let offset = 44
  for (let i = 0; i < samples.length; i += 1) {
    const value = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, value < 0 ? value * 0x8000 : value * 0x7fff, true)
    offset += 2
  }
  return buffer
}

function base64FromBuffer(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  const step = 0x8000
  for (let i = 0; i < bytes.length; i += step) {
    binary += String.fromCharCode(...bytes.subarray(i, i + step))
  }
  return btoa(binary)
}

function countSyllablePeaks(list: number[], floor: number): number {
  if (!list.length) return 0
  let peak = 0
  for (const value of list) if (value > peak) peak = value
  if (peak < floor) return 0
  const high = Math.max(floor, peak * 0.28)
  const low = high * 0.55
  let count = 0
  let armed = true
  let sinceLast = 0
  const minGapFrames = Math.round(110 / FRAME_MS)
  for (const value of list) {
    sinceLast += 1
    if (armed && value >= high && sinceLast >= minGapFrames) {
      count += 1
      armed = false
      sinceLast = 0
    } else if (!armed && value <= low) {
      armed = true
    }
  }
  return count
}

/** Safari 只认 webkitAudioContext，这里做一次兼容。 */
function audioContextCtor(): typeof AudioContext | null {
  const scope = window as unknown as {
    AudioContext?: typeof AudioContext
    webkitAudioContext?: typeof AudioContext
  }
  return scope.AudioContext ?? scope.webkitAudioContext ?? null
}

/**
 * 转写请求的注入点，由调用方提供（便于替换实现与测试）。
 *
 * 入参直接是 base64 编码的 WAV 字符串：采集侧本来就要编码成 WAV 再 base64，
 * 在这里再转回 ArrayBuffer 只是多一次拷贝，接口也更贴近 /asr 的请求体。
 */
export type TranscribeFn = (base64Audio: string, format: string) => Promise<string>

export function useSpeechLab(transcribe: TranscribeFn) {
  const micGranted = ref(false)
  const micState = ref<MicState>('idle')
  const recording = ref(false)
  const transcript = ref('')
  /** 显示用 0–1 电平（已按阈值归一化，说话时接近满格） */
  const liveVolume = ref(0)
  const rawRms = ref(0)
  const peakRms = ref(0)
  const voiceThreshold = ref(MIN_THRESHOLD)
  const noiseFloor = ref(0)
  const calibrated = ref(false)
  const liveCharsPerMin = ref(0)
  const livePauseCount = ref(0)
  const liveSeconds = ref(0)
  const silentMs = ref(0)
  /** 正在飞的转写请求数，界面据此显示"正在转写…" */
  const asrBusy = ref(0)
  /** 累计的转写端到端延迟，用于在报告里给出真实数字 */
  const asrLatencyMs = ref(0)
  const error = ref('')
  /** 转写通道本身的问题（和麦克风权限分开） */
  const recognitionIssue = ref('')

  let audioContext: AudioContext | null = null
  let analyser: AnalyserNode | null = null
  let micStream: MediaStream | null = null
  let samples: Float32Array | null = null
  let ticker: number | undefined
  let collector: ScriptProcessorNode | null = null
  let silentSink: GainNode | null = null

  let startedAt = 0
  let promptEndedAt = 0
  let firstVoiceAt = 0
  let frames: number[] = []
  let speakingFrames = 0

  // 转写缓冲
  let pending: number[] = []
  let pendingVoicedMs = 0
  let pendingSilenceMs = 0
  let inflight = 0
  // 并发转写会乱序返回；带序号入队、按序号出字，字幕才跟说话顺序一致。
  const queue: Array<{ seq: number; data: string }> = []
  let seqCounter = 0
  let emitCursor = 0
  const arrived = new Map<number, string>()
  let closed = false

  // ---------------------------------------------------------------- 设备

  async function openMic(): Promise<MediaStream> {
    if (micStream && micStream.active && analyser) {
      micGranted.value = true
      micState.value = 'ready'
      return micStream
    }
    const Ctor = audioContextCtor()
    if (!Ctor) {
      micState.value = 'suspended'
      error.value = '当前浏览器不支持 Web Audio，无法分析音量'
      throw new Error(error.value)
    }
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          // 取舍：回音消除会削掉句尾，直接影响停顿与语速判断，所以关掉；
          // 自动增益必须开——很多耳麦/笔记本的原始输入只有 -50dB，
          // 不开增益就是"明明在说话却采不到"，这正是最初报的故障。
          // 代价是音量维度变成"相对音量"，报告里已注明。
          echoCancellation: false,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
    } catch (reason) {
      micState.value = 'denied'
      micGranted.value = false
      const name = reason instanceof DOMException ? reason.name : ''
      error.value =
        name === 'NotAllowedError'
          ? '麦克风权限被拒绝。请点地址栏左侧的图标，把麦克风改成"允许"后刷新页面。'
          : name === 'NotFoundError'
            ? '没有找到麦克风设备，请插上耳机或确认系统输入设备。'
            : name === 'NotReadableError'
              ? '麦克风被其他程序占用（会议软件 / 录音软件），关掉它们再试。'
              : '无法打开麦克风，请检查系统声音设置。'
      throw new Error(error.value)
    }
    micGranted.value = true

    audioContext = new Ctor()
    // 关键：Chrome 常常以 suspended 启动，不 resume 的话采样恒为 0，
    // 表现就是"音量条不动、识别不出字"，这正是最初报的故障。
    if (audioContext.state === 'suspended') {
      try {
        await audioContext.resume()
      } catch {
        micState.value = 'suspended'
        error.value = '音频上下文无法启动，请刷新页面后重新进入'
        throw new Error(error.value)
      }
    }
    if (audioContext.state !== 'running') {
      micState.value = 'suspended'
      error.value = '音频上下文处于暂停状态，请刷新页面后重新进入'
      throw new Error(error.value)
    }

    const source = audioContext.createMediaStreamSource(micStream)
    analyser = audioContext.createAnalyser()
    analyser.fftSize = 2048
    analyser.smoothingTimeConstant = 0.2
    source.connect(analyser)
    samples = new Float32Array(analyser.fftSize)
    micState.value = 'ready'
    return micStream
  }

  function currentRms(): number {
    if (!analyser || !samples) return 0
    analyser.getFloatTimeDomainData(samples)
    let sum = 0
    for (let i = 0; i < samples.length; i += 1) sum += samples[i] * samples[i]
    return Math.sqrt(sum / samples.length)
  }

  async function calibrate(durationMs = CALIBRATE_MS): Promise<number> {
    if (!analyser) return voiceThreshold.value
    const readings: number[] = []
    const until = performance.now() + durationMs
    await new Promise<void>((resolve) => {
      const step = (): void => {
        readings.push(currentRms())
        if (performance.now() < until) window.setTimeout(step, FRAME_MS)
        else resolve()
      }
      step()
    })
    // 取 35 百分位而不是中位数：标定时用户很可能已经在说话了，
    // 说话是间歇的高电平，取低百分位才逼近真正的环境噪声底。
    const floor = percentile(readings, 0.35)
    noiseFloor.value = floor
    voiceThreshold.value = Math.min(MAX_THRESHOLD, Math.max(MIN_THRESHOLD, floor * NOISE_RATIO))
    const peak = readings.reduce((best, value) => Math.max(best, value), 0)
    calibrated.value = true
    if (peak < 0.0004) micState.value = 'nosignal'
    else if (micState.value === 'nosignal') micState.value = 'ready'
    return voiceThreshold.value
  }

  function autoTune(peak: number): void {
    if (!calibrated.value || peak <= 0) return
    const floor = noiseFloor.value
    if (peak < Math.max(MIN_THRESHOLD, floor * 1.5)) return
    if (peak >= voiceThreshold.value * 1.6) return
    const target = Math.max(MIN_THRESHOLD, floor * 1.8, peak * 0.65)
    if (target < voiceThreshold.value) voiceThreshold.value = Math.min(MAX_THRESHOLD, target)
  }

  function volumeSpan(): number {
    return Math.max(MIN_THRESHOLD * 4, voiceThreshold.value * 3)
  }

  /** 进房前的试音：持续刷新电平，让用户开口就能看到条子跳。 */
  function startMonitor(): void {
    stopMonitor()
    peakRms.value = 0
    ticker = window.setInterval(() => {
      const rms = currentRms()
      rawRms.value = rms
      if (rms > peakRms.value) {
        peakRms.value = rms
        autoTune(rms)
      }
      liveVolume.value = Math.min(1, rms / volumeSpan())
      if (rms > 0.0004 && micState.value === 'nosignal') micState.value = 'ready'
    }, FRAME_MS)
  }

  function stopMonitor(): void {
    if (ticker !== undefined) window.clearInterval(ticker)
    ticker = undefined
    liveVolume.value = 0
  }

  async function recordSample(durationMs = 3000): Promise<string | null> {
    if (!micStream) return null
    const mime = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find(
      (item) => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(item),
    )
    if (!mime || typeof MediaRecorder === 'undefined') return null
    const chunks: Blob[] = []
    const recorder = new MediaRecorder(micStream, { mimeType: mime })
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data)
    }
    const done = new Promise<Blob>((resolve) => {
      recorder.onstop = () => resolve(new Blob(chunks, { type: mime }))
    })
    recorder.start()
    await new Promise((resolve) => window.setTimeout(resolve, durationMs))
    recorder.stop()
    const blob = await done
    return blob.size > 1200 ? URL.createObjectURL(blob) : null
  }

  // ---------------------------------------------------------------- 转写

  /** 把一段 PCM 送去转写，结果按到达顺序拼进字幕。 */
  function submitSegment(samples: Float32Array, sampleRate: number): void {
    if (!samples.length) return
    const pcm = resample(samples, sampleRate, ASR_SAMPLE_RATE)
    // 太短的一段不值得发，模型会丢字甚至幻觉
    if (pcm.length < ASR_SAMPLE_RATE * 0.8) return
    const wav = encodeWav(pcm, ASR_SAMPLE_RATE)
    queue.push({ seq: seqCounter, data: base64FromWav(wav) })
    seqCounter += 1
    pump()
  }

  /** 按序号把已到达的转写拼进字幕，乱序到达的先存着。 */
  function drainArrived(): void {
    for (;;) {
      const text = arrived.get(emitCursor)
      if (text === undefined) return
      arrived.delete(emitCursor)
      emitCursor += 1
      const trimmed = text.trim()
      if (trimmed) {
        transcript.value = transcript.value ? `${transcript.value}${trimmed}` : trimmed
      }
    }
  }

  /** WAV 已经编码好，直接转 base64；单独拆出来是为了避免重复持有 ArrayBuffer。 */
  function base64FromWav(buffer: ArrayBuffer): string {
    return base64FromBuffer(buffer)
  }

  function pump(): void {
    while (!closed && inflight < ASR_MAX_INFLIGHT && queue.length > 0) {
      const payload = queue.shift()
      if (!payload) break
      inflight += 1
      asrBusy.value = inflight + queue.length
      void (async () => {
        const started = performance.now()
        try {
          const text = await transcribe(payload.data, 'wav')
          arrived.set(payload.seq, text || '')
          drainArrived()
          asrLatencyMs.value = Math.round(performance.now() - started)
          recognitionIssue.value = ''
        } catch (reason) {
          // 失败也占位，否则后面的句子永远等不到自己的序号
          arrived.set(payload.seq, '')
          drainArrived()
          recognitionIssue.value =
            reason instanceof Error ? `语音转写失败：${reason.message}` : '语音转写失败'
        } finally {
          inflight -= 1
          asrBusy.value = inflight + queue.length
          pump()
        }
      })()
    }
  }

  /** 把缓冲里的音频切出去转写。 */
  function flushSegment(): void {
    if (!pending.length || !audioContext) return
    const data = Float32Array.from(pending)
    pending = []
    pendingVoicedMs = 0
    pendingSilenceMs = 0
    submitSegment(data, audioContext.sampleRate)
  }

  /** 等待所有在飞与排队的转写落地（结束作答时用）。 */
  async function drain(timeoutMs = 6000): Promise<void> {
    const until = performance.now() + timeoutMs
    while ((inflight > 0 || queue.length > 0) && performance.now() < until) {
      await new Promise((resolve) => window.setTimeout(resolve, 80))
    }
  }

  // ---------------------------------------------------------------- 采集

  function startCollector(): void {
    if (!audioContext || !micStream || collector) return
    try {
      const source = audioContext.createMediaStreamSource(micStream)
      collector = audioContext.createScriptProcessor(2048, 1, 1)
      const frameMs = (2048 / audioContext.sampleRate) * 1000
      collector.onaudioprocess = (event) => {
        if (!recording.value) return
        const input = event.inputBuffer.getChannelData(0)
        for (let i = 0; i < input.length; i += 1) pending.push(input[i])
        let sum = 0
        for (let i = 0; i < input.length; i += 1) sum += input[i] * input[i]
        const rms = Math.sqrt(sum / input.length)
        if (rms > voiceThreshold.value) {
          pendingVoicedMs += frameMs
          pendingSilenceMs = 0
        } else {
          pendingSilenceMs += frameMs
        }
        const totalMs = (pending.length / audioContext!.sampleRate) * 1000
        const sentenceDone = pendingVoicedMs >= SEGMENT_MIN_VOICED_MS && pendingSilenceMs >= SEGMENT_END_SILENCE_MS
        if (sentenceDone || totalMs >= SEGMENT_MAX_MS) flushSegment()
      }
      // ScriptProcessor 必须接到下游才会持续回调；接一个 0 增益节点避免把自己的声音放出来。
      silentSink = audioContext.createGain()
      silentSink.gain.value = 0
      source.connect(collector)
      collector.connect(silentSink)
      silentSink.connect(audioContext.destination)
    } catch {
      collector = null
    }
  }

  function stopCollector(): void {
    if (collector) {
      collector.onaudioprocess = null
      try {
        collector.disconnect()
      } catch {
        // 已经断开就忽略
      }
      collector = null
    }
    if (silentSink) {
      try {
        silentSink.disconnect()
      } catch {
        // 同上
      }
      silentSink = null
    }
  }

  // ---------------------------------------------------------------- 作答

  /**
   * 开始一题作答；``promptEndedAtMs`` 用来算开口延迟。
   * 返回 false 表示麦克风链路没就绪，调用方应改走文字作答。
   */
  function beginAnswer(promptEndedAtMs: number, _language: string): boolean {
    window.clearInterval(ticker)
    ticker = undefined
    stopMonitor()
    error.value = ''
    transcript.value = ''
    frames = []
    speakingFrames = 0
    startedAt = performance.now()
    promptEndedAt = promptEndedAtMs
    firstVoiceAt = 0
    peakRms.value = 0
    silentMs.value = 0
    livePauseCount.value = 0
    liveSeconds.value = 0
    liveCharsPerMin.value = 0
    pending = []
    pendingVoicedMs = 0
    pendingSilenceMs = 0
    queue.length = 0
    inflight = 0
    seqCounter = 0
    emitCursor = 0
    arrived.clear()
    asrBusy.value = 0
    recognitionIssue.value = ''
    closed = false

    if (!analyser) {
      recording.value = false
      error.value = '麦克风没有就绪，这一题请用文字作答'
      return false
    }

    recording.value = true
    startCollector()
    ticker = window.setInterval(() => {
      const rms = currentRms()
      rawRms.value = rms
      if (rms > peakRms.value) {
        peakRms.value = rms
        autoTune(rms)
      }
      liveVolume.value = Math.min(1, rms / volumeSpan())
      frames.push(rms)
      if (rms > voiceThreshold.value) {
        speakingFrames += 1
        silentMs.value = 0
        if (!firstVoiceAt) firstVoiceAt = performance.now()
      } else {
        silentMs.value += FRAME_MS
      }
      liveSeconds.value = Math.round((performance.now() - startedAt) / 1000)
      const speechMs = speakingFrames * FRAME_MS
      const measured = spokenChars(transcript.value) || countSyllablePeaks(frames, voiceThreshold.value)
      // 与后端保持同一套合理性区间，避免实时面板刷出 600+ 的离谱数字
      liveCharsPerMin.value =
        speechMs > 4000 ? Math.max(60, Math.min(480, Math.round((measured / speechMs) * 60_000))) : 0
      livePauseCount.value = countPauses(frames)
    }, FRAME_MS)
    return true
  }

  function countPauses(list: number[]): number {
    const limit = voiceThreshold.value
    let count = 0
    let silence = 0
    let seenVoice = false
    for (const rms of list) {
      if (rms > limit) {
        if (seenVoice && silence >= PAUSE_MIN_MS) count += 1
        silence = 0
        seenVoice = true
      } else if (seenVoice) {
        silence += FRAME_MS
      }
    }
    return count
  }

  function longestPause(list: number[]): number {
    const limit = voiceThreshold.value
    let best = 0
    let silence = 0
    let seenVoice = false
    for (const rms of list) {
      if (rms > limit) {
        if (seenVoice) best = Math.max(best, silence)
        silence = 0
        seenVoice = true
      } else if (seenVoice) {
        silence += FRAME_MS
      }
    }
    return best
  }

  /**
   * 结束作答并返回这一题的实测指标。
   *
   * 这里会先把最后一段缓冲切出去并等转写落地，否则用户点"回答完毕"时
   * 最后半句还躺在缓冲里，字幕会缺一截。
   */
  async function endAnswer(meta: {
    index: number
    examiner: string
    question: string
    hard: boolean
  }): Promise<AnswerMetricPayload> {
    window.clearInterval(ticker)
    ticker = undefined
    flushSegment()
    recording.value = false
    stopCollector()
    await drain()

    const limit = voiceThreshold.value
    const durationMs = Math.round(performance.now() - startedAt)
    const speechMs = speakingFrames * FRAME_MS
    const voiced = frames.filter((rms) => rms > limit)
    const mean = voiced.length ? voiced.reduce((sum, value) => sum + value, 0) / voiced.length : 0
    const variance = voiced.length
      ? voiced.reduce((sum, value) => sum + (value - mean) ** 2, 0) / voiced.length
      : 0
    const deviation = Math.sqrt(variance)
    const stability = mean > 0 ? Math.max(0, Math.min(1, 1 - deviation / mean / 1.25)) : 0
    const text = transcript.value.trim()
    const chars = spokenChars(text)
    const fillerCount = FILLERS.reduce((total, word) => total + (text.split(word).length - 1), 0)

    return {
      index: meta.index,
      examiner: meta.examiner,
      question: meta.question,
      transcript: text,
      duration_ms: durationMs,
      speech_ms: speechMs,
      latency_ms: firstVoiceAt ? Math.round(firstVoiceAt - promptEndedAt) : 0,
      pause_count: countPauses(frames),
      longest_pause_ms: longestPause(frames),
      avg_volume: Math.max(0, Math.min(1, mean / 0.2)),
      volume_stability: Number(stability.toFixed(3)),
      filler_count: fillerCount,
      chars,
      syllables: countSyllablePeaks(frames, limit),
      hard: meta.hard,
    }
  }

  function abortAnswer(): void {
    window.clearInterval(ticker)
    ticker = undefined
    recording.value = false
    liveVolume.value = 0
    silentMs.value = 0
    stopCollector()
    pending = []
    pendingVoicedMs = 0
    pendingSilenceMs = 0
    queue.length = 0
    arrived.clear()
    closed = true
  }

  function closeMic(): void {
    abortAnswer()
    stopMonitor()
    micStream?.getTracks().forEach((track) => track.stop())
    micStream = null
    void audioContext?.close()
    audioContext = null
    analyser = null
    samples = null
    micGranted.value = false
    micState.value = 'idle'
    calibrated.value = false
  }

  onBeforeUnmount(closeMic)

  return {
    micGranted,
    micState,
    recording,
    transcript,
    liveVolume,
    rawRms,
    peakRms,
    voiceThreshold,
    noiseFloor,
    calibrated,
    liveCharsPerMin,
    livePauseCount,
    liveSeconds,
    silentMs,
    asrBusy,
    asrLatencyMs,
    error,
    recognitionIssue,
    openMic,
    calibrate,
    startMonitor,
    stopMonitor,
    recordSample,
    beginAnswer,
    endAnswer,
    abortAnswer,
    closeMic,
  }
}
