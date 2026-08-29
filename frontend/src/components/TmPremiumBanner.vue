<template>
  <el-alert
    v-if="show"
    class="tm-premium-banner"
    type="warning"
    :closable="false"
    show-icon
    :title="title"
  >
    <p class="tm-premium-banner__desc">{{ description }}</p>
    <p v-if="docHint" class="tm-premium-banner__doc">
      安装说明见帮助中心：测试管理扩展包（brickcore_tm）
    </p>
  </el-alert>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { testPremiumApi } from '@/api/testManagement'

const props = defineProps({
  /** 传入则不再自行请求状态 */
  status: { type: Object, default: null },
  /** 强制显示（例如页面已知 503） */
  force: { type: Boolean, default: false },
})

const localStatus = ref(null)

const effective = computed(() => props.status || localStatus.value)

const show = computed(() => {
  if (props.force) return true
  const s = effective.value
  if (!s) return false
  return !(s.installed && s.compatible)
})

const title = computed(() => {
  const s = effective.value
  if (s?.code === 'tm_premium_incompatible') return '测试管理扩展包版本不兼容'
  return '未检测到测试管理扩展包'
})

const description = computed(() => {
  const s = effective.value
  return (
    s?.message ||
    '质量门禁、指派通知、智能化与导出版本包等高级能力需安装测试管理扩展包。请按帮助中心「测试管理扩展包」下载 .bcpack，执行安装脚本并重启 backend。'
  )
})

const docHint = computed(() => show.value)

async function refresh() {
  if (props.status) return
  try {
    const res = await testPremiumApi.status()
    localStatus.value = res?.data?.data || res?.data || null
  } catch {
    localStatus.value = {
      installed: false,
      compatible: false,
      code: 'tm_premium_required',
      message: '无法检测扩展包状态',
    }
  }
}

onMounted(refresh)
watch(
  () => props.status,
  () => {
    if (!props.status) refresh()
  },
)

defineExpose({ refresh })
</script>

<style scoped>
.tm-premium-banner {
  margin-bottom: 16px;
}
.tm-premium-banner__desc {
  margin: 0 0 4px;
  line-height: 1.5;
}
.tm-premium-banner__doc {
  margin: 0;
  opacity: 0.85;
  font-size: 12px;
}
</style>
