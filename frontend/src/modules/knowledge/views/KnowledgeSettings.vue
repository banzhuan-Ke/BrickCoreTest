<template>
  <div class="knowledge-settings">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="资料库生成配置"
      description="按项目保存。控制报告/计划/方案生成、词法 RAG、可选向量 Embedding 与资料问答模型等。向量 Embedding 默认关闭，在本页开启并保存即可。"
      style="margin-bottom: 16px;"
    />

    <el-alert
      v-if="!loading && retrieveStrategyHint"
      type="info"
      :closable="false"
      show-icon
      :title="'当前检索策略：' + retrieveStrategyLabel"
      :description="retrieveStrategyHint"
      style="margin-bottom: 16px;"
    />

    <el-skeleton v-if="loading" :rows="8" animated />

    <template v-else>
      <el-form :model="form" label-width="168px" class="settings-form">
        <el-card v-for="group in groups" :key="group.key" shadow="never" class="group-card">
          <template #header>
            <div class="group-head">
              <b>{{ group.label }}</b>
              <span class="group-desc">{{ group.description }}</span>
            </div>
          </template>

          <el-form-item
            v-for="field in fieldsByGroup(group.key)"
            :key="field.key"
            :label="field.label"
          >
            <div class="field-body">
              <el-switch
                v-if="field.type === 'bool'"
                v-model="form[field.key]"
                :disabled="isFieldDisabled(field)"
              />
              <el-select
                v-else-if="field.type === 'select'"
                v-model="form[field.key]"
                style="width: 280px;"
                :disabled="isFieldDisabled(field)"
              >
                <el-option
                  v-for="opt in field.options || []"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-select
                v-else-if="field.type === 'embed_provider'"
                v-model="form[field.key]"
                style="width: 280px;"
                :disabled="isFieldDisabled(field)"
                clearable
                placeholder="默认：通义千问"
                @change="onEmbedProviderChange"
              >
                <el-option
                  v-for="opt in embedProviders"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-select
                v-else-if="field.type === 'embed_model'"
                v-model="form[field.key]"
                style="width: 280px;"
                :disabled="isFieldDisabled(field)"
                clearable
                filterable
                allow-create
                default-first-option
                :placeholder="embedModelPlaceholder"
              >
                <el-option
                  v-for="opt in currentEmbedModelOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-select
                v-else-if="field.type === 'embed_config_id'"
                v-model="form[field.key]"
                style="width: 100%; max-width: 420px;"
                clearable
                :disabled="isFieldDisabled(field)"
                :loading="embedConfigsLoading"
                placeholder="留空则使用平台默认 Embedding 配置"
              >
                <el-option label="（留空 · 平台默认）" :value="null" />
                <el-option
                  v-for="c in enabledEmbedConfigs"
                  :key="c.id"
                  :label="embedConfigLabel(c)"
                  :value="c.id"
                />
              </el-select>
              <el-alert
                v-if="field.type === 'embed_config_id' && form.vector_embed_enabled"
                type="warning"
                :closable="false"
                show-icon
                class="embed-config-alert"
                title="Embedding 配置注意"
                description="同一项目请固定使用一套模型与向量维度；切换后须对文档重新「重建向量」，否则检索会不准或失败。通义单批最多 10 条分块，大文档向量化需数分钟属正常情况。"
              />
              <el-select
                v-else-if="field.type === 'ai_config_id'"
                v-model="form[field.key]"
                style="width: 100%; max-width: 420px;"
                clearable
                :disabled="isFieldDisabled(field)"
                :loading="aiConfigsLoading"
                placeholder="留空则使用场景绑定或同 Provider 默认配置"
              >
                <el-option label="（留空 · 使用场景绑定）" :value="null" />
                <el-option
                  v-for="c in enabledAiConfigs"
                  :key="c.id"
                  :label="aiConfigLabel(c)"
                  :value="c.id"
                />
              </el-select>
              <el-select
                v-else-if="field.type === 'multi_select'"
                v-model="form[field.key]"
                multiple
                collapse-tags
                collapse-tags-tooltip
                clearable
                style="width: 100%; max-width: 520px;"
                :disabled="isFieldDisabled(field)"
              >
                <el-option
                  v-for="opt in docTypeOptions"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
              <el-input-number
                v-else-if="field.type === 'int'"
                v-model="form[field.key]"
                :min="field.min"
                :max="field.max"
                :step="field.step || 1"
                controls-position="right"
                style="width: 180px;"
                :disabled="isFieldDisabled(field)"
              />
              <el-input-number
                v-else-if="field.type === 'float'"
                v-model="form[field.key]"
                :min="field.min"
                :max="field.max"
                :step="field.step || 0.05"
                controls-position="right"
                style="width: 180px;"
                :disabled="isFieldDisabled(field)"
              />
              <el-select
                v-else-if="field.type === 'folder_ids'"
                v-model="form[field.key]"
                multiple
                collapse-tags
                collapse-tags-tooltip
                clearable
                placeholder="选择默认引用的迭代文件夹"
                style="width: 100%; max-width: 420px;"
                :loading="foldersLoading"
              >
                <el-option
                  v-for="f in folderOptions"
                  :key="f.id"
                  :label="folderOptionLabel(f)"
                  :value="f.id"
                />
              </el-select>

              <div class="field-meta">
                <div>{{ field.description }}</div>
                <div class="field-tip">
                  推荐：{{ field.recommended }}
                  <span v-if="field.tip"> · {{ field.tip }}</span>
                </div>
              </div>
            </div>
          </el-form-item>
        </el-card>

        <el-form-item>
          <el-button v-if="canEdit" type="primary" :loading="saving" @click="save">保存配置</el-button>
          <el-button @click="resetDefaults">恢复推荐默认值</el-button>
        </el-form-item>
      </el-form>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import { aiConfigApi, embedConfigApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { useKnowledgePermissions } from '@/modules/knowledge/composables/useKnowledgePermissions.js'

const projectId = computed(() => ProjectStore().projectInfo?.id)
const { canEdit } = useKnowledgePermissions()

const loading = ref(true)
const saving = ref(false)
const groups = ref([])
const fields = ref([])
const defaults = ref({})
const embedCapabilities = ref({})
const form = reactive({})
const folderOptions = ref([])
const foldersLoading = ref(false)
const aiConfigList = ref([])
const aiConfigsLoading = ref(false)
const embedConfigList = ref([])
const embedConfigsLoading = ref(false)

const embedProviders = computed(() => embedCapabilities.value.providers || [])
const docTypeOptions = computed(() => embedCapabilities.value.doc_type_options || [])
const enabledAiConfigs = computed(() => aiConfigList.value.filter(c => c.is_enabled !== false))
const enabledEmbedConfigs = computed(() => embedConfigList.value.filter(c => c.is_enabled !== false))

const effectiveEmbedProvider = computed(() => {
  return form.vector_embed_provider || embedCapabilities.value.default_provider || 'qwen'
})

const currentEmbedProviderMeta = computed(() =>
  embedProviders.value.find(p => p.value === effectiveEmbedProvider.value) || embedProviders.value[0]
)

const currentEmbedModelOptions = computed(() => currentEmbedProviderMeta.value?.models || [])

const embedModelPlaceholder = computed(() => {
  const def = currentEmbedProviderMeta.value?.default_model
  return def ? `默认：${def}` : '选择或输入模型名'
})

const retrieveStrategyLabel = computed(() => {
  const s = form.retrieve_strategy || 'lexical'
  return { lexical: '词法检索', vector: '向量检索', hybrid: '混合检索' }[s] || s
})

const retrieveStrategyHint = computed(() => {
  const s = form.retrieve_strategy || 'lexical'
  if (s === 'lexical') {
    return '资料检索、资料问答与报告 RAG 默认用词法匹配，无 Embedding 费用。未建向量索引时，向量/混合策略会自动降级为此模式。'
  }
  if (s === 'vector') {
    return '问答与检索优先使用向量相似度；文档需已完成向量索引。无向量数据时自动降级为词法检索。'
  }
  return `混合检索综合词法与向量分数（当前词法权重 ${form.hybrid_lexical_weight ?? 0.4}）。适合已开启向量且希望兼顾关键词命中的场景。`
})

function folderOptionLabel(f) {
  const tag = f.iteration_label ? ` (${f.iteration_label})` : ''
  return `${f.name}${tag} · ${f.doc_count || 0} 文档`
}

function aiConfigLabel(c) {
  const p = c.provider ? ` · ${c.provider}` : ''
  return `${c.name || c.model}${p}`
}

function embedConfigLabel(c) {
  const def = c.is_default ? ' · 默认' : ''
  const p = c.provider ? ` · ${c.provider}` : ''
  const dim = c.dimensions ? ` · ${c.dimensions}维` : ''
  return `${c.name || c.model}${p}${dim}${def}`
}

function isFieldDisabled(field) {
  if (field.key === 'vector_embed_on_upload' && !form.vector_embed_enabled) return true
  if (field.key === 'hybrid_lexical_weight' && form.retrieve_strategy !== 'hybrid') return true
  return false
}

function onEmbedProviderChange() {
  const models = currentEmbedModelOptions.value.map(m => m.value)
  if (form.vector_embed_model && models.length && !models.includes(form.vector_embed_model)) {
    form.vector_embed_model = ''
  }
}

async function loadFolderOptions() {
  if (!projectId.value) {
    folderOptions.value = []
    return
  }
  foldersLoading.value = true
  try {
    const res = await knowledgeApi.listFolders(projectId.value)
    folderOptions.value = res.data?.items || []
  } finally {
    foldersLoading.value = false
  }
}

async function loadAiConfigs() {
  aiConfigsLoading.value = true
  try {
    const res = await aiConfigApi.getList({ size: 200 })
    if (res.data?.code === 200) {
      aiConfigList.value = res.data.data?.list || []
    }
  } catch (e) {
    console.warn('加载 AI 配置失败', e)
  } finally {
    aiConfigsLoading.value = false
  }
}

async function loadEmbedConfigs() {
  embedConfigsLoading.value = true
  try {
    const res = await embedConfigApi.getSelectOptions()
    if (res.data?.code === 200) {
      embedConfigList.value = res.data.data || []
    }
  } catch (e) {
    console.warn('加载 Embedding 配置失败', e)
  } finally {
    embedConfigsLoading.value = false
  }
}

function fieldsByGroup(groupKey) {
  return fields.value.filter(f => f.group === groupKey)
}

function applyValues(values) {
  for (const f of fields.value) {
    const key = f.key
    if (f.type === 'folder_ids' || f.type === 'multi_select') {
      const raw = (values && values[key] !== undefined) ? values[key] : defaults.value[key]
      form[key] = Array.isArray(raw) ? [...raw] : []
      continue
    }
    if (f.type === 'ai_config_id' || f.type === 'embed_config_id') {
      const raw = values && values[key] !== undefined ? values[key] : defaults.value[key]
      form[key] = raw == null || raw === '' ? null : raw
      continue
    }
    if (values && values[key] !== undefined) {
      form[key] = values[key]
    } else if (defaults.value[key] !== undefined) {
      form[key] = defaults.value[key]
    }
  }
}

async function load() {
  if (!projectId.value) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const res = await knowledgeApi.getSettings(projectId.value)
    const schema = res.data?.schema || {}
    groups.value = schema.groups || []
    fields.value = schema.fields || []
    defaults.value = schema.defaults || {}
    embedCapabilities.value = schema.embed_capabilities || res.data?.schema?.embed_capabilities || {}
    applyValues(res.data?.values || defaults.value)
    await Promise.all([loadFolderOptions(), loadAiConfigs(), loadEmbedConfigs()])
  } catch (e) {
    ElMessage.error(e?.message || '加载配置失败')
  } finally {
    loading.value = false
  }
}

function resetDefaults() {
  applyValues(defaults.value)
  ElMessage.info('已恢复为系统推荐默认值（未保存）')
}

async function save() {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  saving.value = true
  try {
    const payload = { ...form }
    const res = await knowledgeApi.updateSettings(payload, projectId.value)
    applyValues(res.data?.values || payload)
    ElMessage.success('资料库生成配置已保存')
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(load)
watch(projectId, load)
</script>

<style scoped>
.knowledge-settings {
  max-width: 960px;
}
.group-card {
  margin-bottom: 16px;
}
.group-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.group-desc {
  font-size: 12px;
  font-weight: normal;
  color: var(--el-text-color-secondary);
}
.field-body {
  width: 100%;
}
.field-meta {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}
.field-tip {
  color: var(--el-text-color-secondary);
}
.embed-config-alert {
  margin-top: 8px;
  max-width: 520px;
}
</style>
