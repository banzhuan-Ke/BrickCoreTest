<template>
  <el-dialog
    v-model="visible"
    title="批量修改目录"
    width="480px"
    destroy-on-close
    @closed="handleClosed"
  >
    <p class="batch-catalog-tip">
      已选择 <strong>{{ caseIds.length }}</strong> 条用例，请选择目标目录。
    </p>
    <el-form label-width="88px">
      <el-form-item label="目标目录">
        <CatalogTreeSelect
          v-model="catalogId"
          :project-id="projectId"
          placeholder="不选则移出目录（未分类）"
          clearable
          style="width: 100%"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="loading" @click="handleConfirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  caseIds: { type: Array, default: () => [] },
  projectId: { type: Number, required: true },
  submitFn: { type: Function, required: true },
})

const emit = defineEmits(['update:modelValue', 'success'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const catalogId = ref(null)
const loading = ref(false)

watch(
  () => props.modelValue,
  (open) => {
    if (open) catalogId.value = null
  }
)

function handleClosed() {
  catalogId.value = null
  loading.value = false
}

async function handleConfirm() {
  if (!props.caseIds.length) {
    ElMessage.warning('请先选择用例')
    return
  }
  loading.value = true
  try {
    await props.submitFn({
      case_ids: props.caseIds,
      catalog_id: catalogId.value ?? null,
    })
    ElMessage.success('目录修改成功')
    visible.value = false
    emit('success')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || err.message || '目录修改失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.batch-catalog-tip {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--el-text-color-regular);
}
</style>
