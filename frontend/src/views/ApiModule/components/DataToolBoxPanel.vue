<template>
  <div class="toolbox-layout">
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
      通用工具箱：随机/编码/加密/JSON/测试数据等。用例中可直接点「<strong>插入工具</strong>」生成 <code v-pre>${{dt:md5|text=@变量}}</code>；固定值也可「保存为标签」后用 <code v-pre>${{df:标签名}}</code>。
    </el-alert>

    <div v-if="favoriteTools.length" class="favorites-bar">
      <span class="favorites-label">常用工具</span>
      <el-tag
        v-for="t in favoriteTools"
        :key="t.id"
        class="fav-tag"
        effect="plain"
        type="warning"
        @click="pickTool(t.id)"
      >{{ t.name }}</el-tag>
    </div>

    <div class="toolbox-body">
      <div class="toolbox-sidebar">
        <div
          v-for="cat in categories"
          :key="cat.id"
          :class="['cat-item', { active: activeCategory === cat.id }]"
          @click="selectCategory(cat.id)"
        >
          {{ cat.label }}
        </div>
      </div>

      <div class="toolbox-main">
        <div class="tool-select-row">
          <el-select v-model="selectedToolId" placeholder="选择工具" style="flex: 1;" @change="onToolChange">
            <el-option v-for="t in filteredTools" :key="t.id" :label="t.name" :value="t.id">
              <span>{{ t.name }}</span>
              <span style="float:right;color:#909399;font-size:12px">{{ t.description }}</span>
            </el-option>
          </el-select>
          <el-button
            v-if="selectedToolId"
            link
            :type="isToolFavorited(selectedToolId) ? 'warning' : 'info'"
            :icon="isToolFavorited(selectedToolId) ? 'StarFilled' : 'Star'"
            @click="toggleToolFavorite(selectedToolId)"
          >{{ isToolFavorited(selectedToolId) ? '已收藏' : '收藏' }}</el-button>
        </div>

        <template v-if="currentTool">
          <p class="tool-desc">{{ currentTool.description }}</p>
          <el-alert
            v-if="factoryOnlyToolIds.has(currentTool.id)"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px;"
          >
            此工具用于数据工厂内调试/比对，输出不适合直接写入请求参数；加密、随机、摘要等单值结果请保存为标签后在用例中引用。
          </el-alert>
          <el-form label-width="100px" size="default">
            <el-form-item v-for="field in currentTool.inputs" :key="field.key" :label="field.label">
              <el-input
                v-if="field.type === 'textarea'"
                v-model="toolInputs[field.key]"
                type="textarea"
                :rows="4"
                :placeholder="field.placeholder || ''"
              />
              <el-input-number
                v-else-if="field.type === 'number'"
                v-model="toolInputs[field.key]"
                controls-position="right"
                style="width: 200px;"
              />
              <el-input v-else v-model="toolInputs[field.key]" :placeholder="field.placeholder || ''" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="executing" @click="runTool">执行</el-button>
              <el-button :disabled="!outputText" @click="copyOutput">复制结果</el-button>
            </el-form-item>
          </el-form>

          <div v-if="outputText" class="output-box">
            <div class="output-title">
              <span>输出结果</span>
              <span class="output-resize-hint">拖拽右下角可调整高度</span>
            </div>
            <div v-if="qrcodePreviewSrc" class="qrcode-preview">
              <img :src="qrcodePreviewSrc" alt="二维码预览" />
              <div class="qrcode-preview-tip">扫码预览（保存标签后可在接口中引用 Base64 或单独存文本）</div>
            </div>
            <pre class="output-pre">{{ outputText }}</pre>
          </div>

          <el-divider v-if="outputText">保存为标签（供接口引用）</el-divider>
          <el-form v-if="outputText" label-width="100px" size="default">
            <el-form-item label="环境">
              <DfEnvScopeSelect v-model="saveEnvId" placeholder="选择标签生效范围" />
              <div class="tag-hint">选「当前项目通用」表示本项目下所有执行环境均可引用；选具体环境则仅在该环境覆盖/隔离。</div>
            </el-form-item>
            <el-form-item label="主标签" required>
              <el-input v-model="saveTag" placeholder="如 login_mobile" />
              <div class="tag-hint">引用写法：<code v-pre>${{df:标签名}}</code></div>
            </el-form-item>
            <el-form-item label="附加标签">
              <el-input v-model="saveExtraTags" placeholder="逗号分隔，可选" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="saveRemark" />
            </el-form-item>
            <el-form-item>
              <el-button type="success" :loading="saving" @click="saveRecord">保存记录</el-button>
            </el-form-item>
          </el-form>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dataFactoryApi } from '@/api/modules/dataFactory'
import { ProjectStore } from '@/stores/module/ProjectStore'
import DfEnvScopeSelect from '@/components/DfEnvScopeSelect.vue'

const props = defineProps({
  projectId: { type: Number, required: true }
})

const emit = defineEmits(['saved'])

const proStore = ProjectStore()
const factoryOnlyToolIds = new Set(['json_compare', 'cron_validate'])
const categories = ref([])
const tools = ref([])
const activeCategory = ref('random')
const selectedToolId = ref('')
const toolInputs = ref({})
const executing = ref(false)
const saving = ref(false)
const outputText = ref('')
const outputData = ref(null)
const saveEnvId = ref(null)
const saveTag = ref('')
const saveExtraTags = ref('')
const saveRemark = ref('')
const favoriteToolIds = ref(new Set())

const filteredTools = computed(() => tools.value.filter(t => t.category === activeCategory.value))
const favoriteTools = computed(() => {
  const ids = favoriteToolIds.value
  return tools.value.filter((t) => ids.has(t.id))
})
const currentTool = computed(() => tools.value.find(t => t.id === selectedToolId.value))
const qrcodePreviewSrc = computed(() => {
  if (selectedToolId.value !== 'qrcode_base64') return ''
  const text = outputText.value || ''
  return text.startsWith('data:image') ? text : ''
})

function pickTool(toolId) {
  const tool = tools.value.find((t) => t.id === toolId)
  if (!tool) return
  activeCategory.value = tool.category
  selectedToolId.value = tool.id
  resetInputs(tool)
}

function selectCategory(id) {
  activeCategory.value = id
  const first = filteredTools.value[0]
  if (first) {
    selectedToolId.value = first.id
    resetInputs(first)
  }
}

function isToolFavorited(toolId) {
  return favoriteToolIds.value.has(toolId)
}

async function loadFavorites() {
  try {
    const res = await dataFactoryApi.listFavorites({ project_id: props.projectId })
    const ids = new Set()
    for (const item of res.data || []) {
      if (item.item_type === 'tool') ids.add(item.item_key)
    }
    favoriteToolIds.value = ids
  } catch {
    favoriteToolIds.value = new Set()
  }
}

async function toggleToolFavorite(toolId) {
  try {
    if (isToolFavorited(toolId)) {
      await dataFactoryApi.removeFavorite(props.projectId, { item_type: 'tool', item_key: toolId })
      favoriteToolIds.value.delete(toolId)
      ElMessage.success('已取消收藏')
    } else {
      await dataFactoryApi.addFavorite(props.projectId, { item_type: 'tool', item_key: toolId })
      favoriteToolIds.value.add(toolId)
      ElMessage.success('已加入常用工具')
    }
    favoriteToolIds.value = new Set(favoriteToolIds.value)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '操作失败')
  }
}

function resetInputs(tool) {
  const inputs = {}
  for (const f of tool?.inputs || []) {
    inputs[f.key] = f.default ?? (f.type === 'number' ? 0 : '')
  }
  toolInputs.value = inputs
  outputText.value = ''
  outputData.value = null
}

function onToolChange() {
  resetInputs(currentTool.value)
}

async function loadCatalog() {
  const res = await dataFactoryApi.getToolsCatalog()
  categories.value = res.data?.categories || []
  tools.value = res.data?.tools || []
  if (categories.value.length && !selectedToolId.value) {
    activeCategory.value = categories.value[0].id
    const first = filteredTools.value[0]
    if (first) {
      selectedToolId.value = first.id
      resetInputs(first)
    }
  }
}

async function runTool() {
  if (!selectedToolId.value) return
  executing.value = true
  try {
    const res = await dataFactoryApi.executeTool({
      tool_id: selectedToolId.value,
      inputs: { ...toolInputs.value }
    })
    outputText.value = res.data?.output_text ?? ''
    outputData.value = res.data?.output ?? null
    if (!saveTag.value && currentTool.value) {
      saveTag.value = `${currentTool.value.id}_${Date.now().toString().slice(-6)}`
    }
    ElMessage.success('执行成功')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '执行失败')
  } finally {
    executing.value = false
  }
}

async function copyOutput() {
  try {
    await navigator.clipboard.writeText(outputText.value)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function saveRecord() {
  if (!saveTag.value?.trim()) {
    ElMessage.warning('请填写主标签')
    return
  }
  saving.value = true
  try {
    const extra = saveExtraTags.value.split(/[,，]/).map(s => s.trim()).filter(Boolean)
    await dataFactoryApi.createToolRecord({
      project_id: props.projectId,
      environment_id: saveEnvId.value || null,
      tool_id: selectedToolId.value,
      tool_name: currentTool.value?.name || selectedToolId.value,
      tool_category: currentTool.value?.category || '',
      tag: saveTag.value.trim(),
      tags: extra,
      input_data: { ...toolInputs.value },
      output_data: outputData.value,
      output_text: outputText.value,
      remark: saveRemark.value || null
    })
    ElMessage.success('已保存，可在接口用例中使用 ${{df:' + saveTag.value.trim() + '}}')
    emit('saved')
    saveTag.value = ''
    saveExtraTags.value = ''
    saveRemark.value = ''
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

watch(() => props.projectId, async () => {
  await loadCatalog()
  await loadFavorites()
})

onMounted(async () => {
  if (!proStore.envList?.length) await proStore.getEnvList(props.projectId)
  await Promise.all([loadCatalog(), loadFavorites()])
})
</script>

<style scoped>
.toolbox-layout { width: 100%; }
.favorites-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: #fdf6ec;
  border-radius: 4px;
}
.favorites-label {
  font-size: 12px;
  color: #e6a23c;
  font-weight: 500;
}
.fav-tag { cursor: pointer; }
.tool-select-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.toolbox-body {
  display: flex;
  gap: 16px;
  min-height: 420px;
}
.toolbox-sidebar {
  width: 120px;
  flex-shrink: 0;
  border-right: 1px solid #ebeef5;
  padding-right: 8px;
}
.cat-item {
  padding: 8px 10px;
  cursor: pointer;
  border-radius: 4px;
  font-size: 13px;
  color: #606266;
}
.cat-item:hover { background: #f5f7fa; }
.cat-item.active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 500;
}
.toolbox-main { flex: 1; min-width: 0; }
.tool-desc { font-size: 13px; color: #909399; margin: 0 0 12px; }
.output-box {
  background: #f5f7fa;
  border-radius: 4px;
  padding: 10px;
  margin-bottom: 12px;
}
.output-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}
.output-resize-hint {
  font-size: 11px;
  color: #c0c4cc;
  font-weight: normal;
}
.qrcode-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 12px;
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
}
.qrcode-preview img {
  max-width: 220px;
  max-height: 220px;
  object-fit: contain;
}
.qrcode-preview-tip {
  font-size: 12px;
  color: #909399;
}
.tag-hint { font-size: 12px; color: #909399; margin-top: 4px; }
.output-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  height: 200px;
  min-height: 120px;
  max-height: 80vh;
  overflow: auto;
  resize: vertical;
  box-sizing: border-box;
  padding: 8px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}
</style>
