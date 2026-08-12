<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowUp, PhMinus, PhPaperPlaneTilt, PhSparkle } from '@phosphor-icons/vue'
import { chatHistory, streamChat, type ChatMessage } from '../api'

type PetState = 'idle' | 'wave' | 'sleep' | 'snack' | 'milktea' | 'listening' | 'thinking' | 'talking' | 'caring'
const router = useRouter()
const route = useRoute()
const pet = ref<HTMLElement | null>(null)
const open = ref(false)
const minimized = ref(false)
const loading = ref(false)
const input = ref('')
const state = ref<PetState>('wave')
const messages = ref<ChatMessage[]>([{ role: 'assistant', content: '嗨，我是小齐。可以拖动我，也可以和我聊聊今天。' }])
const position = ref({ x: 0, y: 0 })
const providerOnline = ref<boolean | null>(null)
const loadedHistory = ref(false)
const rotateX = ref(0)
const rotateY = ref(0)
let pointerId: number | null = null
let origin = { x: 0, y: 0, left: 0, top: 0 }
let dragged = false
let idleTimer: number | undefined

const idleStates: PetState[] = ['idle', 'wave', 'sleep', 'snack', 'milktea']
const stateCopy: Record<PetState, string> = {
  idle: '在陪你', wave: '今天也见面啦', sleep: '打个小盹', snack: '补充一点能量', milktea: '奶茶时间',
  listening: '认真听你说', thinking: '正在想一想', talking: '正在回应', caring: '先陪你稳住',
}

function clampPosition(x: number, y: number) {
  const width = pet.value?.offsetWidth ?? 118
  const height = pet.value?.offsetHeight ?? 178
  return { x: Math.max(8, Math.min(x, window.innerWidth - width - 8)), y: Math.max(64, Math.min(y, window.innerHeight - height - 8)) }
}
function savePosition() { localStorage.setItem('zhihui-guide-position-v2', JSON.stringify(position.value)) }
function beginDrag(event: PointerEvent) {
  if ((event.target as HTMLElement).closest('.guide-dialog')) return
  pointerId = event.pointerId; dragged = false
  origin = { x: event.clientX, y: event.clientY, left: position.value.x, top: position.value.y }
  window.addEventListener('pointermove', movePet); window.addEventListener('pointerup', endDrag, { once: true })
}
function movePet(event: PointerEvent) {
  if (event.pointerId !== pointerId) return
  const dx = event.clientX - origin.x; const dy = event.clientY - origin.y
  if (Math.abs(dx) + Math.abs(dy) > 5) dragged = true
  position.value = clampPosition(origin.left + dx, origin.top + dy)
}
async function endDrag(event: PointerEvent) {
  if (event.pointerId !== pointerId) return
  window.removeEventListener('pointermove', movePet); pointerId = null
  if (dragged) savePosition(); else if (!minimized.value) await toggleDialog()
}
async function toggleDialog() {
  open.value = !open.value
  if (open.value) {
    state.value = 'listening'; await loadHistory(); await nextTick()
    document.querySelector<HTMLInputElement>('.guide-dialog input')?.focus()
  } else scheduleIdle()
}
async function loadHistory() {
  if (loadedHistory.value) return
  try {
    const history = await chatHistory('wellbeing')
    if (history.length) messages.value = history.slice(-8)
  } catch { /* first-use greeting remains available */ }
  loadedHistory.value = true
}
async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text }, { role: 'assistant', content: '' })
  input.value = ''; loading.value = true; state.value = 'thinking'
  const answer = messages.value[messages.value.length - 1]
  try {
    const result = await streamChat('wellbeing', text, {}, (token) => { answer.content += token; state.value = 'talking' })
    providerOnline.value = result.providerOnline
    state.value = result.escalated ? 'caring' : 'talking'
  } catch (reason) {
    answer.content = reason instanceof Error ? reason.message : '我暂时没有连上服务。你仍然可以去暖心空间记录状态。'
    providerOnline.value = false; state.value = 'caring'
  } finally {
    loading.value = false
    window.setTimeout(() => { if (open.value) state.value = 'listening' }, 1800)
  }
}
function onInputKeydown(event: KeyboardEvent) { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send() } }
function enterWellbeing() { open.value = false; void router.push('/wellbeing') }
function minimize() { open.value = false; minimized.value = true; window.clearTimeout(idleTimer) }
function restore() { minimized.value = false; restorePosition(); scheduleIdle() }
function restorePosition() {
  const stored = localStorage.getItem('zhihui-guide-position-v2')
  if (stored) { try { const parsed = JSON.parse(stored) as { x: number; y: number }; position.value = clampPosition(parsed.x, parsed.y); return } catch { /* use default */ } }
  position.value = clampPosition(window.innerWidth - 150, window.innerHeight - 220)
}
function scheduleIdle() {
  window.clearTimeout(idleTimer)
  idleTimer = window.setTimeout(() => {
    if (!open.value && !minimized.value && pointerId === null) state.value = idleStates[Math.floor(Math.random() * idleStates.length)]
    scheduleIdle()
  }, 8000 + Math.random() * 7000)
}
function handleResize() { position.value = clampPosition(position.value.x, position.value.y) }
function openFromPage() { if (minimized.value) minimized.value = false; if (!open.value) void toggleDialog() }

// 3D鼠标跟踪效果
function handleMouseMove(event: MouseEvent) {
  if (!pet.value || open.value) return
  const rect = pet.value.getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2
  const mouseX = event.clientX
  const mouseY = event.clientY
  
  // 计算鼠标相对于角色中心的角度
  const deltaX = (mouseX - centerX) / (window.innerWidth / 2)
  const deltaY = (mouseY - centerY) / (window.innerHeight / 2)
  
  // 限制旋转角度在±15度范围内
  rotateY.value = Math.max(-15, Math.min(15, deltaX * 15))
  rotateX.value = Math.max(-10, Math.min(10, -deltaY * 10))
}

function handleMouseLeave() {
  // 鼠标离开时平滑回到初始位置
  rotateX.value = 0
  rotateY.value = 0
}

watch(() => route.fullPath, () => { open.value = false; scheduleIdle() })
onMounted(() => { 
  restorePosition(); 
  scheduleIdle(); 
  window.addEventListener('resize', handleResize); 
  window.addEventListener('zhq-open-guide', openFromPage)
  window.addEventListener('mousemove', handleMouseMove)
})
onBeforeUnmount(() => { 
  window.clearTimeout(idleTimer); 
  window.removeEventListener('resize', handleResize); 
  window.removeEventListener('zhq-open-guide', openFromPage); 
  window.removeEventListener('pointermove', movePet)
  window.removeEventListener('mousemove', handleMouseMove)
})
</script>

<template>
  <button v-if="minimized" class="guide-restore" type="button" aria-label="显示暖心引导员" @click="restore">
    <PhSparkle :size="22" weight="fill" />
  </button>
  <div v-else ref="pet" class="guide-pet" :class="['is-' + state, { open }]" :style="{ transform: 'translate3d(' + position.x + 'px, ' + position.y + 'px, 0)' }" @pointerdown="beginDrag" @mouseleave="handleMouseLeave">
    <section v-if="open" class="guide-dialog" aria-label="与暖心引导员对话" @pointerdown.stop>
      <header>
        <div>
          <span class="guide-online"><i :class="{ offline: providerOnline === false }"></i>小齐 · {{ stateCopy[state] }}</span>
          <small>{{ providerOnline === false ? '当前为本地陪伴模式' : '多轮对话仅在本会话保留' }}</small>
        </div>
        <button type="button" aria-label="最小化引导员" @click="minimize"><PhMinus :size="18" /></button>
      </header>
      <div class="guide-messages" aria-live="polite">
        <div v-for="(item, index) in messages" :key="index" :class="['guide-message', item.role]">
          <span v-if="item.role === 'assistant'">齐</span>
          <p>{{ item.content || '正在组织语言…' }}</p>
        </div>
      </div>
      <form class="guide-composer" @submit.prevent="send">
        <input v-model="input" maxlength="4000" placeholder="想聊什么都可以…" aria-label="发送给暖心引导员" @keydown="onInputKeydown">
        <button type="submit" :disabled="loading || !input.trim()" aria-label="发送消息"><PhPaperPlaneTilt :size="19" weight="fill" /></button>
      </form>
      <footer>
        <button type="button" @click="enterWellbeing">打开暖心空间 <PhArrowUp :size="14" /></button>
        <span>AI 陪伴不能替代专业或紧急支持</span>
      </footer>
    </section>

    <div class="pet-stage" role="button" :aria-label="'暖心引导员小齐，' + stateCopy[state] + '，可拖动位置或点击对话'" :style="{ perspective: '800px', perspectiveOrigin: '50% 50%' }">
      <span class="pet-status">{{ stateCopy[state] }}</span>
      <div class="pet-z">Z<sup>z</sup></div>
      <div class="pet-prop snack">小饼干</div>
      <div class="pet-prop cup"><i></i><b>奶茶</b></div>
      <div class="pet-shadow"></div>
      <div class="pet-character" :style="{ transform: 'rotateX(' + rotateX + 'deg) rotateY(' + rotateY + 'deg)', transformStyle: 'preserve-3d' }">
        <div class="pet-3d-body">
          <div class="pet-hair back"></div>
          <div class="pet-leg left"><i></i></div>
          <div class="pet-leg right"><i></i></div>
          <div class="pet-torso"><span class="pet-scarf"></span><b>齐</b></div>
          <div class="pet-arm left"></div>
          <div class="pet-arm right"></div>
          <div class="pet-head">
            <div class="pet-hair front"></div>
            <span class="pet-ear left"></span>
            <span class="pet-ear right"></span>
            <div class="pet-face">
              <i class="pet-eye left"></i>
              <i class="pet-eye right"></i>
              <span class="pet-blush left"></span>
              <span class="pet-blush right"></span>
              <b class="pet-mouth"></b>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>