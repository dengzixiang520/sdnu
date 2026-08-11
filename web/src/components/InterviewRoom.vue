<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { PhArrowLeft, PhMicrophone, PhMicrophoneSlash, PhPaperPlaneRight, PhPause, PhPlay, PhSpeakerHigh, PhStop, PhTimer } from '@phosphor-icons/vue'
import { command, streamChat, type ChatMessage } from '../api'

const major = ref('人工智能'); const duration = ref(15); const focus = ref('均衡'); const strictness = ref('常规')
const started = ref(false); const loading = ref(false); const answer = ref(''); const messages = ref<ChatMessage[]>([]); const error = ref('')
const voiceEnabled = ref(true); const listening = ref(false); const elapsed = ref(0); const finished = ref(false)
const evaluation = ref<Record<string, { score: number; recommendation: string }>>({}); let timer: number | undefined; let recognition: any
const elapsedText = computed(() => `${String(Math.floor(elapsed.value / 60)).padStart(2, '0')}:${String(elapsed.value % 60).padStart(2, '0')}`)
const labels: Record<string, string> = { expression: '表达', professional_knowledge: '专业', english: '英语', pressure_resilience: '抗压', emotional_stability: '稳定' }

async function start() {
  if (!major.value.trim()) { error.value = '请先填写目标专业。'; return }
  started.value = true; finished.value = false; messages.value = []; elapsed.value = 0; timer = window.setInterval(() => { elapsed.value += 1 }, 1000)
  await askAi(`请开始一场${duration.value}分钟的模拟复试。先用一句话说明规则，然后提出第一个问题。`)
}
async function submitAnswer() {
  const text = answer.value.trim(); if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text }); answer.value = ''
  await askAi('请基于我刚才的回答自然追问下一题。不要点评，不要一次提出多个问题。')
}
async function askAi(message: string) {
  loading.value = true; error.value = ''; const assistant: ChatMessage = { role: 'assistant', content: '' }; messages.value.push(assistant)
  try {
    await streamChat('academic_interview', message, { major: major.value, focus: `${focus.value}，严格度${strictness.value}` }, (token) => { assistant.content += token })
    if (voiceEnabled.value) speak(assistant.content)
  } catch (reason) { assistant.content = '提问服务暂时不可用，请检查后端或 AI 配置。'; error.value = reason instanceof Error ? reason.message : '提问失败' }
  finally { loading.value = false }
}
function speak(text: string) {
  if (!('speechSynthesis' in window)) return
  window.speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(text); utterance.lang = /[A-Za-z]{12}/.test(text) ? 'en-US' : 'zh-CN'; utterance.rate = .96; window.speechSynthesis.speak(utterance)
}
function toggleVoice() { voiceEnabled.value = !voiceEnabled.value; if (!voiceEnabled.value) window.speechSynthesis?.cancel() }
function toggleRecognition() {
  if (listening.value) { recognition?.stop(); listening.value = false; return }
  const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!Recognition) { error.value = '当前浏览器不支持语音转文字，请使用 Chrome 或直接输入。'; return }
  recognition = new Recognition(); recognition.lang = 'zh-CN'; recognition.continuous = true; recognition.interimResults = true
  recognition.onresult = (event: any) => { answer.value = Array.from(event.results).map((result: any) => result[0].transcript).join('') }
  recognition.onerror = () => { listening.value = false; error.value = '麦克风未授权或识别失败，你仍可使用键盘回答。' }
  recognition.onend = () => { listening.value = false }; recognition.start(); listening.value = true
}
async function finish() {
  window.clearInterval(timer); window.speechSynthesis?.cancel(); recognition?.stop(); listening.value = false; loading.value = true
  const transcript = messages.value.filter((item) => item.role === 'user').map((item) => item.content).join('\n')
  try { evaluation.value = (await command('academic', 'evaluate_interview', transcript || '本次模拟未提交有效回答。')).data as typeof evaluation.value; finished.value = true }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '评估失败' }
  finally { loading.value = false }
}
function reset() { started.value = false; finished.value = false; messages.value = []; evaluation.value = {}; window.clearInterval(timer); window.speechSynthesis?.cancel() }
onBeforeUnmount(() => { window.clearInterval(timer); window.speechSynthesis?.cancel(); recognition?.stop() })
</script>

<template>
  <section class="interview-room">
    <header class="interview-top"><RouterLink to="/academic"><PhArrowLeft :size="18" /> 返回功能选择</RouterLink><div v-if="started" class="interview-clock"><PhTimer :size="18" /><span>{{ elapsedText }}</span><b>/ {{ duration }} 分钟</b></div><button v-if="started" type="button" class="voice-toggle" @click="toggleVoice"><component :is="voiceEnabled ? PhSpeakerHigh : PhPause" :size="18" /> {{ voiceEnabled ? '语音提问已开' : '语音提问已关' }}</button></header>
    <div v-if="!started" class="interview-lobby"><div><span class="lobby-mark">复</span><h1>把紧张留在这里，<br><em>把经验带走。</em></h1><p>AI 导师会逐题提问并根据回答追问。语音由浏览器本地朗读，麦克风只在你点击后请求权限。</p></div><form @submit.prevent="start"><label>目标专业<input v-model="major" required></label><div><label>模拟时长<select v-model.number="duration"><option :value="5">5 分钟热身</option><option :value="15">15 分钟标准</option><option :value="30">30 分钟完整</option></select></label><label>提问侧重<select v-model="focus"><option>均衡</option><option>英语口语</option><option>专业深度</option></select></label></div><label>导师风格<select v-model="strictness"><option>鼓励</option><option>常规</option><option>严格追问</option></select></label><button type="submit">进入模拟面试</button></form></div>
    <div v-else-if="!finished" class="interview-stage">
      <div class="interviewer-panel"><div class="interviewer-avatar"><span>AI</span><i :class="{ speaking: loading }"></i></div><strong>复试导师 Agent</strong><small>{{ major }} · {{ focus }} · {{ strictness }}</small><div class="voice-wave" :class="{ active: loading }"><i v-for="n in 12" :key="n"></i></div></div>
      <main class="interview-dialogue"><div class="interview-transcript"><article v-for="(item, index) in messages" :key="index" :class="item.role"><small>{{ item.role === 'assistant' ? '导师提问' : '我的回答' }}</small><p>{{ item.content || '正在生成下一道问题…' }}</p><button v-if="item.role === 'assistant' && item.content" type="button" aria-label="朗读本题" @click="speak(item.content)"><PhPlay :size="15" weight="fill" /></button></article></div><form class="answer-console" @submit.prevent="submitAnswer"><textarea v-model="answer" :disabled="loading" placeholder="输入回答，或点击麦克风开始口述…"></textarea><div><button type="button" :class="{ recording: listening }" @click="toggleRecognition"><component :is="listening ? PhMicrophoneSlash : PhMicrophone" :size="19" /> {{ listening ? '停止口述' : '语音回答' }}</button><button type="submit" :disabled="loading || !answer.trim()">提交回答 <PhPaperPlaneRight :size="18" /></button></div></form></main>
      <aside class="interview-side"><h2>面试提示</h2><ul><li>先给结论，再说明依据。</li><li>不会的问题可以澄清边界。</li><li>避免背稿式长段输出。</li></ul><button type="button" :disabled="loading" @click="finish"><PhStop :size="17" weight="fill" /> 结束并生成复盘</button></aside>
    </div>
    <div v-else class="interview-report"><header><div><h1>这次模拟已经结束</h1><p>评分来自本次回答中的可观察文本信号，仅用于训练。</p></div><button type="button" @click="reset">再练一次</button></header><div class="report-scores"><article v-for="(value, key) in evaluation" :key="key"><span>{{ labels[key] }}</span><strong>{{ value.score }}</strong><p>{{ value.recommendation }}</p></article></div></div>
    <p v-if="error" class="inline-error page-error">{{ error }}</p>
  </section>
</template>
