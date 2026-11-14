<script setup lang="ts">
/**
 * 一条输出的「有用 / 没用」评价。
 *
 * 赛题把「用户评分」列进了评审维度，所以每个能给分的模块底下都要有这个东西。
 * 刻意做得低调：不抢主任务，只在结果卡底部占一行；好评一次点完，
 * 差评才展开一句话输入框，不让想吐槽的人打字打到放弃。
 */
import { ref } from 'vue'
import { PhThumbsUp, PhThumbsDown, PhCheckCircle } from '@phosphor-icons/vue'
import { submitFeedback } from '../api'

const props = defineProps<{
  target: string
  hint?: string
}>()

const state = ref<'idle' | 'compose' | 'done'>('idle')
const note = ref('')
const busy = ref(false)
const notice = ref('')
const voted = ref<boolean | null>(null)

async function send(helpful: boolean, withNote = '') {
  if (busy.value) return
  busy.value = true
  notice.value = ''
  try {
    const result = await submitFeedback(props.target, helpful, withNote)
    notice.value = result.message
    voted.value = helpful
    state.value = 'done'
  } catch (error) {
    notice.value = error instanceof Error ? error.message : '评价没发出去'
  } finally {
    busy.value = false
  }
}

function voteUp() {
  void send(true)
}

function voteDown() {
  state.value = 'compose'
}

function sendNote() {
  void send(false, note.value)
}
</script>

<template>
  <div class="answer-feedback">
    <template v-if="state === 'idle'">
      <span class="af-label">{{ hint || '这条回答有用吗' }}</span>
      <button type="button" class="af-btn" :disabled="busy" @click="voteUp">
        <PhThumbsUp :size="14" /> 有用
      </button>
      <button type="button" class="af-btn" :disabled="busy" @click="voteDown">
        <PhThumbsDown :size="14" /> 没用
      </button>
    </template>

    <template v-else-if="state === 'compose'">
      <label class="af-compose">
        <span>哪里不够？一句话就行，也可以直接提交</span>
        <input
          v-model="note"
          type="text"
          maxlength="200"
          placeholder="比如：没告诉我下一步该做什么"
          @keydown.enter.prevent="sendNote"
        >
      </label>
      <button type="button" class="af-btn is-primary" :disabled="busy" @click="sendNote">
        {{ busy ? '提交中…' : '提交' }}
      </button>
    </template>

    <p v-else class="af-done">
      <PhCheckCircle :size="14" :weight="voted ? 'fill' : 'regular'" />
      {{ notice }}
    </p>
  </div>
</template>

<style scoped>
.answer-feedback {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #e2e6dc;
}

.af-label {
  font-size: .78rem;
  color: #667572;
}

.af-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid #d8ded4;
  border-radius: 999px;
  background: #fffef8;
  color: #172b2a;
  font: inherit;
  font-size: .78rem;
  cursor: pointer;
  transition: border-color .16s ease, background .16s ease;
}

.af-btn:hover:not(:disabled) {
  border-color: #397f72;
  background: #f5f4eb;
}

.af-btn:disabled {
  opacity: .55;
  cursor: progress;
}

.af-btn.is-primary {
  border-color: #397f72;
  background: #397f72;
  color: #fffef8;
}

.af-compose {
  display: flex;
  flex: 1 1 240px;
  flex-direction: column;
  gap: 4px;
  font-size: .76rem;
  color: #667572;
}

.af-compose input {
  padding: 7px 10px;
  border: 1px solid #d8ded4;
  border-radius: 9px;
  background: #fffef8;
  color: #172b2a;
  font: inherit;
  font-size: .82rem;
}

.af-compose input:focus-visible {
  outline: 2px solid #397f72;
  outline-offset: 1px;
}

.af-done {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 0;
  font-size: .78rem;
  color: #397f72;
}
</style>
