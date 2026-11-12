<script setup lang="ts">
/**
 * 沉浸式复试教室：用 Three.js 现场搭一个 3D 场景，不加载任何外部模型文件。
 *
 * 为什么全程序化建模而不是导 glTF：
 *   1. 答辩现场是离线环境，任何外部资源都可能加载失败；
 *   2. 程序化几何体的总体积比一个带贴图的 glTF 小两个数量级；
 *   3. 导师的姿态、朝向、发言状态都要随对话实时变化，程序化控制更直接。
 *
 * 构图是按真实复试现场的第一人称推出来的：
 *   考生坐在长桌前约 2.6 m 处，视线高度 1.28 m；
 *   画面下三分之一是桌面，中段是三位导师的上半身，上段是黑板与会标。
 *
 * 坐标系：Y 向上，考生在 +Z 一侧朝 -Z 看。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as THREE from 'three'

const props = defineProps<{
  /** 当前发言的考官 id；null 表示无人发言 */
  speaking?: string | null
  /** 现场状态，用于微调镜头与光 */
  phase?: 'idle' | 'question' | 'answer' | 'report'
}>()

const host = ref<HTMLDivElement | null>(null)
const labelRoot = ref<HTMLDivElement | null>(null)
const failed = ref(false)

interface ExaminerRig {
  id: string
  group: THREE.Group
  torso: THREE.Mesh
  head: THREE.Group
  shoulderL: THREE.Mesh
  shoulderR: THREE.Mesh
  anchor: THREE.Vector3
  phase: number
}

const EXAMINER_SEATS: Array<{ id: string; x: number; suit: number; tie: number; hair: number; scale: number }> = [
  { id: 'host', x: 0, suit: 0x2b3a52, tie: 0x8c2f39, hair: 0x241f1c, scale: 1.02 },
  { id: 'major', x: -1.25, suit: 0x39463c, tie: 0x3f5a72, hair: 0x1d1a18, scale: 1.0 },
  { id: 'english', x: 1.25, suit: 0x453246, tie: 0x9a7f52, hair: 0x2a2220, scale: 0.97 },
]

const EXAMINER_LABELS: Array<{ id: string; name: string; title: string }> = [
  { id: 'host', name: '陈立群', title: '复试组长 · 教授' },
  { id: 'major', name: '周敏行', title: '专业面试官 · 副教授' },
  { id: 'english', name: '苏静宜', title: '综合素质考官 · 副教授' },
]

// 房间与构图常量：改这里就能整体重新取景，不用到处找魔法数字
const ROOM_W = 10.4
const ROOM_D = 7.6
const ROOM_H = 3.5
const DESK_Z = -1.55
const EXAMINER_Z = -2.2
const CAMERA_POS = { x: 0, y: 1.3, z: 0.02 }
const CAMERA_FOV = 58
const LOOK_DEFAULT = { x: 0, y: 1.42, z: -2.3 }

let renderer: THREE.WebGLRenderer | undefined
let scene: THREE.Scene | undefined
let camera: THREE.PerspectiveCamera | undefined
let frame = 0
let observer: ResizeObserver | undefined
let sceneStart = 0
let rigs: ExaminerRig[] = []
let labels: Array<{ id: string; el: HTMLElement; anchor: THREE.Vector3 }> = []
let screenLight: THREE.PointLight | undefined
const disposables: Array<{ dispose: () => void }> = []
const lookAt = new THREE.Vector3(LOOK_DEFAULT.x, LOOK_DEFAULT.y, LOOK_DEFAULT.z)
const desiredLook = new THREE.Vector3(LOOK_DEFAULT.x, LOOK_DEFAULT.y, LOOK_DEFAULT.z)
const tmpVector = new THREE.Vector3()

/** 生成一张 canvas 贴图并登记释放。 */
function canvasTexture(width: number, height: number, draw: (ctx: CanvasRenderingContext2D) => void): THREE.CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (ctx) draw(ctx)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  disposables.push(texture)
  return texture
}

function mat(options: THREE.MeshStandardMaterialParameters): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial(options)
  disposables.push(material)
  return material
}

function mesh(geometry: THREE.BufferGeometry, material: THREE.Material, cast = true): THREE.Mesh {
  disposables.push(geometry)
  const item = new THREE.Mesh(geometry, material)
  item.castShadow = cast
  item.receiveShadow = true
  return item
}

/** 黑板：粉笔字直接画在 canvas 上，比贴图清晰且可以随时改文案。 */
function blackboardTexture(): THREE.CanvasTexture {
  return canvasTexture(1024, 400, (ctx) => {
    const bg = ctx.createLinearGradient(0, 0, 1024, 400)
    bg.addColorStop(0, '#22322a')
    bg.addColorStop(0.5, '#1d2b24')
    bg.addColorStop(1, '#243530')
    ctx.fillStyle = bg
    ctx.fillRect(0, 0, 1024, 400)
    ctx.globalAlpha = 0.06
    ctx.fillStyle = '#ffffff'
    for (let i = 0; i < 20; i += 1) {
      ctx.fillRect(Math.random() * 1024, Math.random() * 400, 110 + Math.random() * 170, 5 + Math.random() * 8)
    }
    ctx.globalAlpha = 1
    ctx.fillStyle = '#f2f5ef'
    ctx.textAlign = 'center'
    ctx.font = '600 40px "Microsoft YaHei", "PingFang SC", sans-serif'
    ctx.fillText('山东师范大学', 512, 66)
    ctx.font = '700 54px "Microsoft YaHei", "PingFang SC", sans-serif'
    ctx.fillText('2027 年硕士研究生招生复试', 512, 130)
    ctx.font = '500 34px "Microsoft YaHei", "PingFang SC", sans-serif'
    ctx.fillText('人工智能（0812）· 综合面试', 512, 178)
    ctx.strokeStyle = 'rgba(242,245,239,0.5)'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(170, 202)
    ctx.lineTo(854, 202)
    ctx.stroke()
    ctx.font = '500 26px "Microsoft YaHei", "PingFang SC", sans-serif'
    ctx.fillStyle = 'rgba(242,245,239,0.9)'
    ctx.fillText('一、中文自我介绍 1—2 分钟', 512, 246)
    ctx.fillText('二、专业基础与项目追问', 512, 288)
    ctx.fillText('三、英语问答 · 综合素质', 512, 330)
    ctx.font = '500 22px "Microsoft YaHei", "PingFang SC", sans-serif'
    ctx.fillStyle = 'rgba(242,245,239,0.55)'
    ctx.fillText('请按自己的思路回答，不必背稿', 512, 372)
  })
}

/** 红底白字的会标。 */
function bannerTexture(): THREE.CanvasTexture {
  return canvasTexture(1536, 144, (ctx) => {
    const bg = ctx.createLinearGradient(0, 0, 0, 144)
    bg.addColorStop(0, '#9d1f22')
    bg.addColorStop(1, '#7d1418')
    ctx.fillStyle = bg
    ctx.fillRect(0, 0, 1536, 144)
    ctx.fillStyle = '#f7e7c8'
    ctx.textAlign = 'center'
    ctx.font = '700 72px "Microsoft YaHei", "PingFang SC", sans-serif'
    ctx.fillText('人工智能专业硕士研究生复试现场', 768, 96)
    ctx.strokeStyle = 'rgba(247,231,200,0.45)'
    ctx.lineWidth = 3
    ctx.strokeRect(10, 10, 1516, 124)
  })
}

/** 木地板：横条纹 + 细微噪点，避免纯色显得假。 */
function floorTexture(): THREE.CanvasTexture {
  return canvasTexture(1024, 1024, (ctx) => {
    ctx.fillStyle = '#b39b7d'
    ctx.fillRect(0, 0, 1024, 1024)
    for (let row = 0; row < 16; row += 1) {
      const y = row * 64
      const offset = row % 2 === 0 ? 0 : 128
      for (let col = -1; col < 9; col += 1) {
        const x = col * 256 + offset
        const tone = 168 + Math.floor(Math.random() * 26)
        ctx.fillStyle = `rgb(${tone + 12}, ${tone - 4}, ${tone - 34})`
        ctx.fillRect(x + 2, y + 2, 252, 60)
        ctx.strokeStyle = 'rgba(90,70,50,0.18)'
        ctx.lineWidth = 1
        for (let line = 0; line < 3; line += 1) {
          ctx.beginPath()
          ctx.moveTo(x + 8, y + 12 + line * 18 + Math.random() * 6)
          ctx.lineTo(x + 244, y + 14 + line * 18 + Math.random() * 6)
          ctx.stroke()
        }
      }
    }
    ctx.strokeStyle = 'rgba(80,62,44,0.28)'
    ctx.lineWidth = 2
    for (let row = 0; row <= 16; row += 1) {
      ctx.beginPath()
      ctx.moveTo(0, row * 64)
      ctx.lineTo(1024, row * 64)
      ctx.stroke()
    }
  })
}

/** 墙上的宣传板，给侧墙一点信息量。 */
function wallBoardTexture(): THREE.CanvasTexture {
  return canvasTexture(768, 1024, (ctx) => {
    ctx.fillStyle = '#f6f2ea'
    ctx.fillRect(0, 0, 768, 1024)
    ctx.fillStyle = '#1d4f7c'
    ctx.fillRect(0, 0, 768, 128)
    ctx.fillStyle = '#ffffff'
    ctx.textAlign = 'center'
    ctx.font = '700 52px "Microsoft YaHei", sans-serif'
    ctx.fillText('复试流程', 384, 84)
    const steps = ['报到与资格审查', '候场与抽签', '综合面试', '英语听说', '离场']
    ctx.textAlign = 'left'
    steps.forEach((step, index) => {
      const y = 220 + index * 132
      ctx.fillStyle = '#1d4f7c'
      ctx.beginPath()
      ctx.arc(96, y - 12, 26, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = '#ffffff'
      ctx.font = '700 28px "Microsoft YaHei", sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(String(index + 1), 96, y - 2)
      ctx.textAlign = 'left'
      ctx.fillStyle = '#2b2b2b'
      ctx.font = '500 34px "Microsoft YaHei", sans-serif'
      ctx.fillText(step, 148, y)
      if (index < steps.length - 1) {
        ctx.strokeStyle = 'rgba(29,79,124,0.35)'
        ctx.lineWidth = 3
        ctx.beginPath()
        ctx.moveTo(96, y + 20)
        ctx.lineTo(96, y + 96)
        ctx.stroke()
      }
    })
    ctx.fillStyle = '#7a6a52'
    ctx.font = '500 26px "Microsoft YaHei", sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('请保持安静 · 手机静音', 384, 960)
  })
}

/** 桌牌：把导师姓名写进贴图，比 3D 文字便宜也比 HTML 投影稳。 */
function nameplateTexture(name: string, title: string): THREE.CanvasTexture {
  return canvasTexture(384, 128, (ctx) => {
    ctx.fillStyle = '#f7f4ee'
    ctx.fillRect(0, 0, 384, 128)
    ctx.fillStyle = '#1d4f7c'
    ctx.fillRect(0, 0, 384, 8)
    ctx.textAlign = 'center'
    ctx.fillStyle = '#1c2733'
    ctx.font = '700 52px "Microsoft YaHei", "PingFang SC", sans-serif'
    ctx.fillText(name, 192, 62)
    ctx.font = '500 26px "Microsoft YaHei", "PingFang SC", sans-serif'
    ctx.fillStyle = '#5a6472'
    ctx.fillText(title, 192, 104)
  })
}

/** 一位导师：躯干 + 头 + 双臂 + 椅子，全部用基础几何体拼。 */
function buildExaminer(seat: (typeof EXAMINER_SEATS)[number], index: number): ExaminerRig {
  const group = new THREE.Group()
  group.position.set(seat.x, 0, EXAMINER_Z)
  group.scale.setScalar(seat.scale)

  const skin = mat({ color: 0xd8b096, roughness: 0.85 })
  const suit = mat({ color: seat.suit, roughness: 0.78 })
  const shirt = mat({ color: 0xf0eee9, roughness: 0.7 })
  const tie = mat({ color: seat.tie, roughness: 0.6 })
  const hair = mat({ color: seat.hair, roughness: 0.9 })

  // 椅子
  const chairMat = mat({ color: 0x3b3f46, roughness: 0.65, metalness: 0.1 })
  const chairBack = mesh(new THREE.BoxGeometry(0.5, 0.6, 0.06), chairMat)
  chairBack.position.set(0, 1.0, -0.3)
  group.add(chairBack)
  const chairSeat = mesh(new THREE.BoxGeometry(0.5, 0.07, 0.48), chairMat)
  chairSeat.position.set(0, 0.45, 0)
  group.add(chairSeat)
  const chairPost = mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.42, 12), chairMat)
  chairPost.position.set(0, 0.23, 0)
  group.add(chairPost)

  // 躯干：略前倾，坐着的人不会是笔直的
  const torso = mesh(new THREE.CapsuleGeometry(0.185, 0.32, 6, 14), suit)
  torso.position.set(0, 0.96, 0)
  torso.rotation.x = 0.06
  torso.scale.set(1.1, 1, 0.76)
  group.add(torso)

  const collar = mesh(new THREE.CylinderGeometry(0.085, 0.105, 0.1, 14), shirt, false)
  collar.position.set(0, 1.23, 0.03)
  group.add(collar)
  const tieMesh = mesh(new THREE.BoxGeometry(0.05, 0.24, 0.02), tie, false)
  tieMesh.position.set(0, 1.09, 0.13)
  tieMesh.rotation.x = 0.08
  group.add(tieMesh)

  // 肩：比第一版收窄，避免"驼背"的团块感
  const shoulderL = mesh(new THREE.SphereGeometry(0.098, 16, 12), suit)
  shoulderL.position.set(-0.19, 1.18, 0)
  shoulderL.scale.set(1, 0.82, 0.85)
  group.add(shoulderL)
  const shoulderR = mesh(new THREE.SphereGeometry(0.098, 16, 12), suit)
  shoulderR.position.set(0.19, 1.18, 0)
  shoulderR.scale.set(1, 0.82, 0.85)
  group.add(shoulderR)

  // 手臂：搭在桌面上
  const armL = mesh(new THREE.CapsuleGeometry(0.062, 0.32, 5, 12), suit)
  armL.position.set(-0.23, 0.99, 0.2)
  armL.rotation.set(1.24, 0, 0.1)
  group.add(armL)
  const armR = mesh(new THREE.CapsuleGeometry(0.062, 0.32, 5, 12), suit)
  armR.position.set(0.23, 0.99, 0.2)
  armR.rotation.set(1.24, 0, -0.1)
  group.add(armR)
  const handL = mesh(new THREE.SphereGeometry(0.055, 12, 10), skin)
  handL.position.set(-0.21, 0.9, 0.38)
  handL.scale.set(1, 0.8, 1.3)
  group.add(handL)
  const handR = mesh(new THREE.SphereGeometry(0.055, 12, 10), skin)
  handR.position.set(0.21, 0.9, 0.38)
  handR.scale.set(1, 0.8, 1.3)
  group.add(handR)

  // 头（放在独立 Group 里，方便做点头和转头）
  const head = new THREE.Group()
  head.position.set(0, 1.34, 0.02)
  const neck = mesh(new THREE.CylinderGeometry(0.052, 0.062, 0.09, 12), skin, false)
  neck.position.set(0, -0.05, 0)
  head.add(neck)
  const skull = mesh(new THREE.SphereGeometry(0.112, 20, 16), skin)
  skull.position.set(0, 0.06, 0)
  skull.scale.set(0.94, 1.06, 1)
  head.add(skull)
  const hairCap = mesh(new THREE.SphereGeometry(0.118, 20, 16, 0, Math.PI * 2, 0, Math.PI * 0.6), hair)
  hairCap.position.set(0, 0.072, -0.006)
  hairCap.scale.set(0.98, 1.04, 1.04)
  head.add(hairCap)
  // 后脑勺的头发，让侧面看不是一个光球
  const hairBack = mesh(new THREE.SphereGeometry(0.104, 16, 12, 0, Math.PI * 2, 0, Math.PI * 0.75), hair)
  hairBack.position.set(0, 0.055, -0.03)
  hairBack.scale.set(0.94, 0.96, 0.9)
  head.add(hairBack)
  const browMat = mat({ color: 0x2b2320, roughness: 0.9 })
  const eyeMat = mat({ color: 0x1b1b1f, roughness: 0.5 })
  for (const side of [-1, 1]) {
    const eye = mesh(new THREE.SphereGeometry(0.016, 10, 8), eyeMat, false)
    eye.position.set(side * 0.041, 0.068, 0.101)
    eye.scale.set(1, 1, 0.6)
    head.add(eye)
    const brow = mesh(new THREE.BoxGeometry(0.042, 0.008, 0.012), browMat, false)
    brow.position.set(side * 0.043, 0.1, 0.1)
    brow.rotation.z = side * 0.06
    head.add(brow)
  }
  const nose = mesh(new THREE.ConeGeometry(0.017, 0.042, 8), skin, false)
  nose.position.set(0, 0.05, 0.104)
  nose.rotation.x = Math.PI * 0.52
  head.add(nose)
  const mouth = mesh(new THREE.BoxGeometry(0.036, 0.008, 0.01), mat({ color: 0x8a5a52, roughness: 0.8 }), false)
  mouth.position.set(0, 0.02, 0.1)
  head.add(mouth)
  group.add(head)

  scene?.add(group)

  return {
    id: seat.id,
    group,
    torso,
    head,
    shoulderL,
    shoulderR,
    anchor: new THREE.Vector3(seat.x, 1.78 * seat.scale, EXAMINER_Z),
    phase: index * 1.7,
  }
}

/** 长桌 + 桌上的桌牌、纸、水杯。 */
function buildDesk(): void {
  if (!scene) return
  const wood = mat({ color: 0x8b5f3c, roughness: 0.62 })
  const woodDark = mat({ color: 0x6d472c, roughness: 0.7 })
  const top = mesh(new THREE.BoxGeometry(5.2, 0.07, 0.92), wood)
  top.position.set(0, 0.78, DESK_Z)
  scene.add(top)
  const apron = mesh(new THREE.BoxGeometry(5.1, 0.16, 0.06), woodDark)
  apron.position.set(0, 0.68, DESK_Z + 0.44)
  scene.add(apron)
  for (const x of [-2.4, 2.4]) {
    for (const z of [DESK_Z + 0.38, DESK_Z - 0.38]) {
      const leg = mesh(new THREE.BoxGeometry(0.09, 0.78, 0.09), woodDark)
      leg.position.set(x, 0.39, z)
      scene.add(leg)
    }
  }
  // 桌布前沿：深绿色台呢，一眼就是复试现场
  const cloth = mesh(new THREE.BoxGeometry(5.22, 0.5, 0.02), mat({ color: 0x24413a, roughness: 0.95 }))
  cloth.position.set(0, 0.5, DESK_Z + 0.47)
  scene.add(cloth)

  const paper = mat({ color: 0xf4f2ec, roughness: 0.95 })
  const cupMat = mat({ color: 0xd9e2e8, roughness: 0.25, metalness: 0.05, transparent: true, opacity: 0.72 })
  const penMat = mat({ color: 0x1f2a37, roughness: 0.5 })
  const room = scene
  EXAMINER_SEATS.forEach((seat, i) => {
    const x = seat.x
    const pad = mesh(new THREE.BoxGeometry(0.4, 0.012, 0.28), paper)
    pad.position.set(x + 0.22, 0.822, DESK_Z + 0.08)
    pad.rotation.y = (i - 1) * 0.05
    room.add(pad)
    const pen = mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.14, 8), penMat, false)
    pen.position.set(x + 0.34, 0.83, DESK_Z + 0.16)
    pen.rotation.set(Math.PI / 2, 0, 0.5)
    room.add(pen)
    const cup = mesh(new THREE.CylinderGeometry(0.034, 0.028, 0.11, 16), cupMat)
    cup.position.set(x - 0.32, 0.87, DESK_Z + 0.1)
    room.add(cup)
    // 桌牌：正面贴上姓名贴图，背面留白
    const label = EXAMINER_LABELS[i]
    const plateMat = mat({ map: nameplateTexture(label.name, label.title), roughness: 0.8 })
    const plate = new THREE.Mesh(new THREE.PlaneGeometry(0.28, 0.094), plateMat)
    disposables.push(plate.geometry, plateMat)
    plate.position.set(x, 0.872, DESK_Z + 0.33)
    plate.rotation.x = -0.34
    plate.castShadow = false
    room.add(plate)
    const plateBase = mesh(new THREE.BoxGeometry(0.3, 0.018, 0.1), mat({ color: 0xcfc6b6, roughness: 0.9 }))
    plateBase.position.set(x, 0.815, DESK_Z + 0.3)
    room.add(plateBase)
  })
}

/** 考生这一侧：一张椅子 + 桌面边缘，给第一人称一点参照物。 */
function buildExamineeSide(): void {
  if (!scene) return
  const wood = mat({ color: 0x8b5f3c, roughness: 0.62 })
  const desk = mesh(new THREE.BoxGeometry(1.45, 0.06, 0.58), wood)
  desk.position.set(0, 0.74, -0.55)
  scene.add(desk)
  const legMat = mat({ color: 0x6d472c, roughness: 0.7 })
  for (const x of [-0.64, 0.64]) {
    for (const z of [-0.3, -0.8]) {
      const leg = mesh(new THREE.BoxGeometry(0.07, 0.74, 0.07), legMat)
      leg.position.set(x, 0.37, z)
      scene.add(leg)
    }
  }
  const paper = mesh(new THREE.BoxGeometry(0.3, 0.008, 0.22), mat({ color: 0xf6f4ef, roughness: 0.95 }))
  paper.position.set(-0.18, 0.776, -0.5)
  paper.rotation.y = 0.16
  scene.add(paper)
  // 桌沿的手机（静音扣在桌上），复试现场的真实细节
  const phone = mesh(new THREE.BoxGeometry(0.07, 0.012, 0.14), mat({ color: 0x22262c, roughness: 0.4 }), false)
  phone.position.set(0.3, 0.78, -0.45)
  phone.rotation.y = -0.3
  scene.add(phone)
}

function buildRoom(): void {
  if (!scene) return
  const halfW = ROOM_W / 2
  const halfD = ROOM_D / 2

  const floor = mesh(new THREE.PlaneGeometry(ROOM_W, ROOM_D), mat({ map: floorTexture(), roughness: 0.82 }), false)
  floor.rotation.x = -Math.PI / 2
  scene.add(floor)

  const ceiling = mesh(new THREE.PlaneGeometry(ROOM_W, ROOM_D), mat({ color: 0xefeae1, roughness: 0.95 }), false)
  ceiling.rotation.x = Math.PI / 2
  ceiling.position.y = ROOM_H
  scene.add(ceiling)

  const wallMat = mat({ color: 0xe6e0d4, roughness: 0.95 })
  const back = mesh(new THREE.PlaneGeometry(ROOM_W, ROOM_H), wallMat, false)
  back.position.set(0, ROOM_H / 2, -halfD)
  scene.add(back)
  const front = mesh(new THREE.PlaneGeometry(ROOM_W, ROOM_H), wallMat, false)
  front.position.set(0, ROOM_H / 2, halfD)
  front.rotation.y = Math.PI
  scene.add(front)
  const left = mesh(new THREE.PlaneGeometry(ROOM_D, ROOM_H), wallMat, false)
  left.position.set(-halfW, ROOM_H / 2, 0)
  left.rotation.y = Math.PI / 2
  scene.add(left)
  const right = mesh(new THREE.PlaneGeometry(ROOM_D, ROOM_H), wallMat, false)
  right.position.set(halfW, ROOM_H / 2, 0)
  right.rotation.y = -Math.PI / 2
  scene.add(right)

  const skirtMat = mat({ color: 0xc9c0b0, roughness: 0.9 })
  const skirts: Array<[number, number, number, number]> = [
    [0, -halfD + 0.02, 0, ROOM_W],
    [0, halfD - 0.02, Math.PI, ROOM_W],
    [-halfW + 0.02, 0, Math.PI / 2, ROOM_D],
    [halfW - 0.02, 0, -Math.PI / 2, ROOM_D],
  ]
  for (const [x, z, ry, len] of skirts) {
    const skirt = mesh(new THREE.BoxGeometry(len, 0.12, 0.03), skirtMat, false)
    skirt.position.set(x, 0.06, z)
    skirt.rotation.y = ry
    scene.add(skirt)
  }

  // 黑板（不与天花板打架：0.95 → 2.95）
  const frameMat = mat({ color: 0x6d472c, roughness: 0.75 })
  const frameMesh = mesh(new THREE.BoxGeometry(4.9, 2.0, 0.09), frameMat, false)
  frameMesh.position.set(0, 1.95, -halfD + 0.06)
  scene.add(frameMesh)
  const board = mesh(new THREE.PlaneGeometry(4.62, 1.76), mat({ map: blackboardTexture(), roughness: 0.92 }), false)
  board.position.set(0, 1.95, -halfD + 0.115)
  scene.add(board)
  const tray = mesh(new THREE.BoxGeometry(4.6, 0.05, 0.1), frameMat, false)
  tray.position.set(0, 0.99, -halfD + 0.16)
  scene.add(tray)

  // 会标（在黑板上方，不重叠）
  const banner = mesh(new THREE.PlaneGeometry(5.2, 0.44), mat({ map: bannerTexture(), roughness: 0.85 }), false)
  banner.position.set(0, 3.17, -halfD + 0.05)
  scene.add(banner)

  // 左侧窗户：三个窗洞 + 透光面
  const windowGlow = mat({ color: 0xe8f2ff, emissive: 0xc9dcf6, emissiveIntensity: 0.75, roughness: 1 })
  const windowFrame = mat({ color: 0xf2efe8, roughness: 0.85 })
  for (const z of [-1.9, 0.3, 2.5]) {
    const pane = mesh(new THREE.PlaneGeometry(1.6, 1.4), windowGlow, false)
    pane.position.set(-halfW + 0.04, 2.05, z)
    pane.rotation.y = Math.PI / 2
    scene.add(pane)
    const mullion = mesh(new THREE.BoxGeometry(0.04, 1.4, 0.05), windowFrame, false)
    mullion.position.set(-halfW + 0.06, 2.05, z)
    scene.add(mullion)
    const mullionH = mesh(new THREE.BoxGeometry(0.04, 0.05, 1.6), windowFrame, false)
    mullionH.position.set(-halfW + 0.06, 2.05, z)
    scene.add(mullionH)
  }

  // 右侧宣传板
  const board2 = mesh(new THREE.PlaneGeometry(1.6, 2.1), mat({ map: wallBoardTexture(), roughness: 0.9 }), false)
  board2.position.set(halfW - 0.04, 1.8, 0.6)
  board2.rotation.y = -Math.PI / 2
  scene.add(board2)

  // 天花板灯盘
  const lampMat = mat({ color: 0xffffff, emissive: 0xfff4dc, emissiveIntensity: 0.9, roughness: 1 })
  for (const z of [-1.3, 1.0]) {
    const lamp = mesh(new THREE.BoxGeometry(2.6, 0.06, 0.4), lampMat, false)
    lamp.position.set(0, ROOM_H - 0.04, z)
    scene.add(lamp)
  }

  // 墙上的挂钟
  const clockFace = mesh(new THREE.CircleGeometry(0.22, 28), mat({ color: 0xfaf8f4, roughness: 0.8 }), false)
  clockFace.position.set(3.1, 2.55, -halfD + 0.05)
  scene.add(clockFace)
  const clockRim = mesh(new THREE.TorusGeometry(0.22, 0.016, 8, 30), mat({ color: 0x4a4a52, roughness: 0.6 }), false)
  clockRim.position.copy(clockFace.position)
  scene.add(clockRim)
  const handMat = mat({ color: 0x2a2a30, roughness: 0.6 })
  const hourHand = mesh(new THREE.BoxGeometry(0.012, 0.12, 0.006), handMat, false)
  hourHand.position.set(3.1, 2.6, -halfD + 0.06)
  scene.add(hourHand)
  const minuteHand = mesh(new THREE.BoxGeometry(0.01, 0.17, 0.006), handMat, false)
  minuteHand.position.set(3.14, 2.58, -halfD + 0.06)
  minuteHand.rotation.z = -0.9
  scene.add(minuteHand)
}

function buildLights(): void {
  if (!scene) return
  scene.add(new THREE.AmbientLight(0xffffff, 0.2))
  scene.add(new THREE.HemisphereLight(0xfdfbf5, 0x6b6153, 0.85))

  const sun = new THREE.DirectionalLight(0xfff4e0, 1.7)
  sun.position.set(-6.2, 4.6, 2.8)
  sun.target.position.set(0, 0.9, -1.6)
  sun.castShadow = true
  sun.shadow.mapSize.set(1024, 1024)
  sun.shadow.camera.near = 1
  sun.shadow.camera.far = 20
  sun.shadow.camera.left = -6
  sun.shadow.camera.right = 6
  sun.shadow.camera.top = 5
  sun.shadow.camera.bottom = -2
  sun.shadow.bias = -0.0012
  sun.shadow.radius = 2
  scene.add(sun)
  scene.add(sun.target)

  const fill = new THREE.DirectionalLight(0xdfe9ff, 0.5)
  fill.position.set(5.5, 3.4, 4.0)
  scene.add(fill)

  for (const z of [-1.3, 1.0]) {
    const lamp = new THREE.PointLight(0xfff2dc, 11, 10, 2)
    lamp.position.set(0, ROOM_H - 0.35, z)
    scene.add(lamp)
  }

  // 一盏补光，跟随当前发言的考官，让"谁在说话"有视觉焦点
  screenLight = new THREE.PointLight(0xffe9c4, 5, 4.6, 2)
  screenLight.position.set(0, 2.0, -2.5)
  scene.add(screenLight)
}

function buildLabels(): void {
  labels = []
  const root = labelRoot.value
  if (!root) return
  root.innerHTML = ''
  for (const item of EXAMINER_LABELS) {
    const el = document.createElement('div')
    el.className = 'examiner-tag'
    el.dataset.examiner = item.id
    el.innerHTML = `<strong>${item.name}</strong><span>${item.title}</span>`
    root.appendChild(el)
    const rig = rigs.find((entry) => entry.id === item.id)
    labels.push({ id: item.id, el, anchor: rig ? rig.anchor.clone() : new THREE.Vector3() })
  }
}

function resize(): void {
  const element = host.value
  if (!element || !renderer || !camera) return
  const width = element.clientWidth || 1
  const height = element.clientHeight || 1
  renderer.setSize(width, height, false)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}

function animate(): void {
  frame = requestAnimationFrame(animate)
  if (!renderer || !scene || !camera) return
  const t = (performance.now() - sceneStart) / 1000
  const speaking = props.speaking ?? null
  const answering = props.phase === 'answer'

  for (const rig of rigs) {
    const active = rig.id === speaking
    const breath = 1 + 0.009 * Math.sin(t * 1.45 + rig.phase)
    rig.torso.scale.y = breath
    rig.shoulderL.position.y = 1.18 + 0.004 * Math.sin(t * 1.45 + rig.phase)
    rig.shoulderR.position.y = rig.shoulderL.position.y

    if (active) {
      rig.head.rotation.x = 0.055 * Math.sin(t * 3.1) + 0.02
      rig.head.rotation.y = 0.075 * Math.sin(t * 1.15)
      rig.head.rotation.z = 0.012 * Math.sin(t * 2.3)
    } else {
      rig.head.rotation.x = 0.03 * Math.sin(t * 0.62 + rig.phase) + 0.01
      rig.head.rotation.y = 0.05 * Math.sin(t * 0.37 + rig.phase)
      rig.head.rotation.z = 0.008 * Math.sin(t * 0.5 + rig.phase)
    }
  }

  if (speaking === 'host') desiredLook.set(0, 1.48, -2.3)
  else if (speaking === 'major') desiredLook.set(-1.15, 1.46, -2.3)
  else if (speaking === 'english') desiredLook.set(1.15, 1.46, -2.3)
  else desiredLook.set(LOOK_DEFAULT.x, LOOK_DEFAULT.y, LOOK_DEFAULT.z)
  lookAt.lerp(desiredLook, 0.035)

  const swayX = 0.05 * Math.sin(t * 0.29)
  const swayY = CAMERA_POS.y + 0.013 * Math.sin(t * 1.05)
  const swayZ = CAMERA_POS.z + (answering ? 0.05 : 0)
  camera.position.x += (swayX - camera.position.x) * 0.04
  camera.position.y += (swayY - camera.position.y) * 0.04
  camera.position.z += (swayZ - camera.position.z) * 0.04
  camera.lookAt(lookAt)

  if (screenLight) {
    const targetX = speaking === 'host' ? 0 : speaking === 'major' ? -1.15 : speaking === 'english' ? 1.15 : 0
    screenLight.position.x += (targetX - screenLight.position.x) * 0.05
    screenLight.intensity = 4.4 + (speaking ? 2.6 : 0) + 0.4 * Math.sin(t * 2.1)
  }

  const element = host.value
  if (element) {
    const width = element.clientWidth
    const height = element.clientHeight
    for (const label of labels) {
      tmpVector.copy(label.anchor).project(camera)
      const x = (tmpVector.x * 0.5 + 0.5) * width
      const y = (-tmpVector.y * 0.5 + 0.5) * height
      const visible = tmpVector.z < 1
      label.el.style.transform = `translate(-50%, -100%) translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`
      label.el.style.opacity = visible ? '1' : '0'
      label.el.classList.toggle('is-speaking', label.id === speaking)
    }
  }

  renderer.render(scene, camera)
}

function init(): void {
  const element = host.value
  if (!element) return
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: 'high-performance' })
  } catch {
    failed.value = true
    return
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFShadowMap
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.15
  element.appendChild(renderer.domElement)

  scene = new THREE.Scene()
  scene.fog = new THREE.Fog(0xd8d1c5, 13, 26)

  camera = new THREE.PerspectiveCamera(CAMERA_FOV, 1, 0.1, 60)
  camera.position.set(CAMERA_POS.x, CAMERA_POS.y, CAMERA_POS.z)

  sceneStart = performance.now()
  buildRoom()
  buildDesk()
  buildExamineeSide()
  buildLights()
  rigs = EXAMINER_SEATS.map((seat, index) => buildExaminer(seat, index))
  buildLabels()
  resize()

  observer = new ResizeObserver(() => resize())
  observer.observe(element)
  window.addEventListener('resize', resize)
  animate()
}

onMounted(init)

onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
  window.removeEventListener('resize', resize)
  for (const item of disposables) item.dispose()
  disposables.length = 0
  if (renderer) {
    renderer.dispose()
    renderer.domElement.remove()
  }
  renderer = undefined
  scene = undefined
  camera = undefined
  rigs = []
  labels = []
})

defineExpose({ failed })
</script>

<template>
  <div class="classroom-scene">
    <div ref="host" class="classroom-canvas" />
    <div ref="labelRoot" class="classroom-labels" />
    <div v-if="failed" class="classroom-fallback">
      <strong>3D 场景未能初始化</strong>
      <span>当前浏览器或显卡不支持 WebGL，面试流程仍可正常进行。</span>
    </div>
  </div>
</template>
