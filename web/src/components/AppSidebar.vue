<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  PhBookOpenText, PhCalendarDots, PhFileText, PhHeart, PhHouse,
  PhList, PhRocketLaunch, PhTrophy, PhX,
} from '@phosphor-icons/vue'

const route = useRoute()
const expanded = ref(false)
const mobileOpen = ref(false)
const links = [
  { path: '/', icon: PhHouse, label: '今日概览', hint: 'Campus desk' },
  { path: '/wellbeing', icon: PhHeart, label: '暖心空间', hint: 'Care & calm' },
  { path: '/dormitory', icon: PhCalendarDots, label: '宿舍协同', hint: 'Life together' },
  { path: '/academic', icon: PhBookOpenText, label: '学习成长', hint: 'Study studio' },
  { path: '/innovation', icon: PhRocketLaunch, label: '双创孵化', hint: 'Build & compete' },
  { path: '/documents', icon: PhFileText, label: '文档工坊', hint: 'Format lab' },
  { path: '/points', icon: PhTrophy, label: '积分中心', hint: 'Points & Badges' },
]

function active(path: string) {
  return path === '/' ? route.path === '/' : route.path.startsWith(path)
}
</script>

<template>
  <button class="mobile-menu" type="button" aria-label="打开导航" @click="mobileOpen = true"><PhList :size="22" /></button>
  <aside class="sidebar" :class="{ expanded, 'mobile-open': mobileOpen }" @mouseenter="expanded = true" @mouseleave="expanded = false">
    <div class="sidebar-brand">
      <span class="brand-seal">SDNU</span>
      <div class="brand-copy"><strong>山东师范大学</strong><small>全域同频</small></div>
      <button class="mobile-close" type="button" aria-label="关闭导航" @click="mobileOpen = false"><PhX :size="20" /></button>
    </div>
    <nav class="sidebar-nav" aria-label="主导航">
      <RouterLink v-for="link in links" :key="link.path" :to="link.path" class="side-link" :class="{ active: active(link.path) }" @click="mobileOpen = false">
        <span class="side-icon" aria-hidden="true"><component :is="link.icon" :size="22" weight="duotone" /></span>
        <span class="side-label"><strong>{{ link.label }}</strong><small>{{ link.hint }}</small></span>
      </RouterLink>
    </nav>
    <div class="sidebar-foot"><span class="profile-mark">同</span><div><strong>Agent 联邦在线</strong><small>安全网关常驻</small></div></div>
  </aside>
  <button v-if="mobileOpen" class="sidebar-backdrop" type="button" aria-label="关闭导航" @click="mobileOpen = false"></button>
</template>
