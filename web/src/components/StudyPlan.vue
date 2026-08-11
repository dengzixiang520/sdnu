<script setup lang="ts">
import { ref } from 'vue'
import { PhArrowLeft, PhCalendarCheck, PhCheckCircle } from '@phosphor-icons/vue'

const goal = ref('完成复试专业课第一轮复习'); const hours = ref(12); const generated = ref(false)
const days = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const tasks = ref<string[]>([])
function generate() { const perDay = Math.max(1, Math.round(hours.value / 6 * 10) / 10); tasks.value = days.map((day, index) => index === 6 ? `${day}：复盘本周，整理错题和下周入口` : `${day}：${perDay} 小时专注学习，推进“${goal.value}”`); generated.value = true; localStorage.setItem('zhq-study-plan', JSON.stringify(tasks.value)) }
</script>

<template><section class="study-plan-page"><RouterLink to="/academic"><PhArrowLeft :size="18" /> 返回功能选择</RouterLink><header><PhCalendarCheck :size="38" weight="duotone" /><div><h1>把大目标拆成一周。</h1><p>先安排可做到的节奏，再根据真实完成情况调整。</p></div></header><div class="plan-builder"><form @submit.prevent="generate"><label>本周目标<textarea v-model="goal" maxlength="200"></textarea></label><label>可投入时间 <input v-model.number="hours" type="range" min="3" max="40"><strong>{{ hours }} 小时</strong></label><button type="submit">生成一周计划</button></form><div class="week-sheet"><article v-for="(item, index) in tasks" :key="item"><span>{{ days[index] }}</span><p>{{ item.split('：')[1] }}</p><button type="button" aria-label="标记完成"><PhCheckCircle :size="21" /></button></article><p v-if="!generated" class="plan-empty">填写目标和时间后，这里会生成一份可以继续编辑的周计划。</p></div></div></section></template>
