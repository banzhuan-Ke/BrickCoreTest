<template>
  <el-dialog
    v-model="visible"
    title="从选中步骤生成片段"
    width="640px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
    >
      将把已选的 {{ selectedCount }} 个步骤保存为可复用片段；条件分支、片段引用等结构会一并保留。
    </el-alert>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="88px">
      <el-form-item label="片段名称" prop="name">
        <el-input v-model="form.name" placeholder="请输入片段名称" maxlength="100" show-word-limit />
      </el-form-item>
      <el-form-item label="分类标签">
        <el-input v-model="form.tags" placeholder="如：登录、导航" maxlength="200" />
      </el-form-item>
      <el-form-item label="说明">
        <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" show-word-limit />
      </el-form-item>
      <el-form-item label="替换原步骤">
        <el-checkbox v-model="form.replaceWithRef">
          生成后用片段引用替换选中的步骤
        </el-checkbox>
      </el-form-item>
    </el-form>

    <div class="preview-block">
      <div class="preview-title">包含步骤预览</div>
      <el-table :data="previewRows" size="small" border stripe max-height="220">
        <el-table-column type="index" label="#" width="48" align="center" />
        <el-table-column prop="keyword" label="步骤名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="method" label="类型" width="120" show-overflow-tooltip />
      </el-table>
    </div>

    <p v-if="fragmentVarNames.length" class="var-hint">
      检测到片段入参占位符：
      <el-tag v-for="name in fragmentVarNames" :key="name" size="small" type="info" style="margin: 2px;">
        fragment.{{ name }}
      </el-tag>
      ，引用该片段时可在「配置」中填写入参。
    </p>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">生成片段</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import { uiFragmentApi } from '@/api/modules/ui'
import { appFragmentApi } from '@/api/modules/app'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { extractFragmentVarNames } from '@/utils/fragmentVars'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  selectedCount: { type: Number, default: 0 },
  steps: { type: Array, default: () => [] },
  domain: { type: String, default: 'ui' },
})

const emit = defineEmits(['update:modelValue', 'created'])

const proStore = ProjectStore()
const formRef = ref()
const submitting = ref(false)

const form = reactive({
  name: '',
  tags: '',
  description: '',
  replaceWithRef: true,
})

const rules = {
  name: [{ required: true, message: '请输入片段名称', trigger: 'blur' }],
}

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const previewRows = computed(() =>
  (props.steps || []).map((step) => ({
    keyword: step.keyword || step.desc || '未命名步骤',
    method: step.method === 'fragment_ref'
      ? '片段引用'
      : step.method === 'condition_branch'
        ? '条件分支'
        : (step.method || '-'),
  })),
)

const fragmentVarNames = computed(() => extractFragmentVarNames(props.steps || []))

function resetForm() {
  form.name = ''
  form.tags = ''
  form.description = ''
  form.replaceWithRef = true
  submitting.value = false
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (!props.steps?.length) {
    ElMessage.warning('没有可生成的步骤')
    return
  }

  const projectId = proStore.projectInfo?.id
  if (!projectId) {
    ElMessage.warning('请先选择项目')
    return
  }

  submitting.value = true
  try {
    const api = props.domain === 'app' ? appFragmentApi : uiFragmentApi
    const res = await api.create({
      project_id: projectId,
      name: form.name.trim(),
      description: form.description,
      tags: form.tags,
      steps: props.steps,
    })
    if (res.data?.code !== 200) {
      ElNotification.error(res.data?.message || '创建失败')
      return
    }
    const fragment = res.data?.data
    emit('created', {
      fragment,
      replaceWithRef: form.replaceWithRef,
    })
    visible.value = false
    const actionHint = form.replaceWithRef ? '，已替换为片段引用' : '，原步骤保持不变'
    ElNotification.success(`片段「${fragment?.name || form.name}」已创建${actionHint}`)
  } catch (e) {
    const detail = e?.response?.data?.detail
    ElNotification.error(typeof detail === 'string' ? detail : detail?.message || e?.data?.message || '创建失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.preview-block {
  margin-top: 8px;
}

.preview-title {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.var-hint {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
