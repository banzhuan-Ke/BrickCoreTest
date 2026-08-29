<template>
  <span v-if="visible" class="link-fc-wrap">
    <el-button :link="link" :type="type" :size="size" @click="open">
      {{ label }}
    </el-button>
    <AssetLinkDialog
      v-if="projectId"
      v-model="dialogVisible"
      :project-id="projectId"
      :asset-type="assetType"
      :asset-id="assetId"
    />
  </span>
</template>

<script setup>
import { computed, ref } from 'vue'
import AssetLinkDialog from './AssetLinkDialog.vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'

const props = defineProps({
  assetType: { type: String, required: true },
  assetId: { type: Number, required: true },
  label: { type: String, default: '关联功能用例' },
  link: { type: Boolean, default: true },
  type: { type: String, default: 'primary' },
  size: { type: String, default: 'default' }
})

const proStore = ProjectStore()
const uStore = UserStore()
const dialogVisible = ref(false)
const projectId = computed(() => proStore.projectInfo?.id)
const visible = computed(
  () =>
    !!props.assetId &&
    uStore.hasPermission('test_release:view')
)

const open = () => {
  dialogVisible.value = true
}
</script>

<style scoped>
.link-fc-wrap {
  display: inline-flex;
  align-items: center;
}
</style>
