<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { command } from '../api'

const router = useRouter()
const greeting = ref('需要聊聊、整理日程或准备复试，都可以从这里开始。')
const loading = ref(false)
const error = ref('')
const capabilities = [
  { path: '/wellbeing', no: '01', title: '记录心情', detail: '心情打卡、环境音与辅导员寄语', status: '可用' },
  { path: '/dormitory', no: '02', title: '协调宿舍', detail: '课表导入、AA 分摊、值日冲突', status: '可用' },
  { path: '/academic', no: '03', title: '准备复试', detail: '模拟提问、五维评估、笔记整理', status: '可用' },
  { path: '/innovation', no: '04', title: '推进竞赛', detail: '赛事提交、组队匹配、申报大纲', status: '可用' },
]

async function wakeGuide() {
  loading.value = true
  error.value = ''
  try {
    greeting.value = (await command('wellbeing', 'greeting')).message
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法连接后端服务'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="dashboard-page">
    <header class="dashboard-heading entrance entrance-top">
      <div><p class="section-kicker">2026 / SDNU</p><h1>今天要处理什么？</h1><p>选择一个具体任务，系统会调用对应 Skill。没有虚构数据，也不会自动执行高风险操作。</p></div>
      <div class="date-block"><strong>30</strong><span>JUL<br />THU</span></div>
    </header>

    <section class="dashboard-grid">
      <article class="agent-console entrance entrance-left">
        <div class="console-head"><span>SUPER AGENT</span><i></i></div>
        <div class="agent-copy"><small>当前响应</small><h2>{{ greeting }}</h2><p v-if="error" class="inline-error">{{ error }}</p></div>
        <div class="console-actions"><button class="primary-action" type="button" :disabled="loading" @click="wakeGuide">{{ loading ? '连接中' : '唤醒引导员' }}</button><button class="text-action" type="button" @click="router.push('/wellbeing')">进入暖心空间</button></div>
      </article>

      <div class="capability-list entrance entrance-center">
        <button v-for="item in capabilities" :key="item.path" class="capability-row" type="button" @click="router.push(item.path)">
          <span>{{ item.no }}</span><div><strong>{{ item.title }}</strong><small>{{ item.detail }}</small></div><em>{{ item.status }}</em><b>↗</b>
        </button>
      </div>

      <aside class="system-panel entrance entrance-right">
        <div><span class="panel-label">系统状态</span><strong>6</strong><small>业务 Skill 已注册</small></div>
        <dl><div><dt>记忆后端</dt><dd>SQLite / 可切换</dd></div><div><dt>安全网关</dt><dd>常驻</dd></div><div><dt>生产认证</dt><dd class="pending">待接 SSO</dd></div></dl>
        <button class="system-link" type="button" @click="router.push('/documents')">打开文档工坊 <span>05</span></button>
      </aside>
    </section>
  </section>
</template>
