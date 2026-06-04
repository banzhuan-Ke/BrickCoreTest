<template>
  <div class="assistant-mascot" :class="{ small: size === 'small', large: size === 'large' }" aria-hidden="true">
    <svg viewBox="0 0 64 64" class="mascot-svg">
      <!-- 阴影 -->
      <ellipse cx="32" cy="58" rx="14" ry="3" class="shadow" />
      <!-- 身体 -->
      <rect x="22" y="28" width="20" height="18" rx="6" class="body" />
      <!-- 头 -->
      <circle cx="32" cy="20" r="11" class="head" />
      <!-- 眼睛 -->
      <circle cx="28" cy="19" r="1.8" class="eye" />
      <circle cx="36" cy="19" r="1.8" class="eye" />
      <!-- 腮红 -->
      <ellipse cx="24" cy="23" rx="2.5" ry="1.5" class="blush" />
      <ellipse cx="40" cy="23" rx="2.5" ry="1.5" class="blush" />
      <!-- 腿 -->
      <g class="legs">
        <rect x="24" y="44" width="5" height="10" rx="2" class="leg leg-l" />
        <rect x="35" y="44" width="5" height="10" rx="2" class="leg leg-r" />
      </g>
      <!-- 手臂 + 砖块 -->
      <g class="carry-arm">
        <rect x="14" y="30" width="10" height="4" rx="2" class="arm" />
        <g class="brick-group">
          <rect x="4" y="22" width="16" height="10" rx="2" class="brick" />
          <line x1="6" y1="25" x2="18" y2="25" class="brick-line" />
          <line x1="6" y1="28" x2="18" y2="28" class="brick-line" />
        </g>
      </g>
      <rect x="42" y="32" width="10" height="4" rx="2" class="arm arm-r" />
      <!-- 安全帽 -->
      <path d="M22 14 Q32 6 42 14 L42 18 Q32 14 22 18 Z" class="helmet" />
    </svg>
  </div>
</template>

<script setup>
defineProps({
  size: { type: String, default: 'medium' } // small | medium | large
})
</script>

<style scoped lang="scss">
.assistant-mascot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;

  &.small {
    width: 28px;
    height: 28px;
  }

  &.large {
    width: 52px;
    height: 52px;
  }
}

.mascot-svg {
  width: 100%;
  height: 100%;
  overflow: visible;
}

.shadow {
  fill: rgba(0, 0, 0, 0.12);
  animation: shadow-pulse 1.2s ease-in-out infinite;
}

.head {
  fill: #ffe0bd;
  stroke: #e6b88a;
  stroke-width: 1;
}

.body {
  fill: #409eff;
}

.helmet {
  fill: #f5a623;
  stroke: #d48806;
  stroke-width: 0.8;
}

.eye {
  fill: #303133;
}

.blush {
  fill: rgba(255, 120, 120, 0.35);
}

.arm {
  fill: #ffe0bd;
}

.arm-r {
  animation: arm-swing 1.2s ease-in-out infinite;
  transform-origin: 42px 34px;
}

.carry-arm {
  animation: carry-bob 1.2s ease-in-out infinite;
  transform-origin: 20px 32px;
}

.brick {
  fill: #c2714f;
  stroke: #8b4513;
  stroke-width: 0.8;
}

.brick-line {
  stroke: rgba(255, 255, 255, 0.35);
  stroke-width: 0.8;
}

.leg-l {
  animation: leg-walk 1.2s ease-in-out infinite;
}

.leg-r {
  animation: leg-walk 1.2s ease-in-out infinite reverse;
}

@keyframes carry-bob {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(-2px) rotate(-4deg); }
}

@keyframes arm-swing {
  0%, 100% { transform: rotate(0deg); }
  50% { transform: rotate(8deg); }
}

@keyframes leg-walk {
  0%, 100% { transform: rotate(0deg); }
  50% { transform: rotate(6deg); }
}

@keyframes shadow-pulse {
  0%, 100% { transform: scaleX(1); opacity: 0.12; }
  50% { transform: scaleX(0.85); opacity: 0.08; }
}
</style>
