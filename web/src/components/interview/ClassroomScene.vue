<script setup lang="ts">
/**
 * 沉浸式复试教室：直接复用 classroom-preview.html 那份建模，不重写几何。
 *
 * 为什么用 iframe：那份教室是把 Three.js 和场景代码一起压缩成单个 IIFE 的产物，
 * 262 个网格、103 段几何，源码不可读也不可拆分。与其照抄一遍、必然走形，
 * 不如同源嵌进来，用它在页面上暴露的 window.__debug 驱动：
 *
 *   __debug = { scene, camera, controls, renderer,
 *               setView(i), setInterview(bool), setEvening(bool), viewNames, getState() }
 *
 * 父窗口能直接读到子窗口的 camera 矩阵，所以考官名牌仍然由 Vue 层投影定位，
 * 不依赖 iframe 内部的任何 DOM。
 */

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

type Phase = 'idle' | 'question' | 'answer' | 'report'

/** 写在后墙黑板上的内容。 */
export interface BoardContent {
  speaker: string
  intent: string
  question: string
  step: number
  total: number
}

const props = defineProps<{
  speaking?: string | null
  phase?: Phase
  /** lobby = 还没进面试；live/report = 已经在考场里。视角只认这个，不认 phase。 */
  stage?: 'lobby' | 'live' | 'report'
  board?: BoardContent | null
}>()

interface Seat {
  id: string
  name: string
  title: string
  /** 考官在世界坐标里的位置（取自 __debug 场景：examiner-0/1/2 都在 z=-4.03） */
  world: [number, number, number]
}

/** 三位考官：中间是组长，左侧专业课，右侧英语。与旧版命名保持一致。 */
const SEATS: Seat[] = [
  { id: 'major', name: '周敏行', title: '专业课 · 计算机与人工智能学院', world: [-1.22, 1.34, -4.03] },
  { id: 'host', name: '陈立群', title: '组长 · 复试专家组', world: [0, 1.34, -4.03] },
  { id: 'english', name: '苏静宜', title: '英语 · 外国语学院', world: [1.22, 1.34, -4.03] },
]

/** 大厅阶段的广角：预览自带的「教室实景」。 */
const VIEW_WIDE = 0

/**
 * 复试机位：坐姿视高、平视略仰，瞄点放在头顶上方留头。
 *
 * 预览自带的「考官近景」瞄 y=1.10，而考官头顶在 1.17——视线压在脸上、额头被裁，
 * 所以不用它的预设，按旧版的构图重新定：眼高 1.24、瞄 1.30、距考官 2.4 米、fov 58。
 */
const INTERVIEW_POSE = {
  pos: [0, 1.24, -1.62] as [number, number, number],
  target: [0, 1.30, -4.03] as [number, number, number],
  fov: 58,
}

/**
 * 说话时的机位：往该考官方向平移、fov 略收，另外两位仍留在画面里。
 *
 * 幅度是量出来的，不是拍的：第一版偏 0.52 米 + fov 52，说话者到了画面 -0.17，
 * 但另一侧的考官被推到 NDC +1.16，直接出画，就成了单人特写。
 * 现在这组参数下说话者约 -0.30，对侧约 +0.92，刚好还在画内。
 */
const SPEAKER_SHOTS: Record<string, { pos: [number, number, number]; target: [number, number, number]; fov: number }> = {
  host: { pos: [0, 1.25, -1.66], target: [0, 1.30, -4.03], fov: 56 },
  major: { pos: [-0.32, 1.25, -1.68], target: [-0.55, 1.30, -4.03], fov: 55 },
  english: { pos: [0.32, 1.25, -1.68], target: [0.55, 1.30, -4.03], fov: 55 },
}

/** 过渡时长：太短像硬切镜头，太长跟不上说话节奏。 */
const SHOT_MS = 620

const frame = ref<HTMLIFrameElement | null>(null)
const labelRoot = ref<HTMLElement | null>(null)
const failed = ref(false)
const ready = ref(false)
const labelEls = new Map<string, HTMLElement>()

let win: (Window & { __debug?: Record<string, any> }) | null = null
let raf = 0
let pollTimer = 0

/** 把考官世界坐标投到 iframe 画布像素坐标；z 越界或背对镜头时返回 null。 */
function project(cam: any, world: [number, number, number], width: number, height: number) {
  const view = cam?.matrixWorldInverse?.elements
  const proj = cam?.projectionMatrix?.elements
  if (!view || !proj) return null
  const [x, y, z] = world

  const vx = view[0] * x + view[4] * y + view[8] * z + view[12]
  const vy = view[1] * x + view[5] * y + view[9] * z + view[13]
  const vz = view[2] * x + view[6] * y + view[10] * z + view[14]
  const vw = view[3] * x + view[7] * y + view[11] * z + view[15]

  const cx = proj[0] * vx + proj[4] * vy + proj[8] * vz + proj[12] * vw
  const cy = proj[1] * vx + proj[5] * vy + proj[9] * vz + proj[13] * vw
  const cw = proj[3] * vx + proj[7] * vy + proj[11] * vz + proj[15] * vw
  if (cw <= 1e-4) return null

  const ndcX = cx / cw
  const ndcY = cy / cw
  const ndcZ = (proj[2] * vx + proj[6] * vy + proj[10] * vz + proj[14] * vw) / cw
  if (ndcZ > 1) return null

  return {
    x: (ndcX * 0.5 + 0.5) * width,
    y: (-ndcY * 0.5 + 0.5) * height,
    // 贴着画面边缘的考官（侧看时）淡出，避免名牌堆在边框上
    opacity: Math.min(1, Math.max(0, (1 - Math.abs(ndcX)) * 3)) * (ndcZ > -1 ? 1 : 0.35),
  }
}

function tick() {
  const cam = win?.__debug?.camera
  const root = labelRoot.value
  if (cam && root) {
    const width = root.clientWidth
    const height = root.clientHeight
    for (const seat of SEATS) {
      const el = labelEls.get(seat.id)
      if (!el) continue
      const point = project(cam, seat.world, width, height)
      if (!point) {
        el.style.opacity = '0'
        continue
      }
      el.style.transform = `translate3d(${point.x}px, ${point.y}px, 0) translate(-50%, -100%)`
      el.style.opacity = String(point.opacity)
    }
  }
  raf = requestAnimationFrame(tick)
}

/** 藏掉预览自带的页面外壳（标题、视角坞、帮助、关于），只留 3D 画面。 */
function dressFrame(doc: Document) {
  const style = doc.createElement('style')
  style.textContent = `
    html, body { margin: 0 !important; padding: 0 !important; overflow: hidden !important; background: #e0e5df !important; }
    .brand, .actions, .help, .bottom, .credit, .credits, #loading { display: none !important; }
    #app { position: fixed !important; inset: 0 !important; width: 100vw !important; height: 100vh !important; }
    #app canvas { display: block !important; width: 100% !important; height: 100% !important; }
  `
  doc.head.appendChild(style)
}

let shotRaf = 0

function cancelShot() {
  if (shotRaf) {
    cancelAnimationFrame(shotRaf)
    shotRaf = 0
  }
}

/**
 * 把相机平滑挪到目标机位。
 *
 * 只改 position / target / fov 三个量，剩下的交给 OrbitControls.update() 自己算朝向；
 * 过渡用 easeInOutQuad，起手和收尾都软，中途不会有一顿。
 */
function moveCameraTo(shot: { pos: [number, number, number]; target: [number, number, number]; fov: number }) {
  const debug = win?.__debug
  const cam = debug?.camera
  const controls = debug?.controls
  if (!cam || !controls?.target) return
  cancelShot()
  const fromPos = { x: cam.position.x, y: cam.position.y, z: cam.position.z }
  const fromTarget = { x: controls.target.x, y: controls.target.y, z: controls.target.z }
  const fromFov = typeof cam.fov === 'number' ? cam.fov : shot.fov
  const start = performance.now()
  const step = (now: number) => {
    const t = Math.min(1, Math.max(0, (now - start) / SHOT_MS))
    const eased = t < 0.5 ? 2 * t * t : 1 - ((-2 * t + 2) ** 2) / 2
    cam.position.set(
      fromPos.x + (shot.pos[0] - fromPos.x) * eased,
      fromPos.y + (shot.pos[1] - fromPos.y) * eased,
      fromPos.z + (shot.pos[2] - fromPos.z) * eased,
    )
    controls.target.set(
      fromTarget.x + (shot.target[0] - fromTarget.x) * eased,
      fromTarget.y + (shot.target[1] - fromTarget.y) * eased,
      fromTarget.z + (shot.target[2] - fromTarget.z) * eased,
    )
    if (typeof cam.fov === 'number') {
      cam.fov = fromFov + (shot.fov - fromFov) * eased
      cam.updateProjectionMatrix?.()
    }
    controls.update?.()
    shotRaf = t < 1 ? requestAnimationFrame(step) : 0
  }
  shotRaf = requestAnimationFrame(step)
}

/** 当前停在哪个机位。切换老师时直接从这个机位滑过去，中间不回中景。 */
let currentShot: { pos: [number, number, number]; target: [number, number, number]; fov: number } = INTERVIEW_POSE

/** 谁在说话就往谁那边偏。说完保持原位等下一个，不要退回中景再切过去。 */
function focusSpeaker(id: string | null | undefined) {
  if (props.stage === 'lobby') return
  if (!id || !SPEAKER_SHOTS[id]) return
  currentShot = SPEAKER_SHOTS[id]
  moveCameraTo(currentShot)
}

function applyView() {
  const debug = win?.__debug
  if (!debug) return
  cancelShot()

  // 大厅（还没进面试）：教室实景广角，允许拖动环顾
  if (props.stage === 'lobby') {
    currentShot = INTERVIEW_POSE
    try {
      debug.setInterview?.(false)
      debug.setView?.(VIEW_WIDE)
      if (debug.controls) debug.controls.enabled = true
    } catch {
      // 视角切换失败不影响画面本身
    }
    return
  }

  // 面试中：锁在考生机位，禁止拖动跑出画面。
  // 落点优先取「正在说话的人」，其次沿用上一帧的机位——不回落中景，
  // 否则每次提问都会先弹回三人全景再推过去。
  try {
    debug.setInterview?.(true)
    const cam = debug.camera
    const controls = debug.controls
    if (!cam || !controls?.target) {
      debug.setView?.(3)
      return
    }
    if (props.phase === 'report') currentShot = INTERVIEW_POSE
    const shot = (props.speaking && SPEAKER_SHOTS[props.speaking]) || currentShot
    currentShot = shot
    cam.position.set(...shot.pos)
    if (typeof cam.fov === 'number') {
      cam.fov = shot.fov
      cam.updateProjectionMatrix?.()
    }
    controls.target.set(...shot.target)
    controls.enabled = false
    controls.update?.()
  } catch {
    // 同上：机位设置失败时保持当前视角，画面仍然可用
  }
}

/* ----------------------------------------------------------------- 黑板 */

const BOARD_W = 2048
const BOARD_H = 640

let boardMesh: any = null
let boardBase: HTMLCanvasElement | null = null

/** 按字符折行：中英混排逐字试宽度，不依赖空格切分。 */
function wrapText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const lines: string[] = []
  let line = ''
  for (const char of text) {
    const next = line + char
    if (line && ctx.measureText(next).width > maxWidth) {
      lines.push(line)
      line = char
    } else {
      line = next
    }
  }
  if (line) lines.push(line)
  return lines
}

/**
 * 在场景里认黑板：后墙上一块几乎没厚度、约 5.7×1.7 米、带贴图的平面。
 * 那份模型里 mesh 一个名字都没有，只能按几何尺寸和世界坐标认。
 */
function locateBoard() {
  const scene = win?.__debug?.scene
  if (!scene || boardMesh) return
  let hit: any = null
  scene.traverse((obj: any) => {
    if (hit || !obj.isMesh || !obj.geometry || !obj.material?.map) return
    if (!obj.geometry.boundingBox) obj.geometry.computeBoundingBox?.()
    const box = obj.geometry.boundingBox
    if (!box) return
    const width = box.max.x - box.min.x
    const height = box.max.y - box.min.y
    const depth = box.max.z - box.min.z
    const matrix = obj.matrixWorld?.elements
    if (!matrix) return
    if (width > 5 && width < 6.4 && height > 1.4 && height < 2.0 && depth < 0.12 && matrix[14] < -4.4) hit = obj
  })
  if (!hit) return
  boardMesh = hit
  // 原贴图留一份快照：每次重绘都从它复制，否则会把上一次的字叠上去。
  const source = hit.material.map.image
  if (source) {
    const base = document.createElement('canvas')
    base.width = BOARD_W
    base.height = BOARD_H
    const ctx = base.getContext('2d')
    if (ctx) {
      try {
        ctx.drawImage(source as CanvasImageSource, 0, 0, BOARD_W, BOARD_H)
      } catch {
        // 贴图还没解码就退回纯色底，不影响后面写字
      }
    }
    boardBase = base
  }
  paintBoard()
}

/** 把当前这一问写到黑板上；还没出题时显示「准备中」。 */
function paintBoard() {
  const mesh = boardMesh
  if (!mesh?.material?.map) return
  const canvas = document.createElement('canvas')
  canvas.width = BOARD_W
  canvas.height = BOARD_H
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  if (boardBase) ctx.drawImage(boardBase, 0, 0)
  else {
    ctx.fillStyle = '#1d2b24'
    ctx.fillRect(0, 0, BOARD_W, BOARD_H)
  }
  // 压暗原贴图，保证粉笔字够清楚
  ctx.fillStyle = 'rgba(16, 27, 23, 0.78)'
  ctx.fillRect(0, 0, BOARD_W, BOARD_H)
  ctx.textAlign = 'center'

  const content = props.board
  if (!content) {
    ctx.fillStyle = 'rgba(242, 245, 239, 0.75)'
    ctx.font = '500 46px "LXGW WenKai", "Microsoft YaHei", sans-serif'
    ctx.fillText('准备中…', BOARD_W / 2, BOARD_H / 2 + 16)
  } else {
    ctx.fillStyle = 'rgba(242, 245, 239, 0.88)'
    ctx.font = '500 34px "Microsoft YaHei", "PingFang SC", sans-serif'
    ctx.fillText(`第 ${content.step} / ${content.total} 题　·　${content.speaker}`, BOARD_W / 2, 88)

    ctx.strokeStyle = 'rgba(242, 245, 239, 0.28)'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(BOARD_W * 0.12, 118)
    ctx.lineTo(BOARD_W * 0.88, 118)
    ctx.stroke()

    ctx.fillStyle = '#f2f5ef'
    ctx.font = '600 52px "LXGW WenKai", "Microsoft YaHei", "PingFang SC", sans-serif'
    const all = wrapText(ctx, content.question, BOARD_W * 0.84)
    const lines = all.slice(0, 4)
    if (all.length > 4) lines[3] = `${lines[3].slice(0, -1)}…`
    // 正文压在 canvas 上半部：黑板下沿正对考官头顶，写在下面会被挡住。
    const lineHeight = 76
    const startY = 300 - ((lines.length - 1) * lineHeight) / 2
    lines.forEach((line, index) => ctx.fillText(line, BOARD_W / 2, startY + index * lineHeight))

    ctx.fillStyle = 'rgba(242, 245, 239, 0.7)'
    ctx.font = '500 28px "Microsoft YaHei", "PingFang SC", sans-serif'
    ctx.fillText(`考察点：${content.intent}`, BOARD_W / 2, 486)
  }

  const map = mesh.material.map
  map.image = canvas
  map.needsUpdate = true
}

function attach() {
  const iframe = frame.value
  const child = iframe?.contentWindow as (Window & { __debug?: Record<string, any> }) | null
  const doc = iframe?.contentDocument
  if (!child || !doc) {
    failed.value = true
    return
  }
  win = child
  dressFrame(doc)
  applyView()
  locateBoard()
  // setInterview 换布置时可能自己动相机，稍后再压一次，确保停在我们定的机位
  window.setTimeout(applyView, 260)
  window.setTimeout(applyView, 700)
  child.dispatchEvent(new Event('resize'))
  ready.value = true
}

/** 等 __debug 出现：预览要等纹理和场景都建好才挂上去。 */
function waitForDebug(attempt = 0) {
  const child = frame.value?.contentWindow as (Window & { __debug?: Record<string, any> }) | null
  if (child?.__debug) {
    attach()
    return
  }
  if (attempt > 50) {
    failed.value = true
    return
  }
  pollTimer = window.setTimeout(() => waitForDebug(attempt + 1), 120)
}

function onFrameLoad() {
  waitForDebug()
}

function bindLabel(id: string, el: Element | null) {
  if (el instanceof HTMLElement) labelEls.set(id, el)
  else labelEls.delete(id)
}

watch(() => props.phase, applyView)
watch(() => props.stage, applyView)
watch(() => props.speaking, focusSpeaker)
watch(() => props.board, paintBoard)

onMounted(() => {
  raf = requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  cancelShot()
  window.clearTimeout(pollTimer)
  labelEls.clear()
  boardMesh = null
  boardBase = null
  win = null
})

defineExpose({ failed })
</script>

<template>
  <div ref="labelRoot" class="cls-root">
    <iframe
      ref="frame"
      class="cls-frame"
      :class="{ 'is-ready': ready }"
      src="/classroom.html"
      title="山东师范大学复试教室三维场景"
      allow="autoplay"
      @load="onFrameLoad"
    />
    <div class="cls-labels" aria-hidden="true">
      <div
        v-for="seat in SEATS"
        :key="seat.id"
        :ref="(el) => bindLabel(seat.id, el as Element | null)"
        class="examiner-tag"
        :class="{ 'is-speaking': props.speaking === seat.id }"
      >
        <strong>{{ seat.name }}</strong>
        <span>{{ seat.title }}</span>
      </div>
    </div>
    <p v-if="failed" class="cls-fallback">
      三维教室加载失败，面试流程不受影响。可以点「改用文字」继续作答。
    </p>
  </div>
</template>

<style scoped>
.cls-root {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: #101a1e;
}
.cls-frame {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  opacity: 0;
  transition: opacity .5s ease;
}
.cls-root:has(.cls-frame) .cls-frame { opacity: 1; }
.cls-frame.is-ready { opacity: 1; }
.cls-labels {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.cls-labels .examiner-tag {
  position: absolute;
  top: 0;
  left: 0;
  display: grid;
  gap: .05rem;
  padding: .3rem .55rem;
  text-align: center;
  white-space: nowrap;
  background: rgba(16, 34, 36, .62);
  border: 1px solid rgba(255, 255, 255, .16);
  border-radius: 9px;
  backdrop-filter: blur(6px);
  transition: opacity .18s ease, background .2s ease;
  will-change: transform, opacity;
}
.cls-fallback {
  position: absolute;
  inset: auto 0 12% 0;
  margin: 0 auto;
  width: min(88%, 420px);
  padding: .7rem .9rem;
  font-size: .8rem;
  line-height: 1.6;
  color: #ffe9c9;
  text-align: center;
  background: rgba(120, 58, 40, .78);
  border-radius: 10px;
}
</style>
