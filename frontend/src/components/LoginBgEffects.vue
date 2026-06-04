<template>
  <div v-show="motionEnabled" class="login-bg-motion" aria-hidden="true">
    <canvas ref="canvasRef" class="login-particles-canvas" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { LOGIN_PAGE_DEFAULTS, LOGIN_MOTION_LIMITS } from '@/constants/loginPageBackgrounds.js'

const props = defineProps({
  container: {
    type: Object,
    default: null,
  },
  motionConfig: {
    type: Object,
    default: () => ({}),
  },
})

const canvasRef = ref(null)

const counts = computed(() => ({
  brick: clampCount(props.motionConfig?.bg_brick_count, LOGIN_PAGE_DEFAULTS.bg_brick_count, LOGIN_MOTION_LIMITS.brick.max),
  star: clampCount(props.motionConfig?.bg_star_count, LOGIN_PAGE_DEFAULTS.bg_star_count, LOGIN_MOTION_LIMITS.star.max),
  dot: clampCount(props.motionConfig?.bg_dot_count, LOGIN_PAGE_DEFAULTS.bg_dot_count, LOGIN_MOTION_LIMITS.dot.max),
}))

const motionEnabled = computed(() => props.motionConfig?.bg_motion_enabled !== false)

let rafId = 0
let running = false
let reducedMotion = false
let width = 0
let height = 0
let dpr = 1
let particles = []
/** @type {{ x: number, y: number, t: number }[]} */
let trailPoints = []
let lastTrailX = -9999
let lastTrailY = -9999
let mouseX = -9999
let mouseY = -9999
let mouseActive = false
let frameTick = 0

const TRAIL_MAX = 18
const TRAIL_MIN_DIST = 16
const TRAIL_DECAY_MS = 1100

function clampCount(value, fallback, max) {
  const n = Number(value)
  if (!Number.isFinite(n)) return fallback
  return Math.max(0, Math.min(max, Math.round(n)))
}

function getContainerEl() {
  const c = props.container
  return c?.value ?? c ?? null
}

function rand(min, max) {
  return min + Math.random() * (max - min)
}

function createParticles() {
  const list = []
  const { brick, star, dot } = counts.value

  for (let i = 0; i < star; i++) {
    list.push({
      kind: 'star',
      x: Math.random() * width,
      y: Math.random() * height,
      vx: rand(-0.14, 0.14),
      vy: rand(-0.12, 0.12),
      size: rand(1.4, 3.6),
      baseAlpha: rand(0.4, 0.9),
      phase: Math.random() * Math.PI * 2,
      twinkleSpeed: rand(0.8, 2.2),
    })
  }

  for (let i = 0; i < dot; i++) {
    list.push({
      kind: 'dot',
      x: Math.random() * width,
      y: Math.random() * height,
      vx: rand(-0.2, 0.2),
      vy: rand(-0.16, 0.16),
      size: rand(3.5, 8),
      baseAlpha: rand(0.14, 0.36),
      phase: Math.random() * Math.PI * 2,
      twinkleSpeed: rand(0.4, 1),
    })
  }

  for (let i = 0; i < brick; i++) {
    list.push({
      kind: 'brick',
      x: Math.random() * width,
      y: Math.random() * height,
      vx: rand(-0.1, 0.1),
      vy: rand(-0.08, 0.08),
      w: rand(14, 34),
      h: rand(10, 24),
      rot: rand(0, Math.PI * 2),
      rotSpeed: rand(-0.0025, 0.0025),
      baseAlpha: rand(0.16, 0.42),
      phase: Math.random() * Math.PI * 2,
      twinkleSpeed: rand(0.3, 0.8),
    })
  }

  particles = list
}

function resizeCanvas() {
  const el = getContainerEl()
  const canvas = canvasRef.value
  if (!el || !canvas) return
  const rect = el.getBoundingClientRect()
  width = Math.max(1, Math.floor(rect.width))
  height = Math.max(1, Math.floor(rect.height))
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = width * dpr
  canvas.height = height * dpr
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`
  const ctx = canvas.getContext('2d')
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  createParticles()
  trailPoints = []
}

function wrapParticle(p) {
  const pad = 48
  if (p.x < -pad) p.x = width + pad
  if (p.x > width + pad) p.x = -pad
  if (p.y < -pad) p.y = height + pad
  if (p.y > height + pad) p.y = -pad
}

function drawStar(ctx, x, y, size, alpha) {
  const spikes = 4
  const outer = size * 2.4
  const inner = size * 0.55
  ctx.beginPath()
  for (let i = 0; i < spikes * 2; i++) {
    const r = i % 2 === 0 ? outer : inner
    const a = (Math.PI / spikes) * i - Math.PI / 2
    const px = x + Math.cos(a) * r
    const py = y + Math.sin(a) * r
    if (i === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  }
  ctx.closePath()
  ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`
  ctx.fill()
}

function drawBrick(ctx, x, y, w, h, rot, alpha) {
  ctx.save()
  ctx.translate(x, y)
  ctx.rotate(rot)
  const top = -h * 0.35
  const half = w * 0.5
  const skew = h * 0.22

  ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.38})`
  ctx.strokeStyle = `rgba(255, 255, 255, ${alpha * 0.72})`
  ctx.lineWidth = 1
  ctx.lineJoin = 'round'

  ctx.beginPath()
  ctx.moveTo(0, top)
  ctx.lineTo(half, top + skew)
  ctx.lineTo(0, top + skew * 2)
  ctx.lineTo(-half, top + skew)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()

  ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.24})`
  ctx.beginPath()
  ctx.moveTo(-half, top + skew)
  ctx.lineTo(0, top + skew * 2)
  ctx.lineTo(0, top + skew * 2 + h * 0.55)
  ctx.lineTo(-half, top + skew + h * 0.55)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()

  ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.3})`
  ctx.beginPath()
  ctx.moveTo(half, top + skew)
  ctx.lineTo(0, top + skew * 2)
  ctx.lineTo(0, top + skew * 2 + h * 0.55)
  ctx.lineTo(half, top + skew + h * 0.55)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()

  ctx.restore()
}

function mouseBoost(px, py) {
  if (!mouseActive) return 0
  const dist = Math.hypot(mouseX - px, mouseY - py)
  if (dist > 200) return 0
  return (1 - dist / 200) * 0.42
}

function applyMouseInfluence(p) {
  if (!mouseActive) return
  const dx = mouseX - p.x
  const dy = mouseY - p.y
  const dist = Math.hypot(dx, dy)
  if (dist > 200 || dist < 2) return
  const force = (1 - dist / 200) * 0.028
  p.vx += (dx / dist) * force
  p.vy += (dy / dist) * force
  const maxV = 0.35
  const speed = Math.hypot(p.vx, p.vy)
  if (speed > maxV) {
    p.vx = (p.vx / speed) * maxV
    p.vy = (p.vy / speed) * maxV
  }
}

function pushTrailPoint(x, y, now) {
  if (lastTrailX > -9000) {
    const d = Math.hypot(x - lastTrailX, y - lastTrailY)
    if (d < TRAIL_MIN_DIST) return
  }
  lastTrailX = x
  lastTrailY = y
  trailPoints.push({ x, y, t: now })
  if (trailPoints.length > TRAIL_MAX) trailPoints.shift()
}

function drawSparseTrail(ctx, now) {
  trailPoints = trailPoints.filter((p) => now - p.t < TRAIL_DECAY_MS)
  if (trailPoints.length < 2) return

  const len = trailPoints.length
  for (let i = 1; i < len; i++) {
    const p0 = trailPoints[i - 1]
    const p1 = trailPoints[i]
    const t = i / len
    const alpha = 0.12 + t * 0.38
    ctx.beginPath()
    ctx.strokeStyle = `rgba(255, 255, 255, ${alpha})`
    ctx.lineWidth = 1.5 + t * 5
    ctx.lineCap = 'round'
    ctx.moveTo(p0.x, p0.y)
    ctx.lineTo(p1.x, p1.y)
    ctx.stroke()
  }

  const head = trailPoints[len - 1]
  const g = ctx.createRadialGradient(head.x, head.y, 0, head.x, head.y, 22)
  g.addColorStop(0, 'rgba(255, 255, 255, 0.5)')
  g.addColorStop(1, 'rgba(255, 255, 255, 0)')
  ctx.fillStyle = g
  ctx.beginPath()
  ctx.arc(head.x, head.y, 22, 0, Math.PI * 2)
  ctx.fill()
}

function tick(now) {
  if (!running) return
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!ctx) {
    rafId = requestAnimationFrame(tick)
    return
  }

  const t = now / 1000
  ctx.clearRect(0, 0, width, height)

  drawSparseTrail(ctx, now)

  for (const p of particles) {
    applyMouseInfluence(p)
    p.x += p.vx
    p.y += p.vy
    wrapParticle(p)

    const twinkle = Math.sin(t * p.twinkleSpeed + p.phase) * 0.14
    const boost = mouseBoost(p.x, p.y)
    const alpha = Math.min(1, p.baseAlpha + twinkle + boost)

    if (p.kind === 'star') {
      drawStar(ctx, p.x, p.y, p.size, alpha)
      if (alpha > 0.45) {
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.size * 3.5, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.15})`
        ctx.fill()
      }
    } else if (p.kind === 'dot') {
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`
      ctx.fill()
    } else if (p.kind === 'brick') {
      p.rot += p.rotSpeed
      drawBrick(ctx, p.x, p.y, p.w, p.h, p.rot, alpha)
    }
  }

  if (mouseActive) {
    const g = ctx.createRadialGradient(mouseX, mouseY, 0, mouseX, mouseY, 130)
    g.addColorStop(0, 'rgba(255, 255, 255, 0.22)')
    g.addColorStop(0.45, 'rgba(255, 255, 255, 0.08)')
    g.addColorStop(1, 'rgba(255, 255, 255, 0)')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, width, height)
  }

  rafId = requestAnimationFrame(tick)
}

function onPointerMove(e) {
  const el = getContainerEl()
  if (!el) return
  const rect = el.getBoundingClientRect()
  const inside =
    e.clientX >= rect.left &&
    e.clientX <= rect.right &&
    e.clientY >= rect.top &&
    e.clientY <= rect.bottom
  if (!inside) {
    mouseActive = false
    return
  }
  mouseX = e.clientX - rect.left
  mouseY = e.clientY - rect.top
  mouseActive = true
  frameTick += 1
  if (frameTick % 2 === 0) {
    pushTrailPoint(mouseX, mouseY, performance.now())
  }
}

function onPointerLeave() {
  mouseActive = false
}

let resizeObserver = null
let containerEl = null

function startLoop() {
  if (running || reducedMotion || !motionEnabled.value) return
  running = true
  rafId = requestAnimationFrame(tick)
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  window.addEventListener('pointerleave', onPointerLeave)
}

function stopLoop() {
  running = false
  if (rafId) cancelAnimationFrame(rafId)
  rafId = 0
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerleave', onPointerLeave)
  trailPoints = []
  mouseActive = false
}

function setup() {
  containerEl = getContainerEl()
  if (!containerEl) return
  resizeCanvas()
  stopLoop()
  if (!reducedMotion && motionEnabled.value) {
    startLoop()
  }
}

watch(
  () => [counts.value.brick, counts.value.star, counts.value.dot, motionEnabled.value],
  () => {
    if (width > 0) createParticles()
    stopLoop()
    if (motionEnabled.value && !reducedMotion) startLoop()
  }
)

onMounted(async () => {
  reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  await nextTick()
  setup()
  resizeObserver = new ResizeObserver(() => resizeCanvas())
  if (containerEl) resizeObserver.observe(containerEl)
  window.addEventListener('resize', resizeCanvas, { passive: true })
})

onUnmounted(() => {
  stopLoop()
  resizeObserver?.disconnect()
  window.removeEventListener('resize', resizeCanvas)
})
</script>
