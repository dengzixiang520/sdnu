<script setup lang="ts">
import { ref, watch } from 'vue'
import { PhArrowSquareOut, PhFilePlus, PhFunnel, PhLightbulb, PhMagnifyingGlass, PhNewspaper, PhRocketLaunch, PhUsersThree } from '@phosphor-icons/vue'
import { command } from '../api'
import { useIdentity } from '../identity'

type Tool = 'submit' | 'team' | 'proposal' | 'review'
interface PendingSubmission { submission_id: string; competition_name: string; edition: string; submitter_id: string }
const { identity } = useIdentity(); const activeTool = ref<Tool>('submit'); const search = ref(''); const category = ref('全部')
const name = ref('校园人工智能创新应用大赛'); const edition = ref('2026'); const url = ref(''); const submitMessage = ref('')
const project = ref('智汇齐鲁 · 全域同频'); const outline = ref<string[]>([]); const matches = ref<Array<{ display_name: string; score: number; matched_skills: string[] }>>([]); const error = ref(''); const pending = ref<PendingSubmission[]>([])
const sources = [
  { kind: '学校通知', title: '山东师范大学官网通知入口', summary: '查看学校公开发布的新闻、通知和专题信息。本站不抓取或改写未核验内容。', source: '山东师范大学官网', url: 'https://www.sdnu.edu.cn/', tag: '校内' },
  { kind: '竞赛入口', title: '中国国际大学生创新大赛官方平台', summary: '赛事通知、报名入口与参赛资料以官方平台发布为准。', source: '国家大学生就业服务平台', url: 'https://cy.ncss.cn/', tag: '双创' },
  { kind: '竞赛入口', title: '“挑战杯”全国大学生系列竞赛', summary: '查看挑战杯及创业计划竞赛的公开赛程与作品要求。', source: '挑战杯官网', url: 'https://www.tiaozhanbei.net/', tag: '竞赛' },
  { kind: '学习资源', title: '从需求到验证：参赛项目的证据链', summary: '演示学习卡片：梳理用户问题、解决方案、验证方法与量化结果。', source: '平台学习资料 · 演示内容', url: '', tag: '学习' },
  { kind: '学习资源', title: '五分钟路演如何分配时间', summary: '演示学习卡片：问题 40 秒、方案 80 秒、验证 90 秒、团队与计划 50 秒。', source: '平台学习资料 · 演示内容', url: '', tag: '学习' },
]
function visibleSources() { return sources.filter((item) => (category.value === '全部' || item.tag === category.value) && `${item.title}${item.summary}${item.source}`.includes(search.value.trim())) }
async function submit() { if (!name.value.trim() || !edition.value.trim()) { error.value = '赛事名称和届次不能为空'; return } error.value = ''; try { const result = await command('innovation', 'submit_competition', '', { submission: { competition_name: name.value, edition: edition.value, official_url: url.value || undefined } }); submitMessage.value = `已提交审核，建议积分 ${String((result.data.scoring_advice as { points?: number }).points ?? 0)}` } catch (reason) { error.value = reason instanceof Error ? reason.message : '提交失败' } }
async function makeOutline() { try { const result = await command('innovation', 'proposal_outline', '', { project_name: project.value, competition_name: name.value, technical_keywords: ['多 Agent', 'FastAPI', 'Vue'] }); outline.value = (result.data.sections ?? []) as string[] } catch (reason) { error.value = reason instanceof Error ? reason.message : '生成失败' } }
async function match() { try { const result = await command('innovation', 'match_team', '', { requirement: { project_name: project.value, required_skills: { python: 1, frontend: 1, design: .7 } }, profiles: [{ student_id: 's1', display_name: '林同学', skills: { python: 1, frontend: .8 } }, { student_id: 's2', display_name: '周同学', skills: { design: 1, frontend: .6 } }] }); matches.value = (result.data.matches ?? []) as typeof matches.value } catch (reason) { error.value = reason instanceof Error ? reason.message : '匹配失败' } }
async function loadPending() { if (identity.value.role !== 'administrator') { pending.value = []; return } try { pending.value = ((await command('innovation', 'pending_competitions')).data.submissions ?? []) as PendingSubmission[] } catch (reason) { error.value = reason instanceof Error ? reason.message : '加载失败' } }
async function review(id: string, approved: boolean) { try { await command('innovation', 'review_competition', '', { submission_id: id, decision: { approved, note: approved ? '信息核验通过' : '信息不完整' } }); await loadPending() } catch (reason) { error.value = reason instanceof Error ? reason.message : '审核失败' } }
watch(() => identity.value.role, loadPending, { immediate: true })
</script>

<template>
  <section class="innovation-page">
    <main class="innovation-feed">
      <header class="innovation-masthead"><div><span><PhNewspaper :size="18" /> 校园双创情报站</span><h1>先发现值得投入的事，<br><em>再把项目做成。</em></h1><p>官方入口、竞赛线索与学习资料放在主页面；提交、组队和申报工具收进右侧工作栏。</p></div><div class="launch-stamp"><PhRocketLaunch :size="38" weight="duotone" /><strong>BUILD<br>WITH<br>EVIDENCE</strong></div></header>
      <div class="feed-controls"><label><PhMagnifyingGlass :size="19" /><input v-model="search" placeholder="搜索竞赛、通知或学习资料"></label><div><PhFunnel :size="17" /><button v-for="item in ['全部', '校内', '双创', '竞赛', '学习']" :key="item" :class="{ active: category === item }" type="button" @click="category = item">{{ item }}</button></div></div>
      <section class="notice-stream">
        <article v-for="item in visibleSources()" :key="item.title" :class="{ learning: item.tag === '学习' }">
          <div class="notice-kind">{{ item.kind }}</div><div><h2>{{ item.title }}</h2><p>{{ item.summary }}</p><small>来源：{{ item.source }}</small></div><a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer">查看原始来源 <PhArrowSquareOut :size="17" /></a><span v-else>演示学习内容</span>
        </article>
        <div v-if="!visibleSources().length" class="feed-empty">没有找到匹配内容。试试更短的关键词。</div>
      </section>
    </main>

    <aside class="innovation-rail">
      <header><h2>孵化工具</h2><p>选择一项工作，不离开当前信息上下文。</p></header>
      <nav aria-label="双创孵化工具">
        <button :class="{ active: activeTool === 'submit' }" type="button" @click="activeTool = 'submit'"><PhFilePlus :size="20" weight="duotone" /><span><strong>提交竞赛</strong><small>UGC 审核入库</small></span></button>
        <button :class="{ active: activeTool === 'team' }" type="button" @click="activeTool = 'team'"><PhUsersThree :size="20" weight="duotone" /><span><strong>技能组队</strong><small>按项目需求匹配</small></span></button>
        <button :class="{ active: activeTool === 'proposal' }" type="button" @click="activeTool = 'proposal'"><PhLightbulb :size="20" weight="duotone" /><span><strong>申报书大纲</strong><small>先搭结构再写作</small></span></button>
        <button v-if="identity.role === 'administrator'" :class="{ active: activeTool === 'review' }" type="button" @click="activeTool = 'review'"><PhNewspaper :size="20" weight="duotone" /><span><strong>审核大厅</strong><small>{{ pending.length }} 条待处理</small></span></button>
      </nav>
      <section class="innovation-tool-panel">
        <form v-if="activeTool === 'submit'" @submit.prevent="submit"><h3>提交一条竞赛信息</h3><label>赛事名称<input v-model="name"></label><label>届次<input v-model="edition"></label><label>官方链接 <small>可选</small><input v-model="url" type="url" placeholder="https://"></label><button type="submit">提交管理员核验</button><p>{{ submitMessage || '审核通过后才会公开并计入积分。' }}</p></form>
        <div v-else-if="activeTool === 'team'" class="team-tool"><h3>寻找互补队友</h3><label>项目名称<input v-model="project"></label><button type="button" @click="match">执行技能匹配</button><div v-for="item in matches" :key="item.display_name"><strong>{{ item.display_name }}</strong><span>{{ Math.round(item.score * 100) }}%</span><small>{{ item.matched_skills.join(' / ') }}</small></div><p v-if="!matches.length">当前使用演示成员数据，接入真实学生技能档案前不会公开联系方式。</p></div>
        <div v-else-if="activeTool === 'proposal'" class="proposal-tool"><h3>搭建申报书骨架</h3><label>项目名称<input v-model="project"></label><button type="button" @click="makeOutline">生成章节大纲</button><ol><li v-for="item in outline" :key="item">{{ item }}</li></ol><p v-if="!outline.length">大纲只组织结构，不编造团队成果或验证数据。</p></div>
        <div v-else class="review-tool"><h3>待审核信息</h3><article v-for="item in pending" :key="item.submission_id"><div><strong>{{ item.competition_name }}</strong><small>{{ item.edition }} · {{ item.submitter_id }}</small></div><button type="button" @click="review(item.submission_id, true)">通过</button><button type="button" @click="review(item.submission_id, false)">驳回</button></article><p v-if="!pending.length">目前没有待审核项目。</p></div>
      </section>
      <p v-if="error" class="rail-error">{{ error }}</p>
    </aside>
  </section>
</template>
