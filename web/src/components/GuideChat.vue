<script setup lang="ts">
/**
 * 暖心空间的独立聊天面板。
 *
 * 和右下角桌宠的区别：桌宠是全局浮层，这里属于「记录自己」这一页的正文，
 * 进页面就由小齐先说第一句（后端 compose_opening，不走大模型，零等待）。
 * 后续轮次走 /api/v1/chat/stream，人设来自 prompts/guide_persona.md。
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { PhChatCircleDots, PhPaperPlaneTilt, PhShieldWarning } from '@phosphor-icons/vue'
import { chatHistory, command, streamChat, type ChatMessage } from '../api'

interface Bubble {
  id: number
  role: 'user' | 'assistant'
  content: string
  /** 安全提示气泡单独上色，不和普通安慰混在一起 */
  crisis?: boolean
}

const bubbles = ref<Bubble[]>([])
const chips = ref<string[]>([])
const draft = ref('')
const busy = ref(false)
const notice = ref('')
const level = ref('green')
const scroller = ref<HTMLElement | null>(null)
let sequence = 0

const tone = computed(() => {
  if (level.value === 'red') return 'urgent'
  if (level.value === 'orange' || level.value === 'yellow') return 'watch'
  return 'normal'
})

function push(role: Bubble['role'], content: string, crisis = false): Bubble {
  sequence += 1
  const bubble: Bubble = { id: sequence, role, content, crisis }
  bubbles.value = [...bubbles.value, bubble]
  return bubble
}

async function scrollToEnd() {
  await nextTick()
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
}

/** 进页面：有历史就接着聊，没历史就让小齐先说一句。 */
async function bootstrap() {
  try {
    const history = (await chatHistory('wellbeing')) as ChatMessage[]
    if (history.length) {
      bubbles.value = history.map((item) => {
        sequence += 1
        return { id: sequence, role: item.role === 'assistant' ? 'assistant' : 'user', content: item.content }
      })
      await scrollToEnd()
      return
    }
  } catch {
    // 历史读不到不影响开场白
  }
  try {
    const result = await command('wellbeing', 'guide_opening')
    const data = result.data as { opening?: string; chips?: string[]; alert_level?: string }
    push('assistant', String(data.opening || result.message || '我在。'))
    chips.value = Array.isArray(data.chips) ? data.chips.slice(0, 3) : []
    level.value = String(data.alert_level || 'green')
    await scrollToEnd()
  } catch (reason) {
    notice.value = reason instanceof Error ? reason.message : '小齐暂时没连上，稍后再试'
  }
}

async function send(text?: string) {
  const message = (text ?? draft.value).trim()
  if (!message || busy.value) return
  draft.value = ''
  chips.value = []
  notice.value = ''
  push('user', message)
  const reply = push('assistant', '')
  busy.value = true
  await scrollToEnd()
  try {
    const result = await streamChat('wellbeing', message, {}, (token) => {
      reply.content += token
      void scrollToEnd()
    })
    if (result.escalated) {
      reply.crisis = true
      level.value = 'red'
    }
    if (!result.providerOnline) notice.value = '当前是大模型离线兜底回复，接入模型后会更自然'
  } catch (reason) {
    reply.content = reply.content || '刚才没连上，你再说一次好吗？'
    notice.value = reason instanceof Error ? reason.message : '发送失败'
  } finally {
    busy.value = false
    await scrollToEnd()
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
  }
}

onMounted(() => { void bootstrap() })
</script>

<template>
  <article class="gcx-card" :class="`is-${tone}`">
    <header class="gcx-head">
      <div class="gcx-ident">
        <span class="gcx-avatar" aria-hidden="true">齐</span>
        <div>
          <h2>和小齐聊聊</h2>
          <p>{{ busy ? '正在想怎么回你' : '人设在 prompts/guide_persona.md，改完即时生效' }}</p>
        </div>
      </div>
      <span v-if="tone !== 'normal'" class="gcx-tone">
        <PhShieldWarning :size="14" weight="duotone" />
        {{ tone === 'urgent' ? '安全优先' : '语气已放缓' }}
      </span>
    </header>

    <div ref="scroller" class="gcx-thread" role="log" aria-live="polite">
      <div
        v-for="bubble in bubbles"
        :key="bubble.id"
        class="gcx-row"
        :class="[`is-${bubble.role}`, { 'is-crisis': bubble.crisis }]"
      >
        <p class="gcx-bubble">{{ bubble.content || '…' }}</p>
      </div>
      <p v-if="!bubbles.length" class="gcx-idle">
        <PhChatCircleDots :size="16" weight="duotone" /> 正在准备第一句话…
      </p>
    </div>

    <div v-if="chips.length" class="gcx-chips">
      <button v-for="chip in chips" :key="chip" type="button" :disabled="busy" @click="send(chip)">{{ chip }}</button>
    </div>

    <div class="gcx-compose">
      <input
        v-model="draft"
        maxlength="500"
        :disabled="busy"
        placeholder="想说什么就说什么，不用组织语言"
        @keydown="onKeydown"
      >
      <button type="button" :disabled="busy || !draft.trim()" @click="send()">
        <PhPaperPlaneTilt :size="16" weight="duotone" /> 发送
      </button>
    </div>
    <p v-if="notice" class="gcx-notice">{{ notice }}</p>
  </article>
</template>

<style scoped>
.gcx-card {
  margin-top: 20px;
  padding: 20px 22px;
  background: var(--paper);
  border-radius: 20px;
  box-shadow: var(--shadow);
  border-left: 4px solid var(--green);
}
.gcx-card.is-watch { border-left-color: var(--gold); }
.gcx-card.is-urgent { border-left-color: #b3261e; }

.gcx-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
.gcx-ident { display: flex; align-items: center; gap: .6rem; min-width: 0; }
.gcx-avatar {
  flex: none; width: 34px; height: 34px;
  display: grid; place-items: center;
  color: #fff; background: var(--green); border-radius: 50%;
  font: 400 1rem "LXGW WenKai", cursive;
}
.gcx-card.is-watch .gcx-avatar { background: #b4842c; }
.gcx-card.is-urgent .gcx-avatar { background: #b3261e; }
.gcx-ident h2 { margin: 0; font: 400 1.24rem "LXGW WenKai", cursive; }
.gcx-ident p { margin: .1rem 0 0; color: var(--muted); font-size: .72rem; }
.gcx-tone {
  flex: none; display: inline-flex; align-items: center; gap: .25rem;
  padding: .22rem .5rem; color: #7c5a1e; background: #fff0c6;
  border-radius: 999px; font-size: .7rem; font-weight: 700;
}
.gcx-card.is-urgent .gcx-tone { color: #9e3030; background: #fde8e5; }

.gcx-thread {
  margin-top: .8rem;
  max-height: 320px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: .5rem;
  padding-right: 4px;
}
.gcx-row { display: flex; }
.gcx-row.is-user { justify-content: flex-end; }
.gcx-bubble {
  margin: 0;
  max-width: 86%;
  padding: .55rem .75rem;
  border-radius: 13px;
  font-size: .86rem;
  line-height: 1.72;
  white-space: pre-wrap;
  word-break: break-word;
}
.gcx-row.is-assistant .gcx-bubble { color: var(--ink); background: #f4f7f4; border-bottom-left-radius: 5px; }
.gcx-row.is-user .gcx-bubble { color: #fff; background: var(--navy); border-bottom-right-radius: 5px; }
.gcx-row.is-crisis .gcx-bubble { color: #7a2018; background: #fdeceb; box-shadow: inset 0 0 0 1px rgba(179, 38, 30, .22); }

.gcx-idle {
  margin: 0; display: flex; align-items: center; gap: .35rem;
  color: var(--muted); font-size: .8rem;
}

.gcx-chips { margin-top: .6rem; display: flex; flex-wrap: wrap; gap: .4rem; }
.gcx-chips button {
  padding: .32rem .65rem;
  color: var(--green); background: var(--green-soft);
  border: 1px solid transparent; border-radius: 999px;
  font-size: .78rem; font-weight: 650; cursor: pointer;
}
.gcx-chips button:hover:not(:disabled) { border-color: var(--green); }
.gcx-chips button:disabled { opacity: .5; cursor: default; }

.gcx-compose { margin-top: .6rem; display: flex; gap: .5rem; }
.gcx-compose input {
  flex: 1; min-width: 0;
  padding: .55rem .7rem;
  color: var(--ink); background: #fff;
  border: 1px solid rgba(23, 63, 67, .14); border-radius: 11px;
  font-size: .84rem;
}
.gcx-compose input:focus { outline: none; border-color: var(--green); }
.gcx-compose button {
  flex: none; display: inline-flex; align-items: center; gap: .3rem;
  padding: .55rem .85rem; color: #fff; background: var(--navy);
  border: 0; border-radius: 11px; font-size: .82rem; font-weight: 700; cursor: pointer;
}
.gcx-compose button:disabled { opacity: .45; cursor: default; }

.gcx-notice { margin: .5rem 0 0; color: var(--muted); font-size: .74rem; line-height: 1.6; }

@media (max-width: 720px) {
  .gcx-card { padding: 16px; }
  .gcx-thread { max-height: 260px; }
  .gcx-bubble { max-width: 92%; }
}
</style>
