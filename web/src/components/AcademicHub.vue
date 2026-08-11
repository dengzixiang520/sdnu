<script setup lang="ts">
import { PhArrowRight, PhBooks, PhCalendarCheck, PhChartBar, PhMicrophoneStage, PhNotebook } from '@phosphor-icons/vue'

const features = [
  { to: '/academic/interview', icon: PhMicrophoneStage, title: 'AI 模拟复试', copy: '逐题追问、语音播报与五维复盘，像真正坐进候考室。', tone: 'interview', action: '开始一场模拟' },
  { to: '/academic/notes', icon: PhNotebook, title: '组会与课堂笔记', copy: '把转录文本整理成摘要、知识树和带时间点的待办。', tone: 'notes', action: '整理一份材料' },
  { to: '/academic/plan', icon: PhCalendarCheck, title: '学习计划', copy: '从目标与可用时间出发，安排一周的可执行学习节奏。', tone: 'plan', action: '安排本周' },
]
</script>

<template>
  <section class="academic-hub">
    <header class="academic-hub-head"><div><h1>今天想把哪件事，<br><em>向前推进一点？</em></h1><p>先选择任务，再进入专注页面。这里不把所有工具挤在一张工作台上。</p></div><div class="study-snapshot"><PhBooks :size="34" weight="duotone" /><strong>学习成长中心</strong><span>模拟 · 整理 · 计划</span></div></header>
    <div class="academic-feature-list">
      <RouterLink v-for="feature in features" :key="feature.to" :to="feature.to" :class="['academic-feature', feature.tone]">
        <span class="feature-index">0{{ features.indexOf(feature) + 1 }}</span><component :is="feature.icon" :size="42" weight="duotone" /><div><h2>{{ feature.title }}</h2><p>{{ feature.copy }}</p><b>{{ feature.action }} <PhArrowRight :size="18" /></b></div>
      </RouterLink>
    </div>
    <section class="growth-evidence"><div><PhChartBar :size="26" weight="duotone" /><h2>成长记录如何使用</h2></div><p>模拟评估只依据本次可观察回答生成训练建议，并将摘要保留在短期记忆中。它不判断人格，也不作录取预测。</p></section>
  </section>
</template>
