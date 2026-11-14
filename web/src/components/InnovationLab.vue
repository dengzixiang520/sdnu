<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { PhArrowSquareOut, PhFilePlus, PhFunnel, PhLightbulb, PhMagnifyingGlass, PhMegaphone, PhNewspaper, PhRocketLaunch, PhUsersThree, PhTrophy, PhCalendar, PhUsers, PhStar, PhArrowLeft, PhTarget, PhMedal, PhClock, PhBookOpen, PhUpload, PhChartBar, PhCheckCircle, PhCircle, PhWarningCircle } from '@phosphor-icons/vue'
import { command, requestJson } from '../api'
import { useIdentity } from '../identity'

type Tool = 'submit' | 'wish' | 'recruit' | 'team' | 'proposal' | 'review' | 'upload'
interface CompetitionDoc {
  title: string
  url: string
  kind: string
}
interface CompetitionValue {
  score: number
  rating: string
  schoolTier: string
  summary: string
  uses: string[]
  nationalAwards: number
  provincialAwards: number
  schoolLevelAwards: number
  totalAwards: number
  rarityNote: string
}
interface Competition {
  id: string
  name: string
  category: string
  level: string
  organizer: string
  awards: Record<string, number>
  teamSize: string
  schoolParticipants: string
  difficulty: string
  skills: string[]
  tips: string
  isAlevel: boolean
  year: string
  note: string
  intro?: string
  audience?: string
  value?: CompetitionValue
  website?: string
  registration?: string
  schedule?: string
  fee?: string
  tracks?: string[]
  documents?: CompetitionDoc[]
  highlights?: string[]
  prep?: string
}

const { identity } = useIdentity()
const activeTool = ref<Tool>('submit')
const search = ref('')
const category = ref('全部')
const competitions = ref<Competition[]>([])
const categories = ref<string[]>([])
const loading = ref(false)
const error = ref('')
const selectedCompetition = ref<Competition | null>(null)

const isStaff = computed(() => identity.value.role === 'counselor' || identity.value.role === 'administrator')

async function fetchCompetitions() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams()
    if (category.value !== '全部') params.append('category', category.value)
    if (search.value) params.append('keyword', search.value)
    const data = await requestJson<{ success: boolean; data: { competitions: Competition[]; categories: string[] } }>(
      `/api/v1/competitions?${params}`, {}, '竞赛库加载失败')
    if (data.success) {
      competitions.value = data.data.competitions
      categories.value = ['全部', ...data.data.categories]
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function viewDetail(comp: Competition) { selectedCompetition.value = comp }
function backToList() { selectedCompetition.value = null }

function difficultyColor(d: string) {
  switch (d) {
    case '低': return '#52c41a'
    case '中': return '#1890ff'
    case '中高': return '#faad14'
    case '高': return '#ff7a45'
    case '极高': return '#ff4d4f'
    default: return '#666'
  }
}

function awardLevelColor(level: string) {
  if (level.startsWith('A')) return '#ff4d4f'
  if (level.startsWith('B')) return '#ff7a45'
  if (level.startsWith('C')) return '#faad14'
  if (level.startsWith('D')) return '#52c41a'
  return '#999'
}

function awardLevelBg(level: string) {
  if (level.startsWith('A')) return '#fff1f0'
  if (level.startsWith('B')) return '#fff7e6'
  if (level.startsWith('C')) return '#fffbe6'
  if (level.startsWith('D')) return '#f6ffed'
  return '#f5f5f5'
}

function getTotalAwards(awards: Record<string, number>) {
  return Object.values(awards).reduce((sum, count) => sum + count, 0)
}

/* 含金量五档配色，与后端 rating_of() 的阈值一致 */
const RATING_STYLE: Record<string, { fg: string; bg: string }> = {
  '极高': { fg: '#a8071a', bg: '#fff1f0' },
  '高': { fg: '#d4380d', bg: '#fff7e6' },
  '中高': { fg: '#ad6800', bg: '#fffbe6' },
  '中': { fg: '#237804', bg: '#f6ffed' },
  '一般': { fg: '#595959', bg: '#f5f5f5' },
}

function ratingColor(rating?: string) {
  return (rating && RATING_STYLE[rating]?.fg) || '#595959'
}

function ratingBg(rating?: string) {
  return (rating && RATING_STYLE[rating]?.bg) || '#f5f5f5'
}

const sortBy = ref<'value' | 'awards' | 'default'>('value')

const sortedCompetitions = computed(() => {
  const list = [...competitions.value]
  if (sortBy.value === 'value') {
    list.sort((a, b) => (b.value?.score ?? 0) - (a.value?.score ?? 0))
  } else if (sortBy.value === 'awards') {
    list.sort((a, b) => getTotalAwards(b.awards) - getTotalAwards(a.awards))
  }
  return list
})

const ratingSummary = computed(() => {
  const buckets: Record<string, number> = {}
  for (const c of competitions.value) {
    const r = c.value?.rating
    if (r) buckets[r] = (buckets[r] ?? 0) + 1
  }
  return ['极高', '高', '中高', '中', '一般']
    .filter(r => buckets[r])
    .map(r => ({ rating: r, count: buckets[r] }))
})

/* ==================== 工具面板：提交 / 组队 / 申报 / 档案 ==================== */

/* ---------- 1. 提交竞赛 ---------- */
const submitForm = ref({ name: '', edition: '', url: '', deadline: '', organizer: '', description: '' })
const submitBusy = ref(false)
const submitNotice = ref('')

const SUBMISSION_KEY = 'zhq-innovation-submissions-v1'
interface SubmissionRow {
  at: string
  name: string
  edition: string
  status: 'pending' | 'approved' | 'rejected'
  id: string
}
const submissions = ref<SubmissionRow[]>([])

function loadSubmissions() {
  try {
    const raw = localStorage.getItem(SUBMISSION_KEY)
    if (raw) submissions.value = JSON.parse(raw) as SubmissionRow[]
  } catch {
    submissions.value = []
  }
}

function persistSubmissions() {
  try {
    localStorage.setItem(SUBMISSION_KEY, JSON.stringify(submissions.value.slice(0, 20)))
  } catch {
    // 隐私模式写不进去，档案只在本次会话可见。
  }
}

function clearSubmissions() {
  submissions.value = []
  try {
    localStorage.removeItem(SUBMISSION_KEY)
  } catch {
    // 忽略
  }
  submitNotice.value = '参赛档案已清空'
}

const submissionStats = computed(() => ({
  total: submissions.value.length,
  approved: submissions.value.filter((row) => row.status === 'approved').length,
  pending: submissions.value.filter((row) => row.status === 'pending').length,
}))

async function submitCompetition() {
  if (!submitForm.value.name.trim()) {
    submitNotice.value = '先填竞赛名称'
    return
  }
  if (!submitForm.value.edition.trim()) {
    submitNotice.value = '填一下届次，例如「2026 年第十六届」'
    return
  }
  submitBusy.value = true
  submitNotice.value = ''
  try {
    const payload: Record<string, unknown> = {
      competition_name: submitForm.value.name.trim(),
      edition: submitForm.value.edition.trim(),
    }
    if (submitForm.value.url.trim()) payload.official_url = submitForm.value.url.trim()
    if (submitForm.value.organizer.trim()) payload.organizer = submitForm.value.organizer.trim()
    if (submitForm.value.description.trim()) payload.description = submitForm.value.description.trim()
    if (submitForm.value.deadline.trim()) payload.deadline = `${submitForm.value.deadline.trim()}T23:59:00`

    const result = await command('innovation', 'submit_competition', '', { submission: payload })
    const id = String(result.data.submission_id ?? '')
    const row: SubmissionRow = {
      at: new Date().toISOString(),
      name: submitForm.value.name.trim(),
      edition: submitForm.value.edition.trim(),
      status: 'pending',
      id,
    }
    submissions.value = [row, ...submissions.value].slice(0, 20)
    persistSubmissions()
    submitNotice.value = result.message || '已提交审核大厅'
    submitForm.value = { name: '', edition: '', url: '', deadline: '', organizer: '', description: '' }
  } catch (reason) {
    submitNotice.value = reason instanceof Error ? reason.message : '提交失败'
  } finally {
    submitBusy.value = false
  }
}

/* ---------- 2. 组队匹配 ---------- */
interface TeamMatchRow {
  student_id: string
  display_name: string
  score: number
  matched_skills: string[]
}

const SKILL_POOL = ['前端开发', '算法建模', '数据分析', '硬件嵌入式', '视觉设计', '文案写作']

/** 从技能池里补一项到需求侧，权重先给 0.5。 */
function addTeamSkill() {
  const next = SKILL_POOL.find((skill) => !(skill in teamSkills.value))
  if (!next) {
    teamNotice.value = '技能池里的项目都已经加上了'
    return
  }
  teamSkills.value = { ...teamSkills.value, [next]: 0.5 }
  teamCandidates.value = teamCandidates.value.map((item) => ({
    ...item,
    skills: { ...item.skills, [next]: item.skills[next] ?? 0.4 },
  }))
}

function removeTeamSkill(skill: string) {
  if (Object.keys(teamSkills.value).length <= 1) {
    teamNotice.value = '至少保留一项技能'
    return
  }
  const next = { ...teamSkills.value }
  delete next[skill]
  teamSkills.value = next
}

const teamProject = ref('校园智能助手')
const teamSkills = ref<Record<string, number>>({ 前端开发: 0.8, 算法建模: 0.7, 数据分析: 0.5 })
const teamCandidates = ref<Array<{ name: string; skills: Record<string, number> }>>([])
const teamMatches = ref<TeamMatchRow[]>([])
const teamBusy = ref(false)
const teamNotice = ref('')

function ensureCandidateSkills(skills: Record<string, number>): Record<string, number> {
  const next: Record<string, number> = {}
  for (const skill of Object.keys(teamSkills.value)) {
    next[skill] = skills[skill] ?? 0.4
  }
  return next
}

function addCandidate() {
  const index = teamCandidates.value.length + 1
  teamCandidates.value = [
    ...teamCandidates.value,
    { name: `候选人 ${index}`, skills: ensureCandidateSkills({}) },
  ]
}

function removeCandidate(index: number) {
  teamCandidates.value = teamCandidates.value.filter((_, i) => i !== index)
}

/** 演示用的三位候选人，覆盖「强前端」「强算法」「均衡」三种画像。 */
function fillDemoCandidates() {
  teamCandidates.value = [
    {
      name: '李思远',
      skills: ensureCandidateSkills({ 前端开发: 0.92, 算法建模: 0.35, 数据分析: 0.55, 视觉设计: 0.7, 文案写作: 0.4 }),
    },
    {
      name: '王雨桐',
      skills: ensureCandidateSkills({ 前端开发: 0.4, 算法建模: 0.9, 数据分析: 0.85, 硬件嵌入式: 0.3, 文案写作: 0.5 }),
    },
    {
      name: '陈昱宁',
      skills: ensureCandidateSkills({ 前端开发: 0.7, 算法建模: 0.68, 数据分析: 0.62, 视觉设计: 0.55, 文案写作: 0.6 }),
    },
  ]
  teamNotice.value = '已填入 3 位示例候选人'
}

async function runMatch() {
  const required = Object.entries(teamSkills.value).filter(([, weight]) => weight > 0)
  if (!teamProject.value.trim()) {
    teamNotice.value = '先填项目名'
    return
  }
  if (!required.length) {
    teamNotice.value = '至少给一项技能设置大于 0 的权重'
    return
  }
  if (!teamCandidates.value.length) {
    teamNotice.value = '至少添加一位候选人'
    return
  }
  teamBusy.value = true
  teamNotice.value = ''
  try {
    const result = await command('innovation', 'match_team', '', {
      requirement: {
        project_name: teamProject.value.trim(),
        required_skills: Object.fromEntries(required),
        max_candidates: Math.min(20, teamCandidates.value.length),
      },
      profiles: teamCandidates.value.map((item, index) => ({
        student_id: `cand-${index + 1}`,
        display_name: item.name,
        skills: item.skills,
      })),
    })
    teamMatches.value = (result.data.matches ?? []) as TeamMatchRow[]
    teamNotice.value = teamMatches.value.length
      ? `匹配完成，共 ${teamMatches.value.length} 位候选人`
      : '没有候选人满足最低技能要求'
  } catch (reason) {
    teamNotice.value = reason instanceof Error ? reason.message : '匹配失败'
  } finally {
    teamBusy.value = false
  }
}

function scoreColor(score: number): string {
  if (score >= 0.8) return '#2f7a52'
  if (score >= 0.6) return '#c98a2b'
  return '#8a9994'
}

function setWeight(skill: string, event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  teamSkills.value = { ...teamSkills.value, [skill]: value }
}

function setCandidateName(index: number, event: Event) {
  const value = (event.target as HTMLInputElement).value
  teamCandidates.value = teamCandidates.value.map((item, i) =>
    i === index ? { ...item, name: value } : item,
  )
}

function setCandidateSkill(index: number, skill: string, event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  teamCandidates.value = teamCandidates.value.map((item, i) =>
    i === index ? { ...item, skills: { ...item.skills, [skill]: value } } : item,
  )
}

function candidateSkill(index: number, skill: string): number {
  return teamCandidates.value[index]?.skills[skill] ?? 0
}

function candidateName(index: number): string {
  return teamCandidates.value[index]?.name ?? ''
}

/* ---------- 3. 我想参加的比赛 ---------- */
const WISH_KEY = 'zhq-innovation-wishlist-v1'
const WISH_STAGES = ['观望中', '备赛中', '组队中', '已报名', '已提交'] as const

interface WishRow {
  id: string
  name: string
  deadline: string
  stage: string
  note: string
  addedAt: string
}

const wishlist = ref<WishRow[]>([])
const wishPick = ref('')
const wishManual = ref('')
const wishDeadline = ref('')
const wishNotice = ref('')

function loadWishlist() {
  try {
    const raw = localStorage.getItem(WISH_KEY)
    if (raw) wishlist.value = JSON.parse(raw) as WishRow[]
  } catch {
    wishlist.value = []
  }
}

function persistWishlist() {
  try {
    localStorage.setItem(WISH_KEY, JSON.stringify(wishlist.value.slice(0, 40)))
  } catch {
    // 隐私模式下写不进去，当次会话内仍然可用
  }
}

/** 剩余天数按本地 0 点算，避免 toISOString 的 UTC 偏移把日期算差一天 */
function daysLeft(deadline: string): number | null {
  if (!deadline) return null
  const target = new Date(`${deadline}T00:00:00`)
  if (Number.isNaN(target.getTime())) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((target.getTime() - today.getTime()) / 86400000)
}

function wishTone(deadline: string): string {
  const left = daysLeft(deadline)
  if (left === null) return 'is-none'
  if (left < 0) return 'is-over'
  if (left <= 7) return 'is-soon'
  return 'is-normal'
}

function wishCountdown(deadline: string): string {
  const left = daysLeft(deadline)
  if (left === null) return '未设截止'
  if (left < 0) return `已截止 ${-left} 天`
  if (left === 0) return '今天截止'
  return `还剩 ${left} 天`
}

const sortedWishlist = computed(() => [...wishlist.value].sort((left, right) => {
  const a = daysLeft(left.deadline)
  const b = daysLeft(right.deadline)
  if (a === null && b === null) return left.name.localeCompare(right.name)
  if (a === null) return 1
  if (b === null) return -1
  return a - b
}))

const wishStats = computed(() => ({
  total: wishlist.value.length,
  soon: wishlist.value.filter((row) => {
    const left = daysLeft(row.deadline)
    return left !== null && left >= 0 && left <= 30
  }).length,
  registered: wishlist.value.filter((row) => row.stage === '已报名' || row.stage === '已提交').length,
}))

function addWish(name: string, deadline = '') {
  const trimmed = name.trim()
  if (!trimmed) {
    wishNotice.value = '先选一个竞赛，或者手填个名字'
    return
  }
  if (wishlist.value.some((row) => row.name === trimmed)) {
    wishNotice.value = `「${trimmed}」已经在意向清单里了`
    return
  }
  const row: WishRow = {
    id: `wish-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name: trimmed,
    deadline,
    stage: WISH_STAGES[0],
    note: '',
    addedAt: new Date().toISOString(),
  }
  wishlist.value = [row, ...wishlist.value]
  persistWishlist()
  wishNotice.value = deadline
    ? `已加入「${trimmed}」，${wishCountdown(deadline)}`
    : `已加入「${trimmed}」，记得设一下报名截止`
}

function addWishFromCatalog() {
  if (!wishPick.value) {
    wishNotice.value = '先在下拉里选一个竞赛'
    return
  }
  const picked = competitions.value.find((item) => item.name === wishPick.value)
  addWish(wishPick.value)
  // 竞赛库里的报名时间是「每年 3–5 月」这类自然语言，没法自动转成截止日期，只能提示用户自己填
  if (picked?.registration && wishlist.value.some((row) => row.name === picked.name)) {
    wishNotice.value = `已加入「${picked.name}」，报名时间：${picked.registration}`
  }
  wishPick.value = ''
}

function addWishManual() {
  addWish(wishManual.value, wishDeadline.value)
  wishManual.value = ''
  wishDeadline.value = ''
}

function advanceStage(row: WishRow) {
  const index = WISH_STAGES.indexOf(row.stage as (typeof WISH_STAGES)[number])
  const next = WISH_STAGES[Math.min(WISH_STAGES.length - 1, index + 1)]
  if (next === row.stage) {
    wishNotice.value = `「${row.name}」已经在最后一档（已提交）了`
    return
  }
  wishlist.value = wishlist.value.map((item) => (item.id === row.id ? { ...item, stage: next } : item))
  persistWishlist()
  wishNotice.value = `「${row.name}」推进到「${next}」`
}

function removeWish(id: string) {
  wishlist.value = wishlist.value.filter((row) => row.id !== id)
  persistWishlist()
}

/** 把这条意向带进招人板块，比赛名直接填进招募表单 */
function wishToRecruit(row: WishRow) {
  recruitForm.value = { ...recruitForm.value, competition: row.name }
  activeTool.value = 'recruit'
  recruitNotice.value = `已把「${row.name}」带到招募表单，写一下缺什么人就发出去`
}

/* ---------- 4. 招人板块 ---------- */
const RECRUIT_MINE_KEY = 'zhq-innovation-recruit-mine-v1'
const RECRUIT_APPLIED_KEY = 'zhq-innovation-applied-v1'

interface RecruitMatchRow {
  student_id: string
  display_name: string
  score: number
  matched_skills: string[]
}

interface RecruitPost {
  post_id: string
  competition: string
  title: string
  owner: string
  slots: number
  deadline: string
  skills: Record<string, number>
  note: string
  match?: RecruitMatchRow | null
}

interface MyRecruit {
  id: string
  competition: string
  title: string
  slots: number
  deadline: string
  note: string
  skills: Record<string, number>
  at: string
}

const recruitPosts = ref<RecruitPost[]>([])
const recruitMine = ref<MyRecruit[]>([])
const appliedPosts = ref<string[]>([])
const recruitBusy = ref(false)
const recruitNotice = ref('')
/** 「我」的技能画像：招募板用它算匹配度，发布招募时也复用它当技能要求 */
const mySkills = ref<Record<string, number>>({ 前端开发: 0.8, 算法建模: 0.7, 数据分析: 0.5 })
const recruitForm = ref({ competition: '', title: '', slots: 1, deadline: '', note: '' })

function loadRecruitLocal() {
  try {
    const mine = localStorage.getItem(RECRUIT_MINE_KEY)
    if (mine) recruitMine.value = JSON.parse(mine) as MyRecruit[]
    const applied = localStorage.getItem(RECRUIT_APPLIED_KEY)
    if (applied) appliedPosts.value = JSON.parse(applied) as string[]
  } catch {
    recruitMine.value = []
    appliedPosts.value = []
  }
}

function persistRecruitLocal() {
  try {
    localStorage.setItem(RECRUIT_MINE_KEY, JSON.stringify(recruitMine.value.slice(0, 20)))
    localStorage.setItem(RECRUIT_APPLIED_KEY, JSON.stringify(appliedPosts.value.slice(0, 40)))
  } catch {
    // 忽略写入失败
  }
}

async function loadRecruitBoard() {
  recruitBusy.value = true
  recruitNotice.value = ''
  try {
    const result = await command('innovation', 'recruit_board', '', {
      my_skills: Object.fromEntries(Object.entries(mySkills.value).filter(([, value]) => value > 0)),
    })
    recruitPosts.value = (result.data.posts ?? []) as RecruitPost[]
    recruitNotice.value = result.message
  } catch (reason) {
    recruitNotice.value = reason instanceof Error ? reason.message : '招募板加载失败'
  } finally {
    recruitBusy.value = false
  }
}

function setMySkill(skill: string, event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  mySkills.value = { ...mySkills.value, [skill]: value }
}

function addMySkill() {
  const used = new Set(Object.keys(mySkills.value))
  const free = SKILL_POOL.find((skill) => !used.has(skill))
  if (!free) {
    recruitNotice.value = '六项技能都在列表里了'
    return
  }
  mySkills.value = { ...mySkills.value, [free]: 0.5 }
}

function removeMySkill(skill: string) {
  const next = { ...mySkills.value }
  delete next[skill]
  mySkills.value = next
}

function publishRecruit() {
  const form = recruitForm.value
  if (!form.competition.trim() || !form.title.trim()) {
    recruitNotice.value = '「参加哪个比赛」和「缺什么人」这两项要填'
    return
  }
  const row: MyRecruit = {
    id: `mine-${Date.now()}`,
    competition: form.competition.trim(),
    title: form.title.trim(),
    slots: Math.max(1, Math.min(10, Number(form.slots) || 1)),
    deadline: form.deadline,
    note: form.note.trim(),
    skills: Object.fromEntries(Object.entries(mySkills.value).filter(([, value]) => value > 0)),
    at: new Date().toISOString(),
  }
  recruitMine.value = [row, ...recruitMine.value].slice(0, 20)
  persistRecruitLocal()
  recruitNotice.value = `招募已发布：${row.title}（缺 ${row.slots} 人）`
  recruitForm.value = { competition: '', title: '', slots: 1, deadline: '', note: '' }
}

function removeMyRecruit(id: string) {
  recruitMine.value = recruitMine.value.filter((row) => row.id !== id)
  persistRecruitLocal()
}

function applyPost(post: RecruitPost) {
  if (appliedPosts.value.includes(post.post_id)) {
    recruitNotice.value = `已经申请过「${post.title}」了，等对方回消息`
    return
  }
  appliedPosts.value = [post.post_id, ...appliedPosts.value]
  persistRecruitLocal()
  recruitNotice.value = `已向 ${post.owner} 发出申请：${post.title}`
}

function hasApplied(postId: string): boolean {
  return appliedPosts.value.includes(postId)
}

function skillWeightText(skills: Record<string, number>): string {
  return Object.entries(skills)
    .sort(([, a], [, b]) => b - a)
    .map(([skill, weight]) => `${skill} ${Math.round(weight * 100)}`)
    .join(' · ')
}

/* ---------- 5. 申报大纲（对齐官方九大要素 + 逐条自检） ---------- */
interface ProposalSection { id: string; title: string; weight_note: string; checkpoints: string[] }
interface ProposalOutline {
  project_name: string
  competition_name: string
  sections: string[]
  blueprint: ProposalSection[]
  source_note: string
  checkpoint_total: number
}

const PROPOSAL_CHECK_KEY = 'zhq-proposal-check-v1'

const proposalProject = ref('')
const proposalCompetition = ref('')
const proposalKeywords = ref('')
const proposalOutline = ref<ProposalOutline | null>(null)
const proposalBusy = ref(false)
const proposalNotice = ref('')
/** 自检勾选状态：key = 段落 id | 自检点序号，按项目名+赛事名一起存 */
const proposalChecked = ref<Record<string, boolean>>({})

function proposalStoreKey(): string {
  if (!proposalOutline.value) return ''
  return `${proposalOutline.value.project_name}||${proposalOutline.value.competition_name}`
}

function checkKey(sectionId: string, index: number): string {
  return `${sectionId}|${index}`
}

function loadProposalChecks() {
  try {
    const raw = localStorage.getItem(PROPOSAL_CHECK_KEY)
    const parsed = raw ? JSON.parse(raw) as Record<string, Record<string, boolean>> : {}
    proposalChecked.value = parsed[proposalStoreKey()] ?? {}
  } catch {
    proposalChecked.value = {}
  }
}

function persistProposalChecks() {
  if (!proposalOutline.value) return
  try {
    const raw = localStorage.getItem(PROPOSAL_CHECK_KEY)
    const parsed = raw ? JSON.parse(raw) as Record<string, Record<string, boolean>> : {}
    parsed[proposalStoreKey()] = proposalChecked.value
    localStorage.setItem(PROPOSAL_CHECK_KEY, JSON.stringify(parsed))
  } catch {
    // 隐私模式下写不进去，勾选仍然在当前会话可用
  }
}

function toggleCheck(sectionId: string, index: number) {
  const key = checkKey(sectionId, index)
  proposalChecked.value = { ...proposalChecked.value, [key]: !proposalChecked.value[key] }
  persistProposalChecks()
}

const proposalTotal = computed(() => proposalOutline.value?.blueprint.reduce((sum, item) => sum + item.checkpoints.length, 0) ?? 0)
const proposalDone = computed(() => Object.values(proposalChecked.value).filter(Boolean).length)
const proposalPercent = computed(() => (proposalTotal.value ? Math.round((proposalDone.value / proposalTotal.value) * 100) : 0))
/** 一段都没勾的段落：直接告诉用户「哪几段是空的」，比给个百分比有用 */
const proposalEmptySections = computed(() => {
  const outline = proposalOutline.value
  if (!outline) return []
  return outline.blueprint
    .filter((section) => section.checkpoints.every((_, index) => !proposalChecked.value[checkKey(section.id, index)]))
    .map((section) => section.title.replace(/^[一二三四五六七八九十]+、/, ''))
})

async function generateProposal() {
  if (!proposalProject.value.trim() || !proposalCompetition.value.trim()) {
    proposalNotice.value = '项目名和赛事名都要填'
    return
  }
  proposalBusy.value = true
  proposalNotice.value = ''
  try {
    const keywords = proposalKeywords.value
      .split(/[,，、\s]+/)
      .map((item) => item.trim())
      .filter(Boolean)
    const result = await command('innovation', 'proposal_outline', '', {
      project_name: proposalProject.value.trim(),
      competition_name: proposalCompetition.value.trim(),
      technical_keywords: keywords,
    })
    proposalOutline.value = result.data as unknown as ProposalOutline
    loadProposalChecks()
    proposalNotice.value = `已按官方九大要素生成 ${proposalOutline.value.sections.length} 段、${proposalTotal.value} 条自检点`
  } catch (reason) {
    proposalNotice.value = reason instanceof Error ? reason.message : '生成失败'
  } finally {
    proposalBusy.value = false
  }
}

function proposalMarkdown(): string {
  const outline = proposalOutline.value
  if (!outline) return ''
  const lines = [
    `# ${outline.project_name} 申报书大纲`,
    '',
    `参赛赛事：${outline.competition_name}`,
    `自检进度：${proposalDone.value} / ${proposalTotal.value}（${proposalPercent.value}%）`,
    '',
  ]
  for (const section of outline.blueprint) {
    lines.push(`## ${section.title}`, '', `> 评委看什么：${section.weight_note}`, '')
    section.checkpoints.forEach((point, index) => {
      const mark = proposalChecked.value[checkKey(section.id, index)] ? 'x' : ' '
      lines.push(`- [${mark}] ${point}`)
    })
    lines.push('')
  }
  if (outline.source_note) lines.push(`---`, outline.source_note, '')
  return lines.join('\n')
}

async function copyProposal() {
  const text = proposalMarkdown()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    proposalNotice.value = '大纲与自检清单已复制到剪贴板'
  } catch {
    proposalNotice.value = '浏览器不允许写剪贴板，请手动选中复制'
  }
}

function exportProposal() {
  const text = proposalMarkdown()
  if (!text) return
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')
  anchor.href = url
  anchor.download = `${proposalOutline.value?.project_name || '申报大纲'}-${stamp}.md`
  anchor.click()
  URL.revokeObjectURL(url)
  proposalNotice.value = '已导出 Markdown（含自检勾选状态）'
}

onMounted(() => {
  fetchCompetitions()
  loadSubmissions()
  loadWishlist()
  loadRecruitLocal()
})
</script>

<template>
  <section class="innovation-page" :class="{ 'detail-mode': selectedCompetition }">
    <!-- 竞赛详情 -->
    <div v-if="selectedCompetition" class="competition-detail">
      <div class="detail-top-bar">
        <button class="back-btn" @click="backToList"><PhArrowLeft :size="18" /> 返回列表</button>
        <div class="detail-title-row">
          <h1>{{ selectedCompetition.name }}</h1>
          <span class="category-tag">{{ selectedCompetition.category }}</span>
          <span class="level-tag">{{ selectedCompetition.level }}</span>
        </div>
      </div>
      
      <!-- 数据说明 -->
      <div class="data-notice">
        <PhClock :size="16" />
        <span>{{ selectedCompetition.note }}（{{ selectedCompetition.year }}学年）</span>
      </div>
      
      <!-- 信息卡片行 -->
      <div class="detail-info-row">
        <div class="info-card-h">
          <div class="info-icon"><PhUsers :size="22" /></div>
          <div><span class="info-label">建议队伍人数</span><span class="info-val">{{ selectedCompetition.teamSize }} 人</span></div>
        </div>
        <div class="info-card-h">
          <div class="info-icon"><PhStar :size="22" /></div>
          <div><span class="info-label">难度</span><span class="info-val" :style="{color: difficultyColor(selectedCompetition.difficulty)}">{{ selectedCompetition.difficulty }}</span></div>
        </div>
        <div class="info-card-h">
          <div class="info-icon"><PhTarget :size="22" /></div>
          <div><span class="info-label">学校认定类别</span><span class="info-val">{{ selectedCompetition.level }}</span></div>
        </div>
        <div class="info-card-h">
          <div class="info-icon"><PhTrophy :size="22" /></div>
          <div><span class="info-label">校内获奖总数</span><span class="info-val">{{ getTotalAwards(selectedCompetition.awards) }} 项</span></div>
        </div>
      </div>

      <!-- 含金量 -->
      <div v-if="selectedCompetition.value" class="value-block">
        <div class="value-head">
          <div class="value-score-box" :style="{ backgroundColor: ratingBg(selectedCompetition.value.rating), borderColor: ratingColor(selectedCompetition.value.rating) }">
            <span class="value-score" :style="{ color: ratingColor(selectedCompetition.value.rating) }">{{ selectedCompetition.value.score }}</span>
            <span class="value-score-unit">/ 100</span>
          </div>
          <div class="value-head-text">
            <div class="value-title-row">
              <h3><PhChartBar :size="20" weight="duotone" /> 含金量</h3>
              <span class="value-rating" :style="{ color: ratingColor(selectedCompetition.value.rating), backgroundColor: ratingBg(selectedCompetition.value.rating), borderColor: ratingColor(selectedCompetition.value.rating) }">
                {{ selectedCompetition.value.rating }}
              </span>
              <span class="value-tier">学校认定 {{ selectedCompetition.value.schoolTier }}</span>
            </div>
            <p class="value-summary">{{ selectedCompetition.value.summary }}</p>
          </div>
        </div>

        <div class="value-bar">
          <div class="value-bar-fill" :style="{ width: selectedCompetition.value.score + '%', background: ratingColor(selectedCompetition.value.rating) }"></div>
        </div>

        <div class="value-meta">
          <span><b>{{ selectedCompetition.value.nationalAwards }}</b> 项国家级认定</span>
          <span><b>{{ selectedCompetition.value.provincialAwards }}</b> 项省级认定</span>
          <span><b>{{ selectedCompetition.value.schoolLevelAwards }}</b> 项校级</span>
          <span class="value-rarity">{{ selectedCompetition.value.rarityNote }}</span>
        </div>

        <div class="value-uses">
          <span class="value-uses-label">这个奖项能用在</span>
          <span v-for="use in selectedCompetition.value.uses" :key="use" class="value-use-chip">{{ use }}</span>
        </div>
      </div>

      <!-- 简介 + 官网 -->
      <div class="detail-body">
        <div class="detail-desc-block">
          <h3><PhBookOpen :size="20" /> 竞赛简介</h3>
          <p v-if="selectedCompetition.intro" class="competition-intro">{{ selectedCompetition.intro }}</p>
          <p><strong>主办单位：</strong>{{ selectedCompetition.organizer || '以当年通知为准' }}</p>
          <p v-if="selectedCompetition.audience" class="audience-line">
            <strong>适合谁：</strong>{{ selectedCompetition.audience }}
          </p>
          <p class="detail-links-row">
            <a v-if="selectedCompetition.website" :href="selectedCompetition.website" target="_blank" rel="noopener noreferrer" class="official-link">
              <PhArrowSquareOut :size="15" /> 访问官网
            </a>
            <span v-if="selectedCompetition.registration" class="detail-inline-note">
              报名参考：{{ selectedCompetition.registration }}
            </span>
          </p>
        </div>
      </div>

      <!-- 赛事亮点 -->
      <div v-if="selectedCompetition.highlights?.length" class="detail-highlights">
        <h3><PhLightbulb :size="20" /> 赛事亮点与注意事项</h3>
        <ul>
          <li v-for="item in selectedCompetition.highlights" :key="item">{{ item }}</li>
        </ul>
      </div>

      <!-- 关键信息：报名、赛程、费用、赛道 -->
      <div class="detail-keyfacts">
        <div class="keyfact">
          <span class="keyfact-label"><PhCalendar :size="15" /> 大致报名时间</span>
          <p>{{ selectedCompetition.registration || '以当年通知为准' }}</p>
        </div>
        <div class="keyfact">
          <span class="keyfact-label"><PhClock :size="15" /> 赛程安排</span>
          <p>{{ selectedCompetition.schedule || '以当年通知为准' }}</p>
        </div>
        <div class="keyfact">
          <span class="keyfact-label">💰 大致费用</span>
          <p>{{ selectedCompetition.fee || '以当年通知为准' }}</p>
        </div>
        <div class="keyfact">
          <span class="keyfact-label"><PhFunnel :size="15" /> 赛道 / 组别</span>
          <div class="chip-wrap tight">
            <span v-for="track in selectedCompetition.tracks" :key="track" class="chip">{{ track }}</span>
            <span v-if="!selectedCompetition.tracks?.length" class="keyfact-empty">以当年通知为准</span>
          </div>
        </div>
      </div>
      <p class="keyfacts-note">报名时间、赛程与费用为往年规律整理，用于提前规划；具体以主办方当年通知为准。</p>

      <!-- 需要学什么 -->
      <div class="detail-bottom-row">
        <div class="bottom-card">
          <h4><PhMedal :size="18" /> 主要需要学习的内容</h4>
          <div class="chip-wrap">
            <span v-for="s in selectedCompetition.skills" :key="s" class="chip green">{{ s }}</span>
            <span v-if="!selectedCompetition.skills?.length" class="keyfact-empty">暂无</span>
          </div>
        </div>
        <div class="bottom-card">
          <h4><PhLightbulb :size="18" /> 备赛建议</h4>
          <p class="tips-copy">{{ selectedCompetition.tips || '暂无' }}</p>
        </div>
      </div>

      <!-- 备赛路线 -->
      <div v-if="selectedCompetition.prep" class="detail-prep">
        <h3><PhRocketLaunch :size="20" /> 备赛路线（从零到参赛）</h3>
        <p>{{ selectedCompetition.prep }}</p>
      </div>

      <!-- 获奖情况 -->
      <div class="awards-detail">
        <h3><PhTrophy :size="20" /> 校内获奖情况</h3>
        <div class="awards-grid">
          <div v-for="(count, level) in selectedCompetition.awards" :key="level" class="award-item" :style="{backgroundColor: awardLevelBg(level), borderColor: awardLevelColor(level)}">
            <span class="award-level" :style="{color: awardLevelColor(level)}">{{ level }}</span>
            <span class="award-count">{{ count }}项</span>
          </div>
        </div>
        <div class="award-legend">
          <p><strong>等级说明：</strong></p>
          <p>A1/A2/A3 = A类竞赛国家级特等/一等/二等/三等</p>
          <p>B1/B2/B3 = B类竞赛国家级一等/二等/三等</p>
          <p>C1/C2/C3 = C类竞赛省级一等/二等/三等</p>
          <p>D1/D2/D3 = D类竞赛校级一等/二等/三等</p>
          <p>校级 / 不入级 = 校级竞赛奖项，或省级以上三等奖未达到学校认定等级</p>
        </div>
      </div>

      <!-- 文档与资源 -->
      <div class="detail-docs">
        <h3><PhBookOpen :size="20" /> 直达链接</h3>
        <div class="doc-list">
          <a v-for="doc in selectedCompetition.documents" :key="doc.url" :href="doc.url" target="_blank" rel="noopener noreferrer" class="doc-link" :class="{ 'is-official': doc.kind === 'official' }">
            <PhArrowSquareOut :size="15" />
            <span>{{ doc.title }}</span>
          </a>
        </div>
        <p class="keyfacts-note">链接均指向官网或官方通知页，点击在新标签页打开。</p>
      </div>
    </div>
    
    <!-- 竞赛列表 -->
    <template v-else>
      <main class="innovation-feed">
        <header class="innovation-masthead">
          <div>
            <span><PhNewspaper :size="18" /> 竞赛信息中心</span>
            <h1>山东师范大学竞赛成绩，<br><em>以赛促学，以赛促创。</em></h1>
            <p>收录 {{ competitions.length }} 个学校有参赛经验的竞赛，{{ categories.length - 1 }} 个类别</p>
          </div>
          <div class="launch-stamp"><PhTrophy :size="38" weight="duotone" /><strong>SDNU<br>COMPETE</strong></div>
        </header>
        
        <!-- 数据说明 -->
        <div class="data-notice-banner">
          <PhClock :size="16" />
          <span>获奖数据为 2024-2025 学年学校统计结果；含金量评分综合学校认定类别、国家级获奖突破与赛事行业认可度换算，仅供参考；报名时间、赛程与费用为往年规律整理，具体以主办方当年通知为准。</span>
        </div>
        
        <div class="feed-controls">
          <label><PhMagnifyingGlass :size="19" /><input v-model="search" placeholder="搜索竞赛" @input="fetchCompetitions"></label>
          <div><PhFunnel :size="17" /><button v-for="item in categories" :key="item" :class="{active:category===item}" @click="category=item;fetchCompetitions()">{{ item }}</button></div>
        </div>

        <div class="sort-row">
          <span class="sort-label">排序</span>
          <button :class="{ active: sortBy === 'value' }" @click="sortBy = 'value'">按含金量</button>
          <button :class="{ active: sortBy === 'awards' }" @click="sortBy = 'awards'">按校内获奖数</button>
          <button :class="{ active: sortBy === 'default' }" @click="sortBy = 'default'">按录入顺序</button>
          <span class="sort-legend">
            <span v-for="item in ratingSummary" :key="item.rating" class="sort-legend-item">
              <i :style="{ backgroundColor: ratingColor(item.rating) }"></i>{{ item.rating }} {{ item.count }}
            </span>
          </span>
        </div>

        <section class="notice-stream">
          <article v-for="comp in sortedCompetitions" :key="comp.id" class="competition-card" @click="viewDetail(comp)">
            <div class="notice-kind">
              <span class="category-tag">{{ comp.category }}</span>
              <span
                v-if="comp.value"
                class="value-badge"
                :style="{ color: ratingColor(comp.value.rating), backgroundColor: ratingBg(comp.value.rating), borderColor: ratingColor(comp.value.rating) }"
                :title="`含金量 ${comp.value.score}/100 · ${comp.value.rating}`"
              >含金量 {{ comp.value.score }}</span>
            </div>
            <div class="competition-info">
              <h2>{{ comp.name }}</h2>
              <p v-if="comp.intro" class="card-intro">{{ comp.intro }}</p>
              <div class="competition-meta">
                <span><PhUsers :size="14" /> {{ comp.teamSize }} 人</span>
                <span :style="{color:difficultyColor(comp.difficulty)}"><PhStar :size="14" /> 难度 {{ comp.difficulty }}</span>
                <span v-if="comp.level"><PhTarget :size="14" /> {{ comp.level }}</span>
                <span><PhTrophy :size="14" /> {{ getTotalAwards(comp.awards) }} 项获奖</span>
              </div>
              <div class="competition-meta muted">
                <span v-if="comp.registration"><PhCalendar :size="14" /> 报名：{{ comp.registration }}</span>
              </div>
              <div class="awards-preview">
                <span v-for="(count, level) in comp.awards" :key="level" class="award-badge" :style="{backgroundColor: awardLevelBg(level), color: awardLevelColor(level), borderColor: awardLevelColor(level)}">
                  {{ level }}: {{ count }}
                </span>
              </div>
            </div>
            <div class="card-footer"><span class="view-detail">查看详情 →</span></div>
          </article>
          
          <div v-if="loading" class="feed-empty">加载中...</div>
          <div v-else-if="!competitions.length" class="feed-empty">没有找到匹配内容</div>
        </section>
      </main>

      <aside class="innovation-rail">
        <header><h2>竞赛工具</h2></header>
        <nav>
          <button :class="{active:activeTool==='submit'}" @click="activeTool='submit'"><PhFilePlus :size="20" weight="duotone" /><span><strong>提交竞赛</strong></span></button>
          <button :class="{active:activeTool==='wish'}" @click="activeTool='wish'"><PhStar :size="20" weight="duotone" /><span><strong>我想参加</strong><em v-if="wishlist.length">{{ wishlist.length }}</em></span></button>
          <button :class="{active:activeTool==='recruit'}" @click="activeTool='recruit'"><PhMegaphone :size="20" weight="duotone" /><span><strong>招人板块</strong><em v-if="recruitMine.length">{{ recruitMine.length }}</em></span></button>
          <button :class="{active:activeTool==='team'}" @click="activeTool='team'"><PhUsersThree :size="20" weight="duotone" /><span><strong>组队匹配</strong></span></button>
          <button :class="{active:activeTool==='proposal'}" @click="activeTool='proposal'"><PhLightbulb :size="20" weight="duotone" /><span><strong>申报大纲</strong></span></button>
          <button v-if="isStaff" :class="{active:activeTool==='upload'}" @click="activeTool='upload'"><PhUpload :size="20" weight="duotone" /><span><strong>上传成果</strong></span></button>
        </nav>

        <section class="innovation-tool-panel">
          <!-- 提交竞赛 -->
          <div v-if="activeTool==='submit'" class="innx-panel">
            <h3>提交竞赛信息</h3>
            <p class="innx-hint">提交后进入审核大厅，通过才会发积分。信息越完整，审核越快。</p>
            <label class="innx-field">竞赛名称<input v-model="submitForm.name" placeholder="例如：中国大学生计算机设计大赛" maxlength="200"></label>
            <label class="innx-field">届次<input v-model="submitForm.edition" placeholder="例如：2026 年第十九届" maxlength="100"></label>
            <label class="innx-field">官网<input v-model="submitForm.url" placeholder="https://" maxlength="200"></label>
            <label class="innx-field">报名截止<input v-model="submitForm.deadline" type="date"></label>
            <label class="innx-field">主办单位<input v-model="submitForm.organizer" placeholder="可空" maxlength="200"></label>
            <label class="innx-field">说明<textarea v-model="submitForm.description" rows="2" maxlength="2000" placeholder="赛道、组别、参赛要求…"></textarea></label>
            <button class="ink-button primary" type="button" :disabled="submitBusy" @click="submitCompetition">
              {{ submitBusy ? '提交中…' : '提交审核' }}
            </button>
            <p v-if="submitNotice" class="innx-notice">{{ submitNotice }}</p>
          </div>

          <!-- 我想参加的比赛 -->
          <div v-if="activeTool==='wish'" class="innx-panel">
            <h3>我想参加的比赛</h3>
            <p class="innx-hint">把想打的比赛收进来，按报名截止倒计时排。推进阶段记录你到哪一步了。</p>

            <div class="innx-wish-stats">
              <span><strong>{{ wishStats.total }}</strong> 项意向</span>
              <span :class="{ 'is-warn': wishStats.soon > 0 }"><strong>{{ wishStats.soon }}</strong> 项 30 天内截止</span>
              <span><strong>{{ wishStats.registered }}</strong> 项已报名</span>
            </div>

            <label class="innx-field">从竞赛库选
              <select v-model="wishPick">
                <option value="">— 选一个竞赛 —</option>
                <option v-for="comp in competitions" :key="comp.id" :value="comp.name">{{ comp.name }}</option>
              </select>
            </label>
            <button class="ink-button" type="button" @click="addWishFromCatalog">加入意向</button>

            <div class="innx-wish-manual">
              <label class="innx-field">或者手填名称<input v-model="wishManual" placeholder="例如：中国高校计算机大赛" maxlength="120"></label>
              <label class="innx-field">报名截止<input v-model="wishDeadline" type="date"></label>
              <button class="ink-button" type="button" @click="addWishManual">加进去</button>
            </div>

            <p v-if="wishNotice" class="innx-notice">{{ wishNotice }}</p>

            <ul v-if="sortedWishlist.length" class="innx-wish-list">
              <li v-for="row in sortedWishlist" :key="row.id" class="innx-wish-row">
                <div class="innx-wish-head">
                  <strong>{{ row.name }}</strong>
                  <span class="innx-wish-count" :class="wishTone(row.deadline)">{{ wishCountdown(row.deadline) }}</span>
                </div>
                <div class="innx-wish-foot">
                  <button type="button" class="innx-stage" :class="`is-stage-${WISH_STAGES.indexOf(row.stage as (typeof WISH_STAGES)[number])}`" @click="advanceStage(row)">
                    {{ row.stage }} · 点一下推进
                  </button>
                  <span class="innx-wish-actions">
                    <button type="button" class="innx-mini" @click="wishToRecruit(row)">去招人</button>
                    <button type="button" class="innx-mini is-ghost" title="移除" @click="removeWish(row.id)">×</button>
                  </span>
                </div>
              </li>
            </ul>
            <p v-else class="innx-empty">还没有意向。从上面挑一个比赛加进来，报名季就不会漏。</p>
          </div>

          <!-- 招人板块 -->
          <div v-if="activeTool==='recruit'" class="innx-panel">
            <h3>招人板块</h3>
            <p class="innx-hint">先填「我的技能」，后端按技能向量算你和每条招募的重合度，再决定申请哪队。</p>

            <div class="innx-sub-head">
              <span>我的技能</span>
              <button type="button" class="innx-mini" @click="addMySkill">+ 加一项</button>
            </div>
            <div v-for="(weight, skill) in mySkills" :key="skill" class="innx-slider-row">
              <span class="innx-skill-name">{{ skill }}</span>
              <input type="range" min="0" max="1" step="0.1" :value="weight" @input="setMySkill(String(skill), $event)">
              <em>{{ Math.round(Number(weight) * 100) }}</em>
              <button type="button" class="innx-mini is-ghost" title="移除" @click="removeMySkill(String(skill))">×</button>
            </div>

            <button class="ink-button primary" type="button" :disabled="recruitBusy" @click="loadRecruitBoard">
              {{ recruitBusy ? '加载中…' : '看谁能带我' }}
            </button>
            <p v-if="recruitNotice" class="innx-notice">{{ recruitNotice }}</p>

            <div v-if="recruitPosts.length" class="innx-recruit-list">
              <article v-for="post in recruitPosts" :key="post.post_id" class="innx-recruit-card">
                <div class="innx-recruit-head">
                  <strong>{{ post.title }}</strong>
                  <span v-if="post.match" class="innx-recruit-score" :style="{ color: scoreColor(post.match.score) }">
                    {{ Math.round(post.match.score * 100) }}%
                  </span>
                  <span v-else class="innx-recruit-score is-none">技能不重合</span>
                </div>
                <p class="innx-recruit-meta">{{ post.competition }} · {{ post.owner }} · 缺 {{ post.slots }} 人 · 截止 {{ post.deadline }}</p>
                <p class="innx-recruit-note">{{ post.note }}</p>
                <p class="innx-recruit-skills">要：{{ skillWeightText(post.skills) }}</p>
                <div v-if="post.match && post.match.matched_skills.length" class="innx-match-skills">
                  <span v-for="skill in post.match.matched_skills" :key="skill">{{ skill }}</span>
                </div>
                <button
                  type="button"
                  class="innx-mini"
                  :class="{ 'is-applied': hasApplied(post.post_id) }"
                  @click="applyPost(post)"
                >{{ hasApplied(post.post_id) ? '已申请' : '申请加入' }}</button>
              </article>
            </div>

            <div class="innx-sub-head">
              <span>我发布的招募（{{ recruitMine.length }}）</span>
            </div>
            <label class="innx-field">参加哪个比赛<input v-model="recruitForm.competition" placeholder="例如：中国大学生计算机设计大赛" maxlength="120"></label>
            <label class="innx-field">缺什么人<input v-model="recruitForm.title" placeholder="例如：缺一个做视觉的" maxlength="80"></label>
            <label class="innx-field">缺几人<input v-model.number="recruitForm.slots" type="number" min="1" max="10"></label>
            <label class="innx-field">报名截止<input v-model="recruitForm.deadline" type="date"></label>
            <label class="innx-field">补充说明<textarea v-model="recruitForm.note" rows="2" maxlength="300" placeholder="现有几人、做什么方向、对什么技能有要求…"></textarea></label>
            <button class="ink-button primary" type="button" @click="publishRecruit">发布招募</button>

            <ul v-if="recruitMine.length" class="innx-mine-list">
              <li v-for="row in recruitMine" :key="row.id">
                <div>
                  <strong>{{ row.title }}</strong>
                  <p>{{ row.competition }} · 缺 {{ row.slots }} 人<span v-if="row.deadline"> · 截止 {{ row.deadline }}</span></p>
                  <p v-if="Object.keys(row.skills).length" class="innx-mine-skills">要：{{ skillWeightText(row.skills) }}</p>
                </div>
                <button type="button" class="innx-mini is-ghost" title="下架" @click="removeMyRecruit(row.id)">×</button>
              </li>
            </ul>
            <p v-else class="innx-empty">还没发过招募。填完上面几项就能挂出来。</p>
          </div>

          <!-- 组队匹配 -->
          <div v-if="activeTool==='team'" class="innx-panel">
            <h3>组队匹配</h3>
            <p class="innx-hint">按技能向量算加权相似度。权重越高，这项越关键。</p>

            <label class="innx-field">项目名<input v-model="teamProject" maxlength="80"></label>

            <div class="innx-sub-head">
              <span>技能权重</span>
              <button type="button" class="innx-mini" @click="addTeamSkill">+ 加一项</button>
            </div>
            <div v-for="(weight, skill) in teamSkills" :key="skill" class="innx-slider-row">
              <span class="innx-skill-name">{{ skill }}</span>
              <input type="range" min="0" max="1" step="0.1" :value="weight" @input="setWeight(String(skill), $event)">
              <em>{{ Math.round(Number(weight) * 100) }}</em>
              <button type="button" class="innx-mini is-ghost" title="移除" @click="removeTeamSkill(String(skill))">×</button>
            </div>

            <div class="innx-sub-head">
              <span>候选人（{{ teamCandidates.length }}）</span>
              <span class="innx-sub-actions">
                <button type="button" class="innx-mini" @click="fillDemoCandidates">示例</button>
                <button type="button" class="innx-mini" @click="addCandidate">+ 添加</button>
              </span>
            </div>

            <div v-for="(candidate, index) in teamCandidates" :key="index" class="innx-candidate">
              <div class="innx-candidate-head">
                <input :value="candidateName(index)" maxlength="20" @input="setCandidateName(index, $event)">
                <button type="button" class="innx-mini is-ghost" @click="removeCandidate(index)">×</button>
              </div>
              <div v-for="(_, skill) in teamSkills" :key="skill" class="innx-slider-row is-compact">
                <span class="innx-skill-name">{{ skill }}</span>
                <input type="range" min="0" max="1" step="0.1" :value="candidateSkill(index, String(skill))" @input="setCandidateSkill(index, String(skill), $event)">
                <em>{{ Math.round(candidateSkill(index, String(skill)) * 100) }}</em>
              </div>
            </div>

            <button class="ink-button primary" type="button" :disabled="teamBusy" @click="runMatch">
              {{ teamBusy ? '匹配中…' : '开始匹配' }}
            </button>
            <p v-if="teamNotice" class="innx-notice">{{ teamNotice }}</p>

            <div v-if="teamMatches.length" class="innx-matches">
              <div v-for="(match, index) in teamMatches" :key="match.student_id" class="innx-match-row">
                <div class="innx-match-head">
                  <strong>{{ match.display_name }}</strong>
                  <span v-if="index === 0" class="innx-best">最优</span>
                  <em :style="{ color: scoreColor(match.score) }">{{ Math.round(match.score * 100) }}%</em>
                </div>
                <div class="innx-match-bar">
                  <i :style="{ width: `${Math.round(match.score * 100)}%`, background: scoreColor(match.score) }" />
                </div>
                <div class="innx-match-skills">
                  <span v-for="skill in match.matched_skills" :key="skill">{{ skill }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 申报大纲 -->
          <div v-if="activeTool==='proposal'" class="innx-panel">
            <h3>申报大纲</h3>
            <p class="innx-hint">按项目名、赛事和技术关键词生成章节骨架，导出后直接往里面填内容。</p>
            <label class="innx-field">项目名<input v-model="proposalProject" placeholder="例如：校园智能助手" maxlength="80"></label>
            <label class="innx-field">参赛赛事<input v-model="proposalCompetition" placeholder="例如：中国大学生计算机设计大赛" maxlength="120"></label>
            <label class="innx-field">技术关键词<input v-model="proposalKeywords" placeholder="FastAPI、Vue3、多 Agent（逗号分隔）" maxlength="200"></label>
            <button class="ink-button primary" type="button" :disabled="proposalBusy" @click="generateProposal">
              {{ proposalBusy ? '生成中…' : '生成大纲' }}
            </button>
            <p v-if="proposalNotice" class="innx-notice">{{ proposalNotice }}</p>

            <div v-if="proposalOutline" class="innx-outline">
              <p class="innx-outline-head">{{ proposalOutline.project_name }} · {{ proposalOutline.competition_name }}</p>

              <div class="innx-progress">
                <div class="innx-progress-bar"><i :style="{ width: `${proposalPercent}%` }" /></div>
                <span>{{ proposalDone }} / {{ proposalTotal }} 条自检点（{{ proposalPercent }}%）</span>
              </div>
              <p v-if="proposalEmptySections.length" class="innx-outline-warn">
                <PhWarningCircle :size="15" /> 一段都没动的：{{ proposalEmptySections.join('、') }}
              </p>
              <p v-else-if="proposalTotal" class="innx-outline-ok">九段都动过了，接下来是往每条自检点里填证据。</p>

              <section v-for="section in proposalOutline.blueprint" :key="section.id" class="innx-section">
                <h4>{{ section.title }}</h4>
                <p class="innx-weight">评委看什么：{{ section.weight_note }}</p>
                <ul class="innx-checks">
                  <li v-for="(point, index) in section.checkpoints" :key="point">
                    <button
                      type="button"
                      :aria-pressed="Boolean(proposalChecked[checkKey(section.id, index)])"
                      @click="toggleCheck(section.id, index)"
                    >
                      <PhCheckCircle v-if="proposalChecked[checkKey(section.id, index)]" :size="17" weight="fill" />
                      <PhCircle v-else :size="17" />
                      <span :class="{ 'is-done': proposalChecked[checkKey(section.id, index)] }">{{ point }}</span>
                    </button>
                  </li>
                </ul>
              </section>

              <p v-if="proposalOutline.source_note" class="innx-outline-source">{{ proposalOutline.source_note }}</p>

              <div class="innx-outline-actions">
                <button type="button" class="innx-mini" @click="copyProposal">复制全文</button>
                <button type="button" class="innx-mini" @click="exportProposal">导出 Markdown</button>
              </div>
            </div>
          </div>

          <!-- 上传成果（staff） -->
          <div v-if="activeTool==='upload' && isStaff" class="innx-panel">
            <h3>上传竞赛成果</h3>
            <p class="innx-hint">批量导入获奖数据，导入后进入审核大厅。</p>
            <button class="ink-button primary" type="button" @click="error='批量导入需要管理员在上传页操作，当前演示环境未开放'">导入竞赛数据</button>
            <p class="innx-notice">演示环境保留入口，实际导入由管理员在后台完成。</p>
          </div>
        </section>

        <!-- 我的参赛档案 -->
        <div class="innx-archive">
          <div class="innx-archive-head">
            <h3>我的参赛档案</h3>
            <button v-if="submissions.length" type="button" class="innx-mini is-ghost" @click="clearSubmissions">清空</button>
          </div>
          <p class="innx-archive-stats">
            已提交 {{ submissionStats.total }} 项 · 待审 {{ submissionStats.pending }} · 通过 {{ submissionStats.approved }}
          </p>
          <ul v-if="submissions.length" class="innx-archive-list">
            <li v-for="row in submissions" :key="row.id + row.at">
              <span class="innx-archive-time">{{ row.at.slice(5, 16).replace('T', ' ') }}</span>
              <span class="innx-archive-name">{{ row.name }}</span>
              <span class="innx-archive-badge" :class="`is-${row.status}`">
                {{ row.status === 'pending' ? '待审' : row.status === 'approved' ? '通过' : '驳回' }}
              </span>
            </li>
          </ul>
          <p v-else class="innx-archive-empty">提交竞赛后会记在这里，换设备前记得截图。</p>
        </div>

        <div class="stats-panel">
          <h3>竞赛统计</h3>
          <div class="stat-item"><span>竞赛数</span><span class="stat-value">{{ competitions.length }}</span></div>
          <div class="stat-item"><span>类别数</span><span class="stat-value">{{ categories.length - 1 }}</span></div>
          <div class="stat-item"><span>校内获奖记录</span><span class="stat-value">{{ competitions.reduce((s, c) => s + getTotalAwards(c.awards), 0) }}</span></div>
          <div v-if="ratingSummary.length" class="stat-ratings">
            <span v-for="item in ratingSummary" :key="item.rating" class="stat-rating" :style="{ color: ratingColor(item.rating), backgroundColor: ratingBg(item.rating) }">
              {{ item.rating }} {{ item.count }}
            </span>
          </div>
        </div>
      </aside>
    </template>
  </section>
</template>

<style scoped>
/* ---------- 工具面板 ---------- */
.innx-panel {
  display: grid;
  gap: 10px;
}

.innx-panel h3 {
  margin: 0;
  color: #2f4a45;
  font-size: 15px;
}

.innx-hint {
  margin: 0;
  color: #7b8b86;
  font-size: 12px;
  line-height: 1.65;
}

.innx-field {
  display: grid;
  gap: 5px;
  color: #5d6f6a;
  font-size: 12px;
}

.innx-field input,
.innx-field textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid rgba(47, 74, 69, 0.16);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.9);
  color: #22302d;
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
}

.innx-field input:focus,
.innx-field textarea:focus {
  outline: 2px solid rgba(47, 122, 82, 0.28);
  border-color: rgba(47, 122, 82, 0.4);
}

.innx-notice {
  margin: 0;
  padding: 7px 10px;
  border-radius: 8px;
  background: rgba(47, 122, 82, 0.08);
  color: #2f7a52;
  font-size: 12px;
  line-height: 1.6;
}

.innx-sub-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
  color: #5d6f6a;
  font-size: 12px;
  font-weight: 600;
}

.innx-sub-actions {
  display: inline-flex;
  gap: 6px;
}

.innx-mini {
  padding: 3px 8px;
  border: 1px solid rgba(47, 74, 69, 0.18);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.92);
  color: #3f5350;
  font-size: 11.5px;
  font-family: inherit;
  cursor: pointer;
}

.innx-mini:hover {
  border-color: rgba(47, 122, 82, 0.45);
  color: #2f7a52;
}

.innx-mini.is-ghost {
  border-color: transparent;
  background: transparent;
  color: #97a5a0;
}

.innx-mini.is-ghost:hover {
  color: #b84a30;
}

/* ---------- 技能滑块 ---------- */
.innx-slider-row {
  display: grid;
  grid-template-columns: 68px minmax(0, 1fr) 30px 18px;
  gap: 7px;
  align-items: center;
}

.innx-slider-row.is-compact {
  grid-template-columns: 68px minmax(0, 1fr) 30px;
}

.innx-slider-row input[type='range'] {
  width: 100%;
  accent-color: #2f7a52;
}

.innx-skill-name {
  overflow: hidden;
  color: #4a5f5a;
  font-size: 11.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.innx-slider-row em {
  color: #7b8b86;
  font-size: 11px;
  font-style: normal;
  font-variant-numeric: tabular-nums;
  text-align: right;
}

/* ---------- 候选人 ---------- */
.innx-candidate {
  padding: 9px 10px;
  border: 1px solid rgba(47, 74, 69, 0.1);
  border-radius: 10px;
  background: rgba(255, 253, 248, 0.7);
}

.innx-candidate-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 18px;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
}

.innx-candidate-head input {
  width: 100%;
  padding: 5px 8px;
  border: 1px solid rgba(47, 74, 69, 0.14);
  border-radius: 7px;
  background: #fff;
  color: #22302d;
  font-size: 12.5px;
  font-family: inherit;
}

/* ---------- 匹配结果 ---------- */
.innx-matches {
  display: grid;
  gap: 10px;
  margin-top: 4px;
  padding-top: 10px;
  border-top: 1px dashed rgba(47, 74, 69, 0.16);
}

.innx-match-row {
  display: grid;
  gap: 5px;
}

.innx-match-head {
  display: flex;
  align-items: center;
  gap: 7px;
}

.innx-match-head strong {
  color: #22302d;
  font-size: 13px;
}

.innx-match-head em {
  margin-left: auto;
  font-size: 12.5px;
  font-style: normal;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.innx-best {
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(47, 122, 82, 0.14);
  color: #2f7a52;
  font-size: 10.5px;
  font-weight: 600;
}

.innx-match-bar {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(47, 74, 69, 0.09);
}

.innx-match-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  transition: width 0.3s ease;
}

.innx-match-skills {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.innx-match-skills span {
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(47, 74, 69, 0.07);
  color: #5d6f6a;
  font-size: 10.5px;
}

/* ---------- 侧栏计数徽标 ---------- */
.innovation-rail button em {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  margin-left: 6px;
  padding: 0 4px;
  border-radius: 999px;
  background: rgba(47, 74, 69, 0.12);
  color: #2f4a45;
  font-size: 10px;
  font-style: normal;
  font-weight: 700;
  line-height: 1;
  vertical-align: middle;
}

.innovation-rail button.active em {
  background: rgba(255, 255, 255, 0.28);
  color: #fff;
}

/* ---------- 我想参加的比赛 ---------- */
.innx-wish-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-bottom: 10px;
  color: #6a7b76;
  font-size: 11.5px;
}

.innx-wish-stats strong {
  color: #2f4a45;
  font-size: 14px;
  font-variant-numeric: tabular-nums;
}

.innx-wish-stats .is-warn strong {
  color: #b3261e;
}

.innx-wish-manual {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(47, 74, 69, 0.14);
}

.innx-wish-list {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.innx-wish-row {
  padding: 9px 11px;
  border: 1px solid rgba(47, 74, 69, 0.12);
  border-radius: 11px;
  background: rgba(255, 253, 248, 0.9);
}

.innx-wish-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.innx-wish-head strong {
  color: #2f4a45;
  font-size: 12.5px;
  line-height: 1.45;
}

.innx-wish-count {
  flex: none;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.innx-wish-count.is-normal {
  background: rgba(47, 122, 82, 0.12);
  color: #2f7a52;
}

.innx-wish-count.is-soon {
  background: rgba(201, 138, 43, 0.16);
  color: #a06c14;
}

.innx-wish-count.is-over {
  background: rgba(179, 38, 30, 0.12);
  color: #b3261e;
}

.innx-wish-count.is-none {
  background: rgba(47, 74, 69, 0.08);
  color: #7b8b86;
}

.innx-wish-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
}

.innx-stage {
  padding: 2px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: rgba(47, 74, 69, 0.08);
  color: #46605a;
  font-size: 10.5px;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease;
}

.innx-stage:hover {
  background: rgba(47, 74, 69, 0.16);
}

.innx-stage.is-stage-2 {
  background: rgba(201, 138, 43, 0.16);
  color: #a06c14;
}

.innx-stage.is-stage-3,
.innx-stage.is-stage-4 {
  background: rgba(47, 122, 82, 0.16);
  color: #2f7a52;
}

.innx-wish-actions {
  display: flex;
  align-items: center;
  gap: 5px;
}

.innx-empty {
  margin: 10px 0 0;
  padding: 12px;
  border: 1px dashed rgba(47, 74, 69, 0.18);
  border-radius: 11px;
  color: #7b8b86;
  font-size: 11.5px;
  line-height: 1.7;
  text-align: center;
}

/* ---------- 招人板块 ---------- */
.innx-recruit-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 10px 0 4px;
}

.innx-recruit-card {
  padding: 10px 12px;
  border: 1px solid rgba(47, 74, 69, 0.12);
  border-radius: 12px;
  background: rgba(255, 253, 248, 0.92);
}

.innx-recruit-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.innx-recruit-head strong {
  color: #2f4a45;
  font-size: 12.5px;
}

.innx-recruit-score {
  flex: none;
  font-size: 13px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.innx-recruit-score.is-none {
  color: #a4b0ab;
  font-size: 10.5px;
  font-weight: 600;
}

.innx-recruit-meta {
  margin: 3px 0 0;
  color: #7b8b86;
  font-size: 10.5px;
  line-height: 1.6;
}

.innx-recruit-note {
  margin: 5px 0 0;
  color: #4a5f5a;
  font-size: 11.5px;
  line-height: 1.65;
}

.innx-recruit-skills {
  margin: 5px 0 0;
  color: #8a9994;
  font-size: 10.5px;
}

.innx-recruit-card .innx-match-skills {
  margin-top: 5px;
}

.innx-recruit-card .innx-mini {
  margin-top: 7px;
}

.innx-mini.is-applied {
  background: rgba(47, 122, 82, 0.14);
  color: #2f7a52;
  cursor: default;
}

.innx-mine-list {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.innx-mine-list li {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-left: 3px solid rgba(47, 74, 69, 0.22);
  border-radius: 0 9px 9px 0;
  background: rgba(47, 74, 69, 0.04);
}

.innx-mine-list strong {
  color: #2f4a45;
  font-size: 12px;
}

.innx-mine-list p {
  margin: 2px 0 0;
  color: #7b8b86;
  font-size: 10.5px;
  line-height: 1.6;
}

.innx-mine-list .innx-mine-skills {
  color: #8a9994;
}

/* ---------- 申报大纲 ---------- */
.innx-outline {
  margin-top: 4px;
  padding: 11px 12px;
  border: 1px solid rgba(47, 74, 69, 0.12);
  border-radius: 11px;
  background: rgba(255, 253, 248, 0.85);
}

.innx-outline-head {
  margin: 0 0 8px;
  color: #2f4a45;
  font-size: 12.5px;
  font-weight: 600;
}

.innx-outline ol {
  margin: 0;
  padding-left: 18px;
  color: #3f5350;
  font-size: 12.5px;
  line-height: 1.9;
}

/* ---------- 九要素自检 ---------- */
.innx-progress {
  display: grid;
  gap: 5px;
  margin-bottom: 8px;
}

.innx-progress-bar {
  height: 5px;
  border-radius: 999px;
  background: rgba(47, 74, 69, 0.1);
  overflow: hidden;
}

.innx-progress-bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #2f7a52, #4f9b6d);
  transition: width 0.25s ease;
}

.innx-progress span {
  color: #7b8b86;
  font-size: 11.5px;
}

.innx-outline-warn {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  margin: 0 0 10px;
  padding: 7px 9px;
  border-left: 3px solid #c98a2b;
  border-radius: 0 7px 7px 0;
  background: rgba(201, 138, 43, 0.09);
  color: #8a5c15;
  font-size: 11.5px;
  line-height: 1.6;
}

.innx-outline-ok {
  margin: 0 0 10px;
  padding: 7px 9px;
  border-left: 3px solid rgba(47, 122, 82, 0.5);
  border-radius: 0 7px 7px 0;
  background: rgba(47, 122, 82, 0.07);
  color: #2f6b4c;
  font-size: 11.5px;
}

.innx-section {
  padding: 9px 0;
  border-top: 1px dashed rgba(47, 74, 69, 0.13);
}

.innx-section:first-of-type {
  border-top: none;
}

.innx-section h4 {
  margin: 0;
  color: #2f4a45;
  font-size: 12.5px;
  font-weight: 600;
}

.innx-weight {
  margin: 4px 0 7px;
  color: #7b8b86;
  font-size: 11.5px;
  line-height: 1.65;
}

.innx-checks {
  display: grid;
  gap: 3px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.innx-checks button {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  width: 100%;
  padding: 3px 0;
  border: none;
  background: none;
  color: #4c6b64;
  font-size: 11.5px;
  font-family: inherit;
  line-height: 1.6;
  text-align: left;
  cursor: pointer;
}

.innx-checks button:hover {
  color: #2f7a52;
}

.innx-checks button svg {
  flex: 0 0 auto;
  margin-top: 1px;
  color: #a8b3af;
}

.innx-checks button[aria-pressed='true'] svg {
  color: #2f7a52;
}

.innx-checks .is-done {
  color: #a8b3af;
  text-decoration: line-through;
}

.innx-outline-source {
  margin: 10px 0 0;
  color: #a8b3af;
  font-size: 11px;
  line-height: 1.65;
}

.innx-outline-actions {
  display: flex;
  gap: 7px;
  margin-top: 10px;
}

/* ---------- 参赛档案 ---------- */
.innx-archive {
  margin-top: 14px;
  padding: 12px 13px;
  border: 1px solid rgba(47, 74, 69, 0.12);
  border-radius: 12px;
  background: rgba(255, 253, 248, 0.72);
}

.innx-archive-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.innx-archive-head h3 {
  margin: 0;
  color: #2f4a45;
  font-size: 13px;
}

.innx-archive-stats {
  margin: 6px 0 8px;
  color: #7b8b86;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}

.innx-archive-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.innx-archive-list li {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr) auto;
  gap: 7px;
  align-items: center;
  font-size: 11.5px;
}

.innx-archive-time {
  color: #97a5a0;
  font-variant-numeric: tabular-nums;
}

.innx-archive-name {
  overflow: hidden;
  color: #3f5350;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.innx-archive-badge {
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 10.5px;
  font-weight: 600;
}

.innx-archive-badge.is-pending {
  background: rgba(201, 138, 43, 0.14);
  color: #a5701c;
}

.innx-archive-badge.is-approved {
  background: rgba(47, 122, 82, 0.14);
  color: #2f7a52;
}

.innx-archive-badge.is-rejected {
  background: rgba(184, 74, 48, 0.13);
  color: #b84a30;
}

.innx-archive-empty {
  margin: 0;
  color: #97a5a0;
  font-size: 11.5px;
  line-height: 1.7;
}
</style>