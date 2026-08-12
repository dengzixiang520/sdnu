<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowUp, PhMinus, PhPaperPlaneTilt, PhSparkle } from '@phosphor-icons/vue'
import { chatHistory, streamChat, type ChatMessage } from '../api'

type PetState = 'idle' | 'wave' | 'sleep' | 'snack' | 'milktea' | 'glasses' | 'listening' | 'thinking' | 'talking' | 'caring'
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
const isHovering = ref(false)
let pointerId: number | null = null
let origin = { x: 0, y: 0, left: 0, top: 0 }
let dragged = false
let idleTimer: number | undefined

const idleStates: PetState[] = ['idle', 'wave', 'sleep', 'snack', 'milktea', 'glasses']
const stateCopy: Record<PetState, string> = {
  idle: '在陪你', wave: '今天也见面啦', sleep: '打个小盹', snack: '吃颗糖果', milktea: '喝杯奶茶', glasses: '看书学习中',
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
  }, 6000 + Math.random() * 6000)
}
function handleResize() { position.value = clampPosition(position.value.x, position.value.y) }
function openFromPage() { if (minimized.value) minimized.value = false; if (!open.value) void toggleDialog() }

function handleMouseMove(event: MouseEvent) {
  if (!pet.value || open.value) return
  const rect = pet.value.getBoundingClientRect()
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2
  const deltaX = (event.clientX - centerX) / (window.innerWidth / 2)
  const deltaY = (event.clientY - centerY) / (window.innerHeight / 2)
  rotateY.value = Math.max(-20, Math.min(20, deltaX * 20))
  rotateX.value = Math.max(-12, Math.min(12, -deltaY * 12))
  isHovering.value = true
}

function handleMouseLeave() {
  rotateX.value = 0
  rotateY.value = 0
  isHovering.value = false
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
  <div v-else ref="pet" class="guide-pet" :class="['is-' + state, { open, hovering: isHovering }]" :style="{ transform: 'translate3d(' + position.x + 'px, ' + position.y + 'px, 0)' }" @pointerdown="beginDrag" @mouseleave="handleMouseLeave">
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
          <span v-if="item.role === 'assistant'">SDNU</span>
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

    <div class="pet-stage" role="button" :aria-label="'暖心引导员小齐，' + stateCopy[state] + '，可拖动位置或点击对话'">
      <span class="pet-status">{{ stateCopy[state] }}</span>
      
      <!-- 3D角色容器 -->
      <div class="pet-3d-scene">
        <div class="pet-character" :style="{ transform: 'rotateX(' + rotateX + 'deg) rotateY(' + rotateY + 'deg)' }">
          <!-- 身体主体 -->
          <div class="pet-body">
            <!-- 头发后层 -->
            <div class="pet-hair-back"></div>
            
            <!-- 腿部 -->
            <div class="pet-legs">
              <div class="pet-leg left"></div>
              <div class="pet-leg right"></div>
            </div>
            
            <!-- 躯干 -->
            <div class="pet-torso">
              <div class="pet-scarf"></div>
              <div class="pet-badge">SDNU</div>
            </div>
            
            <!-- 手臂 -->
            <div class="pet-arm left"></div>
            <div class="pet-arm right"></div>
            
            <!-- 头部 -->
            <div class="pet-head">
              <div class="pet-hair-front"></div>
              <div class="pet-ear left"></div>
              <div class="pet-ear right"></div>
              <div class="pet-face">
                <div class="pet-eye left">
                  <div class="pet-pupil"></div>
                </div>
                <div class="pet-eye right">
                  <div class="pet-pupil"></div>
                </div>
                <div class="pet-blush left"></div>
                <div class="pet-blush right"></div>
                <div class="pet-mouth"></div>
              </div>
              <!-- 眼镜（glasses状态显示） -->
              <div class="pet-glasses">
                <div class="pet-glasses-frame left"></div>
                <div class="pet-glasses-frame right"></div>
                <div class="pet-glasses-bridge"></div>
              </div>
            </div>
          </div>
          
          <!-- 道具层 -->
          <div class="pet-props">
            <!-- 奶茶 -->
            <div class="pet-prop-milktea">
              <div class="pet-cup">
                <div class="pet-cup-straw"></div>
                <div class="pet-cup-body"></div>
                <div class="pet-cup-lid"></div>
              </div>
            </div>
            <!-- 糖果 -->
            <div class="pet-prop-candy">
              <div class="pet-candy">
                <div class="pet-candy-left"></div>
                <div class="pet-candy-center"></div>
                <div class="pet-candy-right"></div>
              </div>
            </div>
            <!-- 书本 -->
            <div class="pet-prop-book">
              <div class="pet-book">
                <div class="pet-book-cover"></div>
                <div class="pet-book-pages"></div>
                <div class="pet-book-text">ABC</div>
              </div>
            </div>
          </div>
          
          <!-- 睡眠Z -->
          <div class="pet-zzz">
            <span>Z</span><span>z</span><span>z</span>
          </div>
        </div>
      </div>
      
      <!-- 阴影 -->
      <div class="pet-shadow"></div>
    </div>
  </div>
</template>