<script setup lang="ts">
/**
 * 演示模式：把 6 分钟的路演路线钉在界面上。
 *
 * 线下展示最怕两件事：点错页面、讲乱了顺序。所以这里把 6 站写死成一条线，
 * 点一下就直达，还带一句「这一站该说什么」。键盘 ← / → 也能翻，站着讲不用找鼠标。
 *
 * 第 6 站需要辅导员身份才能看到「一页纸」，所以进站时自动切身份；
 * 演示结束时切回学生，免得下一位评委看到的是辅导员视角。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhCaretLeft, PhCaretRight, PhPresentationChart, PhX } from '@phosphor-icons/vue'
import { useIdentity, type WebRole } from '../identity'

interface TourStop {
  id: string
  path: string
  title: string
  script: string
  role?: WebRole
}

const STOPS: TourStop[] = [
  {
    id: 'overview',
    path: '/',
    title: '今日概览',
    script: '第一屏只回答一件事：这个学生今天该干什么。成长导言、真实评价条、今日三件事都在这一屏。',
  },
  {
    id: 'wellbeing',
    path: '/wellbeing',
    title: '暖心空间 · 四题自评',
    script: '四题自评 → 橙档 → 预约卡自己弹出来 → 提交后辅导员台账可见。筛查、建议、预约是一条链，不是三个页面。',
  },
  {
    id: 'credit',
    path: '/academic/credit',
    title: '学业预警自检',
    script: '填年级、学制、额定学分、已修学分四个数，直接命中学校 65% 线，并给四步处置流程。',
  },
  {
    id: 'proposal',
    path: '/innovation',
    title: '竞赛申报大纲',
    script: '按官方九大要素生成大纲，47 条自检点逐条勾，勾两条进度条就动。',
  },
  {
    id: 'document',
    path: '/documents',
    title: '文档工坊 · 上传改格式',
    script: '拖一份格式乱的通知进来，40 处改动逐条带依据，正文一个字不改。这段最容易被评委当场验证。',
  },
  {
    id: 'profile',
    path: '/wellbeing',
    title: '辅导员 · 学生一页纸',
    script: '切成辅导员身份，点预警列表的「一页纸」：只有档位、次数和时间，不给打卡正文。',
    role: 'counselor',
  },
]

const router = useRouter()
const route = useRoute()
const { identity, update } = useIdentity()

const open = ref(false)
const index = ref(0)

const current = computed(() => STOPS[index.value])
const onStop = computed(() => STOPS.findIndex((stop) => stop.path === route.path) === index.value)
const progress = computed(() => `${index.value + 1} / ${STOPS.length}`)

function go(next: number) {
  const bounded = Math.max(0, Math.min(STOPS.length - 1, next))
  index.value = bounded
  const stop = STOPS[bounded]
  if (stop.role && identity.value.role !== stop.role) {
    update({ role: stop.role })
  }
  void router.push(stop.path)
}

function next() {
  go(index.value + 1)
}

function prev() {
  go(index.value - 1)
}

function finish() {
  // 演示结束回到学生视角，下一位评委看到的是默认界面。
  if (identity.value.role !== 'student') update({ role: 'student' })
  index.value = 0
  open.value = false
  void router.push('/')
}

function onKey(event: KeyboardEvent) {
  if (!open.value) return
  if (event.key === 'ArrowRight') {
    event.preventDefault()
    next()
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    prev()
  } else if (event.key === 'Escape') {
    open.value = false
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="demo-tour">
    <button
      type="button"
      class="demo-toggle"
      :class="{ active: open }"
      title="按 6 站顺序演示，键盘 ← → 可翻页"
      @click="open = !open"
    >
      <PhPresentationChart :size="16" weight="duotone" />
      演示
    </button>

    <div v-if="open" class="demo-panel">
      <header>
        <div>
          <strong>6 分钟路演</strong>
          <small>{{ progress }} · 键盘 ← → 可翻页</small>
        </div>
        <button type="button" aria-label="关闭演示面板" @click="open = false"><PhX :size="16" /></button>
      </header>

      <ol class="demo-stops">
        <li v-for="(stop, position) in STOPS" :key="stop.id">
          <button
            type="button"
            :class="{ current: position === index }"
            @click="go(position)"
          >
            <span class="demo-no">{{ position + 1 }}</span>
            <span class="demo-title">{{ stop.title }}</span>
            <em v-if="stop.role" class="demo-role">辅导员</em>
          </button>
        </li>
      </ol>

      <div class="demo-script">
        <p class="demo-script-label">这一站说什么</p>
        <p>{{ current.script }}</p>
        <p v-if="!onStop" class="demo-drift">你现在不在这一站，点上面的编号回去。</p>
      </div>

      <footer>
        <button type="button" class="demo-step" :disabled="index === 0" @click="prev">
          <PhCaretLeft :size="14" /> 上一站
        </button>
        <button type="button" class="demo-step primary" :disabled="index === STOPS.length - 1" @click="next">
          下一站 <PhCaretRight :size="14" />
        </button>
        <button type="button" class="demo-end" @click="finish">结束演示</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.demo-tour {
  position: relative;
}

.demo-toggle {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  padding: 6px 12px;
  border: 1px solid #d8ded4;
  border-radius: 999px;
  background: #fffef8;
  color: #172b2a;
  font: inherit;
  font-size: .78rem;
  font-weight: 700;
  cursor: pointer;
  transition: border-color .16s ease, background .16s ease;
}

.demo-toggle:hover {
  border-color: #397f72;
  background: #f5f4eb;
}

.demo-toggle.active {
  border-color: #173f43;
  background: #173f43;
  color: #fffef8;
}

.demo-panel {
  position: fixed;
  top: 64px;
  right: 18px;
  z-index: 240;
  width: min(360px, calc(100vw - 36px));
  padding: 14px 15px 12px;
  border: 1px solid #d8ded4;
  border-radius: 16px;
  background: rgba(255, 254, 248, .98);
  box-shadow: 0 22px 55px rgba(28, 61, 57, .22);
  backdrop-filter: blur(14px);
}

.demo-panel > header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.demo-panel > header strong {
  display: block;
  font-size: .95rem;
  color: #172b2a;
}

.demo-panel > header small {
  display: block;
  margin-top: 2px;
  font-size: .72rem;
  color: #667572;
}

.demo-panel > header button {
  flex: 0 0 auto;
  padding: 2px;
  border: 0;
  background: transparent;
  color: #7c8b86;
  cursor: pointer;
}

.demo-stops {
  display: grid;
  gap: 3px;
  margin: 0 0 10px;
  padding: 0;
  list-style: none;
}

.demo-stops button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 9px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: #3f5551;
  font: inherit;
  font-size: .82rem;
  text-align: left;
  cursor: pointer;
}

.demo-stops button:hover {
  background: #f5f4eb;
}

.demo-stops button.current {
  border-color: #397f72;
  background: #dfece5;
  color: #173f43;
  font-weight: 700;
}

.demo-no {
  flex: 0 0 20px;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: #eef1ea;
  color: #667572;
  font-size: .72rem;
  font-weight: 700;
}

.demo-stops button.current .demo-no {
  background: #397f72;
  color: #fffef8;
}

.demo-title {
  flex: 1 1 auto;
}

.demo-role {
  flex: 0 0 auto;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(214, 168, 73, .18);
  color: #8a6a3d;
  font-style: normal;
  font-size: .66rem;
}

.demo-script {
  padding: 10px 12px;
  border-radius: 11px;
  background: #f5f4eb;
}

.demo-script-label {
  margin: 0 0 3px;
  font-size: .68rem;
  font-weight: 700;
  letter-spacing: .05em;
  color: #8a6a3d;
}

.demo-script p {
  margin: 0;
  font-size: .82rem;
  line-height: 1.65;
  color: #172b2a;
}

.demo-drift {
  margin-top: 6px !important;
  font-size: .74rem !important;
  color: #b63d3d !important;
}

.demo-panel > footer {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 11px;
}

.demo-step {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 6px 11px;
  border: 1px solid #d8ded4;
  border-radius: 9px;
  background: #fffef8;
  color: #172b2a;
  font: inherit;
  font-size: .78rem;
  cursor: pointer;
}

.demo-step:disabled {
  opacity: .45;
  cursor: not-allowed;
}

.demo-step.primary {
  border-color: #397f72;
  background: #397f72;
  color: #fffef8;
}

.demo-end {
  margin-left: auto;
  padding: 6px 4px;
  border: 0;
  background: transparent;
  color: #667572;
  font: inherit;
  font-size: .74rem;
  text-decoration: underline;
  cursor: pointer;
}
</style>
