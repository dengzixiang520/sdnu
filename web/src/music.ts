import { computed, reactive } from 'vue'

import { requestJson } from './api'

/** 一首搜索结果。字段由后端 `/api/v1/music/search` 归一化，前端不用记网易云的两套命名。 */
export interface MusicTrack {
  id: number
  name: string
  artists: string
  album: string
  cover: string
  duration: number
  fee: number
}

export interface LyricLine {
  time: number
  text: string
}

export interface MusicStatus {
  available: boolean
  channel: 'local' | 'public' | 'none'
  localBase: string
  localReady: boolean
  publicReady: boolean
  accountReady: boolean
}

const LRC_TAG = /\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]/g

/**
 * 解析 LRC。
 *
 * 一行可能有多个时间标签（副歌复用），所以按标签逐个展开；纯时间轴行（只有标签没有
 * 文字）直接丢掉——它们只是网易云在排版权信息时的占位。
 */
export function parseLrc(raw: string): LyricLine[] {
  const lines: LyricLine[] = []
  for (const row of raw.split('\n')) {
    const tags = [...row.matchAll(LRC_TAG)]
    if (tags.length === 0) continue
    const text = row.replace(LRC_TAG, '').trim()
    if (!text) continue
    for (const tag of tags) {
      const minutes = Number(tag[1])
      const seconds = Number(tag[2])
      const fraction = Number((tag[3] ?? '0').padEnd(3, '0'))
      lines.push({ time: minutes * 60 + seconds + fraction / 1000, text })
    }
  }
  return lines.sort((left, right) => left.time - right.time)
}

export const player = reactive({
  kind: '' as '' | 'track' | 'local',
  track: null as MusicTrack | null,
  localName: '',
  objectUrl: '',
  playing: false,
  loading: false,
  currentTime: 0,
  duration: 0,
  volume: 0.42,
  error: '',
  lyrics: [] as LyricLine[],
  translation: [] as LyricLine[],
  lyricLoading: false,
  instrumental: false,
})

let audio: HTMLAudioElement | null = null

function element(): HTMLAudioElement {
  if (audio) return audio
  const node = new Audio()
  node.preload = 'metadata'
  node.volume = player.volume
  node.addEventListener('play', () => { player.playing = true })
  node.addEventListener('pause', () => { player.playing = false })
  node.addEventListener('ended', () => { player.playing = false })
  node.addEventListener('loadedmetadata', () => {
    if (Number.isFinite(node.duration)) player.duration = node.duration
  })
  node.addEventListener('timeupdate', () => { player.currentTime = node.currentTime })
  node.addEventListener('error', () => {
    if (!node.getAttribute('src')) return
    player.playing = false
    player.error = '音频加载失败，换一首试试。'
  })
  audio = node
  return node
}

/**
 * 歌词面板的显示偏好。侧栏太窄，长句只能挤成一列竖着滚，所以这里把「怎么显示」
 * 交回给用户：横排还是竖排、字号多大、放在屏幕哪个位置，都能自己调。
 * 偏好写进 localStorage，刷新后保持。
 */
export type LyricWriting = 'horizontal' | 'vertical'

const PREFS_KEY = 'zhq.lyric.prefs'

export const lyricView = reactive({
  open: false,
  writing: 'horizontal' as LyricWriting,
  fontSize: 22,
  x: 0,
  y: 0,
  placed: false,
})

export function loadLyricPrefs(): void {
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    if (!raw) return
    const saved = JSON.parse(raw) as Partial<typeof lyricView>
    if (saved.writing === 'horizontal' || saved.writing === 'vertical') lyricView.writing = saved.writing
    if (typeof saved.fontSize === 'number') lyricView.fontSize = Math.min(52, Math.max(12, saved.fontSize))
    if (typeof saved.x === 'number') lyricView.x = saved.x
    if (typeof saved.y === 'number') lyricView.y = saved.y
    if (typeof saved.placed === 'boolean') lyricView.placed = saved.placed
  } catch {
    // 坏掉的偏好不值得中断播放，直接用默认值。
  }
}

export function saveLyricPrefs(): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify({
      writing: lyricView.writing,
      fontSize: lyricView.fontSize,
      x: lyricView.x,
      y: lyricView.y,
      placed: lyricView.placed,
    }))
  } catch {
    // 隐私模式下 localStorage 可能不可写，忽略即可。
  }
}

export const currentTitle = computed(() => {  if (player.kind === 'local') return player.localName
  return player.track?.name ?? ''
})

export const currentSubtitle = computed(() => {
  if (player.kind === 'local') return '本地文件'
  return player.track?.artists ?? ''
})

/** 当前应该高亮的歌词行；没有歌词或还没开始唱时返回 -1。 */export const activeLyricIndex = computed(() => {
  const list = player.lyrics
  if (list.length === 0) return -1
  const now = player.currentTime
  let low = 0
  let high = list.length - 1
  let found = -1
  while (low <= high) {
    const mid = (low + high) >> 1
    if (list[mid].time <= now) { found = mid; low = mid + 1 } else { high = mid - 1 }
  }
  return found
})

export function musicStatus(): Promise<MusicStatus> {
  return requestJson<MusicStatus>('/api/v1/music/status', {}, '音乐服务状态未知')
}

export async function searchMusic(keyword: string): Promise<MusicTrack[]> {
  const query = keyword.trim()
  if (!query) return []
  const result = await requestJson<{ items: MusicTrack[] }>(
    `/api/v1/music/search?q=${encodeURIComponent(query)}&limit=20`,
    {},
    '搜索失败',
  )
  return result.items
}

/**
 * 会员曲目要换第三方音源，单次要 3-8 秒。列表出来后就先把前两条的地址解析掉，
 * 用户看完歌名再点，通常已经命中后端的地址缓存。只取 URL 不下载音频，成本很低。
 */
export function warmUpTracks(items: MusicTrack[]): void {
  for (const item of items.filter((entry) => entry.fee === 1).slice(0, 2)) {
    const query = new URLSearchParams({ fee: '1', name: item.name, artists: item.artists })
    void fetch(`/api/v1/music/url/${item.id}?${query.toString()}`).catch(() => {})
  }
}

async function loadLyric(id: number): Promise<void> {
  player.lyricLoading = true
  try {
    const result = await requestJson<{ lrc: string; translation: string; instrumental: boolean }>(
      `/api/v1/music/lyric/${id}`,
      {},
      '歌词加载失败',
    )
    player.lyrics = parseLrc(result.lrc)
    player.translation = parseLrc(result.translation)
    player.instrumental = result.instrumental
  } catch {
    player.lyrics = []
    player.translation = []
    player.instrumental = false
  } finally {
    player.lyricLoading = false
  }
}

/** 点歌：同一首就切播放/暂停，换歌才重新取地址。 */
export async function playTrack(track: MusicTrack): Promise<void> {
  const node = element()
  if (player.kind === 'track' && player.track?.id === track.id && node.getAttribute('src')) {
    if (node.paused) { await node.play().catch(() => { player.error = '播放被浏览器拦住了，再点一次。' }) } else { node.pause() }
    return
  }
  player.loading = true
  player.error = ''
  player.kind = 'track'
  player.track = track
  player.currentTime = 0
  player.duration = track.duration / 1000
  player.lyrics = []
  player.translation = []
  player.instrumental = false
  try {
    const query = new URLSearchParams({
      fee: String(track.fee ?? -1),
      name: track.name,
      artists: track.artists,
    })
    const result = await requestJson<{ url: string }>(
      `/api/v1/music/url/${track.id}?${query.toString()}`,
      {},
      '取播放地址失败',
    )
    node.src = result.url
    node.volume = player.volume
    await node.play()
  } catch (reason) {
    player.error = reason instanceof Error ? reason.message : '这首歌暂时放不了。'
    player.track = null
    player.kind = ''
    player.duration = 0
    player.currentTime = 0
  } finally {
    player.loading = false
  }
  void loadLyric(track.id)
}

/** 播放内置或用户选择的本地音频；与在线曲目共用同一个 audio 元素，切歌不会串音。 */
export async function playLocalSource(name: string, source: string): Promise<void> {
  const node = element()
  if (player.kind === 'local' && player.localName === name && node.getAttribute('src')) {
    if (node.paused) { await node.play().catch(() => { player.error = '播放被浏览器拦住了，再点一次。' }) } else { node.pause() }
    return
  }
  player.error = ''
  player.kind = 'local'
  player.localName = name
  player.track = null
  player.lyrics = []
  player.translation = []
  player.instrumental = false
  player.currentTime = 0
  player.duration = 0
  node.src = source
  node.volume = player.volume
  try { await node.play() }
  catch { player.error = '播放被浏览器拦住了，再点一次。' }
}

/** 用户上传的本地文件；对象 URL 在换歌或卸载时释放。 */
export async function playLocalFile(file: File): Promise<void> {
  if (player.objectUrl) URL.revokeObjectURL(player.objectUrl)
  player.objectUrl = URL.createObjectURL(file)
  await playLocalSource(file.name, player.objectUrl)
}

export function releaseLocalFile(): void {
  if (player.kind === 'local' && player.objectUrl) stopMusic()
  if (player.objectUrl) URL.revokeObjectURL(player.objectUrl)
  player.objectUrl = ''
  if (player.kind === 'local') { player.localName = ''; player.kind = '' }
}

export function togglePlay(): void {
  const node = element()
  if (!node.getAttribute('src')) {
    player.error = '还没取到音源，稍等一下或换一首。'
    return
  }
  player.error = ''
  if (node.paused) void node.play().catch(() => { player.error = '播放被浏览器拦住了，再点一次。' })
  else node.pause()
}

export function seek(seconds: number): void {
  const node = element()
  if (!node.getAttribute('src')) return
  node.currentTime = Math.max(0, seconds)
  player.currentTime = node.currentTime
}

export function setVolume(value: number): void {
  player.volume = Math.min(1, Math.max(0, value))
  if (audio) audio.volume = player.volume
}

export function stopMusic(): void {
  const node = element()
  node.pause()
  node.currentTime = 0
  player.currentTime = 0
  player.playing = false
}

export function formatClock(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0:00'
  const total = Math.floor(value)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}
