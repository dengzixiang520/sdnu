<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { PhMusicNotes, PhPause, PhPlay, PhSpeakerHigh, PhStop, PhTrash, PhUploadSimple } from '@phosphor-icons/vue'
import { command } from '../api'
import { playAmbient, setAmbientVolume, stopAmbient } from '../ambient'

const fileInput = ref<HTMLInputElement | null>(null)
const localAudio = ref<HTMLAudioElement | null>(null)
const selectedSound = ref('')
const localUrl = ref(''); const localName = ref(''); const localPlaying = ref(false)
const currentTime = ref(0); const duration = ref(0); const volume = ref(.42); const error = ref('')
const presets = [{ id: '雨声', label: '窗边小雨' }, { id: '钢琴', label: '夜晚钢琴' }, { id: '森林', label: '清晨树林' }] as const

async function setSound(name: '雨声' | '钢琴' | '森林') {
  if (selectedSound.value === name) { stopAll(); return }
  error.value = ''; stopLocal()
  try { await command('wellbeing', 'control', `请播放${name}`); setAmbientVolume(volume.value); await playAmbient(name); selectedSound.value = name }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '音频启动失败' }
}
function stopAll() { stopAmbient(); selectedSound.value = ''; stopLocal() }
function chooseLocal() { fileInput.value?.click() }
function loadLocal(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (!file.type.startsWith('audio/')) { error.value = '请选择浏览器支持的音频文件。'; return }
  if (localUrl.value) URL.revokeObjectURL(localUrl.value)
  stopAmbient(); selectedSound.value = ''; localUrl.value = URL.createObjectURL(file); localName.value = file.name; localPlaying.value = false
  localAudio.value?.load()
}
async function toggleLocal() { const audio = localAudio.value; if (!audio) return; if (audio.paused) { audio.volume = volume.value; await audio.play(); localPlaying.value = true } else { audio.pause(); localPlaying.value = false } }
function stopLocal() { localAudio.value?.pause(); localPlaying.value = false }
function removeLocal() { stopLocal(); if (localUrl.value) URL.revokeObjectURL(localUrl.value); localUrl.value = ''; localName.value = ''; currentTime.value = 0; duration.value = 0; if (fileInput.value) fileInput.value.value = '' }
function updateVolume() { setAmbientVolume(volume.value); if (localAudio.value) localAudio.value.volume = volume.value }
function seek(event: Event) { if (localAudio.value) localAudio.value.currentTime = Number((event.target as HTMLInputElement).value) }
function time(value: number) { if (!Number.isFinite(value)) return '0:00'; return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, '0')}` }
onBeforeUnmount(() => { stopAll(); if (localUrl.value) URL.revokeObjectURL(localUrl.value) })
</script>

<template>
  <aside class="wellbeing-rail" aria-label="暖心空间声音侧栏">
    <header><span><PhMusicNotes :size="21" weight="duotone" /></span><div><h2>声音角落</h2><p>它只是陪伴工具，随时可以停。</p></div></header>
    <div class="now-playing"><div class="record" :class="{ spinning: selectedSound || localPlaying }"><i></i></div><div><small>正在播放</small><strong>{{ localName || selectedSound || '未选择声音' }}</strong></div><button type="button" :disabled="!selectedSound && !localPlaying" aria-label="停止全部声音" @click="stopAll"><PhStop :size="17" weight="fill" /></button></div>
    <div class="sound-presets">
      <button v-for="preset in presets" :key="preset.id" :class="{ active: selectedSound === preset.id }" type="button" @click="setSound(preset.id)"><component :is="selectedSound === preset.id ? PhPause : PhPlay" :size="15" weight="fill" /><span>{{ preset.label }}</span></button>
    </div>
    <label class="sound-volume"><PhSpeakerHigh :size="17" /><input v-model.number="volume" type="range" min="0" max="1" step="0.01" aria-label="音乐音量" @input="updateVolume"><b>{{ Math.round(volume * 100) }}%</b></label>
    <input ref="fileInput" class="visually-hidden" type="file" accept="audio/*" @change="loadLocal">
    <button v-if="!localUrl" class="local-upload" type="button" @click="chooseLocal"><PhUploadSimple :size="20" /><span><strong>播放本地音乐</strong><small>文件只留在当前浏览器</small></span></button>
    <div v-else class="local-track">
      <audio ref="localAudio" :src="localUrl" @loadedmetadata="duration = localAudio?.duration || 0" @timeupdate="currentTime = localAudio?.currentTime || 0" @ended="localPlaying = false"></audio>
      <div><button type="button" @click="toggleLocal"><component :is="localPlaying ? PhPause : PhPlay" :size="17" weight="fill" /></button><strong :title="localName">{{ localName }}</strong><button type="button" aria-label="移除本地音乐" @click="removeLocal"><PhTrash :size="17" /></button></div>
      <label><span>{{ time(currentTime) }}</span><input type="range" min="0" :max="duration || 0" step="0.1" :value="currentTime" aria-label="音乐进度" @input="seek"><span>{{ time(duration) }}</span></label>
    </div>
    <p v-if="error" class="rail-error">{{ error }}</p>
    <div class="sound-privacy"><strong>本地播放</strong><p>平台不会上传、分析或保存你选择的音频文件。</p></div>
  </aside>
</template>
