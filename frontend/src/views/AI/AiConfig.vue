<template>
  <ConfigShell :embedded="embedded">
    <template #title>
      <b>🤖 AI 模型配置</b>
    </template>
    <template #main>
      <el-tabs v-model="activeTab" type="border-card">
        <!-- Tab 1: LLM 模型配置 -->
        <el-tab-pane label="LLM 模型配置" name="config">
          <div style="margin-bottom: 16px;">
            <el-button type="primary" @click="openConfigDialog()" icon="Plus">新增配置</el-button>
          </div>

          <el-table :data="configList" stripe border v-loading="configLoading">
            <el-table-column prop="name" label="配置名称" min-width="120"/>
            <el-table-column prop="provider" label="供应商" width="100">
              <template #default="{row}">
                <el-tag size="small">{{ providerMap[row.provider] || row.provider }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="model" label="模型" min-width="140"/>
            <el-table-column prop="api_key" label="API Key" min-width="140">
              <template #default="{row}">
                <span class="key-mask">{{ row.api_key }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="temperature" label="温度" width="80"/>
            <el-table-column prop="thinking_enabled" label="思考模式" width="100">
              <template #default="{row}">
                <el-tag v-if="row.thinking_enabled" type="warning" size="small">{{ row.reasoning_effort || '中' }}</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="is_default" label="默认" width="80">
              <template #default="{row}">
                <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="is_enabled" label="启用" width="80">
              <template #default="{row}">
                <el-switch v-model="row.is_enabled" @change="(val) => toggleEnabled(row, val)" size="small"/>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{row}">
                <el-tooltip content="连通性测试" placement="top">
                  <el-button circle size="small" type="success" @click="testConfig(row)" :loading="row._testing" icon="VideoPlay"/>
                </el-tooltip>
                <el-tooltip v-if="!row.is_default" content="设为默认" placement="top">
                  <el-button circle size="small" @click="setDefault(row)" icon="Star"/>
                </el-tooltip>
                <el-tooltip content="编辑" placement="top">
                  <el-button circle size="small" type="primary" @click="openConfigDialog(row)" icon="Edit"/>
                </el-tooltip>
                <el-tooltip content="删除" placement="top">
                  <el-button circle size="small" type="danger" @click="deleteConfig(row)" icon="Delete"/>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="Embedding 模型配置" name="embed">
          <AiEmbedConfig />
        </el-tab-pane>

        <!-- Tab: 场景绑定 -->
        <el-tab-pane label="场景绑定" name="scene">
          <el-alert
            v-if="!sceneMeta.has_enabled_config"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px;"
            title="尚未创建任何已启用的 LLM 配置。请先在「LLM 模型配置」Tab 新建并启用至少一条配置。"
          />
          <el-alert
            v-else-if="sceneMeta.unbound_count > 0"
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 12px;"
            :title="`还有 ${sceneMeta.unbound_count} 个场景未绑定专用模型，将跟随全局默认。可点击下方「一键套用推荐」快速绑定。`"
          />
          <el-alert
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom: 16px;"
            title="为各 AI 业务场景指定默认模型；留空表示跟随「LLM 模型配置」中的全局默认项。弹窗中手动选择的模型仍优先。"
          />
          <div class="scene-toolbar">
            <el-button type="primary" plain :loading="sceneApplying" @click="applySceneRecommendations">
              一键套用推荐
            </el-button>
            <el-button @click="activeTab = 'config'">去创建 LLM 配置</el-button>
          </div>
          <el-table :data="groupedSceneBindings" stripe border v-loading="sceneLoading" style="width: 100%;">
            <el-table-column label="分组" width="110">
              <template #default="{ row }">{{ sceneGroupLabel(row.group) }}</template>
            </el-table-column>
            <el-table-column prop="label" label="场景" width="150" />
            <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
            <el-table-column label="推荐模型" width="160">
              <template #default="{ row }">
                <span v-if="row.recommended_model">{{ row.recommended_provider }} / {{ row.recommended_model }}</span>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="temperature_hint" label="温度建议" width="100" />
            <el-table-column label="绑定模型" min-width="240">
              <template #default="{ row }">
                <el-select
                  v-model="row.config_id"
                  clearable
                  placeholder="跟随全局默认"
                  style="width: 100%;"
                  filterable
                >
                  <el-option
                    v-for="c in sceneConfigOptions"
                    :key="c.id"
                    :label="`${c.name} (${c.model})`"
                    :value="c.id"
                  />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="参数覆盖" width="200">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openSceneOverrides(row)">
                  {{ sceneOverrideSummary(row) }}
                </el-button>
              </template>
            </el-table-column>
            <el-table-column label="配置提示" min-width="240">
              <template #default="{ row }">
                <div class="scene-tip">{{ row.tip || '—' }}</div>
              </template>
            </el-table-column>
          </el-table>
          <div style="margin-top: 16px;">
            <el-button type="primary" :loading="sceneSaving" @click="saveSceneBindings">保存场景绑定</el-button>
          </div>
        </el-tab-pane>

        <!-- Tab 2: 提示词模板 -->
        <el-tab-pane label="提示词模板" name="prompt">
          <el-row :gutter="20" style="height: calc(100vh - 280px); min-height: 400px;">
            <!-- 左侧模板列表 -->
            <el-col :span="6" style="height: 100%; overflow-y: auto;">
              <el-menu
                :default-active="selectedPromptCode"
                @select="handlePromptSelect"
                style="border-right: none;"
              >
                <el-menu-item
                  v-for="item in promptList"
                  :key="item.code"
                  :index="item.code"
                >
                  <el-icon><Document /></el-icon>
                  <span>{{ item.name }}</span>
                  <el-tag v-if="item.is_custom" type="warning" size="small" style="margin-left: 8px;">已修改</el-tag>
                </el-menu-item>
              </el-menu>
            </el-col>

            <!-- 右侧编辑器 -->
            <el-col :span="18" style="height: 100%; display: flex; flex-direction: column;">
              <div v-if="selectedPrompt" style="flex: 1; display: flex; flex-direction: column; overflow: hidden;">
                <!-- 顶部信息 -->
                <div style="margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
                  <div>
                    <b style="font-size: 16px;">{{ selectedPrompt.name }}</b>
                    <el-tag size="small" style="margin-left: 8px;">{{ sceneTypeMap[selectedPrompt.scene_type] }}</el-tag>
                    <span style="margin-left: 12px; color: #999; font-size: 12px;">{{ selectedPrompt.description }}</span>
                  </div>
                  <div>
                    <el-button type="primary" @click="savePrompt" :loading="promptSaving" icon="Check">保存</el-button>
                    <el-button @click="resetPrompt" icon="RefreshLeft">重置默认</el-button>
                    <el-button type="success" @click="openPromptTestDialog" icon="VideoPlay">测试 Prompt</el-button>
                  </div>
                </div>

                <!-- 编辑器区域 -->
                <div style="flex: 1; display: flex; flex-direction: column; gap: 12px; overflow-y: auto;">
                  <div>
                    <div style="font-weight: bold; margin-bottom: 4px;">System Prompt</div>
                    <el-input
                      v-model="editPrompt.system_prompt"
                      type="textarea"
                      :rows="4"
                      placeholder="System Prompt 定义了 AI 的角色和行为..."
                    />
                  </div>
                  <div>
                    <div style="font-weight: bold; margin-bottom: 4px;">User Prompt 模板</div>
                    <el-input
                      v-model="editPrompt.user_prompt_template"
                      type="textarea"
                      :rows="12"
                      placeholder="User Prompt 模板，支持 Jinja2 语法如 {{api_name}}（AI 配置专用，与用例执行变量 ${{变量名}} 不同）"
                    />
                  </div>
                  <div v-if="promptVariables.length > 0">
                    <div style="font-weight: bold; margin-bottom: 4px;">模板变量</div>
                    <div>
                      <el-tag
                        v-for="v in promptVariables"
                        :key="v"
                        type="info"
                        size="small"
                        style="margin-right: 6px; margin-bottom: 4px;"
                        v-text="'{{' + v + '}}'"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <el-empty v-else description="请选择左侧模板"/>
            </el-col>
          </el-row>
        </el-tab-pane>
      </el-tabs>

      <!-- 场景参数覆盖 -->
      <el-dialog v-model="overrideDialog.visible" title="场景参数覆盖" width="480px" destroy-on-close>
        <p class="override-scene-name">{{ overrideDialog.label }}</p>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 12px;"
          title="覆盖绑定模型上的 max_tokens / 温度 / 超时；留空表示使用 LLM 配置中的默认值。问答评判建议 max_tokens≥16384、timeout≥180。"
        />
        <el-form label-width="110px">
          <el-form-item label="最大 Token">
            <el-input-number
              v-model="overrideDialog.form.max_tokens"
              :min="1024"
              :max="131072"
              :step="1024"
              controls-position="right"
              placeholder="留空=跟随模型"
              style="width: 100%;"
            />
          </el-form-item>
          <el-form-item label="温度">
            <el-input-number
              v-model="overrideDialog.form.temperature"
              :min="0"
              :max="2"
              :step="0.1"
              controls-position="right"
              placeholder="留空=跟随模型"
              style="width: 100%;"
            />
          </el-form-item>
          <el-form-item label="超时(秒)">
            <el-input-number
              v-model="overrideDialog.form.timeout"
              :min="30"
              :max="1800"
              controls-position="right"
              placeholder="留空=跟随模型"
              style="width: 100%;"
            />
          </el-form-item>
          <el-form-item label="最短超时">
            <el-input-number
              v-model="overrideDialog.form.min_timeout"
              :min="30"
              :max="1800"
              controls-position="right"
              placeholder="可选，取 max(模型超时, 此值)"
              style="width: 100%;"
            />
          </el-form-item>
          <el-form-item v-if="overrideDialog.defaultOverrides && Object.keys(overrideDialog.defaultOverrides).length">
            <el-button size="small" @click="applyDefaultOverrides">套用本场景推荐参数</el-button>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="overrideDialog.visible = false">取消</el-button>
          <el-button type="primary" @click="confirmSceneOverrides">确定</el-button>
        </template>
      </el-dialog>

      <!-- 配置弹窗 -->
      <el-dialog
        v-model="configDialogVisible"
        :title="configForm.id ? '编辑配置' : '新增配置'"
        width="560px"
        destroy-on-close
      >
        <el-form :model="configForm" label-width="110px" :rules="configRules" ref="configFormRef">
          <el-form-item label="配置名称：" prop="name">
            <el-input v-model="configForm.name" placeholder="如：DeepSeek 默认"/>
          </el-form-item>
          <el-form-item label="供应商：" prop="provider">
            <el-select v-model="configForm.provider" placeholder="选择供应商" style="width: 100%;" @change="onProviderChange">
              <el-option label="OpenAI" value="openai"/>
              <el-option label="DeepSeek" value="deepseek"/>
              <el-option label="通义千问" value="qwen"/>
              <el-option label="Claude" value="claude"/>
              <el-option label="自定义" value="custom"/>
            </el-select>
          </el-form-item>
          <el-form-item label="API Key：" prop="api_key">
            <el-input
              v-model="configForm.api_key"
              type="password"
              show-password
              placeholder="输入 API Key"
            />
            <div style="font-size: 12px; color: #999; margin-top: 2px;">
              {{ configForm.id ? '留空则保持原 Key 不变' : '' }}
            </div>
          </el-form-item>
          <el-form-item label="Base URL：">
            <el-input v-model="configForm.api_base" placeholder="可选，留空使用默认地址"/>
          </el-form-item>
          <el-form-item label="模型：" prop="model">
            <el-input v-model="configForm.model" placeholder="如：gpt-4o / deepseek-v4-flash"/>
          </el-form-item>
          <el-form-item label="思考模式：">
            <el-switch v-model="configForm.thinking_enabled" active-text="开启" inactive-text="关闭"/>
          </el-form-item>
          <el-form-item label="推理努力：" v-if="configForm.thinking_enabled">
            <el-select v-model="configForm.reasoning_effort" placeholder="选择推理努力程度" style="width: 100%;">
              <el-option label="低 (low)" value="low"/>
              <el-option label="中 (medium)" value="medium"/>
              <el-option label="高 (high)" value="high"/>
            </el-select>
          </el-form-item>
          <el-form-item label="温度：">
            <el-slider v-model="configForm.temperature" :min="0" :max="2" :step="0.1" show-stops/>
          </el-form-item>
          <el-form-item label="最大 Token：">
            <el-input-number v-model="configForm.max_tokens" :min="1" :max="131072" :step="1024" controls-position="right"/>
            <div style="font-size: 12px; color: #999; margin-top: 4px;">
              控制单次 AI 输出上限；API 多用例生成建议 8192～16384，复杂 UI 探索可更高（受模型实际上限约束）
            </div>
          </el-form-item>
          <el-form-item label="超时(秒)：">
            <el-input-number v-model="configForm.timeout" :min="5" :max="1800" controls-position="right"/>
            <div style="font-size: 12px; color: #999; margin-top: 4px;">
              最长 1800 秒（30 分钟）；需求用例大批量生成、长文档读图可适当加大
            </div>
          </el-form-item>
          <el-form-item label="设为默认：">
            <el-switch v-model="configForm.is_default"/>
          </el-form-item>
          <el-form-item label="启用：">
            <el-switch v-model="configForm.is_enabled"/>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="configDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="saveConfig" :loading="configSaving">保存</el-button>
        </template>
      </el-dialog>

      <!-- Prompt 测试弹窗 -->
      <el-dialog
        v-model="testDialogVisible"
        title="测试 Prompt"
        width="800px"
        destroy-on-close
      >
        <div style="margin-bottom: 12px; color: #666;">
          请填写以下变量值，系统将渲染 Prompt 并发送给默认 LLM 配置：
        </div>
        <el-form label-width="120px">
          <el-form-item v-for="v in promptVariables" :key="v" :label="v + '：'">
            <el-input v-model="testVariables[v]" :placeholder="'输入 ' + v + ' 的值'"/>
          </el-form-item>
        </el-form>

        <!-- 输出模式切换（暂时隐藏，等换服务器后再开启流式测试） -->
        <!--
        <div style="margin-top: 12px; display: flex; align-items: center; gap: 12px;">
          <span style="color: #666; font-size: 14px;">输出模式：</span>
          <el-radio-group v-model="useStream" :disabled="streamLoading" size="small">
            <el-radio-button :label="true">流式输出（SSE）</el-radio-button>
            <el-radio-button :label="false">非流式输出</el-radio-button>
          </el-radio-group>
        </div>
        -->

        <!-- LLM 输出区域 -->
        <div v-if="streamStarted" style="margin-top: 16px; border-top: 1px solid #e4e7ed; padding-top: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <b>LLM 实时输出：</b>
            <el-tag v-if="streamLoading" type="warning" size="small">生成中...</el-tag>
            <el-tag v-else type="success" size="small">已完成</el-tag>
          </div>
          <pre style="background: #f0f9eb; padding: 12px; border-radius: 4px; max-height: 300px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; line-height: 1.6;">{{ streamContent || '等待输出...' }}</pre>
        </div>

        <template #footer>
          <el-button @click="testDialogVisible = false">关闭</el-button>
          <el-button v-if="streamStarted && !streamLoading" @click="openTestResult">查看完整结果</el-button>
          <el-button type="primary" @click="runPromptTest" :loading="testLoading" :disabled="streamLoading">发送测试</el-button>
        </template>
      </el-dialog>

      <!-- 测试结果展示弹窗（用于查看完整结果） -->
      <el-dialog
        v-model="testResultVisible"
        title="Prompt 测试结果"
        width="800px"
      >
        <div style="margin-bottom: 12px;">
          <b>System Prompt：</b>
          <pre style="background: #f5f7fa; padding: 8px; border-radius: 4px; max-height: 120px; overflow-y: auto;">{{ testResult.system_prompt }}</pre>
        </div>
        <div style="margin-bottom: 12px;">
          <b>User Prompt：</b>
          <pre style="background: #f5f7fa; padding: 8px; border-radius: 4px; max-height: 200px; overflow-y: auto;">{{ testResult.user_prompt }}</pre>
        </div>
        <div>
          <b>LLM 响应：</b>
          <pre style="background: #f0f9eb; padding: 8px; border-radius: 4px; max-height: 300px; overflow-y: auto;">{{ testResult.llm_response || '无响应' }}</pre>
        </div>
        <template #footer>
          <el-button @click="testResultVisible = false">关闭</el-button>
        </template>
      </el-dialog>
    </template>
  </ConfigShell>
</template>

<script setup>
import ConfigShell from '@/components/ConfigShell.vue'
import AiEmbedConfig from '@/views/AI/AiEmbedConfig.vue'

defineProps({
  embedded: { type: Boolean, default: false }
})
import { ref, reactive, onMounted, watch, computed, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { aiConfigApi, aiPromptApi } from "@/api/modules/ai.js"
import { UserStore } from "@/stores/module/UserStore.js"

const activeTab = ref('config')
const route = useRoute()
const router = useRouter()

// ========== LLM 配置相关 ==========
const configList = ref([])
const configLoading = ref(false)
const configDialogVisible = ref(false)
const configSaving = ref(false)
const configFormRef = ref(null)

const providerMap = {
  openai: 'OpenAI',
  deepseek: 'DeepSeek',
  qwen: '通义千问',
  claude: 'Claude',
  custom: '自定义'
}

const configForm = reactive({
  name: '默认配置',
  provider: 'deepseek',
  api_key: '',
  api_base: '',
  model: 'deepseek-v4-flash',
  temperature: 0.7,
  max_tokens: 8192,
  timeout: 60,
  thinking_enabled: false,
  reasoning_effort: 'medium',
  is_default: false,
  is_enabled: true
})

const configRules = {
  name: [{ required: true, message: '请输入配置名称', trigger: 'blur' }],
  provider: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  api_key: [{ required: true, message: '请输入 API Key', trigger: 'blur' }],
  model: [{ required: true, message: '请输入模型名称', trigger: 'blur' }]
}

const sceneBindings = ref([])
const sceneConfigOptions = ref([])
const sceneLoading = ref(false)
const sceneSaving = ref(false)
const sceneApplying = ref(false)
const sceneMeta = reactive({
  has_enabled_config: true,
  unbound_count: 0
})
const overrideDialog = reactive({
  visible: false,
  scene: '',
  label: '',
  defaultOverrides: {},
  form: {
    max_tokens: null,
    temperature: null,
    timeout: null,
    min_timeout: null
  }
})
const sceneGroupOrder = ['assistant', 'generate', 'analysis', 'perf', 'vision', 'other']
const sceneGroupLabels = {
  assistant: '平台助手',
  generate: '用例生成',
  analysis: '失败分析',
  perf: '性能测试',
  vision: 'Vision',
  other: '其他'
}

const groupedSceneBindings = computed(() =>
  [...sceneBindings.value].sort(
    (a, b) => sceneGroupOrder.indexOf(a.group || 'other') - sceneGroupOrder.indexOf(b.group || 'other')
  )
)

const sceneGroupLabel = (group) => sceneGroupLabels[group] || group || '其他'

const isVisionOption = (c) => {
  const m = (c.model || '').toLowerCase()
  return m.includes('vl') || m.includes('vision') || m.includes('gpt-4o')
}

const sceneOverrideSummary = (row) => {
  const o = row.overrides || {}
  const parts = []
  if (o.max_tokens) parts.push(`tok ${o.max_tokens}`)
  if (o.temperature != null) parts.push(`T ${o.temperature}`)
  if (o.timeout) parts.push(`${o.timeout}s`)
  return parts.length ? parts.join(' · ') : '未覆盖'
}

const openSceneOverrides = (row) => {
  overrideDialog.scene = row.scene
  overrideDialog.label = row.label
  overrideDialog.defaultOverrides = row.default_overrides || {}
  const o = row.overrides || {}
  overrideDialog.form.max_tokens = o.max_tokens ?? null
  overrideDialog.form.temperature = o.temperature ?? null
  overrideDialog.form.timeout = o.timeout ?? null
  overrideDialog.form.min_timeout = o.min_timeout ?? null
  overrideDialog.visible = true
}

const applyDefaultOverrides = () => {
  const d = overrideDialog.defaultOverrides || {}
  overrideDialog.form.max_tokens = d.max_tokens ?? null
  overrideDialog.form.temperature = d.temperature ?? null
  overrideDialog.form.timeout = d.timeout ?? null
  overrideDialog.form.min_timeout = d.min_timeout ?? null
}

const confirmSceneOverrides = () => {
  const row = sceneBindings.value.find(b => b.scene === overrideDialog.scene)
  if (!row) return
  const overrides = {}
  const f = overrideDialog.form
  if (f.max_tokens != null && f.max_tokens !== '') overrides.max_tokens = f.max_tokens
  if (f.temperature != null && f.temperature !== '') overrides.temperature = f.temperature
  if (f.timeout != null && f.timeout !== '') overrides.timeout = f.timeout
  if (f.min_timeout != null && f.min_timeout !== '') overrides.min_timeout = f.min_timeout
  row.overrides = overrides
  overrideDialog.visible = false
}

const loadSceneBindings = async () => {
  sceneLoading.value = true
  try {
    const res = await aiConfigApi.getSceneBindings()
    if (res.data?.code === 200) {
      const options = res.data.data?.config_options || []
      const optionIds = new Set(options.map((c) => c.id))
      sceneBindings.value = (res.data.data?.bindings || []).map((b) => ({
        ...b,
        // 失效 ID 在下拉中不可见但仍会提交，这里统一清成跟随默认
        config_id: b.config_id && optionIds.has(b.config_id) ? b.config_id : null,
        overrides: b.overrides || {}
      }))
      sceneConfigOptions.value = options
      sceneMeta.has_enabled_config = res.data.data?.has_enabled_config !== false
      sceneMeta.unbound_count = res.data.data?.unbound_count ?? 0
    }
  } catch (e) {
    console.error(e)
  } finally {
    sceneLoading.value = false
  }
}

const saveSceneBindings = async () => {
  sceneSaving.value = true
  try {
    const optionIds = new Set(sceneConfigOptions.value.map((c) => c.id))
    const res = await aiConfigApi.saveSceneBindings({
      bindings: sceneBindings.value.map((b) => ({
        scene: b.scene,
        config_id: b.config_id && optionIds.has(b.config_id) ? b.config_id : null,
        overrides: b.overrides || {}
      }))
    })
    if (res.data?.code === 200) {
      ElMessage.success('场景绑定已保存')
      const options = res.data.data?.config_options || []
      const ids = new Set(options.map((c) => c.id))
      sceneBindings.value = (res.data.data?.bindings || []).map((b) => ({
        ...b,
        config_id: b.config_id && ids.has(b.config_id) ? b.config_id : null,
        overrides: b.overrides || {}
      }))
      sceneConfigOptions.value = options
      sceneMeta.has_enabled_config = res.data.data?.has_enabled_config !== false
      sceneMeta.unbound_count = res.data.data?.unbound_count ?? 0
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.response?.data?.message || '保存失败')
  } finally {
    sceneSaving.value = false
  }
}

const applySceneRecommendations = async () => {
  sceneApplying.value = true
  try {
    const res = await aiConfigApi.applySceneRecommendations()
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '已套用推荐绑定')
      sceneBindings.value = (res.data.data?.bindings || []).map(b => ({
        ...b,
        overrides: b.overrides || {}
      }))
      sceneConfigOptions.value = res.data.data?.config_options || []
      sceneMeta.has_enabled_config = res.data.data?.has_enabled_config !== false
      sceneMeta.unbound_count = res.data.data?.unbound_count ?? 0
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.response?.data?.message || '套用失败')
  } finally {
    sceneApplying.value = false
  }
}

const providerDefaults = {
  openai: { model: 'gpt-4o', base_url: '' },
  deepseek: { model: 'deepseek-v4-flash', base_url: '' },
  qwen: { model: 'qwen-vl-max', base_url: '' },
  claude: { model: 'claude-3-sonnet-20240229', base_url: '' },
  custom: { model: '', base_url: '' }
}

const onProviderChange = (val) => {
  const defaults = providerDefaults[val]
  if (defaults && !configForm.id) {
    configForm.model = defaults.model
    configForm.api_base = defaults.base_url
  }
}

const resetConfigForm = () => {
  Object.assign(configForm, {
    id: undefined,
    name: '默认配置',
    provider: 'deepseek',
    api_key: '',
    api_base: '',
    model: 'deepseek-v4-flash',
    temperature: 0.7,
    max_tokens: 8192,
    timeout: 60,
    thinking_enabled: false,
    reasoning_effort: 'medium',
    is_default: false,
    is_enabled: true
  })
}

const loadConfigs = async () => {
  configLoading.value = true
  try {
    const res = await aiConfigApi.getList()
    if (res.data?.code === 200) {
      configList.value = (res.data.data?.list || []).map(item => ({ ...item, _testing: false }))
    }
  } catch (error) {
    console.error('获取配置列表失败:', error)
  } finally {
    configLoading.value = false
  }
}

const openConfigDialog = (row) => {
  resetConfigForm()
  if (row) {
    Object.assign(configForm, { ...row })
  }
  configDialogVisible.value = true
  nextTick(() => configFormRef.value?.clearValidate())
}

const saveConfig = async () => {
  const valid = await configFormRef.value?.validate().catch(() => false)
  if (!valid) return

  configSaving.value = true
  try {
    const payload = { ...configForm }
    if (payload.id && !payload.api_key) {
      delete payload.api_key
    }

    let res
    if (payload.id) {
      res = await aiConfigApi.update(payload.id, payload)
    } else {
      res = await aiConfigApi.create(payload)
    }

    if (res.data?.code === 200) {
      ElMessage.success('保存成功')
      configDialogVisible.value = false
      await loadConfigs()
    } else {
      ElMessage.error(res.data?.message || '保存失败')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    configSaving.value = false
  }
}

const deleteConfig = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除配置「${row.name}」吗？`, '确认删除', { type: 'warning' })
    await aiConfigApi.delete(row.id)
    ElMessage.success('删除成功')
    await loadConfigs()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || '删除失败')
    }
  }
}

const testConfig = async (row) => {
  row._testing = true
  try {
    const res = await aiConfigApi.test(row.id)
    if (res.data?.code === 200 && res.data.data?.connected) {
      ElMessage.success(`连通性测试成功，响应: ${res.data.data.response}`)
    } else {
      ElMessage.error(res.data?.message || '连通性测试失败')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '测试失败')
  } finally {
    row._testing = false
  }
}

const setDefault = async (row) => {
  try {
    const res = await aiConfigApi.setDefault(row.id)
    if (res.data?.code === 200) {
      ElMessage.success('已设为默认配置')
      await loadConfigs()
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '设置失败')
  }
}

const toggleEnabled = async (row, val) => {
  try {
    await aiConfigApi.update(row.id, { is_enabled: val })
    ElMessage.success(val ? '已启用' : '已禁用')
  } catch (error) {
    row.is_enabled = !val
    ElMessage.error(error?.response?.data?.detail || '操作失败')
  }
}

// ========== Prompt 模板相关 ==========
const promptList = ref([])
const selectedPromptCode = ref('')
const selectedPrompt = ref(null)
const editPrompt = reactive({
  system_prompt: '',
  user_prompt_template: ''
})
const promptSaving = ref(false)

const sceneTypeMap = {
  api_case: 'API用例生成',
  ui_case: 'UI用例生成',
  requirement_parse: '需求解析',
  requirement_case: '需求生成用例',
  failure_analysis: '失败分析',
  report_summary: '报告摘要',
  test_data: '测试数据生成',
  perf_report_analysis: '压测单次报告分析',
  perf_compare_analysis: '性能测试报告分析',
  performance_report: '性能测试报告（资料库）',
  iteration_report: '迭代自动化测试报告',
  functional_report: '功能测试报告'
}

const promptVariables = computed(() => {
  const text = editPrompt.user_prompt_template || ''
  const matches = text.match(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g) || []
  const vars = matches.map(m => m.replace(/\{\{\s*|\s*\}\}/g, ''))
  return [...new Set(vars)]
})

const loadPrompts = async () => {
  try {
    const res = await aiPromptApi.getList()
    if (res.data?.code === 200) {
      promptList.value = res.data.data?.list || []
      if (promptList.value.length > 0 && !selectedPromptCode.value) {
        handlePromptSelect(promptList.value[0].code)
      }
    }
  } catch (error) {
    console.error('获取 Prompt 模板列表失败:', error)
  }
}

const handlePromptSelect = async (code) => {
  selectedPromptCode.value = code
  try {
    const res = await aiPromptApi.getDetail(code)
    if (res.data?.code === 200) {
      selectedPrompt.value = res.data.data
      editPrompt.system_prompt = res.data.data.system_prompt
      editPrompt.user_prompt_template = res.data.data.user_prompt_template
    }
  } catch (error) {
    ElMessage.error('获取模板详情失败')
  }
}

const savePrompt = async () => {
  if (!selectedPromptCode.value) return
  promptSaving.value = true
  try {
    const res = await aiPromptApi.update(selectedPromptCode.value, {
      system_prompt: editPrompt.system_prompt,
      user_prompt_template: editPrompt.user_prompt_template
    })
    if (res.data?.code === 200) {
      ElMessage.success('保存成功')
      await loadPrompts()
    } else {
      ElMessage.error(res.data?.message || '保存失败')
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    promptSaving.value = false
  }
}

const resetPrompt = async () => {
  if (!selectedPromptCode.value) return
  try {
    await ElMessageBox.confirm('确定重置为系统默认模板吗？自定义修改将丢失。', '确认重置', { type: 'warning' })
    const res = await aiPromptApi.reset(selectedPromptCode.value)
    if (res.data?.code === 200) {
      ElMessage.success('已重置')
      await loadPrompts()
      await handlePromptSelect(selectedPromptCode.value)
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.detail || '重置失败')
    }
  }
}

// ========== Prompt 测试 ==========
const testDialogVisible = ref(false)
const testVariables = reactive({})
const testLoading = ref(false)
const testResultVisible = ref(false)
const testResult = reactive({
  system_prompt: '',
  user_prompt: '',
  llm_response: ''
})

// 输出模式：true=流式(SSE), false=非流式
const useStream = ref(true)
// SSE 流式输出状态
const streamStarted = ref(false)
const streamLoading = ref(false)
const streamContent = ref('')

const openPromptTestDialog = () => {
  if (promptVariables.value.length === 0) {
    ElMessage.warning('当前 Prompt 模板没有可替换的变量')
    return
  }
  // 清空变量值和流式状态
  Object.keys(testVariables).forEach(k => delete testVariables[k])
  promptVariables.value.forEach(v => { testVariables[v] = '' })
  streamStarted.value = false
  streamLoading.value = false
  streamContent.value = ''
  useStream.value = false  // 默认非流式
  testDialogVisible.value = true
}

const openTestResult = () => {
  testDialogVisible.value = false
  testResultVisible.value = true
}

const runPromptTest = async () => {
  testLoading.value = true
  streamStarted.value = true
  streamLoading.value = true
  streamContent.value = ''
  console.log('[PromptTest] 开始测试, code=', selectedPromptCode.value, 'useStream=', useStream.value, 'typeof useStream=', typeof useStream.value)

  if (useStream.value) {
    // ===== 流式模式（SSE）=====
    console.log('[PromptTest] 进入流式模式')
    const userStore = UserStore()
    const token = userStore.token
    console.log('[PromptTest] token=', token ? ('存在, 前10字符=' + token.substring(0,10)) : '缺失')
    if (!token) {
      ElMessage.error('未登录，请先登录')
      streamLoading.value = false
      testLoading.value = false
      return
    }

    let tempSystemPrompt = ''
    let tempUserPrompt = ''

    console.log('[PromptTest] 准备调用 aiPromptApi.testStream')
    try {
      aiPromptApi.testStream(selectedPromptCode.value, { ...testVariables }, {
        token,
        onStart: (data) => {
          console.log('[PromptTest] SSE start')
          tempSystemPrompt = data.system_prompt || ''
          tempUserPrompt = data.user_prompt || ''
        },
        onChunk: (chunk) => {
          streamContent.value += chunk
        },
        onDone: (data) => {
          console.log('[PromptTest] SSE done')
          streamLoading.value = false
          testLoading.value = false
          testResult.system_prompt = tempSystemPrompt
          testResult.user_prompt = tempUserPrompt
          testResult.llm_response = data.content || streamContent.value
          ElMessage.success('测试完成')
        },
        onError: (msg) => {
          console.error('[PromptTest] SSE error:', msg)
          streamLoading.value = false
          testLoading.value = false
          streamContent.value = '错误: ' + (msg || '测试失败')
          ElMessage.error(msg || '测试失败')
        }
      })
      console.log('[PromptTest] aiPromptApi.testStream 调用完成')
    } catch (err) {
      console.error('[PromptTest] 调用 testStream 时抛出异常:', err)
      streamLoading.value = false
      testLoading.value = false
      ElMessage.error('调用失败: ' + (err.message || '未知错误'))
    }
  } else {
    // ===== 非流式模式 =====
    console.log('[PromptTest] 进入非流式模式')
    try {
      const res = await aiPromptApi.test(selectedPromptCode.value, { ...testVariables })
      console.log('[PromptTest] 响应:', res)
      if (res.data?.code === 200) {
        Object.assign(testResult, res.data.data)
        streamContent.value = res.data.data.llm_response || ''
        streamLoading.value = false
        testLoading.value = false
        ElMessage.success('测试完成')
      } else {
        console.error('[PromptTest] 业务错误:', res.data)
        streamLoading.value = false
        testLoading.value = false
        ElMessage.error(res.data?.message || '测试失败')
      }
    } catch (error) {
      console.error('[PromptTest] 请求异常:', error)
      streamLoading.value = false
      testLoading.value = false
      const msg = error?.response?.data?.detail
        || error?.response?.data?.message
        || error?.message
        || '测试失败'
      ElMessage.error(msg)
    }
  }
}

const syncInnerTabFromRoute = () => {
  // 嵌入平台配置时外层 tab=ai，内层用 sub；独立深链仍可能带 tab
  const raw = route.query.sub || route.query.tab
  if (raw === 'execution') {
    router.replace({ path: '/project-settings', query: { tab: 'execution' } })
    return
  }
  if (['config', 'scene', 'prompt', 'embed'].includes(raw)) {
    activeTab.value = raw
  }
}

onMounted(() => {
  syncInnerTabFromRoute()
  loadConfigs()
  loadPrompts()
  loadSceneBindings()
})

watch(() => [route.query.tab, route.query.sub], syncInnerTabFromRoute)
</script>

<style scoped>
.key-mask {
  font-family: monospace;
  color: #666;
}
.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}
.scene-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.text-muted {
  color: #909399;
}
.override-scene-name {
  font-weight: 600;
  margin: 0 0 8px;
}
.scene-tip {
  font-size: 12px;
  color: #606266;
  line-height: 1.65;
  white-space: normal;
  word-break: break-word;
  padding: 2px 0;
}
</style>
