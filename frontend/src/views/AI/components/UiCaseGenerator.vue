<template>
  <el-dialog
    v-model="visible"
    title="🤖 AI 生成 UI 测试步骤"
    width="900px"
    destroy-on-close
    :close-on-click-modal="false"
    class="ai-generator-dialog"
  >
    <!-- 生成表单 -->
    <div v-if="!generatedSteps.length && !generating" class="generator-form">
      <el-form :model="form" label-width="100px">
        <!-- 目标页面 + 抓取 -->
        <el-form-item label="目标页面">
          <div class="url-input-row">
            <el-input
              v-model="form.page_url"
              :placeholder="pageUrlPlaceholder"
              clearable
            />
            <el-button
              v-if="form.generation_mode === 'single'"
              type="primary"
              :loading="fetching"
              :disabled="!form.page_url"
              @click="handleFetchPage"
              icon="View"
            >
              抓取页面
            </el-button>
          </div>
          <div class="url-hint">
            <span v-if="form.generation_mode === 'agent'">Agent 模式须填写起始 URL，由 Runner 逐步探索页面</span>
            <span v-else-if="form.generation_mode === 'explore'">探索模式由 Runner 自动抓取并执行，无需手动点击抓取</span>
            <span v-else>填写页面地址后，Runner 抓取 DOM 结构，平台 LLM 生成更准确的选择器</span>
          </div>
        </el-form-item>

        <!-- 抓取结果（仅单页面模式显示） -->
        <el-form-item v-if="form.generation_mode === 'single' && fetchedElements.length" label=" ">
          <el-collapse class="elements-collapse">
            <el-collapse-item :title="`📋 已抓取页面元素（共 ${fetchedElements.length} 个）`">
              <el-table :data="fetchedElements" size="small" border max-height="300">
                <el-table-column type="index" width="40" />
                <el-table-column label="标签" prop="tag" width="70" />
                <el-table-column label="类型" prop="type" width="90" />
                <el-table-column label="选择器" min-width="160">
                  <template #default="{ row }">
                    <code class="selector-code">{{ row.selector || row.id || row.class || '-' }}</code>
                  </template>
                </el-table-column>
                <el-table-column label="提示文本" prop="placeholder" show-overflow-tooltip min-width="140" />
                <el-table-column label="显示文本" prop="text" show-overflow-tooltip min-width="100" />
                <el-table-column label="属性" width="100">
                  <template #default="{ row }">
                    <el-tag v-if="row.id" size="small" type="success">id</el-tag>
                    <el-tag v-if="row.name" size="small" type="info">name</el-tag>
                    <el-tag v-if="!row.id && !row.name" size="small" type="warning">class</el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </el-collapse-item>
          </el-collapse>
        </el-form-item>

        <!-- 生成模式 -->
        <el-form-item label="生成模式">
          <el-radio-group v-model="form.generation_mode">
            <el-radio value="single">单页面</el-radio>
            <el-radio value="explore">多轮探索</el-radio>
            <el-radio value="agent">Agent（MCP）</el-radio>
          </el-radio-group>
          <div v-if="form.generation_mode === 'single'" class="url-hint">
            抓取当前页 DOM，一次性生成步骤（成本低，适合单页操作）
          </div>
          <div v-else-if="form.generation_mode === 'explore'" class="url-hint">
            执行→再抓 DOM→再生成，支持登录跳转（每轮 1 次 LLM）
          </div>
          <div v-else class="url-hint agent-hint">
            <strong>Agent（MCP 思路）</strong>：基于无障碍树 snapshot 逐步规划并执行，每步 1 次 LLM。
            适合探索性生成；<strong>产出步骤后可入库，不建议直接用于 CI 定时任务</strong>。
          </div>
        </el-form-item>

        <el-form-item v-if="form.generation_mode !== 'single'" label="最大步数/轮次">
          <el-slider
            v-if="form.generation_mode === 'agent'"
            v-model="form.max_steps"
            :min="3"
            :max="30"
            show-stops
            show-input
          />
          <el-slider
            v-else
            v-model="form.max_rounds"
            :min="1"
            :max="10"
            show-stops
            show-input
          />
          <div class="url-hint">
            {{ form.generation_mode === 'agent'
              ? 'Agent 每步调用 1 次 LLM，步数越多耗时与 Token 越高'
              : '探索模式每轮 1 次 LLM，简单流程 2-3 轮' }}
          </div>
        </el-form-item>

        <BrowserLabTaskTextField
          v-model="form.description"
          label="测试描述"
          required
          :rows="5"
          :placeholder="descriptionPlaceholder"
          :label-tooltip="descriptionTooltip"
          :start-url="form.page_url"
          :ai-config-id="aiConfigId"
          :project-id="projectId"
          optimize-scene="ui_case"
          :generation-mode="form.generation_mode"
        />

        <el-form-item label="AI 模型">
          <el-select
            v-model="aiConfigId"
            placeholder="默认模型"
            clearable
            style="width: 100%;"
            :loading="loadingConfigs"
          >
            <el-option
              v-for="c in enabledConfigs"
              :key="c.id"
              :label="`${c.name} (${c.model})`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>

        <BrowserRunModeFields
          v-if="form.generation_mode !== 'single' || form.page_url?.trim()"
          :form="form"
        />
      </el-form>
    </div>

    <!-- Agent Runner 进度 -->
    <UiAgentProgressPanel
      v-if="generating && (form.generation_mode === 'agent' || form.generation_mode === 'explore') && agentJobId"
      :visible="true"
      :job-id="agentJobId"
      :project-id="projectId"
      @done="onAgentJobDone"
      @fail="onAgentJobFail"
    />

    <!-- 生成中（非异步 job） -->
    <div v-if="generating && !agentJobId" class="generating-state">
      <el-icon class="is-loading" :size="40"><Loading /></el-icon>
      <p>{{ form.generation_mode === 'agent' ? 'Agent 正在逐步探索页面…' : 'AI 正在生成测试步骤，请稍候…' }}</p>
      <p class="hint">{{ form.generation_mode === 'agent' ? '每步调用 LLM+浏览器执行，完整流程约 2-5 分钟；稳定流程更推荐「录制+AI优化」' : '根据描述复杂度，通常需要 10-30 秒' }}</p>
    </div>

    <!-- 生成结果 -->
    <div v-if="generatedSteps.length && !generating" class="result-section">
      <div class="result-header">
        <span class="result-title">生成结果（{{ generatedSteps.length }} 步）</span>
        <el-button type="primary" size="small" @click="handleRegenerate" icon="Refresh">重新生成</el-button>
      </div>

      <el-alert
        v-if="agentInfo"
        :title="`Agent 模式：执行 ${agentInfo.executed_steps || 0} 步`"
        :description="agentSummary"
        type="success"
        show-icon
        :closable="false"
        class="error-alert"
      />

      <el-alert
        v-if="exploreInfo && !agentInfo"
        :title="`探索模式：共 ${exploreInfo.rounds} 轮，页面变化 ${exploreInfo.page_changes} 次`"
        :description="`访问页面：${exploreInfo.urls_visited.join(' → ')}`"
        type="success"
        show-icon
        :closable="false"
        class="error-alert"
      />

      <!-- 截图展示 -->
      <div v-if="exploreInfo?.screenshots?.length" class="screenshot-section">
        <div class="screenshot-title">📷 探索过程截图（{{ exploreInfo.screenshots.length }} 张）</div>
        <div class="screenshot-list">
          <div
            v-for="(shot, idx) in exploreInfo.screenshots"
            :key="idx"
            class="screenshot-item"
          >
            <el-image
              :src="shot.url"
              :preview-src-list="exploreInfo.screenshots.map(s => s.url)"
              :initial-index="idx"
              fit="cover"
              class="screenshot-img"
            >
              <template #error>
                <div class="screenshot-error">加载失败</div>
              </template>
            </el-image>
            <div class="screenshot-meta">
              <el-tag size="small" type="info">第{{ shot.round }}轮</el-tag>
              <span class="screenshot-reason">{{ shot.reason }}</span>
            </div>
          </div>
        </div>
      </div>

      <el-alert
        v-if="errors.length"
        :title="`校验提示：${errors.join('；')}`"
        type="warning"
        show-icon
        :closable="false"
        class="error-alert"
      />

      <!-- 步骤列表 -->
      <div class="step-list">
        <div
          v-for="(step, index) in generatedSteps"
          :key="step.id"
          class="step-card"
          :class="{ 'has-error': stepHasError(index) }"
        >
          <div class="step-header">
            <span class="step-index">#{{ index + 1 }}</span>
            <el-tag size="small" type="primary">{{ step.keyword }}</el-tag>
            <code class="step-method">{{ step.method }}</code>
            <span class="step-desc">{{ step.desc }}</span>
            <div class="step-actions">
              <el-button type="primary" link size="small" @click="toggleEdit(index)" icon="Edit">
                {{ editingIndex === index ? '收起' : '编辑' }}
              </el-button>
              <el-button type="primary" link size="small" @click="handleMoveUp(index)" icon="Top" :disabled="index === 0" />
              <el-button type="primary" link size="small" @click="handleMoveDown(index)" icon="Bottom" :disabled="index === generatedSteps.length - 1" />
              <el-button type="danger" link size="small" @click="handleDeleteStep(index)" icon="Delete" />
            </div>
          </div>

          <!-- 参数编辑区 -->
          <div v-if="editingIndex === index" class="step-edit-panel">
            <el-form :model="editingStep" label-width="100px" size="small">
              <el-form-item label="动作名称">
                <el-input v-model="editingStep.keyword" />
              </el-form-item>
              <el-form-item label="方法">
                <el-input v-model="editingStep.method" disabled />
              </el-form-item>
              <el-form-item label="描述">
                <el-input v-model="editingStep.desc" type="textarea" :rows="2" />
              </el-form-item>
              <el-form-item label="参数 (JSON)">
                <el-input
                  v-model="editingParamsStr"
                  type="textarea"
                  :rows="4"
                  placeholder='{"locator": "#kw", "value": "Kimi"}'
                />
                <div class="params-hint">直接编辑 JSON，保存后会自动校验</div>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" size="small" @click="handleSaveEdit(index)">保存修改</el-button>
                <el-button size="small" @click="editingIndex = -1">取消</el-button>
              </el-form-item>
            </el-form>
          </div>

          <!-- 参数预览 -->
          <div v-else class="step-params-preview">
            <code>{{ JSON.stringify(step.params) }}</code>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <template v-if="!generatedSteps.length && !generating">
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" @click="handleGenerate" :loading="generating" icon="MagicStick">开始生成</el-button>
        </template>
        <template v-if="generatedSteps.length && !generating">
          <el-button @click="visible = false">关闭</el-button>
          <el-button type="primary" @click="handleApply" icon="Check">应用步骤</el-button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, View, Edit, Top, Bottom, Delete } from '@element-plus/icons-vue'
import { aiGenerateApi } from '@/api/modules/ai'
import http from '@/api/index'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import BrowserRunModeFields from '@/components/BrowserRunModeFields.vue'
import BrowserLabTaskTextField from '@/views/AI/browserLab/BrowserLabTaskTextField.vue'
import UiAgentProgressPanel from '@/views/AI/components/UiAgentProgressPanel.vue'
import { notifyUiAgentJobOutcome, shouldPresentUiAgentSteps } from '@/views/AI/components/uiAgentJobHelpers.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect()

const projectId = computed(() => ProjectStore().projectInfo?.id)

const props = defineProps({
  modelValue: Boolean
})

const emit = defineEmits(['update:modelValue', 'apply'])

const visible = ref(false)
const generating = ref(false)
const fetching = ref(false)
const generatedSteps = ref([])
const errors = ref([])
const fetchedElements = ref([])
const editingIndex = ref(-1)
const exploreInfo = ref(null)
const agentInfo = ref(null)
const agentJobId = ref(null)
const editingStep = reactive({
  keyword: '',
  method: '',
  desc: '',
  params: {}
})
const editingParamsStr = ref('')

const form = reactive({
  description: '',
  page_url: '',
  generation_mode: 'single',
  max_rounds: 3,
  max_steps: 15,
  run_mode: 'runner',
  device_id: null,
  headless: true,
})

const pageUrlPlaceholder = computed(() => {
  if (form.generation_mode === 'agent') {
    return '必填，例如：https://xxx/login'
  }
  if (form.generation_mode === 'explore') {
    return '例如：https://xxx/login（探索模式自动抓取）'
  }
  return '例如：https://www.baidu.com（可选）'
})

const agentSummary = computed(() => {
  if (!agentInfo.value) return ''
  const urls = (agentInfo.value.urls_visited || []).join(' → ')
  const errs = agentInfo.value.agent_log?.filter(l => l.error)?.length || 0
  return `访问：${urls || '—'}${errs ? `；${errs} 步有异常` : ''}`
})

const descriptionPlaceholder = computed(() => {
  if (form.generation_mode === 'agent' || form.generation_mode === 'explore') {
    return '描述完整测试流程，建议包含：账号密码、操作步骤、预期结果'
  }
  return '描述当前页面上的具体操作和验证点'
})

const descriptionTooltip = computed(() => {
  if (form.generation_mode === 'agent') {
    return `【Agent 模式】撰写建议：
1. 用「→」串联流程，关键结果写「→ 预期：…」（与录制优化相同）
2. 写明账号密码（如：demo / demo123）
3. Agent 逐步执行 snapshot，勿期望一步生成全部步骤

示例：
使用 demo/demo123 登录 → 进入用户管理 → 搜索 zhangsan 并查询 → 预期：列表中存在 zhangsan → 新增用户「测试」并保存 → 预期：列表中出现用户「测试」

注意：登录只需 click 一次；若步骤重复卡在登录，请拉取最新 Backend 后重试。`
  }
  if (form.generation_mode === 'explore') {
    return `【探索模式】撰写建议：
1. 登录信息：账号和密码（如：使用 admin / 123456 登录）
2. 起始页面：目标系统地址（上方已填写时可省略）
3. 操作步骤：依次点击/输入什么，进入哪个页面或模块
4. 预期结果：最后要验证什么（如：列表中出现新增的数据、页面显示"保存成功"）

示例：
使用 test@example.com / Pass1234 登录系统，进入控制台模块，点击右上角"新增"按钮，在弹窗中填写名称"测试数据"和描述"自动化测试"，点击保存，验证列表中第一条数据的名称为"测试数据"`
  }
  return `【单页面模式】撰写建议：
1. 操作步骤：点击哪个元素、输入什么内容、选择哪个选项
2. 元素特征：用文字描述目标元素（如：蓝色提交按钮、搜索框、用户名输入框）
3. 预期结果：验证页面出现什么文本或元素

示例：
在搜索框输入"测试"，点击蓝色的搜索按钮，等待页面加载完成后，验证搜索结果列表的第一条标题包含"测试"`
})

watch(() => props.modelValue, async (val) => {
  visible.value = val
  if (val) {
    resetForm()
    await loadConfigs()
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

const POPUP_FLOW_PATTERN = /弹窗|弹出|弹层|浮层|充值|对话框|modal|popup|弹.*支付|支付.*弹/i
watch(() => form.description, (val) => {
  if (POPUP_FLOW_PATTERN.test(val || '') && form.generation_mode === 'single' && form.page_url.trim()) {
    form.generation_mode = 'explore'
  }
})

const resetForm = () => {
  form.description = ''
  form.page_url = ''
  form.generation_mode = 'single'
  form.max_rounds = 3
  form.max_steps = 15
  form.run_mode = 'runner'
  form.device_id = null
  form.headless = true
  generatedSteps.value = []
  errors.value = []
  fetchedElements.value = []
  editingIndex.value = -1
  exploreInfo.value = null
  agentInfo.value = null
  agentJobId.value = null
}

// 抓取页面元素
const handleFetchPage = async () => {
  if (!form.page_url.trim()) {
    ElMessage.warning('请输入目标页面地址')
    return
  }
  if (!form.device_id) {
    ElMessage.warning('请选择在线 Runner 执行设备')
    return
  }

  fetching.value = true
  try {
    const res = await aiGenerateApi.fetchPage({
      url: form.page_url.trim(),
      device_id: form.device_id,
      headless: form.headless,
    }, projectId.value)
    if (res.status === 200 && res.data?.data) {
      fetchedElements.value = res.data.data.elements || []
      ElMessage.success(`成功抓取 ${fetchedElements.value.length} 个页面元素`)
    } else {
      ElMessage.error(res.data?.message || '抓取失败')
    }
  } catch (error) {
    console.error('抓取失败:', error)
    ElMessage.error(error.response?.data?.detail || '页面抓取失败，请检查地址是否可访问')
  } finally {
    fetching.value = false
  }
}

// 生成步骤
const handleGenerate = async () => {
  if (!form.description.trim()) {
    ElMessage.warning('请输入测试描述')
    return
  }
  if (form.generation_mode === 'agent' && !form.page_url?.trim()) {
    ElMessage.warning('Agent 模式请填写起始页面 URL')
    return
  }
  if (form.generation_mode === 'agent' && form.run_mode === 'runner' && !form.device_id) {
    ElMessage.warning('请选择在线 Runner 执行设备')
    return
  }
  if (form.generation_mode === 'explore' && !form.page_url?.trim()) {
    ElMessage.warning('多轮探索请填写起始页面 URL')
    return
  }
  if (
    (form.generation_mode === 'agent' || form.generation_mode === 'explore')
    && form.run_mode === 'runner'
    && !form.device_id
  ) {
    ElMessage.warning('请选择在线 Runner 执行设备')
    return
  }
  if (
    form.generation_mode === 'single'
    && form.page_url?.trim()
    && !form.device_id
  ) {
    ElMessage.warning('填写页面 URL 时请选择在线 Runner 执行设备')
    return
  }

  generating.value = true
  generatedSteps.value = []
  errors.value = []
  editingIndex.value = -1
  exploreInfo.value = null
  agentInfo.value = null
  agentJobId.value = null

  try {
    let res
    if (form.generation_mode === 'agent') {
      res = await aiGenerateApi.generateUiCaseAgent({
        description: form.description,
        page_url: form.page_url.trim(),
        max_steps: form.max_steps,
        ai_config_id: aiConfigId.value || undefined,
        run_mode: form.run_mode,
        device_id: form.device_id || undefined,
        headless: form.headless,
      }, projectId.value)
      const payload = res.data?.data
      if (res.status === 200 && payload?.async && payload?.job_id) {
        agentJobId.value = payload.job_id
        const modeLabel = 'Runner'
        ElMessage.success(`Agent 任务已开始（${modeLabel}）`)
        return
      }
    } else {
      res = await aiGenerateApi.generateUiCase({
        description: form.description,
        page_url: form.page_url || undefined,
        auto_explore: form.generation_mode === 'explore',
        max_rounds: form.max_rounds,
        ai_config_id: aiConfigId.value || undefined,
        run_mode: form.generation_mode === 'explore' ? form.run_mode : undefined,
        device_id: form.device_id || undefined,
        headless: form.headless,
      }, projectId.value)
      const payload = res.data?.data
      if (form.generation_mode === 'explore' && res.status === 200 && payload?.async && payload?.job_id) {
        agentJobId.value = payload.job_id
        const modeLabel = 'Runner'
        ElMessage.success(`多轮探索已开始（${modeLabel}）`)
        return
      }
    }

    if (res.status === 200 && res.data?.data?.steps) {
      generatedSteps.value = res.data.data.steps
      errors.value = res.data.data.errors || []
      agentInfo.value = res.data.data.agent_info || null
      exploreInfo.value = res.data.data.explore_info || null

      let msg = `成功生成 ${generatedSteps.value.length} 个步骤`
      if (form.generation_mode === 'agent' && agentInfo.value) {
        msg += `（Agent 执行 ${agentInfo.value.executed_steps || 0} 步）`
      } else if (exploreInfo.value) {
        msg += `（探索 ${exploreInfo.value.rounds} 轮）`
      }
      ElMessage.success(msg)
      if (errors.value.length) {
        ElMessage.warning(`有 ${errors.value.length} 条警告/错误，请检查`)
      }
    } else {
      ElMessage.error(res.data?.message || res.data?.detail || '生成失败')
    }
  } catch (error) {
    console.error('生成失败:', error)
    ElMessage.error(error.response?.data?.detail || error.message || '生成失败')
  } finally {
    generating.value = false
  }
}

const onAgentJobDone = (jobData) => {
  generating.value = false
  agentJobId.value = null
  if (!shouldPresentUiAgentSteps(jobData)) {
    errors.value = [jobData?.error_message || 'Agent 探索失败']
    ElMessage.error(jobData?.error_message || 'Agent 探索失败')
    return
  }
  generatedSteps.value = jobData.steps || []
  const explore = jobData.explore_info || jobData.source_ref?.explore_info
  if (explore) {
    exploreInfo.value = explore
    agentInfo.value = null
  } else {
    agentInfo.value = {
      mode: jobData.run_mode === 'runner' ? 'agent_runner' : 'agent_mcp',
      executed_steps: (jobData.steps || []).length,
      agent_log: jobData.agent_log || [],
    }
  }
  if (jobData.error_message && jobData.status !== 'done') {
    errors.value = [jobData.error_message]
  } else {
    errors.value = []
  }
  const exploreLabel = explore ? `探索 ${explore.rounds || 0} 轮` : `共 ${generatedSteps.value.length} 步`
  notifyUiAgentJobOutcome(jobData, ElMessage, {
    successMessage: `完成，${exploreLabel}`,
    warnSparse: form.generation_mode === 'agent' && !explore,
  })
}

const onAgentJobFail = (payload) => {
  generating.value = false
  agentJobId.value = null
  const msg = payload?.error_message || 'Agent 订阅失败'
  errors.value = [msg]
  ElMessage.error(msg)
}

const handleRegenerate = () => {
  generatedSteps.value = []
  errors.value = []
  editingIndex.value = -1
  exploreInfo.value = null
  agentInfo.value = null
  agentJobId.value = null
}

const handleDeleteStep = (index) => {
  generatedSteps.value.splice(index, 1)
  if (editingIndex.value === index) {
    editingIndex.value = -1
  } else if (editingIndex.value > index) {
    editingIndex.value--
  }
}

const handleMoveUp = (index) => {
  if (index === 0) return
  const temp = generatedSteps.value[index]
  generatedSteps.value[index] = generatedSteps.value[index - 1]
  generatedSteps.value[index - 1] = temp
  if (editingIndex.value === index) {
    editingIndex.value = index - 1
  } else if (editingIndex.value === index - 1) {
    editingIndex.value = index
  }
}

const handleMoveDown = (index) => {
  if (index >= generatedSteps.value.length - 1) return
  const temp = generatedSteps.value[index]
  generatedSteps.value[index] = generatedSteps.value[index + 1]
  generatedSteps.value[index + 1] = temp
  if (editingIndex.value === index) {
    editingIndex.value = index + 1
  } else if (editingIndex.value === index + 1) {
    editingIndex.value = index
  }
}

const toggleEdit = (index) => {
  if (editingIndex.value === index) {
    editingIndex.value = -1
    return
  }
  const step = generatedSteps.value[index]
  editingStep.keyword = step.keyword
  editingStep.method = step.method
  editingStep.desc = step.desc
  editingStep.params = { ...step.params }
  editingParamsStr.value = JSON.stringify(step.params, null, 2)
  editingIndex.value = index
}

const handleSaveEdit = (index) => {
  try {
    const parsed = JSON.parse(editingParamsStr.value)
    if (typeof parsed !== 'object' || parsed === null) {
      throw new Error('参数必须是 JSON 对象')
    }
    generatedSteps.value[index].keyword = editingStep.keyword
    generatedSteps.value[index].desc = editingStep.desc
    generatedSteps.value[index].params = parsed
    editingIndex.value = -1
    ElMessage.success('修改已保存')
  } catch (e) {
    ElMessage.error(`JSON 解析失败: ${e.message}`)
  }
}

const stepHasError = (index) => {
  // 简单判断：如果 errors 中有包含当前步骤索引的提示
  return errors.value.some(err => err.includes(`第 ${index + 1} 步`))
}

const handleApply = () => {
  if (!generatedSteps.value.length) {
    ElMessage.warning('没有可应用的步骤')
    return
  }
  emit('apply', JSON.parse(JSON.stringify(generatedSteps.value)))
  visible.value = false
}
</script>

<style scoped lang="scss">
.ai-generator-dialog {
  :deep(.el-dialog__body) {
    max-height: 70vh;
    overflow-y: auto;
    padding-top: 10px;
  }

  .generator-form {
    padding: 10px 0;

    .url-input-row {
      display: flex;
      gap: 10px;

      .el-input {
        flex: 1;
      }
    }

    .url-hint {
      margin-top: 6px;
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }

    .label-tip-icon {
      margin-left: 4px;
      font-size: 14px;
      color: var(--el-color-info);
      cursor: pointer;
      vertical-align: middle;
    }

    .elements-collapse {
      margin-top: 5px;

      .selector-code {
        font-family: 'Consolas', monospace;
        font-size: 12px;
        color: var(--el-color-primary);
        background: var(--el-fill-color-light);
        padding: 2px 6px;
        border-radius: 3px;
      }
    }
  }

  .generating-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 20px;

    p {
      margin-top: 15px;
      color: var(--el-text-color-primary);
      font-size: 16px;
    }

    .hint {
      color: var(--el-text-color-secondary);
      font-size: 13px;
    }
  }

  .result-section {
    .result-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 15px;

      .result-title {
        font-weight: 600;
        font-size: 15px;
      }
    }

    .error-alert {
      margin-bottom: 15px;
    }

    .step-list {
      display: flex;
      flex-direction: column;
      gap: 10px;

      .step-card {
        border: 1px solid var(--el-border-color);
        border-radius: 6px;
        padding: 10px 12px;
        background: var(--el-fill-color-light);

        &.has-error {
          border-color: var(--el-color-warning);
          background: var(--el-color-warning-light-9);
        }

        .step-header {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;

          .step-index {
            font-weight: 600;
            color: var(--el-text-color-secondary);
            min-width: 30px;
          }

          .step-method {
            font-family: 'Consolas', monospace;
            font-size: 12px;
            color: var(--el-color-primary);
            background: var(--el-bg-color);
            padding: 2px 6px;
            border-radius: 3px;
          }

          .step-desc {
            flex: 1;
            color: var(--el-text-color-regular);
            font-size: 13px;
            min-width: 100px;
          }

          .step-actions {
            display: flex;
            gap: 4px;
            margin-left: auto;
          }
        }

        .step-params-preview {
          margin-top: 8px;
          padding: 6px 10px;
          background: var(--el-bg-color);
          border-radius: 4px;

          code {
            font-family: 'Consolas', monospace;
            font-size: 11px;
            color: var(--el-text-color-secondary);
            word-break: break-all;
          }
        }

        .step-edit-panel {
          margin-top: 10px;
          padding: 10px;
          background: var(--el-bg-color);
          border-radius: 4px;

          .params-hint {
            font-size: 12px;
            color: var(--el-text-color-secondary);
            margin-top: 4px;
          }
        }
      }
    }
  }

  .dialog-footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
  }

  .screenshot-section {
    margin-bottom: 15px;
    padding: 12px;
    background: var(--el-fill-color-light);
    border-radius: 6px;

    .screenshot-title {
      font-weight: 600;
      font-size: 14px;
      margin-bottom: 10px;
      color: var(--el-text-color-primary);
    }

    .screenshot-list {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;

      .screenshot-item {
        width: 220px;
        border: 1px solid var(--el-border-color);
        border-radius: 4px;
        overflow: hidden;
        background: var(--el-bg-color);

        .screenshot-img {
          width: 100%;
          height: 140px;
          cursor: pointer;
        }

        .screenshot-error {
          width: 100%;
          height: 140px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--el-text-color-secondary);
          font-size: 12px;
          background: var(--el-fill-color);
        }

        .screenshot-meta {
          padding: 8px;
          font-size: 12px;

          .screenshot-reason {
            display: block;
            margin-top: 4px;
            color: var(--el-text-color-secondary);
            word-break: break-all;
          }
        }
      }
    }
  }
}
</style>
