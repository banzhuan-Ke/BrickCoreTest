<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="560px"
    destroy-on-close
    @close="emit('update:modelValue', false)"
  >
    <template v-if="mode === 'edit'">
      <el-form label-width="72px">
        <el-form-item label="标题">
          <el-input v-model="form.title" maxlength="500" />
        </el-form-item>
        <el-form-item label="链接">
          <el-input v-model="form.url" placeholder="http(s)://..." />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="4" placeholder="外部需求说明或摘要" />
        </el-form-item>
      </el-form>
    </template>

    <template v-else-if="mode === 'upgrade'">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="将把此外部需求转为项目内 REQ 文档，编号将变为 REQ-{id}。"
      />
      <el-form label-width="90px">
        <el-form-item label="需求名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="初始正文">
          <el-input
            v-model="form.initial_content"
            type="textarea"
            :rows="6"
            placeholder="可粘贴需求摘要；也可稍后在需求工作台上传完整文档"
          />
        </el-form-item>
      </el-form>
    </template>

    <template v-else-if="mode === 'replace'">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="替换后若此前评审已通过，系统将标记为需修改并建议重新发起需求评审。"
      />
      <el-tabs v-model="replaceTab">
        <el-tab-pane label="上传文件" name="file">
          <el-upload
            drag
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-remove="() => (file = null)"
            accept=".pdf,.doc,.docx,.txt,.md,.markdown"
          >
            <div class="upload-tip">拖拽或点击选择需求文档</div>
          </el-upload>
        </el-tab-pane>
        <el-tab-pane label="粘贴正文" name="paste">
          <el-input
            v-model="form.pasted_content"
            type="textarea"
            :rows="12"
            placeholder="粘贴 Markdown 或纯文本需求正文"
          />
        </el-tab-pane>
      </el-tabs>
    </template>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { testReleaseApi } from '@/api/testManagement'
import { aiRequirementApi } from '@/api/modules/ai.js'

const props = defineProps({
  modelValue: Boolean,
  mode: { type: String, default: 'edit' },
  releaseId: { type: Number, required: true },
  projectId: { type: Number, required: true },
  releaseReq: { type: Object, required: true }
})

const emit = defineEmits(['update:modelValue', 'done'])

const saving = ref(false)
const file = ref(null)
const replaceTab = ref('file')
const form = reactive({
  title: '',
  url: '',
  note: '',
  name: '',
  initial_content: '',
  pasted_content: ''
})

const dialogTitle = computed(() => {
  if (props.mode === 'replace') return '更新需求文档'
  if (props.mode === 'upgrade') return '升级为项目需求'
  return '编辑需求'
})

const aiId = () => {
  const row = props.releaseReq
  if (row?.ai_requirement_id) return row.ai_requirement_id
  const m = String(row?.requirement_key || '').match(/^REQ-(\d+)$/i)
  return m ? Number(m[1]) : null
}

const onFileChange = (uploadFile) => {
  file.value = uploadFile?.raw || null
}

const resetForm = () => {
  const row = props.releaseReq || {}
  form.title = row.title || ''
  form.url = row.url || ''
  form.note = row.note || ''
  form.name = row.title || row.requirement_key || ''
  form.initial_content = row.note || row.title || ''
  form.pasted_content = ''
  file.value = null
  replaceTab.value = 'file'
}

const handleReplaceResult = (res, id) => {
  const data = res.data?.data || {}
  emit('update:modelValue', false)
  emit('done', {
    mode: 'replace',
    aiRequirementId: id,
    reviewStatusReset: !!data.review_status_reset
  })
  if (data.review_status_reset) {
    ElMessage.warning('文档已更新，建议发起新一轮需求评审')
  } else {
    ElMessage.success(res.data?.message || '文档已更新')
  }
}

const submit = async () => {
  saving.value = true
  try {
    if (props.mode === 'edit') {
      await testReleaseApi.updateRequirement(
        props.releaseId,
        props.releaseReq.id,
        props.projectId,
        {
          title: form.title,
          url: form.url || null,
          note: form.note || null
        }
      )
      ElMessage.success('已保存')
      emit('update:modelValue', false)
      emit('done', { mode: 'edit' })
    } else if (props.mode === 'upgrade') {
      if (!form.name.trim()) {
        ElMessage.warning('请填写需求名称')
        return
      }
      await testReleaseApi.upgradeRequirementToAi(
        props.releaseId,
        props.releaseReq.id,
        props.projectId,
        {
          name: form.name.trim(),
          initial_content: form.initial_content || null
        }
      )
      ElMessage.success('已升级为项目需求')
      emit('update:modelValue', false)
      emit('done', { mode: 'upgrade' })
    } else if (props.mode === 'replace') {
      const id = aiId()
      if (!id) {
        ElMessage.warning('仅项目需求可更新文档')
        return
      }
      if (replaceTab.value === 'file') {
        if (!file.value) {
          ElMessage.warning('请选择文件')
          return
        }
        const res = await aiRequirementApi.replaceDocument(id, file.value, props.projectId)
        handleReplaceResult(res, id)
      } else {
        const text = form.pasted_content.trim()
        if (!text) {
          ElMessage.warning('请粘贴正文')
          return
        }
        const res = await aiRequirementApi.replaceContent(id, text, props.projectId)
        handleReplaceResult(res, id)
      }
    }
  } catch {
    ElMessage.error('操作失败')
  } finally {
    saving.value = false
  }
}

watch(
  () => [props.modelValue, props.releaseReq],
  ([v]) => {
    if (v) resetForm()
  }
)
</script>

<style scoped>
.upload-tip {
  padding: 24px;
  color: #606266;
  font-size: 13px;
}
</style>
