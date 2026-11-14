<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { PhArrowLeft, PhInfo, PhShieldCheck, PhWarningOctagon } from '@phosphor-icons/vue'
import { command } from '../api'

interface CreditTrigger { code: string; title: string; detail: string; basis: string }
interface CreditResult {
  level: 'ok' | 'watch' | 'warning'
  progress: number
  required_credits: number
  earned_credits: number
  triggers: CreditTrigger[]
  student_steps: string[]
  school_steps: string[]
  note: string
}

const STORAGE_KEY = 'zhq-credit-check-v1'
const LEVEL_LABEL: Record<CreditResult['level'], string> = { ok: '进度正常', watch: '有需要留意的信号', warning: '已命中学校预警标准' }

const grade = ref(3)
const programYears = ref(4)
const requiredCredits = ref(160)
const earnedCredits = ref(96)
const yearCredits = ref(24)
const failedCourses = ref(0)

const result = ref<CreditResult | null>(null)
const loading = ref(false)
const error = ref('')

/** 学年选项跟着学制走：5 年制才会有第 5 学年 */
const gradeOptions = computed(() => Array.from({ length: programYears.value }, (_, index) => index + 1))

const levelTone = computed(() => (result.value ? result.value.level : 'ok'))
const progressPercent = computed(() => (result.value ? Math.round(result.value.progress * 1000) / 10 : 0))

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      grade: grade.value,
      programYears: programYears.value,
      requiredCredits: requiredCredits.value,
      earnedCredits: earnedCredits.value,
      yearCredits: yearCredits.value,
      failedCourses: failedCourses.value,
    }))
  } catch {
    // 隐私模式下写不进去，当前会话仍然可用
  }
}

function restore() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const saved = JSON.parse(raw) as Partial<Record<string, number>>
    if (typeof saved.grade === 'number') grade.value = saved.grade
    if (typeof saved.programYears === 'number') programYears.value = saved.programYears
    if (typeof saved.requiredCredits === 'number') requiredCredits.value = saved.requiredCredits
    if (typeof saved.earnedCredits === 'number') earnedCredits.value = saved.earnedCredits
    if (typeof saved.yearCredits === 'number') yearCredits.value = saved.yearCredits
    if (typeof saved.failedCourses === 'number') failedCourses.value = saved.failedCourses
  } catch {
    // 旧缓存或损坏数据直接忽略
  }
}

watch([grade, programYears, requiredCredits, earnedCredits, yearCredits, failedCourses], persist, { deep: true })
// 学制改成 4 年时，原来选的第 5 学年要收回来，否则后端会判参数非法
watch(programYears, (years) => {
  if (grade.value > years) grade.value = years
})

async function check() {
  loading.value = true
  error.value = ''
  try {
    const response = await command('academic', 'credit_warning', '', {
      grade: grade.value,
      program_years: programYears.value,
      required_credits: requiredCredits.value,
      earned_credits: earnedCredits.value,
      year_credits: yearCredits.value,
      failed_courses: failedCourses.value,
    })
    result.value = response.data as unknown as CreditResult
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '自检失败'
    result.value = null
  } finally {
    loading.value = false
  }
}

onMounted(restore)
</script>

<template>
  <section class="credit-page">
    <RouterLink to="/academic"><PhArrowLeft :size="18" /> 返回功能选择</RouterLink>

    <header>
      <PhShieldCheck :size="38" weight="duotone" />
      <div>
        <h1>先看自己在什么位置，<em>再排这一周。</em></h1>
        <p>
          按学校学业预警办法算一遍：一学年不足 20 学分触发学年预警，毕业班达不到额定学分 65%（五年制 70%）触发毕业班预警。
          这里只做自检提示，正式名单以教务处审核、学院复核后的通知为准。
        </p>
      </div>
    </header>

    <div class="credit-grid">
      <form class="credit-form" @submit.prevent="check">
        <div class="credit-row">
          <label>当前学年
            <select v-model.number="grade">
              <option v-for="item in gradeOptions" :key="item" :value="item">第 {{ item }} 学年</option>
            </select>
          </label>
          <label>学制
            <select v-model.number="programYears">
              <option :value="4">四年制</option>
              <option :value="5">五年制</option>
            </select>
          </label>
        </div>
        <div class="credit-row">
          <label>培养方案额定总学分
            <input v-model.number="requiredCredits" type="number" min="1" max="300" step="0.5">
          </label>
          <label>累计已修学分
            <input v-model.number="earnedCredits" type="number" min="0" max="300" step="0.5">
          </label>
        </div>
        <div class="credit-row">
          <label>本学年已修学分
            <input v-model.number="yearCredits" type="number" min="0" max="80" step="0.5">
          </label>
          <label>不及格门数
            <input v-model.number="failedCourses" type="number" min="0" max="30" step="1">
          </label>
        </div>
        <p class="credit-hint">学分口径：不含通识选修课与辅修专业学分，和预警办法保持一致。</p>
        <button type="submit" :disabled="loading">
          <PhShieldCheck :size="18" weight="duotone" />
          {{ loading ? '正在核对…' : '开始自检' }}
        </button>
        <p v-if="error" class="credit-error">{{ error }}</p>
      </form>

      <div class="credit-sheet">
        <template v-if="result">
          <div class="credit-head" :class="`is-${levelTone}`">
            <span class="credit-badge">{{ LEVEL_LABEL[levelTone] }}</span>
            <strong>{{ progressPercent }}%</strong>
            <small>累计 {{ result.earned_credits }} / {{ result.required_credits }} 学分</small>
          </div>
          <div class="credit-bar"><i :style="{ width: `${Math.min(100, progressPercent)}%` }" /></div>

          <section v-if="result.triggers.length" class="credit-block">
            <h3><PhWarningOctagon :size="17" weight="duotone" /> 命中的标准</h3>
            <ul class="credit-triggers">
              <li v-for="item in result.triggers" :key="item.code">
                <strong>{{ item.title }}</strong>
                <p>{{ item.detail }}</p>
                <small>依据：{{ item.basis }}</small>
              </li>
            </ul>
          </section>
          <p v-else class="credit-clear">没有命中任何标准，保持每学年不低于 20 学分就行。</p>

          <section class="credit-block">
            <h3><PhShieldCheck :size="17" weight="duotone" /> 你这一侧要做的</h3>
            <ol class="credit-steps">
              <li v-for="step in result.student_steps" :key="step">{{ step }}</li>
            </ol>
          </section>

          <section class="credit-block">
            <h3><PhInfo :size="17" weight="duotone" /> 学校这一侧会走的四步</h3>
            <ol class="credit-steps is-school">
              <li v-for="step in result.school_steps" :key="step">{{ step }}</li>
            </ol>
          </section>

          <p class="credit-note">{{ result.note }}</p>
        </template>
        <p v-else class="credit-empty">
          填好学分数据后点「开始自检」，这里会给出命中的标准、你该做的动作，以及学校后面会走的流程。
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.credit-page {
  display: grid;
  gap: 16px;
  padding: 4px 0 40px;
}

.credit-page > a {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #6d7d78;
  font-size: 13px;
  text-decoration: none;
}

.credit-page > a:hover {
  color: #2f7a52;
}

.credit-page header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  color: #2f4a45;
}

.credit-page h1 {
  margin: 0;
  font-size: 26px;
  line-height: 1.35;
}

.credit-page h1 em {
  color: #2f7a52;
  font-style: normal;
}

.credit-page header p {
  max-width: 760px;
  margin: 8px 0 0;
  color: #6d7d78;
  font-size: 13px;
  line-height: 1.75;
}

.credit-grid {
  display: grid;
  grid-template-columns: minmax(280px, 0.85fr) minmax(0, 1.15fr);
  gap: 16px;
}

@media (max-width: 900px) {
  .credit-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

.credit-form,
.credit-sheet {
  padding: 18px 20px;
  border: 1px solid rgba(47, 74, 69, 0.12);
  border-radius: 16px;
  background: rgba(255, 253, 248, 0.85);
}

.credit-form {
  display: grid;
  gap: 12px;
  align-content: start;
}

.credit-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.credit-form label {
  display: grid;
  gap: 5px;
  color: #6d7d78;
  font-size: 12.5px;
}

.credit-form input,
.credit-form select {
  padding: 8px 10px;
  border: 1px solid rgba(47, 74, 69, 0.16);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.8);
  color: #2f4a45;
  font-size: 13px;
  font-family: inherit;
}

.credit-hint {
  margin: 0;
  color: #8a9994;
  font-size: 11.5px;
  line-height: 1.6;
}

.credit-form button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  margin-top: 2px;
  padding: 10px 16px;
  border: none;
  border-radius: 11px;
  background: #2f7a52;
  color: #fff;
  font-size: 13.5px;
  font-family: inherit;
  cursor: pointer;
}

.credit-form button:disabled {
  opacity: 0.6;
  cursor: default;
}

.credit-error {
  margin: 0;
  color: #b84a30;
  font-size: 12.5px;
}

.credit-sheet {
  display: grid;
  gap: 12px;
  align-content: start;
}

.credit-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 10px;
}

.credit-badge {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.credit-head.is-ok .credit-badge {
  background: rgba(47, 122, 82, 0.12);
  color: #2f7a52;
}

.credit-head.is-watch .credit-badge {
  background: rgba(201, 138, 43, 0.14);
  color: #8a5c15;
}

.credit-head.is-warning .credit-badge {
  background: rgba(184, 74, 48, 0.12);
  color: #b84a30;
}

.credit-head strong {
  color: #2f4a45;
  font-size: 26px;
  line-height: 1;
}

.credit-head small {
  color: #8a9994;
  font-size: 12px;
}

.credit-bar {
  height: 6px;
  border-radius: 999px;
  background: rgba(47, 74, 69, 0.1);
  overflow: hidden;
}

.credit-bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #2f7a52, #4f9b6d);
}

.credit-block h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 8px;
  color: #2f4a45;
  font-size: 14px;
}

.credit-triggers {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.credit-triggers li {
  padding: 9px 11px;
  border-left: 3px solid #b84a30;
  border-radius: 0 9px 9px 0;
  background: rgba(184, 74, 48, 0.06);
}

.credit-triggers strong {
  display: block;
  color: #8c1d17;
  font-size: 12.5px;
}

.credit-triggers p {
  margin: 3px 0 0;
  color: #4c6b64;
  font-size: 12.5px;
  line-height: 1.65;
}

.credit-triggers small {
  display: block;
  margin-top: 3px;
  color: #8a9994;
  font-size: 11.5px;
  line-height: 1.6;
}

.credit-clear {
  margin: 0;
  padding: 9px 11px;
  border-left: 3px solid rgba(47, 122, 82, 0.5);
  border-radius: 0 9px 9px 0;
  background: rgba(47, 122, 82, 0.07);
  color: #2f6b4c;
  font-size: 12.5px;
}

.credit-steps {
  display: grid;
  gap: 6px;
  margin: 0;
  padding-left: 20px;
  color: #4c6b64;
  font-size: 12.5px;
  line-height: 1.7;
}

.credit-steps.is-school {
  color: #7b8b86;
}

.credit-note {
  margin: 0;
  padding-top: 10px;
  border-top: 1px dashed rgba(47, 74, 69, 0.14);
  color: #8a9994;
  font-size: 11.5px;
  line-height: 1.7;
}

.credit-empty {
  margin: 0;
  color: #8a9994;
  font-size: 13px;
  line-height: 1.8;
}
</style>
