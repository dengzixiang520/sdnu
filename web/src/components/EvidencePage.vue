<script setup lang="ts">
/**
 * 每条规则的依据。
 *
 * 线下展示时评委不会问「你用了几个模型」，会问「你这个判断凭什么」。
 * 这一页把平台里每一条硬规则的出处摊开，自己设定的部分明确标注，
 * 不冒充学校标准——诚实本身就是这一页要说的话。
 */
import { computed, onMounted, ref } from 'vue'
import { PhArrowSquareOut, PhBooks, PhInfo } from '@phosphor-icons/vue'
import { loadEvidence } from '../api'
import type { EvidencePayload } from '../api'

const payload = ref<EvidencePayload | null>(null)
const error = ref('')
const loading = ref(true)

const groupCount = computed(() => payload.value?.groups.length ?? 0)

async function load() {
  loading.value = true
  error.value = ''
  try {
    payload.value = await loadEvidence()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '读不到依据清单'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="evidence-page">
    <header class="evidence-head">
      <div>
        <p class="eyebrow">依据与出处</p>
        <h1>每条规则，<em>都能追到出处。</em></h1>
        <p class="evidence-lead">
          平台里没有「我们觉得应该这样」。国标、校办细则、学校预警办法、公开量表、赛事评审标准、
          教育部行动计划——每一条硬规则都对着原文写；自己设定的部分明确标成「本系统设定」。
        </p>
      </div>
      <div v-if="payload" class="evidence-count">
        <strong>{{ payload.total }}</strong>
        <span>条规则 · {{ groupCount }} 组</span>
      </div>
    </header>

    <p v-if="error" class="evidence-error">{{ error }}</p>
    <p v-else-if="loading" class="evidence-loading">正在读依据清单…</p>

    <template v-else-if="payload">
      <p class="evidence-note"><PhInfo :size="15" weight="duotone" />{{ payload.note }}</p>

      <div class="evidence-groups">
        <article v-for="group in payload.groups" :key="group.id" class="evidence-group">
          <header>
            <h2><PhBooks :size="18" weight="duotone" />{{ group.title }}</h2>
            <p>{{ group.summary }}</p>
          </header>

          <ul>
            <li v-for="(item, index) in group.items" :key="index">
              <p class="ev-rule">{{ item.rule }}</p>
              <p class="ev-how"><span>怎么用</span>{{ item.how }}</p>
              <p class="ev-source">
                <span>出处</span>
                <a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer noopener">
                  {{ item.source }}<PhArrowSquareOut :size="12" />
                </a>
                <em v-else>{{ item.source }}</em>
              </p>
            </li>
          </ul>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.evidence-page {
  max-width: 1180px;
  margin: 0 auto;
  padding-bottom: 3rem;
}

.evidence-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1.5rem;
  margin: 1.5rem 0 1.5rem;
}

.evidence-head h1 {
  margin: .25rem 0 .6rem;
  font: 400 clamp(2rem, 4vw, 3.2rem)/1.1 "LXGW WenKai", cursive;
  letter-spacing: -.03em;
  color: #172b2a;
}

.evidence-head h1 em {
  font-style: normal;
  color: #397f72;
}

.evidence-lead {
  max-width: 62ch;
  margin: 0;
  color: #667572;
  line-height: 1.75;
}

.evidence-count {
  flex: 0 0 auto;
  padding: .8rem 1.1rem;
  border: 1px solid #d8ded4;
  border-radius: 16px;
  background: #fffef8;
  text-align: right;
}

.evidence-count strong {
  display: block;
  font: 400 2rem/1 "LXGW WenKai", cursive;
  color: #173f43;
}

.evidence-count span {
  display: block;
  margin-top: .3rem;
  font-size: .76rem;
  color: #667572;
}

.evidence-note {
  display: flex;
  align-items: flex-start;
  gap: .45rem;
  margin: 0 0 1.2rem;
  padding: .75rem .95rem;
  border-left: 3px solid #397f72;
  border-radius: 0 12px 12px 0;
  background: #f5f4eb;
  font-size: .84rem;
  line-height: 1.7;
  color: #172b2a;
}

.evidence-error {
  padding: .8rem 1rem;
  border-left: 3px solid #b63d3d;
  border-radius: 0 12px 12px 0;
  background: #fdf6f4;
  color: #8a3d30;
}

.evidence-loading {
  color: #667572;
}

.evidence-groups {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
}

.evidence-group {
  padding: 1.1rem 1.2rem 1.2rem;
  border: 1px solid #d8ded4;
  border-radius: 18px;
  background: #fffef8;
}

.evidence-group > header {
  margin-bottom: .9rem;
}

.evidence-group h2 {
  display: flex;
  align-items: center;
  gap: .4rem;
  margin: 0 0 .35rem;
  font-size: 1rem;
  color: #173f43;
}

.evidence-group > header p {
  margin: 0;
  font-size: .8rem;
  line-height: 1.65;
  color: #667572;
}

.evidence-group ul {
  display: grid;
  gap: .75rem;
  margin: 0;
  padding: 0;
  list-style: none;
}

.evidence-group li {
  padding: .7rem .8rem;
  border-radius: 12px;
  background: #f5f4eb;
}

.ev-rule {
  margin: 0 0 .4rem;
  font-size: .84rem;
  font-weight: 600;
  line-height: 1.6;
  color: #172b2a;
}

.ev-how,
.ev-source {
  display: flex;
  gap: .4rem;
  margin: 0;
  font-size: .76rem;
  line-height: 1.6;
  color: #667572;
}

.ev-source {
  margin-top: .2rem;
}

.ev-how span,
.ev-source span {
  flex: 0 0 auto;
  font-weight: 700;
  color: #8a6a3d;
}

.ev-source a {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  color: #2f6b60;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.ev-source em {
  font-style: normal;
  color: #667572;
}

@media (max-width: 720px) {
  .evidence-groups {
    grid-template-columns: 1fr;
  }

  .evidence-count {
    text-align: left;
  }
}
</style>
