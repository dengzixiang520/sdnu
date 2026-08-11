<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { PhBookOpenText, PhChatCircleDots, PhFirstAid, PhFlowerLotus, PhLockKey, PhPaperPlaneTilt, PhWind } from '@phosphor-icons/vue'
import { command } from '../api'
import { useIdentity } from '../identity'
import WellbeingUtilityRail from './WellbeingUtilityRail.vue'

type Weather = 'sunny' | 'cloudy' | 'rainy' | 'stormy'
interface WallMessage { message_id: string; content: string; topic?: string }
const { identity } = useIdentity()
const weather = ref<Weather>('sunny'); const reflection = ref(''); const response = ref(''); const level = ref(''); const loading = ref(false); const error = ref('')
const wall = ref<WallMessage[]>([]); const journal = ref(localStorage.getItem('zhq-private-journal') ?? ''); const journalSaved = ref(false)
const breathing = ref(false); const breathPhase = ref('准备开始'); const breathSeconds = ref(60); let breathTimer: number | undefined
const wallTopic = ref('今日寄语'); const wallContent = ref(''); const wallStatus = ref('')
const weatherOptions: Array<{ id: Weather; mark: string; label: string; copy: string }> = [
  { id: 'sunny', mark: '晴', label: '轻松', copy: '今天还不错' }, { id: 'cloudy', mark: '云', label: '一般', copy: '有点提不起劲' },
  { id: 'rainy', mark: '雨', label: '低落', copy: '需要一点空间' }, { id: 'stormy', mark: '雷', label: '难熬', copy: '希望有人陪我' },
]
async function fetchWall() { try { wall.value = ((await command('wellbeing', 'wall_messages')).data.messages ?? []) as WallMessage[] } catch { wall.value = [] } }
async function checkIn() { loading.value = true; error.value = ''; try { const result = await command('wellbeing', 'mood_checkin', '', { check_in: { weather: weather.value, reflection: reflection.value } }); response.value = result.message; level.value = String(result.data.alert_level ?? '') } catch (reason) { error.value = reason instanceof Error ? reason.message : '记录失败，请稍后再试。' } finally { loading.value = false } }
function saveJournal() { localStorage.setItem('zhq-private-journal', journal.value); journalSaved.value = true; window.setTimeout(() => { journalSaved.value = false }, 1800) }
function openGuide() { window.dispatchEvent(new Event('zhq-open-guide')) }
function startBreathing() {
  if (breathing.value) { stopBreathing(); return }
  breathing.value = true; breathSeconds.value = 60
  const phases = ['吸气 4 秒', '停留 4 秒', '呼气 6 秒']; let index = 0; breathPhase.value = phases[0]
  breathTimer = window.setInterval(() => { breathSeconds.value -= 1; if (breathSeconds.value <= 0) { stopBreathing(); breathPhase.value = '完成了，慢慢回到当下'; return }; if (breathSeconds.value % 5 === 0) { index = (index + 1) % phases.length; breathPhase.value = phases[index] } }, 1000)
}
function stopBreathing() { window.clearInterval(breathTimer); breathing.value = false; if (breathSeconds.value > 0) breathPhase.value = '随时可以重新开始' }
async function publishWallMessage() { if (!wallContent.value.trim()) { wallStatus.value = '请先填写寄语内容。'; return } loading.value = true; try { await command('wellbeing', 'publish_wall_message', '', { message: { topic: wallTopic.value, content: wallContent.value } }); wallContent.value = ''; wallStatus.value = '寄语已发布。'; await fetchWall() } catch (reason) { wallStatus.value = reason instanceof Error ? reason.message : '发布失败。' } finally { loading.value = false } }
onMounted(fetchWall); onBeforeUnmount(() => window.clearInterval(breathTimer))
</script>

<template>
  <section class="wellbeing-page">
    <div class="wellbeing-main">
      <header class="wellbeing-hero">
        <div><span>给自己留十分钟</span><h1>今天的你，<br><em>不必急着变好。</em></h1><p>先辨认感受，再决定是聊一聊、写下来，还是安静呼吸一会儿。</p></div>
        <button type="button" class="talk-callout" @click="openGuide"><PhChatCircleDots :size="27" weight="duotone" /><span><strong>和小齐聊聊</strong><small>右下角的引导员支持多轮对话</small></span><PhPaperPlaneTilt :size="18" /></button>
      </header>

      <article class="mood-checkin">
        <div class="checkin-title"><div><h2>此刻更像哪一种天气？</h2><p>这是日常状态记录，不是心理诊断。</p></div><span>今日打卡</span></div>
        <div class="weather-picker">
          <button v-for="item in weatherOptions" :key="item.id" :class="{ chosen: weather === item.id }" type="button" @click="weather = item.id"><b>{{ item.mark }}</b><span><strong>{{ item.label }}</strong><small>{{ item.copy }}</small></span></button>
        </div>
        <label class="reflection-field"><span>想补充一点吗？ <small>可选，仅本人可见</small></span><textarea v-model="reflection" maxlength="2000" placeholder="例如：今天汇报前有点紧张，但结束后松了一口气。"></textarea></label>
        <div class="checkin-action"><p v-if="response" :class="['support-result', level]">{{ response }}</p><p v-else>记录会进入你的短期记忆，7 天后按策略过期。</p><button type="button" :disabled="loading" @click="checkIn">{{ loading ? '正在保存' : '保存今天的状态' }}</button></div>
        <p v-if="error" class="inline-error">{{ error }}</p>
      </article>

      <div class="wellbeing-tools">
        <article class="breathing-card">
          <div class="breath-orbit" :class="{ active: breathing }"><span>{{ breathSeconds }}</span></div>
          <div><PhWind :size="24" weight="duotone" /><h2>一分钟呼吸</h2><p>{{ breathPhase }}</p><button type="button" @click="startBreathing">{{ breathing ? '结束练习' : '跟着节奏开始' }}</button></div>
        </article>
        <article class="journal-card">
          <header><div><PhBookOpenText :size="23" weight="duotone" /><h2>只写给自己</h2></div><span><PhLockKey :size="14" /> 仅存本机</span></header>
          <textarea v-model="journal" maxlength="4000" placeholder="不用完整，也不用正确。写下脑海里最响的那句话。"></textarea>
          <button type="button" @click="saveJournal">{{ journalSaved ? '已经保存' : '保存私人片段' }}</button>
        </article>
      </div>

      <section class="support-entries">
        <h2>需要更多支持时</h2>
        <div><article><PhFlowerLotus :size="24" weight="duotone" /><h3>校园心理资源</h3><p>展示校内心理中心、预约方式与值班安排。当前尚未接入学校预约系统。</p><button type="button" disabled>等待官方接口</button></article><article><PhFirstAid :size="24" weight="duotone" /><h3>紧急支持说明</h3><p>当自己或他人可能立即受伤时，请优先联系身边可信任的人和当地紧急服务。</p><a href="tel:120">拨打 120</a></article></div>
      </section>

      <section class="counselor-wall">
        <header><div><h2>辅导员寄语墙</h2><p>发布者身份在学生端匿名展示，内容先经过人工确认。</p></div></header>
        <div v-if="identity.role !== 'student'" class="wall-publisher"><input v-model="wallTopic" maxlength="80" aria-label="寄语主题"><textarea v-model="wallContent" maxlength="1000" placeholder="写下一段简短、明确的支持。"></textarea><div><span>{{ wallStatus }}</span><button type="button" :disabled="loading" @click="publishWallMessage">发布寄语</button></div></div>
        <div class="wall-notes"><article v-for="note in wall" :key="note.message_id"><small>{{ note.topic || '今日寄语' }}</small><p>{{ note.content }}</p></article><article v-if="!wall.length"><small>等待一封寄语</small><p>辅导员还没有发布新内容。</p></article></div>
      </section>
    </div>
    <WellbeingUtilityRail />
  </section>
</template>
