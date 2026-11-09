<script setup lang="ts">
/**
 * 暖心引导员「小曦瑶」。
 *
 * 形象与动作素材来自 dsh-pet 的「大肥鱼」动画包（作者 PC2005-cloud，
 * CC BY-NC-SA 4.0，非商业使用并保留署名），已转成带透明通道的动画 WebP；
 * 出处与许可见 NOTICE.md。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhArrowUp, PhMinus, PhPaperPlaneTilt, PhSparkle } from '@phosphor-icons/vue'
import { chatHistory, command, requestJson, streamChat, type ChatMessage } from '../api'
import { useIdentity } from '../identity'

type PetState = 'idle' | 'wave' | 'sleep' | 'snack' | 'milktea' | 'listening' | 'thinking' | 'talking' | 'caring'
type Look = 'left' | 'right' | 'up' | 'down'

const router = useRouter()
const route = useRoute()
const { identity } = useIdentity()

const pet = ref<HTMLElement | null>(null)
const open = ref(false)
const minimized = ref(false)
const loading = ref(false)
const input = ref('')
const state = ref<PetState>('wave')
const messages = ref<ChatMessage[]>([{ role: 'assistant', content: '嗨，我是小曦瑶。可以拖动我，也可以和我聊聊今天。' }])
const position = ref({ x: 0, y: 0 })
const providerOnline = ref<boolean | null>(null)
const loadedHistory = ref(false)

// 注视感：根据指针方位轻微倾斜并挑选对应待机动画
// 取整到整数像素：亚像素位移会迫使浏览器对动画帧重采样，产生闪烁
const look = ref<Look>('down')
const leanX = ref(0)
const leanY = ref(0)
const leanTransform = computed(() =>
  `translate3d(${Math.round(leanX.value)}px, ${Math.round(leanY.value)}px, 0) scaleX(${squash.value.toFixed(3)}) scaleY(${squash.value.toFixed(3)})`
)
const flying = ref(false)
const squash = ref(1)
let velocity = { x: 0, y: 0 }
let physicsFrame = 0

// 能量卡（点击桌宠弹出，展示本项目自己的数据）
const cardOpen = ref(false)
const cardLoading = ref(false)
const card = ref<{ checkins: number; points: number; level: string; shares: number } | null>(null)
const cardError = ref('')

let pointerId: number | null = null
let origin = { x: 0, y: 0, left: 0, top: 0, t: 0 }
let dragged = false
let idleTimer: number | undefined
let lastPointer = { x: 0, y: 0, t: 0 }

const idleStates: PetState[] = ['idle', 'wave', 'sleep', 'snack', 'milktea']
const stateCopy: Record<PetState, string> = {
  idle: '在陪你', wave: '今天也见面啦', sleep: '打个小盹', snack: '补充一点能量', milktea: '奶茶时间',
  listening: '认真听你说', thinking: '正在想一想', talking: '正在回应', caring: '先陪你稳住',
}

/** 每个状态对应的动画池；随机抽一个，避免每次都同一段。 */
const animationPools: Record<PetState, string[]> = {
  idle: ['idle-breath', 'idle-look', 'yawn'],
  wave: ['wave'],
  sleep: ['sleep'],
  snack: ['snack'],
  milktea: ['milktea'],
  listening: ['idle-breath', 'thinking'],
  thinking: ['thinking'],
  talking: ['talking'],
  caring: ['shy'],
}
const currentAnim = ref('idle-breath')

function pickAnimation(next: PetState) {
  const pool = animationPools[next]
  currentAnim.value = pool[Math.floor(Math.random() * pool.length)]
}

function clampPosition(x: number, y: number) {
  const width = pet.value?.offsetWidth ?? 160
  const height = pet.value?.offsetHeight ?? 200
  return { x: Math.max(8, Math.min(x, window.innerWidth - width - 8)), y: Math.max(64, Math.min(y, window.innerHeight - height - 8)) }
}
function savePosition() { localStorage.setItem('zhihui-guide-position-v3', JSON.stringify(position.value)) }

// ---------- 注视感 ----------
function updateLook(clientX: number, clientY: number) {
  const rect = pet.value?.getBoundingClientRect()
  if (!rect) return
  const cx = rect.left + rect.width / 2
  const cy = rect.top + rect.height / 2
  const dx = clientX - cx
  const dy = clientY - cy
  const distance = Math.hypot(dx, dy)
  // 越近倾斜越明显，但幅度封顶，避免在页面上晃得过分
  const strength = Math.min(1, distance / 420)
  leanX.value = Math.max(-1, Math.min(1, dx / 260)) * 4.5 * strength
  leanY.value = Math.max(-1, Math.min(1, dy / 260)) * 3 * strength
  if (state.value !== 'idle') return
  look.value = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up')
}
function onWindowPointerMove(event: PointerEvent) {
  lastPointer = { x: event.clientX, y: event.clientY, t: performance.now() }
  if (pointerId === null && !flying.value) updateLook(event.clientX, event.clientY)
}

// ---------- 拖拽与物理 ----------
function beginDrag(event: PointerEvent) {
  if ((event.target as HTMLElement).closest('.guide-dialog, .energy-card')) return
  pointerId = event.pointerId; dragged = false
  cancelPhysics()
  origin = { x: event.clientX, y: event.clientY, left: position.value.x, top: position.value.y, t: performance.now() }
  velocity = { x: 0, y: 0 }
  window.addEventListener('pointermove', movePet); window.addEventListener('pointerup', endDrag, { once: true })
}
function movePet(event: PointerEvent) {
  if (event.pointerId !== pointerId) return
  const now = performance.now()
  const dx = event.clientX - origin.x; const dy = event.clientY - origin.y
  if (Math.abs(dx) + Math.abs(dy) > 5) dragged = true
  const dt = Math.max(1, now - origin.t) / 1000
  velocity = { x: dx / dt * 0.35, y: dy / dt * 0.35 }
  position.value = clampPosition(origin.left + dx, origin.top + dy)
}
async function endDrag(event: PointerEvent) {
  if (event.pointerId !== pointerId) return
  window.removeEventListener('pointermove', movePet); pointerId = null
  if (!dragged) {
    if (!minimized.value) await toggleDialog()
    return
  }
  savePosition()
  // 轻拖就停住；快速甩出才触发飞行，避免误触
  if (Math.hypot(velocity.x, velocity.y) > 260) startPhysics()
}
function cancelPhysics() {
  if (physicsFrame) cancelAnimationFrame(physicsFrame)
  physicsFrame = 0; flying.value = false; squash.value = 1
}
function startPhysics() {
  const gravity = 1400
  const restitution = 0.78
  const friction = 2.5
  let vx = Math.max(-1800, Math.min(1800, velocity.x))
  let vy = Math.max(-1800, Math.min(1800, velocity.y))
  let last = performance.now()
  flying.value = true
  const step = (now: number) => {
    const dt = Math.min(0.05, (now - last) / 1000)
    last = now
    vy += gravity * dt
    const next = clampPosition(position.value.x + vx * dt, position.value.y + vy * dt)
    const hitX = next.x !== position.value.x + vx * dt
    const hitY = next.y !== position.value.y + vy * dt
    position.value = next
    if (hitX) { vx = -vx * restitution; vy *= 0.94 }
    if (hitY) {
      vy = -vy * restitution; vx *= Math.max(0, 1 - friction * dt)
      // 落地挤压：只在下落触底时压扁一下
      if (velocity.y > 0 || vy < 0) squash.value = 1.08
    }
    squash.value += (1 - squash.value) * Math.min(1, dt * 9)
    const slow = Math.hypot(vx, vy) < 42
    const grounded = position.value.y >= window.innerHeight - (pet.value?.offsetHeight ?? 200) - 8
    if ((slow && grounded) || now - last > 4200) { cancelPhysics(); savePosition(); return }
    physicsFrame = requestAnimationFrame(step)
  }
  physicsFrame = requestAnimationFrame(step)
}

// ---------- 对话 ----------
async function toggleDialog() {
  open.value = !open.value
  cardOpen.value = false
  if (open.value) {
    setState('listening'); await loadHistory(); await nextTick()
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
  input.value = ''; loading.value = true; setState('thinking')
  const answer = messages.value[messages.value.length - 1]
  try {
    const result = await streamChat('wellbeing', text, {}, (token) => { answer.content += token; setState('talking') })
    providerOnline.value = result.providerOnline
    setState(result.escalated ? 'caring' : 'talking')
  } catch (reason) {
    answer.content = reason instanceof Error ? reason.message : '我暂时没有连上服务。你仍然可以去暖心空间记录状态。'
    providerOnline.value = false; setState('caring')
  } finally {
    loading.value = false
    window.setTimeout(() => { if (open.value) setState('listening') }, 1800)
  }
}
function onInputKeydown(event: KeyboardEvent) { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void send() } }
function enterWellbeing() { open.value = false; void router.push('/wellbeing') }
function minimize() { open.value = false; cardOpen.value = false; minimized.value = true; window.clearTimeout(idleTimer) }
function restore() { minimized.value = false; restorePosition(); scheduleIdle() }

// ---------- 能量卡 ----------
async function toggleCard() {
  if (cardOpen.value) { cardOpen.value = false; return }
  open.value = false
  cardOpen.value = true
  if (card.value || cardLoading.value) return
  cardLoading.value = true; cardError.value = ''
  try {
    const userId = identity.value.userId
    const [points, records, shareResult] = await Promise.all([
      requestJson<{ success: boolean; data: { user: { total_points: number; level: string } } }>(`/api/v1/points/user/${userId}`, {}, '积分读取失败'),
      requestJson<{ success: boolean; data: { records: Array<{ source: string; created_at: string }> } }>(`/api/v1/points/user/${userId}/records`, {}, '记录读取失败'),
      // /commands 需要 X-User-Id / X-Session-Id，走统一的 command() 才会带上身份头
      command('wellbeing', 'happy_shares'),
    ])
    const today = new Date().toISOString().slice(0, 10)
    card.value = {
      checkins: records.data.records.filter((item) => item.source === 'checkin' && item.created_at.startsWith(today)).length,
      points: points.data.user.total_points,
      level: points.data.user.level,
      shares: (shareResult.data.shares as unknown[] | undefined)?.length ?? 0,
    }
  } catch (reason) {
    cardError.value = reason instanceof Error ? reason.message : '读取失败'
  } finally {
    cardLoading.value = false
  }
}

function setState(next: PetState) {
  if (state.value === next) return
  state.value = next
  pickAnimation(next)
}

function restorePosition() {
  const stored = localStorage.getItem('zhihui-guide-position-v3') ?? localStorage.getItem('zhihui-guide-position-v2')
  if (stored) { try { const parsed = JSON.parse(stored) as { x: number; y: number }; position.value = clampPosition(parsed.x, parsed.y); return } catch { /* use default */ } }
  position.value = clampPosition(window.innerWidth - 190, window.innerHeight - 250)
}
function scheduleIdle() {
  window.clearTimeout(idleTimer)
  idleTimer = window.setTimeout(() => {
    if (!open.value && !minimized.value && !cardOpen.value && pointerId === null && !flying.value) {
      setState(idleStates[Math.floor(Math.random() * idleStates.length)])
    }
    scheduleIdle()
  }, 8000 + Math.random() * 7000)
}
function handleResize() { position.value = clampPosition(position.value.x, position.value.y) }
function openFromPage() { if (minimized.value) minimized.value = false; if (!open.value) void toggleDialog() }
watch(() => route.fullPath, () => { open.value = false; cardOpen.value = false; scheduleIdle() })
onMounted(() => {
  restorePosition(); scheduleIdle()
  window.addEventListener('resize', handleResize)
  window.addEventListener('zhq-open-guide', openFromPage)
  window.addEventListener('pointermove', onWindowPointerMove, { passive: true })
  document.addEventListener('mouseleave', () => { leanX.value = 0; leanY.value = 0 })
})
onBeforeUnmount(() => {
  window.clearTimeout(idleTimer); cancelPhysics()
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('zhq-open-guide', openFromPage)
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointermove', movePet)
})
</script>

<template>
  <button v-if="minimized" class="guide-restore" type="button" aria-label="显示暖心引导员" @click="restore"><PhSparkle :size="22" weight="fill" /></button>
  <div
    v-else
    ref="pet"
    class="guide-pet"
    :class="[`is-${state}`, { open, flying, 'card-open': cardOpen }]"
    :style="{ transform: `translate3d(${position.x}px, ${position.y}px, 0)` }"
    @pointerdown="beginDrag"
  >
    <!-- 能量卡：本项目自己的数据，替代原桌宠的账户余额卡 -->
    <section v-if="cardOpen" class="energy-card" @pointerdown.stop>
      <header>
        <strong>今日能量</strong>
        <button type="button" aria-label="关闭能量卡" @click="cardOpen = false">×</button>
      </header>
      <p v-if="cardLoading" class="energy-hint">正在读取…</p>
      <p v-else-if="cardError" class="energy-hint error">{{ cardError }}</p>
      <div v-else-if="card" class="energy-grid">
        <div><span>今日打卡</span><b>{{ card.checkins }}</b></div>
        <div><span>当前积分</span><b>{{ card.points }}</b></div>
        <div><span>成长等级</span><b class="text">{{ card.level }}</b></div>
        <div><span>分享墙</span><b>{{ card.shares }}</b></div>
      </div>
      <footer>数据来自本平台，非外部账户</footer>
    </section>

    <section v-if="open" class="guide-dialog" aria-label="与暖心引导员对话" @pointerdown.stop>
      <header><div><span class="guide-online"><i :class="{ offline: providerOnline === false }"></i>小曦瑶 · {{ stateCopy[state] }}</span><small>{{ providerOnline === false ? '当前为本地陪伴模式' : '多轮对话仅在本会话保留' }}</small></div><button type="button" aria-label="最小化引导员" @click="minimize"><PhMinus :size="18" /></button></header>
      <div class="guide-messages" aria-live="polite">
        <div v-for="(item, index) in messages" :key="index" :class="['guide-message', item.role]">
          <span v-if="item.role === 'assistant'">曦</span><p>{{ item.content || '正在组织语言…' }}</p>
        </div>
      </div>
      <form class="guide-composer" @submit.prevent="send">
        <input v-model="input" maxlength="4000" placeholder="想聊什么都可以…" aria-label="发送给暖心引导员" @keydown="onInputKeydown">
        <button type="submit" :disabled="loading || !input.trim()" aria-label="发送消息"><PhPaperPlaneTilt :size="19" weight="fill" /></button>
      </form>
      <footer><button type="button" @click="enterWellbeing">打开暖心空间 <PhArrowUp :size="14" /></button><span>AI 陪伴不能替代专业或紧急支持</span></footer>
    </section>

    <div class="pet-stage" role="button" :aria-label="`暖心引导员小曦瑶，${stateCopy[state]}，可拖动位置或点击对话`">
      <span class="pet-status">{{ stateCopy[state] }}</span>
      <div class="pet-shadow"></div>
      <!-- lean/squash 挂在外层 wrapper：动画 WebP 的 <img> 本身不做任何 CSS 变换，
           避免 Chrome 合成层在播放中反复重采样导致局部闪烁 -->
      <div class="pet-lean" :style="{ transform: leanTransform }">
        <img
          class="pet-sprite"
          :src="`/pet/${currentAnim}.webp`"
          :alt="`小曦瑶 · ${stateCopy[state]}`"
          draggable="false"
        >
      </div>
      <button type="button" class="pet-card-hint" aria-label="查看今日能量" @pointerdown.stop @click.stop="toggleCard">今日能量</button>
    </div>
  </div>
</template>
