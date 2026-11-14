<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PhArrowsOutCardinal, PhColumns, PhRows, PhX } from '@phosphor-icons/vue'

import {
  activeLyricIndex,
  currentSubtitle,
  currentTitle,
  loadLyricPrefs,
  lyricView,
  player,
  saveLyricPrefs,
  seek,
} from '../../music'

const bodyEl = ref<HTMLElement | null>(null)

const stageStyle = computed(() => {
  const style: Record<string, string> = { '--lyric-size': `${lyricView.fontSize}px` }
  if (lyricView.placed) {
    style.left = `${lyricView.x}px`
    style.top = `${lyricView.y}px`
  } else {
    style.left = '50%'
    style.top = '50%'
    style.transform = 'translate(-50%, -50%)'
  }
  return style
})

function bumpFont(step: number) {
  lyricView.fontSize = Math.min(52, Math.max(12, lyricView.fontSize + step))
  saveLyricPrefs()
}

function toggleWriting() {
  lyricView.writing = lyricView.writing === 'horizontal' ? 'vertical' : 'horizontal'
  saveLyricPrefs()
}

function recenter() {
  lyricView.placed = false
  lyricView.x = 0
  lyricView.y = 0
  saveLyricPrefs()
}

function jump(time: number) { seek(time + 0.05) }

let drag: { dx: number; dy: number } | null = null

function onDragStart(event: PointerEvent) {
  const target = event.target as HTMLElement
  if (target.closest('button')) return
  const bar = event.currentTarget as HTMLElement
  const rect = bar.parentElement?.getBoundingClientRect()
  if (!rect) return
  drag = { dx: event.clientX - rect.left, dy: event.clientY - rect.top }
  bar.setPointerCapture(event.pointerId)
}

function onDragMove(event: PointerEvent) {
  if (!drag) return
  const maxX = Math.max(0, window.innerWidth - 160)
  const maxY = Math.max(0, window.innerHeight - 80)
  lyricView.placed = true
  lyricView.x = Math.min(maxX, Math.max(0, event.clientX - drag.dx))
  lyricView.y = Math.min(maxY, Math.max(0, event.clientY - drag.dy))
}

function onDragEnd(event: PointerEvent) {
  if (!drag) return
  drag = null
  ;(event.currentTarget as HTMLElement).releasePointerCapture?.(event.pointerId)
  saveLyricPrefs()
}

/**
 * 把当前行滚到可视区中间。
 *
 * 横排直接改容器的 scrollTop；竖排（`vertical-rl`）的 scrollLeft 取值区间是负数，
 * 手算偏移会被钳到 0，所以那一支交给 scrollIntoView——面板是 fixed 定位，
 * 它只会滚面板自己的滚动区，不会把整页带跑。
 */
function scrollToActive() {
  const container = bodyEl.value
  const index = activeLyricIndex.value
  if (!container || index < 0) return
  const line = container.children[index] as HTMLElement | undefined
  if (!line) return
  if (lyricView.writing === 'vertical') {
    // vertical-rl 里 block 轴才是横向，所以居中要落在 block 上。
    line.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' })
    return
  }
  const target = line.offsetTop - (container.clientHeight - line.clientHeight) / 2
  container.scrollTo({ top: Math.max(0, Math.min(target, container.scrollHeight - container.clientHeight)), behavior: 'smooth' })
}

watch(activeLyricIndex, () => { void nextTick(scrollToActive) })
watch(() => lyricView.open, (open) => { if (open) void nextTick(scrollToActive) })
watch(() => lyricView.writing, () => { void nextTick(scrollToActive) })

function onKey(event: KeyboardEvent) {
  if (event.key === 'Escape') lyricView.open = false
}

onMounted(() => {
  loadLyricPrefs()
  window.addEventListener('keydown', onKey)
})

onBeforeUnmount(() => { window.removeEventListener('keydown', onKey) })
</script>

<template>
  <Teleport to="body">
    <section
      v-if="lyricView.open"
      class="lyric-stage"
      :class="`is-${lyricView.writing}`"
      :style="stageStyle"
      role="dialog"
      aria-label="歌词面板"
    >
      <header
        class="lyric-bar"
        @pointerdown="onDragStart"
        @pointermove="onDragMove"
        @pointerup="onDragEnd"
        @pointercancel="onDragEnd"
      >
        <div class="lyric-meta">
          <strong :title="currentTitle">{{ currentTitle || '未选择歌曲' }}</strong>
          <small v-if="currentSubtitle">{{ currentSubtitle }}</small>
        </div>
        <div class="lyric-tools">
          <button type="button" :title="lyricView.writing === 'horizontal' ? '改成竖排' : '改成横排'" @click.stop="toggleWriting">
            <component :is="lyricView.writing === 'horizontal' ? PhColumns : PhRows" :size="15" weight="bold" />
            {{ lyricView.writing === 'horizontal' ? '竖排' : '横排' }}
          </button>
          <button type="button" title="字号变小" @click.stop="bumpFont(-2)">A−</button>
          <button type="button" title="字号变大" @click.stop="bumpFont(2)">A+</button>
          <button type="button" title="回到屏幕中央" aria-label="回到屏幕中央" @click.stop="recenter">
            <PhArrowsOutCardinal :size="15" weight="bold" />
          </button>
          <button type="button" title="关闭歌词" aria-label="关闭歌词" @click.stop="lyricView.open = false">
            <PhX :size="15" weight="bold" />
          </button>
        </div>
      </header>

      <div ref="bodyEl" class="lyric-body">
        <p v-if="player.lyricLoading" class="lyric-hint">歌词加载中…</p>
        <p v-else-if="player.lyrics.length === 0" class="lyric-hint">
          {{ player.instrumental ? '这首歌没有歌词（纯音乐）。' : '先点一首歌，歌词会跟着出现。' }}
        </p>
        <template v-else>
          <p
            v-for="(line, index) in player.lyrics"
            :key="`${line.time}-${index}`"
            :class="{ active: index === activeLyricIndex }"
            :title="`跳到 ${Math.floor(line.time / 60)}:${String(Math.floor(line.time % 60)).padStart(2, '0')}`"
            @click="jump(line.time)"
          >{{ line.text }}</p>
        </template>
      </div>

      <footer class="lyric-foot">
        <span>拖动标题栏可移动</span>
        <b>{{ lyricView.fontSize }}px</b>
      </footer>
    </section>
  </Teleport>
</template>
