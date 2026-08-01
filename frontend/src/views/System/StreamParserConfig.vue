<template>
  <ConfigShell :embedded="embedded">
    <template #title>
      <b>SSE 解析配置</b>
    </template>
    <template #main>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="用途说明"
        description="在此维护 SSE 流式接口的解析方案（内置解析器 + 规则/选项）。压测「流式阶段」等可引用此处配置，无需改代码。"
        style="margin-bottom: 16px;"
      />
      <div class="toolbar">
        <el-button v-if="canEdit" type="primary" :icon="Plus" @click="openForm()">新增配置</el-button>
        <el-button :icon="Refresh" @click="loadList">刷新</el-button>
      </div>
      <el-table v-loading="loading" :data="rows" size="small" stripe>
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="parser_display_name" label="解析器类型" width="140" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.is_builtin" type="info" size="small">内置</el-tag>
            <el-tag :type="row.is_enabled ? 'success' : 'info'" size="small">
              {{ row.is_enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="70" />
        <el-table-column prop="update_by" label="更新人" width="100" show-overflow-tooltip />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openForm(row)">编辑</el-button>
            <el-button
              v-if="canEdit && !row.is_builtin"
              link
              type="danger"
              size="small"
              @click="removeRow(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-drawer
        v-model="formVisible"
        :title="form.id ? '编辑解析配置' : '新增解析配置'"
        size="960px"
        class="stream-parser-drawer"
        destroy-on-close
      >
        <el-form label-width="110px" class="config-form">
          <el-collapse v-if="canAiGenerate" v-model="aiCollapse" class="ai-collapse">
            <el-collapse-item title="AI 生成规则" name="ai">
              <el-alert
                type="info"
                :closable="false"
                show-icon
                style="margin-bottom: 12px"
                title="粘贴 SSE 样例 + 白话阶段说明 → 生成「规则配置」草稿；确认后点保存。阶段说明不要粘贴整段 data: JSON；样例可只留代表性几行（思考 / 正式回答首字 / 结束）。"
              />
              <el-form-item label="SSE 样例">
                <el-input
                  v-model="aiSampleText"
                  type="textarea"
                  :rows="6"
                  placeholder="粘贴 data: {...} 行即可（id:/event: 可省略）。超长 eof/references 可删，保留各阶段各 1～2 行代表即可"
                />
              </el-form-item>
              <el-form-item required>
                <template #label>
                  <span class="form-label-with-tip">
                    阶段说明
                    <el-popover
                      placement="bottom-start"
                      :width="440"
                      trigger="click"
                      popper-class="phase-desc-example-pop"
                    >
                      <template #reference>
                        <el-icon class="tip-icon" title="查看案例"><QuestionFilled /></el-icon>
                      </template>
                      <div class="phase-desc-example">
                        <div class="phase-desc-example-head">
                          <span>阶段说明案例（可选中复制）</span>
                          <el-button type="primary" link size="small" @click="copyPhaseDescExample">复制全部</el-button>
                        </div>
                        <pre
                          ref="phaseDescExampleRef"
                          class="phase-desc-example-pre"
                          @click="selectPhaseDescExample"
                        >{{ PHASE_DESC_EXAMPLE }}</pre>
                      </div>
                    </el-popover>
                  </span>
                </template>
                <el-input
                  v-model="aiPhaseDescription"
                  type="textarea"
                  :rows="3"
                  placeholder="白话即可；点左侧问号可查看完整案例并复制"
                />
              </el-form-item>
              <el-form-item label="名称提示">
                <el-input v-model="aiNameHint" placeholder="可选，建议生成配置名称" />
              </el-form-item>
              <el-form-item label="模型">
                <el-select
                  v-model="aiConfigId"
                  clearable
                  filterable
                  placeholder="默认按场景绑定"
                  style="width: 100%"
                >
                  <el-option
                    v-for="c in aiConfigOptions"
                    :key="c.id"
                    :label="formatAiConfigLabel(c)"
                    :value="c.id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="aiGenerating" @click="runAiGenerate">生成规则</el-button>
                <el-button
                  v-if="aiTestPreview"
                  :loading="testing"
                  @click="applyAiTestPreview"
                >查看试解析结果</el-button>
              </el-form-item>
            </el-collapse-item>
          </el-collapse>

          <el-form-item label="名称" required>
            <el-input v-model="form.name" placeholder="如：KCF 问答 SSE v1" />
          </el-form-item>
          <el-form-item label="说明文档">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="4"
              placeholder="Markdown：适用接口、字段说明、鉴权注意事项等"
            />
          </el-form-item>
          <el-form-item label="解析器类型" required>
            <el-select v-model="form.parser_id" style="width: 100%" @change="onParserTypeChange">
              <el-option
                v-for="p in builtinParsers"
                :key="p.parser_id"
                :label="p.display_name"
                :value="p.parser_id"
              >
                <span>{{ p.display_name }}</span>
                <span style="float: right; color: var(--el-text-color-secondary); font-size: 12px">
                  {{ p.parser_id }}
                </span>
              </el-option>
            </el-select>
            <div class="field-hint">
              「问答流式 v1」适用于 KCF 标准协议；「规则配置」为标准 data/event SSE + 阶段匹配（可加预处理整形嵌套 JSON / Patch 流）；
              「自定义 SSE」可改 datas/events 等行前缀，适配其它组协议；「仅总耗时」不做内容解析。
            </div>
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="form.is_enabled" />
          </el-form-item>
          <el-form-item label="排序">
            <el-input-number v-model="form.sort_order" :min="0" :max="9999" />
          </el-form-item>
          <div v-if="usesRuleBuilder" class="rules-panel">
            <StreamRuleBuilder
              v-model="form.parser_options.rules"
              :show-frame-prefixes="form.parser_id === 'custom_sse'"
            />
          </div>
          <el-form-item label="成功判定">
            <el-select v-model="successPhaseKey" style="width: 160px" @change="onSuccessRuleChange">
              <el-option label="阶段出现即成功" value="phase_exists" />
              <el-option label="HTTP 2xx 即成功" value="status_ok" />
            </el-select>
            <el-select
              v-if="successPhaseKey === 'phase_exists'"
              v-model="form.success_rule.phase"
              style="width: 180px; margin-left: 12px"
              placeholder="选择阶段"
            >
              <el-option
                v-for="s in currentPhaseSchema"
                :key="s.key"
                :label="s.label || s.key"
                :value="s.key"
              />
            </el-select>
          </el-form-item>

          <el-divider content-position="left">解析测试</el-divider>
          <el-form-item label="SSE 原始行">
            <el-input
              v-model="testLinesText"
              type="textarea"
              :rows="8"
              placeholder="粘贴 SSE 原始行（标准 data: 或自定义 datas: 等），每行一条"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="success" :loading="testing" @click="runTest">测试解析</el-button>
            <div class="field-hint">
              开启预处理时，结果中的 <code>match_view_samples</code> 为整形后的匹配视图样本，便于核对 path / 字段。
            </div>
          </el-form-item>
          <el-form-item v-if="testResult" label="解析结果">
            <pre class="test-result">{{ testResult }}</pre>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="formVisible = false">取消</el-button>
          <el-button v-if="canEdit" type="primary" :loading="saving" @click="saveForm">保存</el-button>
        </template>
      </el-drawer>
    </template>
  </ConfigShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, QuestionFilled } from '@element-plus/icons-vue'
import ConfigShell from '@/components/ConfigShell.vue'
import StreamRuleBuilder from '@/components/perf/StreamRuleBuilder.vue'
import { streamParserConfigApi } from '@/api/modules/sys.js'
import { aiConfigApi, aiGenerateApi } from '@/api/modules/ai.js'
import { UserStore } from '@/stores/module/UserStore'

defineProps({
  embedded: { type: Boolean, default: false }
})

const uStore = UserStore()
const canEdit = computed(() => uStore.hasPermission('ai_config:edit'))
const canAiGenerate = computed(() => uStore.hasPermission('ai_test:execute'))

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const rows = ref([])
const builtinParsers = ref([])
const formVisible = ref(false)
const testLinesText = ref('')
const testResult = ref('')
const successPhaseKey = ref('phase_exists')

const aiCollapse = ref(['ai'])
const aiSampleText = ref('')
const aiPhaseDescription = ref('')
const aiNameHint = ref('')
const aiConfigId = ref(null)
const aiConfigOptions = ref([])
const aiGenerating = ref(false)
const aiTestPreview = ref(null)
const phaseDescExampleRef = ref(null)

const PHASE_DESC_EXAMPLE = `从 SSE 样例里按字段匹配阶段（不要整段粘贴 JSON）：

【标准多阶段问答】
1. 理解首字：type=think_answer，且 delta 文本非空 → 记为 think_answer
2. 意图完成：type=think，action=intent，status=success → 记为 intent_complete
3. 正式回答首字：type=output_text，且 delta 非空 → 记为 first_char
4. 派生：思考耗时 = first_char - intent_complete；回答耗时 = total_time - first_char

【快速模式：仅检索 + 问答（无多轮）】
1. 检索完成：type=think，action=search，status=success → 记为 search_done
2. 问答开始：type=think，action=done，status=success → 记为 answer_start
3. 派生：问答耗时 = total_time - answer_start
注意：不要写「xxx - start」；阶段时刻本身已是相对流开始的耗时。`

const selectPhaseDescExample = () => {
  const el = phaseDescExampleRef.value
  if (!el) return
  const range = document.createRange()
  range.selectNodeContents(el)
  const sel = window.getSelection()
  sel?.removeAllRanges()
  sel?.addRange(range)
}

const copyPhaseDescExample = async () => {
  try {
    await navigator.clipboard.writeText(PHASE_DESC_EXAMPLE)
    ElMessage.success('已复制阶段说明案例')
  } catch {
    selectPhaseDescExample()
    ElMessage.warning('自动复制失败，已选中文本，请 Ctrl+C')
  }
}

const form = reactive({
  id: null,
  name: '',
  description: '',
  parser_id: 'qa_sse_v1',
  parser_options: { rules: {} },
  success_rule: { type: 'phase_exists', phase: 'first_char' },
  is_enabled: true,
  sort_order: 0
})

const RULE_BUILDER_IDS = new Set(['rule_based', 'custom_sse'])
const usesRuleBuilder = computed(() => RULE_BUILDER_IDS.has(form.parser_id))

const schemaFromRules = (rules) => {
  const schema = []
  for (const p of rules?.phases || []) {
    if (p?.key) schema.push({ key: p.key, label: p.label || p.key })
  }
  for (const d of rules?.derived || []) {
    if (d?.key) schema.push({ key: d.key, label: d.label || d.key })
  }
  schema.push({ key: 'total_time', label: '整体耗时(s)' })
  return schema
}

const currentPhaseSchema = computed(() => {
  if (usesRuleBuilder.value) {
    return schemaFromRules(form.parser_options?.rules)
  }
  const p = builtinParsers.value.find((x) => x.parser_id === form.parser_id)
  return p?.phase_schema || []
})

const formatAiConfigLabel = (c) => {
  if (!c) return ''
  const name = c.name || c.model || `#${c.id}`
  const provider = c.provider ? ` · ${c.provider}` : ''
  return `${name}${provider}`
}

function resetAiFields() {
  aiSampleText.value = ''
  aiPhaseDescription.value = ''
  aiNameHint.value = ''
  aiConfigId.value = null
  aiTestPreview.value = null
  aiCollapse.value = form.id ? [] : ['ai']
}

function resetForm() {
  form.id = null
  form.name = ''
  form.description = ''
  form.parser_id = 'qa_sse_v1'
  form.parser_options = { rules: {} }
  form.success_rule = { type: 'phase_exists', phase: 'first_char' }
  form.is_enabled = true
  form.sort_order = 0
  testLinesText.value = ''
  testResult.value = ''
  successPhaseKey.value = 'phase_exists'
  resetAiFields()
}

async function loadAiConfigOptions() {
  if (!canAiGenerate.value) {
    aiConfigOptions.value = []
    return
  }
  try {
    const res = await aiConfigApi.getSelectOptions()
    const data = res?.data?.data || res?.data || res || []
    aiConfigOptions.value = Array.isArray(data) ? data : []
  } catch {
    aiConfigOptions.value = []
  }
}

function openForm(row) {
  resetForm()
  if (row) {
    form.id = row.id
    form.name = row.name
    form.description = row.description || ''
    form.parser_id = row.parser_id
    form.parser_options = row.parser_options?.rules
      ? { rules: JSON.parse(JSON.stringify(row.parser_options.rules)) }
      : { rules: {} }
    form.success_rule = row.success_rule?.type
      ? { ...row.success_rule }
      : { type: 'phase_exists', phase: 'first_char' }
    form.is_enabled = row.is_enabled !== false
    form.sort_order = row.sort_order || 0
    successPhaseKey.value = form.success_rule.type === 'status_ok' ? 'status_ok' : 'phase_exists'
    aiCollapse.value = []
  }
  loadAiConfigOptions()
  formVisible.value = true
}

function onParserTypeChange() {
  const p = builtinParsers.value.find((x) => x.parser_id === form.parser_id)
  if (p?.default_success_rule) {
    form.success_rule = { ...p.default_success_rule }
    successPhaseKey.value = form.success_rule.type === 'status_ok' ? 'status_ok' : 'phase_exists'
  }
  if (usesRuleBuilder.value && !form.parser_options?.rules?.phases?.length) {
    const preset = p?.default_options?.rules
    if (preset) {
      form.parser_options = { rules: JSON.parse(JSON.stringify(preset)) }
    }
  }
}

function onSuccessRuleChange() {
  if (successPhaseKey.value === 'status_ok') {
    form.success_rule = { type: 'status_ok' }
  } else {
    form.success_rule = {
      type: 'phase_exists',
      phase: form.success_rule?.phase || 'first_char'
    }
  }
}

async function runAiGenerate() {
  if (!canAiGenerate.value) {
    ElMessage.warning('需要 ai_test:execute 权限')
    return
  }
  const sample = (aiSampleText.value || '').trim()
  const phaseDesc = (aiPhaseDescription.value || '').trim()
  if (!sample) {
    ElMessage.warning('请粘贴 SSE 样例')
    return
  }
  if (!phaseDesc) {
    ElMessage.warning('请填写阶段说明')
    return
  }
  aiGenerating.value = true
  aiTestPreview.value = null
  try {
    const res = await aiGenerateApi.generateStreamParserRules({
      sample_text: sample,
      phase_description: phaseDesc,
      name_hint: (aiNameHint.value || '').trim() || undefined,
      ai_config_id: aiConfigId.value || undefined,
      run_test: true
    })
    const data = res.data?.data || res.data || {}
    const draft = data.draft
    if (!draft) {
      ElMessage.error('未返回规则草稿')
      return
    }
    form.parser_id = 'rule_based'
    if (draft.name) form.name = draft.name
    if (draft.description) form.description = draft.description
    form.parser_options = {
      rules: JSON.parse(JSON.stringify(draft.parser_options?.rules || {}))
    }
    form.success_rule = draft.success_rule?.type
      ? { ...draft.success_rule }
      : { type: 'phase_exists', phase: 'first_char' }
    successPhaseKey.value = form.success_rule.type === 'status_ok' ? 'status_ok' : 'phase_exists'
    if (!testLinesText.value.trim()) {
      testLinesText.value = sample
    }
    aiTestPreview.value = data.test_preview || null
    if (aiTestPreview.value && !aiTestPreview.value.error) {
      testResult.value = JSON.stringify(aiTestPreview.value, null, 2)
    }
    const warns = data.normalize_warnings || []
    if (warns.length) {
      ElMessage.warning({
        message: `已生成草稿（自动修正 ${warns.length} 处）：${warns.slice(0, 2).join('；')}${warns.length > 2 ? '…' : ''}，请核对阶段后保存`,
        duration: 8000
      })
    } else {
      ElMessage.success(
        data.tokens_used != null
          ? `已生成规则草稿（${data.tokens_used} tokens），请确认后保存`
          : '已生成规则草稿，请确认后保存'
      )
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '生成失败')
  } finally {
    aiGenerating.value = false
  }
}

function applyAiTestPreview() {
  if (!aiTestPreview.value) return
  testResult.value = JSON.stringify(aiTestPreview.value, null, 2)
  if (!testLinesText.value.trim() && aiSampleText.value) {
    testLinesText.value = aiSampleText.value
  }
}

async function loadBuiltinParsers() {
  const res = await streamParserConfigApi.getBuiltinParsers()
  builtinParsers.value = res.data?.data || res.data || []
}

async function loadList() {
  loading.value = true
  try {
    await loadBuiltinParsers()
    const res = await streamParserConfigApi.getList()
    rows.value = res.data?.data || res.data || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function buildPayload() {
  const payload = {
    name: (form.name || '').trim(),
    description: form.description || '',
    parser_id: form.parser_id,
    parser_options: usesRuleBuilder.value ? { rules: form.parser_options?.rules || {} } : {},
    success_rule: form.success_rule || {},
    is_enabled: form.is_enabled,
    sort_order: form.sort_order || 0
  }
  if (!payload.name) {
    throw new Error('请填写名称')
  }
  return payload
}

async function saveForm() {
  if (!canEdit.value) return
  let payload
  try {
    payload = buildPayload()
  } catch (e) {
    ElMessage.warning(e.message)
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await streamParserConfigApi.update(form.id, payload)
      ElMessage.success('已保存')
    } else {
      await streamParserConfigApi.create(payload)
      ElMessage.success('已创建')
    }
    formVisible.value = false
    await loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function removeRow(row) {
  if (!canEdit.value || row.is_builtin) return
  try {
    await ElMessageBox.confirm(`确定删除「${row.name}」？`, '删除确认', { type: 'warning' })
    await streamParserConfigApi.delete(row.id)
    ElMessage.success('已删除')
    await loadList()
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

async function runTest() {
  const lines = (testLinesText.value || '').split(/\r?\n/).filter((l) => l.trim())
  if (!lines.length) {
    ElMessage.warning('请粘贴 SSE 原始行')
    return
  }
  testing.value = true
  testResult.value = ''
  try {
    const payload = buildPayload()
    const res = await streamParserConfigApi.test({
      parser_id: payload.parser_id,
      lines,
      parser_options: payload.parser_options,
      success_rule: payload.success_rule,
      debug_match_views: true,
    })
    const data = res.data?.data || res.data
    testResult.value = JSON.stringify(data, null, 2)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '测试失败')
  } finally {
    testing.value = false
  }
}

onMounted(loadList)
</script>

<style scoped>
.toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
}
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.test-result {
  margin: 0;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  max-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.ai-collapse {
  margin-bottom: 12px;
}
.rules-panel {
  margin: 4px 0 16px;
  padding: 4px 0 0;
}
.config-form :deep(.el-form-item) {
  margin-bottom: 16px;
}
.form-label-with-tip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.tip-icon {
  color: var(--el-text-color-secondary);
  cursor: pointer;
  font-size: 14px;
  vertical-align: middle;
}
.tip-icon:hover {
  color: var(--el-color-primary);
}
</style>

<style>
/* drawer / popover 挂到 body，需非 scoped */
.stream-parser-drawer.el-drawer {
  --el-drawer-padding-primary: 20px 24px;
}
.stream-parser-drawer .el-drawer__header {
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.stream-parser-drawer .el-drawer__body {
  padding-top: 8px;
}
.phase-desc-example-pop {
  max-width: 460px;
}
.phase-desc-example-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.phase-desc-example-pre {
  margin: 0;
  padding: 10px 12px;
  max-height: 280px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  user-select: text;
  cursor: text;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  color: var(--el-text-color-regular);
}
</style>
