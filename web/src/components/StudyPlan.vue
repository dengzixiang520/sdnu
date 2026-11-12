<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  PhArrowClockwise,
  PhArrowLeft,
  PhCalendarCheck,
  PhCheckCircle,
  PhCircle,
  PhSparkle,
  PhWarningCircle,
} from '@phosphor-icons/vue'
import { requestJson } from '../api'

interface PlanTask { title: string; minutes: number; kind: string }
interface PlanDay { day: string; date: string; focus: string; minutes: number; tasks: PlanTask[] }
interface StudyPlan {
  goal: string
  week_start: string
  week_end: string
  total_minutes: number
  summary: string
  days: PlanDay[]
  checkpoint: string
  source: 'model' | 'offline'
}
interface PlanStatus { available: boolean; model: string; note: string }

const STORAGE_KEY = 'zhq-study-plan-v2'
const KIND_LABEL: Record<string, string> = { focus: '推进', drill: '练手', review: '复盘' }

const goal = ref('完成复试专业课第一轮复习')
const hours = ref(12)
const major = ref('人工智能')
const deadline = ref('')
const weak = ref('')
const plan = ref<StudyPlan | null>(null)
const done = ref<Record<string, boolean>>({})
const loading = ref(false)
const error = ref('')
const status = ref<PlanStatus | null>(null)

/** 任务指纹：日期 + 标题，重排后标题会变，勾选状态自然失效。 */
function taskKey(day: PlanDay, task: PlanTask): string {
  return `${day.date}|${task.title}`
}

const totalTasks = computed(() => plan.value?.days.reduce((sum, day) => sum + day.tasks.length, 0) ?? 0)
const doneTasks = computed(() => {
  if (!plan.value) return 0
  return plan.value.days.reduce(
    (sum, day) => sum + day.tasks.filter((task) => done.value[taskKey(day, task)]).length,
    0,
  )
})
const progress = computed(() => (totalTasks.value ? Math.round((doneTasks.value / totalTasks.value) * 100) : 0))
const doneMinutes = computed(() => {
  if (!plan.value) return 0
  return plan.value.days.reduce(
    (sum, day) => sum + day.tasks.filter((task) => done.value[taskKey(day, task)]).reduce((n, task) => n + task.minutes, 0),
    0,
  )
})
const remainingDays = computed(() => plan.value?.days.filter((day) => day.tasks.some((task) => !done.value[taskKey(day, task)])) ?? [])
const badge = computed(() => {
  if (!status.value) return '正在检查模型状态'
  return status.value.available ? `模型生成 · ${status.value.model}` : '本地模板生成'
})

function dayDone(day: PlanDay): boolean {
  return day.tasks.length > 0 && day.tasks.every((task) => done.value[taskKey(day, task)])
}

function toggle(day: PlanDay, task: PlanTask): void {
  const key = taskKey(day, task)
  done.value = { ...done.value, [key]: !done.value[key] }
}

function persist(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ goal: goal.value, hours: hours.value, major: major.value, deadline: deadline.value, weak: weak.value, plan: plan.value, done: done.value }))
  } catch {
    // 隐私模式下 localStorage 可能直接抛错，计划本身仍然可用。
  }
}

function restore(): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const saved = JSON.parse(raw) as Partial<{ goal: string; hours: number; major: string; deadline: string; weak: string; plan: StudyPlan; done: Record<string, boolean> }>
    if (typeof saved.goal === 'string') goal.value = saved.goal
    if (typeof saved.hours === 'number') hours.value = saved.hours
    if (typeof saved.major === 'string') major.value = saved.major
    if (typeof saved.deadline === 'string') deadline.value = saved.deadline
    if (typeof saved.weak === 'string') weak.value = saved.weak
    if (saved.plan && Array.isArray(saved.plan.days)) plan.value = saved.plan
    if (saved.done && typeof saved.done === 'object') done.value = saved.done
  } catch {
    // 旧版本或损坏的缓存直接忽略，不阻塞页面。
  }
}

watch([goal, hours, major, deadline, weak, plan, done], persist, { deep: true })

async function generate(): Promise<void> {
  if (!goal.value.trim()) {
    error.value = '先写一个本周目标，越具体越好。'
    return
  }
  loading.value = true
  error.value = ''
  try {
    plan.value = await requestJson<StudyPlan>(
      '/api/v1/study-plan/generate',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: goal.value.trim(),
          hours_per_week: hours.value,
          major: major.value.trim(),
          deadline: deadline.value.trim(),
          weak_points: weak.value.trim(),
        }),
      },
      '计划生成失败',
    )
    done.value = {}
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '计划生成失败'
  } finally {
    loading.value = false
  }
}

async function adjust(): Promise<void> {
  if (!plan.value) return
  if (!remainingDays.value.length) {
    error.value = '这一周的任务都完成了，直接生成下一周吧。'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const doneTitles = plan.value.days.flatMap((day) => day.tasks.filter((task) => done.value[taskKey(day, task)]).map((task) => task.title))
    const missedTitles = remainingDays.value.flatMap((day) => day.tasks.filter((task) => !done.value[taskKey(day, task)]).map((task) => task.title))
    plan.value = await requestJson<StudyPlan>(
      '/api/v1/study-plan/adjust',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal: goal.value.trim() || plan.value.goal,
          hours_per_week: hours.value,
          remaining: remainingDays.value.map((day) => ({ day: day.day, date: day.date })),
          done_titles: doneTitles,
          missed_titles: missedTitles,
        }),
      },
      '重排失败',
    )
    done.value = {}
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '重排失败'
  } finally {
    loading.value = false
  }
}

async function loadStatus(): Promise<void> {
  try {
    status.value = await requestJson<PlanStatus>('/api/v1/study-plan/status', {}, '状态未知')
  } catch {
    status.value = null
  }
}

onMounted(() => {
  restore()
  void loadStatus()
})
</script>

<template>
  <section class="study-plan-page">
    <RouterLink to="/academic"><PhArrowLeft :size="18" /> 返回功能选择</RouterLink>

    <header>
      <PhCalendarCheck :size="38" weight="duotone" />
      <div>
        <h1>把大目标拆成一周。</h1>
        <p>计划由大模型按目标和可投入时间排出来，勾掉做完的，剩下的可以重排。</p>
      </div>
      <span class="sp-badge" :class="{ 'is-offline': status && !status.available }">{{ badge }}</span>
    </header>

    <div class="sp-grid">
      <form class="sp-form" @submit.prevent="generate">
        <label>
          本周目标
          <textarea v-model="goal" maxlength="200" rows="3" placeholder="例如：把《人工智能导论》前三章过一遍"></textarea>
        </label>
        <div class="sp-row">
          <label>专业方向 <input v-model="major" maxlength="40" placeholder="人工智能"></label>
          <label>关键节点 <input v-model="deadline" maxlength="40" placeholder="11 月 15 日复试"></label>
        </div>
        <label>
          可投入时间
          <input v-model.number="hours" type="range" min="3" max="40" step="1">
          <strong>{{ hours }} 小时 / 周</strong>
        </label>
        <label>
          薄弱环节
          <textarea v-model="weak" maxlength="300" rows="2" placeholder="英语口语、名词解释记不牢…"></textarea>
        </label>
        <button type="submit" :disabled="loading">
          <PhSparkle :size="18" weight="duotone" />
          {{ loading ? '正在排这一周…' : '生成一周计划' }}
        </button>
        <p v-if="error" class="sp-error"><PhWarningCircle :size="16" />{{ error }}</p>
        <p v-if="status" class="sp-note">{{ status.note }}</p>
      </form>

      <div class="sp-sheet">
        <template v-if="plan">
          <div class="sp-sheet-head">
            <div>
              <strong>{{ plan.week_start }} → {{ plan.week_end }}</strong>
              <p>{{ plan.summary }}</p>
            </div>
            <div class="sp-ring">
              <b>{{ progress }}%</b>
              <span>{{ doneTasks }} / {{ totalTasks }} 项</span>
              <em>{{ doneMinutes }} / {{ plan.total_minutes }} 分钟</em>
            </div>
          </div>
          <div class="sp-bar"><i :style="{ width: `${progress}%` }" /></div>

          <div class="sp-days">
            <article v-for="day in plan.days" :key="`${day.date}-${day.day}`" :class="{ 'is-done': dayDone(day) }">
              <header>
                <span>{{ day.day }}</span>
                <b>{{ day.date }}</b>
                <em>{{ day.minutes }} 分钟</em>
              </header>
              <p class="sp-focus">{{ day.focus }}</p>
              <ul>
                <li v-for="task in day.tasks" :key="task.title">
                  <button
                    type="button"
                    :aria-pressed="Boolean(done[taskKey(day, task)])"
                    :aria-label="done[taskKey(day, task)] ? '取消完成' : '标记完成'"
                    @click="toggle(day, task)"
                  >
                    <PhCheckCircle v-if="done[taskKey(day, task)]" :size="21" weight="fill" />
                    <PhCircle v-else :size="21" />
                  </button>
                  <span :class="{ 'is-checked': done[taskKey(day, task)] }">{{ task.title }}</span>
                  <em>{{ KIND_LABEL[task.kind] ?? '推进' }} · {{ task.minutes }}′</em>
                </li>
              </ul>
            </article>
          </div>

          <div class="sp-foot">
            <div class="sp-check">
              <strong>周末自检</strong>
              <p>{{ plan.checkpoint }}</p>
            </div>
            <button type="button" class="sp-ghost" :disabled="loading || !remainingDays.length" @click="adjust">
              <PhArrowClockwise :size="18" />
              按完成情况重排剩余 {{ remainingDays.length }} 天
            </button>
          </div>
        </template>
        <p v-else class="plan-empty">
          填写目标和可投入时间，这里会生成一份能逐条勾掉的一周计划。
        </p>
      </div>
    </div>
  </section>
</template>
