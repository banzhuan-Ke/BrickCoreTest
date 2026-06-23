<template>
  <el-dialog v-model="dialogVisible" title="管理环境变量" width="680px" destroy-on-close append-to-body>
    <GlobalVarsEditor ref="editorRef" v-model="localVars" json-height="240px" />
    <el-collapse class="quick-tips">
      <el-collapse-item title="引用说明" name="1">
        <p class="tip-line">保存后，套件/计划/压测执行会读取同一环境的变量。</p>
        <p class="tip-line">用例中写 <code v-pre>${{变量名}}</code>；值支持 <code>faker.random_int(min=1,max=99)</code></p>
      </el-collapse-item>
    </el-collapse>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" @click="saveVars" :loading="saving">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'
import GlobalVarsEditor from '@/components/GlobalVarsEditor.vue'

const props = defineProps({
  modelValue: Boolean,
  envId: Number,
})

const emit = defineEmits(['update:modelValue', 'saved'])

const proStore = ProjectStore()
const saving = ref(false)
const localVars = ref({})
const editorRef = ref(null)

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const env = computed(() => {
  if (!props.envId) return null
  return proStore.envList.find((e) => e.id === props.envId)
})

watch(
  () => props.modelValue,
  (visible) => {
    if (visible && env.value) {
      const vars = env.value.global_vars || {}
      localVars.value = typeof vars === 'object' ? { ...vars } : {}
    }
  }
)

const saveVars = async () => {
  if (!props.envId) {
    ElMessage.warning('请先选择参考环境')
    return
  }
  if (!env.value) {
    ElMessage.warning('环境不存在或已删除，请刷新后重试')
    return
  }
  const global_vars = editorRef.value?.validateAndGet?.()
  if (global_vars === null) return
  saving.value = true
  try {
    await http.environmentApi.updateEnv(props.envId, { global_vars })
    const target = proStore.envList.find((e) => e.id === props.envId)
    if (target) target.global_vars = global_vars
    ElMessage.success('保存成功')
    emit('saved')
    dialogVisible.value = false
  } catch (err) {
    const detail = err.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.quick-tips {
  margin-top: 12px;
}

.tip-line {
  margin: 4px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
