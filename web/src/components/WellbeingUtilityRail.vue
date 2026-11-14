<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  PhMagnifyingGlass,
  PhMusicNotes,
  PhPause,
  PhPlay,
  PhSpeakerHigh,
  PhStop,
  PhTextAa,
  PhTrash,
  PhUploadSimple,
} from '@phosphor-icons/vue'

import {
  currentSubtitle,
  currentTitle,
  formatClock,
  lyricView,
  player,
  playLocalFile,
  playLocalSource,
  playTrack,
  releaseLocalFile,
  searchMusic,
  seek,
  setVolume,
  stopMusic,
  togglePlay,
  warmUpTracks,
  type MusicTrack,
} from '../music'

/** 项目自带的离线曲目：网络不通时也能听，答辩现场不至于冷场。 */
const builtins = [
  { id: 'shiguojingqian', name: '时过境迁', artist: '苏艺馨Chency', src: '/music/shiguojingqian.mp3' },
  { id: 'buyaoyishixingqi', name: '请不要一时兴起', artist: '灰小灰、Echo艾歌', src: '/music/buyaoyishixingqi.mp3' },
]

const fileInput = ref<HTMLInputElement | null>(null)
const keyword = ref('')
const results = ref<MusicTrack[]>([])
const searching = ref(false)
const searchError = ref('')
const searched = ref(false)

const hasLyric = computed(() => player.lyrics.length > 0 || player.lyricLoading)
const progressMax = computed(() => (Number.isFinite(player.duration) && player.duration > 0 ? player.duration : 0))

async function runSearch() {
  const query = keyword.value.trim()
  if (!query || searching.value) return
  searching.value = true
  searchError.value = ''
  try {
    const items = await searchMusic(query)
    results.value = items
    searched.value = true
    if (items.length === 0) searchError.value = '没搜到，换个关键词试试。'
    else warmUpTracks(items)
  } catch (reason) {
    results.value = []
    searchError.value = reason instanceof Error ? reason.message : '搜索失败'
  } finally {
    searching.value = false
  }
}

function clearSearch() {
  keyword.value = ''
  results.value = []
  searchError.value = ''
  searched.value = false
}

async function pick(track: MusicTrack) {
  await playTrack(track)
}

async function pickBuiltin(item: typeof builtins[number]) {
  await playLocalSource(item.name, item.src)
}

function chooseLocal() { fileInput.value?.click() }

async function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (!file.type.startsWith('audio/')) { player.error = '请选择浏览器支持的音频文件。'; return }
  await playLocalFile(file)
  input.value = ''
}

function removeLocal() { releaseLocalFile() }

/**
 * 音量直接读事件目标的值，不读 `player.volume`。
 * `v-model.number` 也会写这个字段，两者的 input 监听器谁先跑没有保证；
 * 若本函数先跑就会把上一帧的旧值写回 audio，表现为「滑块在动、音量不变」。
 */
function onVolume(event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  player.volume = value
  setVolume(value)
}

function onSeek(event: Event) { seek(Number((event.target as HTMLInputElement).value)) }
function toggleLyric() { lyricView.open = !lyricView.open }

onBeforeUnmount(() => { stopMusic() })
</script>

<template>
  <aside class="wellbeing-rail" aria-label="暖心空间声音侧栏">
    <header>
      <span><PhMusicNotes :size="21" weight="duotone" /></span>
      <div><h2>声音角落</h2><p>它只是陪伴工具，随时可以停。</p></div>
    </header>

    <div class="now-playing">
      <div class="record" :class="{ spinning: player.playing }"><i></i></div>
      <div>
        <small>{{ player.loading ? '正在解析音源…' : '正在播放' }}</small>
        <strong :title="currentTitle">{{ currentTitle || '未选择声音' }}</strong>
        <em v-if="currentSubtitle">{{ currentSubtitle }}</em>
      </div>
      <button type="button" :disabled="!currentTitle" aria-label="停止声音" @click="stopMusic"><PhStop :size="17" weight="fill" /></button>
    </div>

    <div class="sound-actions">
      <button type="button" class="sound-play" :disabled="!currentTitle" @click="togglePlay">
        <component :is="player.playing ? PhPause : PhPlay" :size="16" weight="fill" />
        {{ player.playing ? '暂停' : '播放' }}
      </button>
      <button type="button" class="sound-lyric" :class="{ active: lyricView.open }" :disabled="!hasLyric" @click="toggleLyric">
        <PhTextAa :size="16" weight="bold" />
        {{ lyricView.open ? '收起歌词' : '看歌词' }}
      </button>
    </div>

    <p v-if="player.error" class="rail-error">{{ player.error }}</p>

    <div class="sound-search">
      <label>
        <PhMagnifyingGlass :size="16" />
        <input
          v-model="keyword"
          type="search"
          placeholder="搜歌名、歌手、专辑"
          aria-label="搜索歌曲"
          @keyup.enter="runSearch"
        >
        <button v-if="keyword" type="button" aria-label="清空搜索" @click="clearSearch"><PhTrash :size="14" /></button>
      </label>
      <button type="button" class="sound-search-go" :disabled="searching || !keyword.trim()" @click="runSearch">
        {{ searching ? '搜索中' : '搜索' }}
      </button>
    </div>

    <p v-if="searchError" class="rail-error">{{ searchError }}</p>

    <ul v-if="results.length" class="sound-results">
      <li v-for="item in results" :key="item.id">
        <button
          type="button"
          :class="{ active: player.kind === 'track' && player.track?.id === item.id }"
          @click="pick(item)"
        >
          <span class="result-main"><strong>{{ item.name }}</strong><small>{{ item.artists }}</small></span>
          <em v-if="item.fee === 1" class="result-vip" title="会员曲目：会自动换第三方音源，首次解析要几秒">VIP</em>
          <span class="result-time">{{ formatClock(item.duration / 1000) }}</span>
        </button>
      </li>
    </ul>

    <p v-else-if="searched && !searching" class="sound-empty">没有结果。也可以试试下面的随手听。</p>

    <p class="sound-label">随手听（离线可用）</p>
    <div class="sound-presets">
      <button
        v-for="item in builtins"
        :key="item.id"
        :class="{ active: player.kind === 'local' && player.localName === item.name }"
        type="button"
        @click="pickBuiltin(item)"
      >
        <component :is="player.kind === 'local' && player.localName === item.name && player.playing ? PhPause : PhPlay" :size="15" weight="fill" />
        <span><strong>{{ item.name }}</strong><small>{{ item.artist }}</small></span>
      </button>
    </div>

    <label v-if="progressMax" class="sound-progress">
      <span>{{ formatClock(player.currentTime) }}</span>
      <input
        type="range"
        min="0"
        :max="progressMax"
        step="0.5"
        :value="player.currentTime"
        aria-label="播放进度"
        @input="onSeek"
      >
      <span>{{ formatClock(player.duration) }}</span>
    </label>

    <label class="sound-volume">
      <PhSpeakerHigh :size="17" />
      <input v-model.number="player.volume" type="range" min="0" max="1" step="0.01" aria-label="音乐音量" @input="onVolume">
      <b>{{ Math.round(player.volume * 100) }}%</b>
    </label>

    <p v-if="player.lyricLoading" class="sound-note">歌词加载中…</p>
    <p v-else-if="player.instrumental && currentTitle" class="sound-note">这首歌没有歌词（纯音乐）。</p>

    <input ref="fileInput" class="visually-hidden" type="file" accept="audio/*" @change="onFile">
    <button v-if="!player.objectUrl" class="local-upload" type="button" @click="chooseLocal">
      <PhUploadSimple :size="20" />
      <span><strong>播放本地音乐</strong><small>文件只留在当前浏览器</small></span>
    </button>
    <div v-else class="local-track">
      <div>
        <button type="button" :aria-label="player.playing ? '暂停本地音乐' : '播放本地音乐'" @click="togglePlay">
          <component :is="player.playing ? PhPause : PhPlay" :size="17" weight="fill" />
        </button>
        <strong :title="player.localName">{{ player.localName }}</strong>
        <button type="button" aria-label="移除本地音乐" @click="removeLocal"><PhTrash :size="17" /></button>
      </div>
    </div>

    <div class="sound-privacy">
      <strong>本地播放</strong>
      <p>上传的音频不会离开当前浏览器；在线歌曲只取播放地址，不做下载或留存。</p>
    </div>
  </aside>
</template>
