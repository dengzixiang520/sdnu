<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import GuidePet from './components/GuidePet.vue'
import { useIdentity, type WebRole } from './identity'

const route = useRoute()
const { identity, update } = useIdentity()
const backendOnline = ref<boolean | null>(null)

async function checkBackend() {
  try {
    const response = await fetch('/healthz')
    backendOnline.value = response.ok
  } catch {
    backendOnline.value = false
  }
}

function changeRole(event: Event) {
  update({ role: (event.target as HTMLSelectElement).value as WebRole })
}

onMounted(checkBackend)
</script>

<template>
  <!--
  THESIS: 把校园服务做成一张可展开的学习桌，而不是同款 AI 卡片陈列。
  OWN-WORLD: 墨蓝、纸白、暖绿与朱红；左侧书脊导航、模块专属工作台、右侧工具抽屉。
  STORY: 学生先看清当前任务，再进入专注流程，Agent 在需要时出现并保持可控。
  FIRST VIEWPORT: 左侧平台导航、中间模块主任务、右侧上下文工具；全身引导员停在内容边缘。
  FORM: 校园图书馆阅读桌，grounded candidate 3，seed 9aa25cc0。
  FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
  -->
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <div class="app-shell">
    <AppSidebar />
    <div class="workspace">
      <header class="topbar">
        <div class="route-context">
          <span>{{ route.meta.section ?? '工作台' }}</span><b>/</b>
          <strong>{{ route.meta.title ?? '今日概览' }}</strong>
        </div>
        <div class="topbar-actions">
          <button class="service-state" type="button" title="重新检测后端服务" @click="checkBackend">
            <i :class="{ online: backendOnline === true, offline: backendOnline === false }"></i>
            {{ backendOnline === null ? '检测服务' : backendOnline ? '服务正常' : '后端离线' }}
          </button>
          <label class="role-switch" title="仅用于本地演示，生产环境由学校统一身份认证提供">
            <span>演示身份</span>
            <select :value="identity.role" @change="changeRole">
              <option value="student">学生</option>
              <option value="counselor">辅导员</option>
              <option value="administrator">管理员</option>
            </select>
          </label>
          <div class="user-chip"><span>{{ identity.displayName.slice(0, 1) }}</span><div><strong>{{ identity.displayName }}</strong><small>{{ identity.userId }}</small></div></div>
        </div>
      </header>

      <main id="main-content" class="page-viewport">
        <RouterView v-slot="{ Component, route: currentRoute }">
          <Transition name="page" mode="out-in">
            <component :is="Component" :key="currentRoute.path" />
          </Transition>
        </RouterView>
      </main>

      <footer class="legal-footer"><span>智汇齐鲁 · 全域同频</span><span>隐私优先 · 最小必要授权 · 演示环境</span></footer>
    </div>
    <GuidePet />
  </div>
</template>
