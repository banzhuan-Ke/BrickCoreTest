<template>
  <el-dialog
    v-model="visible"
    title="🎬 AI 录制 UI 测试步骤"
    width="900px"
    destroy-on-close
    :close-on-click-modal="false"
    :before-close="handleBeforeClose"
    class="ai-recorder-dialog"
  >
    <!-- ===== 配置态 ===== -->
    <div v-if="state === 'config' && !skipConfig" class="recorder-form">
      <el-alert
        v-if="presetMode"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px;"
      >
        <template #title>
          <div class="preset-summary">
            <div><strong>目标页面：</strong>{{ form.url || initialUrl || '—' }}</div>
            <div><strong>执行设备：</strong>{{ selectedDeviceLabel || '未选择' }}</div>
          </div>
        </template>
      </el-alert>

      <el-form :model="form" label-width="100px">
        <el-form-item v-if="!presetMode" label="目标页面" required>
          <el-input
            v-model="form.url"
            placeholder="例如：https://xxx.com/login（录制起始页面）"
            clearable
          />
        </el-form-item>

        <el-form-item v-if="!presetMode" label="执行设备" required>
          <el-select
            v-model="form.device_id"
            placeholder="选择 Runner 设备"
            style="width: 100%"
            :loading="loadingDevices"
            filterable
          >
            <el-option
              v-for="device in onlineDevices"
              :key="device.id"
              :label="`${device.name || device.id} (${device.ip || '未知IP'})`"
              :value="device.id"
            />
          </el-select>
          <div class="url-hint">请选择设备管理页状态为「在线」的 Runner</div>
          <el-alert
            v-if="deviceLoadError"
            type="warning"
            :closable="false"
            show-icon
            style="margin-top: 8px;"
            :title="deviceLoadError"
          />
        </el-form-item>

        <el-form-item label="悬浮停留时间">
          <el-slider
            v-model="form.hover_delay_ms"
            :min="500"
            :max="5000"
            :step="500"
            show-stops
          />
          <div class="url-hint">
            悬浮操作需在元素上方停留 {{ form.hover_delay_ms / 1000 }} 秒才会被录制（500ms~5s 可调）
          </div>
        </el-form-item>

        <el-form-item v-if="existingStepCount > 0 && !lockApplyMode" label="应用方式">
          <el-radio-group v-model="applyMode">
            <el-radio value="append">追加到末尾（保留 {{ existingStepCount }} 步）</el-radio>
            <el-radio v-if="insertAtIndex != null" value="insert">
              插入到第 {{ insertAtIndex + 1 }} 步（其后原步骤顺延）
            </el-radio>
            <el-radio value="replace">全新录制（覆盖全部步骤）</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-else-if="existingStepCount > 0 && lockApplyMode" label="应用方式">
          <el-alert type="info" :closable="false" show-icon>
            将从第 {{ (insertAtIndex ?? 0) + 1 }} 步接录，新步骤将插入该位置（保留前置 {{ insertAtIndex ?? 0 }} 步）
          </el-alert>
        </el-form-item>

        <el-form-item label="录前检查">
          <el-alert type="warning" :closable="false" show-icon class="recorder-checklist-alert">
            <template #title>开始录制前请确认</template>
            <ul class="recorder-checklist">
              <li>Runner 已在<strong>设备管理</strong>中显示<strong>在线</strong></li>
              <li>起始 URL 可访问（内网/VPN 已连通）</li>
              <li>建议浏览器窗口<strong>最大化</strong>，便于回放与截图稳定</li>
              <li>需登录时：在弹出浏览器中<strong>手动完成登录</strong>后再录业务步骤</li>
              <li>下拉/菜单较多时：上方<strong>悬浮停留时间</strong>建议 ≥ 1.5 秒</li>
              <li>录制中可<strong>暂停</strong>；悬停元素后可用「存变量」提取文本或 value 属性</li>
              <li>「应用步骤」默认<strong>追加/插入</strong>已有步骤；选「覆盖全部」会替换编辑器内步骤，请录完后<strong>交互调试</strong>试跑</li>
            </ul>
          </el-alert>
        </el-form-item>

        <el-form-item>
          <el-alert
            type="info"
            :closable="false"
            show-icon
          >
            <template #title>
              点击"开始录制"后，本地将弹出浏览器窗口。请在浏览器中操作页面，系统会自动记录您的操作。
            </template>
          </el-alert>
        </el-form-item>
      </el-form>

      <div class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="starting" @click="handleStart">
          开始录制
        </el-button>
      </div>
    </div>

    <!-- skipConfig 过渡态：避免弹窗短暂空白 -->
    <div
      v-if="skipConfig && state === 'config' && !preparingReplay && !starting && !skipConfigStartFailed"
      class="recorder-form"
    >
      <div class="recording-header">
        <el-icon class="is-loading recording-icon" :size="32"><VideoCamera /></el-icon>
        <div class="recording-info">
          <h4>正在准备接录…</h4>
          <p>请稍候</p>
        </div>
      </div>
      <div class="dialog-footer">
        <el-button @click="cancelAttachFlow">取消</el-button>
      </div>
    </div>

    <!-- skipConfig：回放前置步骤（先出弹窗，避免页面无反馈卡住） -->
    <div
      v-if="skipConfig && state === 'config' && preparingReplay && !skipConfigStartFailed"
      class="recorder-form"
    >
      <div class="recording-header">
        <el-icon class="is-loading recording-icon" :size="32"><VideoCamera /></el-icon>
        <div class="recording-info">
          <h4>正在回放前置步骤…</h4>
          <p>
            将先执行第 1～{{ (replayThroughIndex ?? 0) + 1 }} 步，成功后在当前调试浏览器中接录并插入到第
            {{ (insertAtIndex ?? 0) + 1 }} 步。步骤较多时可能需要几分钟，请勿关闭调试浏览器。
          </p>
        </div>
      </div>
      <div class="dialog-footer">
        <el-button @click="cancelAttachFlow">取消</el-button>
      </div>
    </div>

    <!-- skipConfig 自动接录启动中 -->
    <div
      v-if="skipConfig && state === 'config' && !preparingReplay && starting && !skipConfigStartFailed"
      class="recorder-form"
    >
      <div class="recording-header">
        <el-icon class="is-loading recording-icon" :size="32"><VideoCamera /></el-icon>
        <div class="recording-info">
          <h4>正在启动接录…</h4>
          <p>请稍候，将在当前交互调试浏览器中开始录制</p>
        </div>
      </div>
      <div class="dialog-footer">
        <el-button @click="cancelAttachFlow">取消</el-button>
      </div>
    </div>

    <!-- skipConfig 自动接录失败时的重试面板（避免空白弹窗） -->
    <div v-if="skipConfig && state === 'config' && skipConfigStartFailed" class="recorder-form">
      <el-alert type="warning" :closable="false" show-icon title="接录尚未开始" />
      <p class="url-hint" style="margin-top: 12px;">
        请确认交互调试会话仍为就绪状态，然后重试；或关闭后从步骤行重新发起「从这里开始录制」。
      </p>
      <div class="dialog-footer">
        <el-button @click="cancelAttachFlow">关闭</el-button>
        <el-button type="primary" :loading="starting" @click="retryAttachFlow">重试接录</el-button>
      </div>
    </div>

    <!-- ===== 录制中 ===== -->
    <div v-if="state === 'recording'" class="recording-state">
      <div class="recording-header">
        <el-icon class="is-loading recording-icon" :size="32"><VideoCamera /></el-icon>
        <div class="recording-info">
          <h4>{{ paused ? '⏸ 录制已暂停' : '🔴 正在录制...' }}</h4>
          <p>请在弹出的浏览器窗口中操作页面</p>
          <p class="recording-stats">
            已记录 <strong>{{ actionsCount }}</strong> 个操作
            <span v-if="elapsedTime > 0">，已录制 {{ formatTime(elapsedTime) }}</span>
          </p>
        </div>
      </div>

      <div class="save-variable-row">
        <el-input
          v-model="saveVarName"
          placeholder="变量名，如 order_id"
          size="small"
          style="width: 160px"
          :disabled="paused || savingVariable"
        />
        <el-select
          v-model="saveVarSource"
          size="small"
          style="width: 110px"
          :disabled="paused || savingVariable"
        >
          <el-option label="文本 text" value="text" />
          <el-option label="控件值 value" value="value" />
        </el-select>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="!saveVarName.trim() || paused"
          :loading="savingVariable"
          @click="handleSaveVariable"
        >
          存当前悬停元素
        </el-button>
        <span class="save-var-hint">
          先在浏览器中悬停目标元素，再点击存变量；
          <template v-if="saveVarSource === 'value'">value 取 input/textarea/select 当前控件值（非 HTML 属性）</template>
          <template v-else>text 取元素可见文本</template>
        </span>
      </div>

      <el-divider />

      <div class="recording-actions-preview">
        <h5>实时操作预览</h5>
        <el-timeline v-if="actions.length > 0">
          <el-timeline-item
            v-for="(action, idx) in actions.slice(-10)"
            :key="idx"
            :type="actionTypeColor(action.action_type)"
          >
            <span class="action-tag">{{ actionTypeLabel(action.action_type) }}</span>
            <span class="action-detail">{{ formatActionDetail(action) }}</span>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无操作记录，请在浏览器中点击、输入或拖拽" />
      </div>

      <div class="dialog-footer">
        <el-button
          v-if="!paused"
          :loading="pausing"
          @click="handlePause"
        >
          <el-icon><VideoPause /></el-icon>
          暂停
        </el-button>
        <el-button
          v-else
          type="warning"
          :loading="pausing"
          @click="handleResume"
        >
          继续录制
        </el-button>
        <el-button type="danger" :loading="stopping" @click="handleStop">
          <el-icon><VideoPause /></el-icon>
          停止录制
        </el-button>
      </div>
    </div>

    <!-- ===== 结果态 ===== -->
    <div v-if="state === 'result'" class="result-state">
      <div class="result-header">
        <el-icon :size="32" color="#67C23A"><CircleCheck /></el-icon>
        <div>
          <h4>录制完成</h4>
          <p>共生成 {{ currentSteps.length }} 个步骤</p>
        </div>
      </div>

      <el-divider />

      <!-- 测试描述（用于 AI 优化上下文） -->
      <div class="description-section">
        <el-form-item label-width="80px">
          <template #label>
            <span class="desc-label">测试描述</span>
            <el-tooltip placement="top-start" :show-after="200">
              <template #content>
                <div class="recorder-desc-tooltip">{{ DESCRIPTION_TOOLTIP }}</div>
              </template>
              <el-icon class="desc-help-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="description"
            type="textarea"
            :rows="4"
            maxlength="4000"
            show-word-limit
            :placeholder="DESCRIPTION_PLACEHOLDER"
            style="width: 100%"
          />
          <el-collapse v-if="optimizeOptions.append_assertions" class="desc-example-collapse">
            <el-collapse-item title="查看推荐写法与示例（勾选补充断言时建议参考）" name="example">
              <pre class="desc-example">{{ DESCRIPTION_EXAMPLE }}</pre>
              <el-button link type="primary" size="small" @click="fillDescriptionExample">
                填入示例（可再按实际页面改文案）
              </el-button>
            </el-collapse-item>
          </el-collapse>
        </el-form-item>
      </div>

      <!-- AI 优化区域 -->
      <div class="optimize-section optimize-options">
        <el-form-item label="AI 模型" label-width="80px" style="width: 100%; margin-bottom: 8px;">
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
        <el-checkbox v-model="optimizeOptions.append_assertions">补充断言（基于描述中的预期）</el-checkbox>
        <el-checkbox v-model="optimizeOptions.use_page_context" :disabled="!optimizeOptions.append_assertions">
          使用录制页面文本辅助断言定位
        </el-checkbox>
      </div>
      <div class="optimize-section" v-if="!optimizedSteps.length">
        <el-button type="warning" :loading="optimizing" @click="handleOptimize">
          <el-icon><MagicStick /></el-icon>
          {{ optimizing ? 'AI 优化中...' : 'AI 优化步骤' }}
        </el-button>
        <span class="optimize-hint">录制结果已自动精简冗余步骤；如需合并断言或改写描述，可再点 AI 优化</span>
      </div>

      <div class="optimize-section" v-else>
        <el-radio-group v-model="stepVersion" size="small">
          <el-radio-button label="original">原始步骤 ({{ steps.length }} 步)</el-radio-button>
          <el-radio-button label="optimized">
            AI 优化 ({{ optimizedSteps.length }} 步
            <template v-if="lastOptimizeStats.assertions_count">，含 {{ lastOptimizeStats.assertions_count }} 断言</template>)
          </el-radio-button>
        </el-radio-group>
        <el-button type="warning" size="small" :loading="optimizing" @click="handleOptimize" style="margin-left: 12px;">
          重新优化
        </el-button>
        <el-button
          v-if="stepVersion === 'optimized'"
          type="primary"
          size="small"
          link
          style="margin-left: 8px"
          @click="handleRestoreMetaFromOriginal"
        >
          从原始步骤恢复 meta
        </el-button>
      </div>

      <!-- 步骤列表 -->
      <div class="steps-section">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 10px"
        >
          <template #title>
            <span style="font-size: 13px">
              定位支持 CSS、XPath、<code>get_by_text</code>、<code>get_by_role</code>、<code>header &gt;&gt; get_by_text=设置</code> 等区域链式。录制完成后会<strong>自动去掉重复导航、多余等待、点击输入框再填值等冗余步骤</strong>；黄色/红色「质量」标签请导入前核对。若 AI 优化后少了必要 click，请对照原始步骤或交互调试试跑。
            </span>
          </template>
        </el-alert>
        <h5>
          {{ stepVersion === 'optimized' ? 'AI 优化步骤' : '原始步骤' }}
          <el-button type="primary" size="small" link @click="handleAddStep">
            <el-icon><Plus /></el-icon> 添加步骤
          </el-button>
        </h5>
        <el-alert
          v-if="riskStepsCount > 0"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 8px"
          :title="`有 ${riskStepsCount} 个步骤存在定位风险，导入前请展开「质量」列核对`"
        />
        <el-table :data="currentSteps" size="small" border class="steps-table" :row-class-name="stepRowClassName">
          <el-table-column type="index" width="40" />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="stepTagType(row.method)">{{ row.keyword }}</el-tag>
              <el-tag v-if="row.meta?.ai_inferred_assertion" size="small" type="warning" style="margin-left: 4px;">AI断言</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="质量" width="88" align="center">
            <template #default="{ row }">
              <el-tooltip v-if="row.meta?.quality?.reasons?.length" placement="top">
                <template #content>
                  <div v-for="(r, i) in row.meta.quality.reasons" :key="i">{{ r }}</div>
                </template>
                <el-tag size="small" :type="qualityTagType(row)">{{ qualityLabel(row) }}</el-tag>
              </el-tooltip>
              <el-tag v-else size="small" type="success">正常</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="描述" min-width="180">
            <template #default="{ row, $index }">
              <el-input v-model="row.desc" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="定位表达式" min-width="200">
            <template #default="{ row }">
              <LocatorSelector
                v-if="row.params && row.params.locator !== undefined"
                v-model="row.params.locator"
                :meta="row.meta || {}"
              />
              <span v-else style="color: #999; font-size: 12px">-</span>
              <div v-if="row.meta?.accessibleName || row.meta?.region" class="locator-meta-hint">
                <span v-if="row.meta?.region">区域: {{ row.meta.region }}</span>
                <span v-if="row.meta?.accessibleName">捕获: {{ row.meta.accessibleName }}</span>
                <span v-if="row.meta?.matchIndex > 1">第 {{ row.meta.matchIndex }} 个相似</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="其他参数" min-width="160">
            <template #default="{ row, $index }">
              <el-input
                v-model="currentStepParamsJson[$index]"
                size="small"
                type="textarea"
                :rows="2"
                placeholder="不含 locator 的其他参数"
                @blur="handleParamsBlur($index)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ $index }">
              <el-button type="danger" size="small" link @click="handleDeleteStep($index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="handleApply">
          <el-icon><Check /></el-icon>
          {{ applyLabel }}
        </el-button>
      </div>
    </div>
  </el-dialog>


</template>

<script setup>
import { ref, reactive, computed, watch, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  VideoCamera, VideoPause, CircleCheck, Plus, Delete, Check, MagicStick, QuestionFilled
} from '@element-plus/icons-vue'

/** 测试描述撰写说明（与 Backend extract_expectations 的「预期：」格式对齐） */
const DESCRIPTION_PLACEHOLDER =
  '操作步骤 + 关键节点写「→ 预期：验证点」；不勾选补充断言时可只写流程'

const DESCRIPTION_TOOLTIP = `【怎么写更好】
1. 操作：账号、点哪里、输入什么（不必写「输入框应可见」）
2. 断言：只在关键结果写「→ 预期：…」，平台按条生成少量 outcome 断言
3. 预期写页面真实文案：菜单名、列表用户名、保存成功提示等
4. 否定用「不存在」「不应出现」→ 会生成 not_exist 断言

【识别格式】
• 登录 demo/demo123 → 查询 zhangsan → 预期：列表包含 zhangsan
• 或分行：1. 登录 → 预期：显示用户管理`

const DESCRIPTION_EXAMPLE = `【操作】
1. 使用 demo / demo123 登录
2. 进入用户管理，搜索框输入 zhangsan 并点击查询
3. 新增用户，姓名「测试」，点击保存

【预期】
1. 登录成功 → 预期：侧栏显示「用户管理」
2. 查询 zhangsan → 预期：列表中存在用户 zhangsan
3. 保存新用户 → 预期：列表中出现用户「测试」`

function fillDescriptionExample() {
  description.value = DESCRIPTION_EXAMPLE
}
import { aiRecordApi } from '@/api/modules/ai'
import { containsUnresolvedTemplate } from '@/utils/caseDescription.js'
import { useOnlineDevices } from '@/composables/useOnlineDevices.js'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import LocatorSelector from '@/components/LocatorSelector.vue'

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect({
  scene: 'recorder_optimize',
})

const props = defineProps({
  modelValue: Boolean,
  initialUrl: { type: String, default: '' },
  initialDescription: { type: String, default: '' },
  presetDeviceId: { type: [String, Number], default: '' },
  presetMode: { type: Boolean, default: false },
  skipConfig: { type: Boolean, default: false },
  initialHoverDelayMs: { type: Number, default: 1000 },
  applyLabel: { type: String, default: '应用到用例' },
  existingStepCount: { type: Number, default: 0 },
  defaultApplyMode: { type: String, default: 'replace' },
  insertAtIndex: { type: Number, default: null },
  debugSessionId: { type: Number, default: null },
  lockApplyMode: { type: Boolean, default: false },
  /** 接录前需回放的编辑器下标（含）；null 表示无需回放直接启动 */
  replayThroughIndex: { type: Number, default: null },
})

const emit = defineEmits(['update:modelValue', 'apply', 'prepare-replay'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

// ===== 状态 =====
const state = ref('config') // config / recording / result
const starting = ref(false)
const stopping = ref(false)
const pausing = ref(false)
const paused = ref(false)
const saveVarName = ref('')
const saveVarSource = ref('text')
const savingVariable = ref(false)
const skipConfigStartFailed = ref(false)
const preparingReplay = ref(false)
/** 取消接录流程时递增，避免回放完成后仍自动启动 */
let attachFlowEpoch = 0

// ===== 表单 =====
const form = reactive({
  url: '',
  device_id: '',
  use_ai_optimize: false,
  hover_delay_ms: 1000,
})

// 测试描述（移到结果态，用于 AI 优化上下文）
const description = ref('')
const applyMode = ref('replace')
const activeDebugSessionId = ref(null)

function syncApplyModeFromProps() {
  if (props.lockApplyMode) {
    applyMode.value = 'insert'
    return
  }
  if (props.existingStepCount > 0) {
    applyMode.value = props.defaultApplyMode === 'replace' ? 'replace' : (props.defaultApplyMode || 'append')
  } else {
    applyMode.value = 'replace'
  }
}

function ensureDescriptionPrefilled() {
  if ((description.value || '').trim()) return
  const initial = (props.initialDescription || '').trim()
  if (initial) description.value = initial
}

function resolveStartDescription() {
  const current = (description.value || '').trim()
  if (current) return current.slice(0, 4000)
  const initial = (props.initialDescription || '').trim()
  return initial ? initial.slice(0, 4000) : undefined
}

// 在线设备列表
const { onlineDevices, loadingDevices, deviceLoadError, loadOnlineDevices } = useOnlineDevices()

const selectedDeviceLabel = computed(() => {
  const id = form.device_id
  if (!id) return ''
  const d = onlineDevices.value.find(item => String(item.id) === String(id))
  return d ? `${d.name || d.id} (${d.ip || '未知IP'})` : String(id)
})

const applyPresetValues = () => {
  form.url = props.initialUrl || ''
  if (props.presetDeviceId) form.device_id = props.presetDeviceId
  if (props.initialHoverDelayMs) form.hover_delay_ms = props.initialHoverDelayMs
}

// ===== 录制数据 =====
const recordId = ref(null)
const actions = ref([])
const actionsCount = ref(0)
const elapsedTime = ref(0)
const steps = ref([])
const optimizedSteps = ref([])
const stepVersion = ref('original')
const optimizing = ref(false)
const optimizeOptions = reactive({
  append_assertions: true,
  use_page_context: true,
})
const lastOptimizeStats = reactive({
  trimmed_count: 0,
  assertions_count: 0,
  locators_picked: 0,
  locators_ai_picked: 0,
  locators_rule_picked: 0,
  risk_steps_count: 0,
  llm_applied: true,
  fallback_reason: '',
  meta_patched: 0,
  source_traced: 0,
})

const riskStepsCount = computed(() => {
  return currentSteps.value.filter(s => {
    const level = s.meta?.quality?.level
    return level === 'warn' || level === 'risk'
  }).length
})

function qualityTagType(row) {
  const level = row.meta?.quality?.level
  if (level === 'risk') return 'danger'
  if (level === 'warn') return 'warning'
  return 'success'
}

function qualityLabel(row) {
  const level = row.meta?.quality?.level
  if (level === 'risk') return '风险'
  if (level === 'warn') return '注意'
  return '正常'
}

function stepRowClassName({ row }) {
  const level = row.meta?.quality?.level
  if (level === 'risk') return 'step-row-risk'
  if (level === 'warn') return 'step-row-warn'
  return ''
}

function normalizeDescKey(desc) {
  return (desc || '').replace(/['"「」\s]/g, '')
}

function buildOriginalMetaMaps(originalSteps) {
  const byKey = new Map()
  const byIndex = new Map()
  originalSteps.forEach((s, idx) => {
    const meta = s.meta || {}
    byKey.set(`${s.method}|${normalizeDescKey(s.desc)}`, meta)
    byKey.set(`${s.method}|${s.params?.locator || ''}`, meta)
    byKey.set(`${s.method}|${s.params?.url || ''}`, meta)
    byIndex.set(idx + 1, meta)
    const recIdx = meta.rec_step_index
    if (recIdx) byIndex.set(recIdx, meta)
  })
  return { byKey, byIndex }
}

function restoreMetaForStep(step, maps) {
  const sourceIds = step.meta?.source_step_ids
    || (Array.isArray(step.source_step_ids) ? step.source_step_ids : null)
  if (Array.isArray(sourceIds) && sourceIds.length) {
    const merged = {}
    const cands = []
    sourceIds.forEach((id) => {
      const m = maps.byIndex.get(Number(id))
      if (!m) return
      Object.assign(merged, m)
      ;(m.candidates || []).forEach((c) => { if (c && !cands.includes(c)) cands.push(c) })
    })
    if (cands.length) merged.candidates = cands
    if (Object.keys(merged).length) return merged
  }
  return (
    maps.byKey.get(`${step.method}|${normalizeDescKey(step.desc)}`) ||
    maps.byKey.get(`${step.method}|${step.params?.locator || ''}`) ||
    maps.byKey.get(`${step.method}|${step.params?.url || ''}`) ||
    null
  )
}

function handleRestoreMetaFromOriginal() {
  if (!steps.value.length || !optimizedSteps.value.length) {
    ElMessage.warning('无原始步骤可恢复')
    return
  }
  const maps = buildOriginalMetaMaps(steps.value)
  let count = 0
  optimizedSteps.value.forEach(s => {
    const meta = restoreMetaForStep(s, maps)
    if (meta && Object.keys(meta).length) {
      s.meta = JSON.parse(JSON.stringify(meta))
      count++
    }
  })
  ElMessage.success(count ? `已恢复 ${count} 步的 meta/候选定位` : '未找到可匹配的 meta')
}
const stepParamsJson = ref([])
const optimizedStepParamsJson = ref([])

// ===== 轮询 =====
let pollTimer = null
let elapsedTimer = null
let startTime = 0

// ===== 方法 =====

const shouldCloseOnStartError = () => props.skipConfig && !props.lockApplyMode

const bumpAttachEpoch = () => {
  attachFlowEpoch += 1
  return attachFlowEpoch
}

const cancelAttachFlow = () => {
  bumpAttachEpoch()
  preparingReplay.value = false
  starting.value = false
  skipConfigStartFailed.value = false
  visible.value = false
}

const retryAttachFlow = async () => {
  skipConfigStartFailed.value = false
  if (props.replayThroughIndex != null && props.replayThroughIndex >= 0) {
    preparingReplay.value = true
    emit('prepare-replay', props.replayThroughIndex)
    return
  }
  await handleStart()
}

const startAfterPrepare = async () => {
  const epoch = attachFlowEpoch
  if (!visible.value || epoch !== attachFlowEpoch) return
  preparingReplay.value = false
  skipConfigStartFailed.value = false
  if (!visible.value || epoch !== attachFlowEpoch) return
  await handleStart()
}

const markPrepareFailed = (message) => {
  preparingReplay.value = false
  starting.value = false
  skipConfigStartFailed.value = true
  if (message) ElMessage.warning(message)
}

const abortRecordingQuiet = async () => {
  stopPolling()
  stopElapsedTimer()
  if (!recordId.value) return
  try {
    await aiRecordApi.stop(recordId.value, recordControlPayload())
  } catch {
    /* 关闭弹窗时尽力停止即可 */
  }
}

const handleBeforeClose = async (done) => {
  if (preparingReplay.value || (props.skipConfig && state.value === 'config' && starting.value)) {
    bumpAttachEpoch()
    preparingReplay.value = false
    starting.value = false
    done()
    return
  }
  if (state.value === 'recording' && recordId.value) {
    try {
      await ElMessageBox.confirm(
        '录制仍在进行。关闭将停止录制，未应用的步骤不会写入用例。是否关闭？',
        '退出录制',
        { type: 'warning', confirmButtonText: '停止并关闭', cancelButtonText: '继续录制' },
      )
    } catch {
      return
    }
    bumpAttachEpoch()
    await abortRecordingQuiet()
    state.value = 'config'
    done()
    return
  }
  bumpAttachEpoch()
  done()
}

const handleStart = async () => {
  const flowEpoch = attachFlowEpoch
  if (!visible.value) return
  const attachDebug = props.debugSessionId || activeDebugSessionId.value
  if (!attachDebug && !form.url.trim()) {
    ElMessage.warning('请输入目标页面地址')
    if (shouldCloseOnStartError()) visible.value = false
    return
  }
  const startUrl = (form.url || props.initialUrl || 'about:blank').trim()
  if (!attachDebug && startUrl !== 'about:blank' && containsUnresolvedTemplate(startUrl)) {
    ElMessage.warning('起始 URL 仍含未替换变量，请检查环境变量或填写完整地址')
    if (shouldCloseOnStartError()) visible.value = false
    return
  }
  if (!form.device_id && !props.presetDeviceId) {
    ElMessage.warning('请选择执行设备')
    if (shouldCloseOnStartError()) visible.value = false
    return
  }
  starting.value = true
  skipConfigStartFailed.value = false
  try {
    const payload = {
      url: startUrl || 'about:blank',
      device_id: form.device_id || props.presetDeviceId,
      use_ai_optimize: form.use_ai_optimize,
      hover_delay_ms: form.hover_delay_ms,
      description: resolveStartDescription(),
    }
    const debugSid = props.debugSessionId || activeDebugSessionId.value
    if (debugSid) {
      payload.debug_session_id = debugSid
    }
    const res = await aiRecordApi.start(payload)
    if (flowEpoch !== attachFlowEpoch || !visible.value) {
      // 用户已取消：若后端已建会话则尽力停止
      const rid = res?.data?.data?.record_id
      if (rid) {
        try {
          await aiRecordApi.stop(rid, debugSid ? { debug_session_id: debugSid } : {})
        } catch { /* ignore */ }
      }
      return
    }
    // axios response: res.status = HTTP 状态码, res.data = StandardResponse
    if (res.status === 200 && res.data?.code === 200) {
      recordId.value = res.data.data.record_id
      state.value = 'recording'
      paused.value = false
      saveVarName.value = ''
      saveVarSource.value = 'text'
      startTime = Date.now()
      actions.value = []
      actionsCount.value = 0
      elapsedTime.value = 0
      startPolling()
      startElapsedTimer()
      ElMessage.success('录制已启动，请在浏览器中操作页面')
    } else {
      ElMessage.error(res.data?.message || '启动录制失败')
      if (shouldCloseOnStartError()) {
        visible.value = false
      } else {
        skipConfigStartFailed.value = true
      }
    }
  } catch (e) {
    if (flowEpoch !== attachFlowEpoch || !visible.value) return
    ElMessage.error(e.response?.data?.detail || '启动录制失败')
    if (shouldCloseOnStartError()) {
      visible.value = false
    } else {
      skipConfigStartFailed.value = true
    }
  } finally {
    starting.value = false
  }
}

const handleStop = async () => {
  stopping.value = true
  stopElapsedTimer()
  try {
    const stopPayload = {}
    const debugSid = props.debugSessionId || activeDebugSessionId.value
    if (debugSid) stopPayload.debug_session_id = debugSid
    await aiRecordApi.stop(recordId.value, stopPayload)
    ElMessage.info('停止指令已发送，等待结果...')
    await waitForResult()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '停止录制失败')
    if (state.value === 'recording') {
      startPolling()
      startElapsedTimer()
    }
  } finally {
    stopping.value = false
  }
}

const recordControlPayload = () => {
  const debugSid = props.debugSessionId || activeDebugSessionId.value
  return debugSid ? { debug_session_id: debugSid } : {}
}

const handlePause = async () => {
  pausing.value = true
  try {
    const res = await aiRecordApi.pause(recordId.value, recordControlPayload())
    if (res.status === 200 && res.data?.code === 200) {
      paused.value = !!res.data.data?.paused
      ElMessage.success('录制已暂停')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '暂停失败')
  } finally {
    pausing.value = false
  }
}

const handleResume = async () => {
  pausing.value = true
  try {
    const res = await aiRecordApi.resume(recordId.value, recordControlPayload())
    if (res.status === 200 && res.data?.code === 200) {
      paused.value = false
      ElMessage.success('已恢复录制')
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '恢复失败')
  } finally {
    pausing.value = false
  }
}

const handleSaveVariable = async () => {
  const name = saveVarName.value.trim()
  if (!name) return
  if (paused.value) {
    ElMessage.warning('录制已暂停，请先恢复后再存变量')
    return
  }
  savingVariable.value = true
  try {
    const res = await aiRecordApi.saveVariable(recordId.value, {
      var_name: name,
      source: saveVarSource.value,
      ...recordControlPayload(),
    })
    if (res.status === 200 && res.data?.code === 200) {
      const data = res.data.data || {}
      if (data.ok === false) {
        ElMessage.error(formatSaveVarError(data))
        return
      }
      ElMessage.success(data.message || `已保存变量 ${name}`)
      saveVarName.value = ''
      const statusRes = await aiRecordApi.getStatus(recordId.value)
      if (statusRes.status === 200 && statusRes.data?.code === 200) {
        const statusData = statusRes.data.data
        actions.value = statusData.raw_actions || []
        actionsCount.value = statusData.actions_count
      }
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '存变量失败，请确认已悬停目标元素')
  } finally {
    savingVariable.value = false
  }
}

const SAVE_VAR_ERROR_MAP = {
  not_recording: '当前未在录制中',
  empty_var_name: '变量名不能为空',
  no_hover_target: '请先在浏览器中悬停目标元素（5 秒内）',
}

function formatSaveVarError(result) {
  const reason = result?.reason || ''
  return SAVE_VAR_ERROR_MAP[reason] || result?.message || '存变量失败'
}

const waitForResult = async () => {
  stopPolling()
  // 最多等待 30 秒
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 1000))
    try {
      const res = await aiRecordApi.getStatus(recordId.value)
      if (res.status === 200 && res.data?.code === 200) {
        const data = res.data.data
        actions.value = data.raw_actions || []
        actionsCount.value = data.actions_count
        if (data.status === 'completed') {
          steps.value = data.steps || []
          optimizedSteps.value = data.optimized_steps || []
          syncStepParamsJson()
          ensureDescriptionPrefilled()
          state.value = 'result'
          return
        }
        if (data.status === 'failed') {
          ElMessage.error(data.error || '录制失败')
          state.value = 'config'
          return
        }
      }
    } catch (e) {
      console.error('等待结果失败:', e)
    }
  }
  ElMessage.warning('等待结果超时，请稍后手动查询')
  state.value = 'config'
}

const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!recordId.value) return
    try {
      const res = await aiRecordApi.getStatus(recordId.value)
      if (res.status === 200 && res.data?.code === 200) {
        const data = res.data.data
        actions.value = data.raw_actions || []
        actionsCount.value = data.actions_count
        paused.value = !!data.paused
        // 如果 Runner 已经自动完成
        if (data.status === 'completed' && state.value === 'recording') {
          steps.value = data.steps || []
          optimizedSteps.value = data.optimized_steps || []
          syncStepParamsJson()
          ensureDescriptionPrefilled()
          stopPolling()
          stopElapsedTimer()
          state.value = 'result'
          ElMessage.success('录制完成')
        }
        if (data.status === 'failed' && state.value === 'recording') {
          stopPolling()
          stopElapsedTimer()
          ElMessage.error(data.error || '录制失败')
          state.value = 'config'
        }
      }
    } catch (e) {
      console.error('轮询状态失败:', e)
    }
  }, 1000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startElapsedTimer = () => {
  stopElapsedTimer()
  elapsedTimer = setInterval(() => {
    elapsedTime.value = Math.floor((Date.now() - startTime) / 1000)
  }, 1000)
}

const stopElapsedTimer = () => {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

const currentSteps = computed(() => stepVersion.value === 'optimized' ? optimizedSteps.value : steps.value)
const currentStepParamsJson = computed(() => stepVersion.value === 'optimized' ? optimizedStepParamsJson.value : stepParamsJson.value)

const syncStepParamsJson = () => {
  // 参数 JSON 中排除 locator（locator 已单独用 LocatorSelector 展示和编辑）
  stepParamsJson.value = steps.value.map(s => {
    const { locator, ...rest } = s.params || {}
    return JSON.stringify(rest, null, 2)
  })
  optimizedStepParamsJson.value = optimizedSteps.value.map(s => {
    const { locator, ...rest } = s.params || {}
    return JSON.stringify(rest, null, 2)
  })
}

const handleParamsBlur = (index) => {
  try {
    const paramsJson = stepVersion.value === 'optimized' ? optimizedStepParamsJson.value : stepParamsJson.value
    const targetSteps = stepVersion.value === 'optimized' ? optimizedSteps.value : steps.value
    const parsed = JSON.parse(paramsJson[index])
    // 保留 locator（由 LocatorSelector 单独管理）
    const existingLocator = targetSteps[index].params?.locator
    targetSteps[index].params = { ...parsed, ...(existingLocator !== undefined ? { locator: existingLocator } : {}) }
  } catch (e) {
    ElMessage.warning(`第 ${index + 1} 步参数 JSON 格式错误`)
  }
}

const handleDeleteStep = (index) => {
  if (stepVersion.value === 'optimized') {
    optimizedSteps.value.splice(index, 1)
    optimizedStepParamsJson.value.splice(index, 1)
  } else {
    steps.value.splice(index, 1)
    stepParamsJson.value.splice(index, 1)
  }
}

const handleAddStep = () => {
  const newStep = {
    id: `step_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
    keyword: '点击元素',
    desc: '点击某个元素',
    method: 'click_ele',
    params: { locator: '', index: 1, force: false, timeout: 20000 },
    children: [],
    meta: {},
  }
  const paramsJson = JSON.stringify({ index: 1, force: false, timeout: 20000 }, null, 2)
  if (stepVersion.value === 'optimized') {
    optimizedSteps.value.push(newStep)
    optimizedStepParamsJson.value.push(paramsJson)
  } else {
    steps.value.push(newStep)
    stepParamsJson.value.push(paramsJson)
  }
}

const handleOptimize = async () => {
  if (!recordId.value) {
    ElMessage.warning('录制会话不存在')
    return
  }
  // 把结果态编辑过的 params JSON 写回 steps，再交给后端
  for (let i = 0; i < steps.value.length; i++) {
    try {
      const parsed = JSON.parse(stepParamsJson.value[i] || '{}')
      const existingLocator = steps.value[i].params?.locator
      steps.value[i].params = {
        ...parsed,
        ...(existingLocator !== undefined ? { locator: existingLocator } : {}),
      }
    } catch {
      /* 格式错误时保留已有 params */
    }
  }
  optimizing.value = true
  try {
    const res = await aiRecordApi.optimize(recordId.value, {
      description: description.value,
      ai_config_id: aiConfigId.value || undefined,
      append_assertions: optimizeOptions.append_assertions,
      use_page_context: optimizeOptions.use_page_context,
      // 结果态已编辑步骤（含 pre_wait 等），避免后端只用 DB 里未编辑的原始步骤
      steps: steps.value,
    })
    if (res.status === 200 && res.data?.code === 200) {
      const d = res.data.data || {}
      optimizedSteps.value = d.optimized_steps || []
      lastOptimizeStats.trimmed_count = d.trimmed_count || 0
      lastOptimizeStats.assertions_count = d.assertions_count || 0
      lastOptimizeStats.locators_picked = d.locators_picked || d.locators_restored || 0
      lastOptimizeStats.locators_ai_picked = d.locators_ai_picked || 0
      lastOptimizeStats.locators_rule_picked = d.locators_rule_picked || 0
      lastOptimizeStats.risk_steps_count = d.risk_steps_count || 0
      lastOptimizeStats.llm_applied = d.llm_applied !== false
      lastOptimizeStats.fallback_reason = d.fallback_reason || ''
      lastOptimizeStats.meta_patched = d.meta_patched || 0
      lastOptimizeStats.source_traced = d.source_traced || 0
      optimizedStepParamsJson.value = optimizedSteps.value.map(s => {
        const { locator, ...rest } = s.params || {}
        return JSON.stringify(rest, null, 2)
      })
      stepVersion.value = 'optimized'
      if (!lastOptimizeStats.llm_applied || lastOptimizeStats.fallback_reason) {
        ElMessage.warning(
          lastOptimizeStats.fallback_reason
            ? `AI 优化未完全生效（${lastOptimizeStats.fallback_reason}），已保留原始步骤结构，请核对`
            : 'AI 优化未生效，已保留原始步骤，请核对或重试'
        )
      } else if (d.no_change) {
        ElMessage.info('AI 已完成描述优化，操作步骤与参数基本未变，请重点核对描述与断言')
      } else {
        const parts = ['AI 优化完成']
        if (lastOptimizeStats.trimmed_count) parts.push(`精简 ${lastOptimizeStats.trimmed_count} 步`)
        if (lastOptimizeStats.assertions_count) parts.push(`断言 ${lastOptimizeStats.assertions_count} 条`)
        if (lastOptimizeStats.source_traced) parts.push(`溯源 ${lastOptimizeStats.source_traced} 步`)
        if (lastOptimizeStats.locators_picked) {
          const pickParts = []
          if (lastOptimizeStats.locators_ai_picked) pickParts.push(`AI 选 ${lastOptimizeStats.locators_ai_picked}`)
          if (lastOptimizeStats.locators_rule_picked) pickParts.push(`规则优选 ${lastOptimizeStats.locators_rule_picked}`)
          parts.push(`定位${pickParts.length ? pickParts.join('、') : `优选 ${lastOptimizeStats.locators_picked}`}`)
        }
        if (lastOptimizeStats.risk_steps_count) parts.push(`${lastOptimizeStats.risk_steps_count} 步需核对`)
        if (d.assertions_skipped_reason === 'no_expectations_in_description' && optimizeOptions.append_assertions) {
          parts.push('未补充断言（描述中缺少「预期」）')
        }
        ElMessage.success(parts.join('，'))
      }
    } else {
      ElMessage.error(res.data?.message || 'AI 优化失败')
    }
  } catch (e) {
    const detail = e.response?.data?.detail
    if (e.code === 'ECONNABORTED' || /timeout/i.test(String(e.message || ''))) {
      ElMessage.error('AI 优化超时（步骤较多或已开断言会更久）。可在「AI 场景绑定」调高 timeout，或先关掉「补充断言」再试')
    } else {
      ElMessage.error(detail || e.message || 'AI 优化失败')
    }
  } finally {
    optimizing.value = false
  }
}

const handleApply = async () => {
  const targetSteps = stepVersion.value === 'optimized' ? optimizedSteps.value : steps.value
  if (targetSteps.length === 0) {
    ElMessage.warning('没有可应用的步骤')
    return
  }
  const risks = targetSteps.filter(s => s.meta?.quality?.level === 'risk')
  if (risks.length > 0) {
    try {
      await ElMessageBox.confirm(
        `有 ${risks.length} 个步骤标记为「风险」（描述与捕获元素可能不一致），仍要导入吗？`,
        '定位风险确认',
        { type: 'warning', confirmButtonText: '仍要导入', cancelButtonText: '返回修改' }
      )
    } catch {
      return
    }
  }
  const mode = applyMode.value || 'replace'
  if (mode === 'replace' && props.existingStepCount > 0) {
    try {
      await ElMessageBox.confirm(
        `将用 ${targetSteps.length} 个新步骤覆盖编辑器内全部 ${props.existingStepCount} 步，是否继续？`,
        '覆盖确认',
        { type: 'warning', confirmButtonText: '覆盖', cancelButtonText: '取消' }
      )
    } catch {
      return
    }
  }
  emit('apply', {
    steps: JSON.parse(JSON.stringify(targetSteps)),
    description: (description.value || '').trim(),
    applyMode: mode,
    insertAtIndex: mode === 'insert' ? props.insertAtIndex : null,
  })
  visible.value = false
  resetState()
}

const resetState = () => {
  state.value = 'config'
  skipConfigStartFailed.value = false
  preparingReplay.value = false
  form.url = props.initialUrl || ''
  form.device_id = props.presetDeviceId || ''
  description.value = props.initialDescription || ''
  syncApplyModeFromProps()
  activeDebugSessionId.value = props.debugSessionId || null
  recordId.value = null
  actions.value = []
  actionsCount.value = 0
  elapsedTime.value = 0
  steps.value = []
  stepParamsJson.value = []
  optimizedSteps.value = []
  optimizedStepParamsJson.value = []
  stepVersion.value = 'original'
  stopPolling()
  stopElapsedTimer()
}

const formatTime = (seconds) => {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}分${s}秒`
}

const actionTypeColor = (type) => {
  const map = {
    click: 'primary', fill: 'success', navigate: 'warning', wait: 'info',
    drag_and_drop: 'warning', dblclick: 'danger', hover: '', keydown: 'info',
    scroll: 'info', contextmenu: 'danger', file: 'success', select: 'success',
  }
  return map[type] || ''
}

const actionTypeLabel = (type) => {
  const map = {
    click: '点击', fill: '输入', navigate: '导航', wait: '等待',
    dblclick: '双击', select: '选择', hover: '悬停',     drag_and_drop: '拖拽',
    keydown: '按键', scroll: '滚动', contextmenu: '右键', file: '上传',
    save_variable: '存变量',
  }
  return map[type] || type
}

const formatActionDetail = (action) => {
  if (action.action_type === 'save_variable') {
    return `$${action.value || ''} ← ${action.selector || ''}`
  }
  if (action.action_type === 'drag_and_drop') {
    const end = action.value || action.meta?.end_selector || ''
    return end ? `${action.selector || ''} → ${end}` : (action.selector || '')
  }
  return action.selector || action.url || action.value || ''
}

const stepTagType = (method) => {
  const map = {
    click_ele: 'primary', fill_value: 'success', open_url: 'warning',
    wait_for_time: 'info', double_click_ele: 'danger', hover: '',
    drag_and_drop: 'warning',
  }
  if (String(method || '').startsWith('kw_assert_')) return 'success'
  return map[method] || ''
}

watch(() => props.modelValue, async (val) => {
  if (val) {
    bumpAttachEpoch()
    resetState()
    applyPresetValues()
    syncApplyModeFromProps()
    await loadConfigs()
    if (!props.skipConfig) {
      const list = await loadOnlineDevices()
      if (!form.device_id && list.length === 1) {
        form.device_id = list[0].id
      }
    }
    applyPresetValues()
    if (props.skipConfig && props.presetMode) {
      await nextTick()
      if (!visible.value) return
      if (props.replayThroughIndex != null && props.replayThroughIndex >= 0) {
        preparingReplay.value = true
        emit('prepare-replay', props.replayThroughIndex)
        return
      }
      await handleStart()
    }
  } else {
    bumpAttachEpoch()
    preparingReplay.value = false
  }
})

watch(() => props.initialUrl, (url) => {
  form.url = url || ''
})

watch(() => props.presetDeviceId, (id) => {
  if (id) form.device_id = id
})

defineExpose({
  recordId,
  startAfterPrepare,
  markPrepareFailed,
  cancelAttachFlow,
})

onUnmounted(() => {
  bumpAttachEpoch()
  stopPolling()
  stopElapsedTimer()
})
</script>

<style scoped lang="scss">
.ai-recorder-dialog {
  :deep(.el-dialog__body) {
    max-height: 70vh;
    overflow-y: auto;
    padding-top: 10px;
  }
}

.recorder-form {
  padding: 10px 0;
}

.recorder-checklist-alert {
  :deep(.el-alert__content) {
    width: 100%;
  }
}

.recorder-checklist {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.65;
  color: #606266;

  li + li {
    margin-top: 4px;
  }
}

.preset-summary {
  font-size: 13px;
  line-height: 1.6;
}

.recording-state {
  padding: 10px 0;

  .recording-header {
    display: flex;
    align-items: center;
    gap: 15px;
    padding: 10px;
    background: #fdf6ec;
    border-radius: 8px;
    border: 1px solid #f0c78a;

    .recording-icon {
      color: #f56c6c;
    }

    .recording-info {
      h4 {
        margin: 0 0 5px;
        color: #e6a23c;
      }
      p {
        margin: 0;
        color: #666;
        font-size: 14px;
      }
      .recording-stats {
        margin-top: 5px;
        font-size: 13px;
        strong {
          color: #f56c6c;
          font-size: 16px;
        }
      }
    }
  }

  .recording-actions-preview {
    max-height: 300px;
    overflow-y: auto;
    padding: 10px;
    background: #f5f7fa;
    border-radius: 6px;

    h5 {
      margin: 0 0 10px;
      color: #333;
    }

    .action-tag {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      background: #409eff;
      color: #fff;
      font-size: 12px;
      margin-right: 8px;
    }

    .action-detail {
      color: #666;
      font-size: 13px;
      word-break: break-all;
    }
  }

  .save-variable-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin: 8px 0;

    .save-var-hint {
      color: #909399;
      font-size: 12px;
    }
  }
}

.steps-table {
  :deep(.step-row-risk) {
    background-color: #fef0f0;
  }
  :deep(.step-row-warn) {
    background-color: #fdf6ec;
  }
}

.locator-meta-hint {
  margin-top: 4px;
  font-size: 11px;
  color: #909399;
  line-height: 1.5;
  span + span {
    margin-left: 8px;
  }
}

.result-state {
  padding: 10px 0;

  .result-header {
    display: flex;
    align-items: center;
    gap: 15px;
    padding: 10px;
    background: #f0f9eb;
    border-radius: 8px;
    border: 1px solid #b3e19d;

    h4 {
      margin: 0 0 5px;
      color: #67c23a;
    }
    p {
      margin: 0;
      color: #666;
      font-size: 14px;
    }
  }

  .description-section {
    margin-bottom: 12px;

    :deep(.el-form-item) {
      margin-bottom: 0;
    }
    :deep(.el-form-item__label) {
      color: #606266;
      font-weight: 500;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }

    .desc-label {
      line-height: 1;
    }

    .desc-help-icon {
      color: #909399;
      cursor: help;
      font-size: 14px;
    }

    .desc-example-collapse {
      margin-top: 8px;
      border: none;

      :deep(.el-collapse-item__header) {
        height: 32px;
        line-height: 32px;
        font-size: 12px;
        color: #409eff;
        border: none;
        background: transparent;
      }
      :deep(.el-collapse-item__wrap) {
        border: none;
      }
      :deep(.el-collapse-item__content) {
        padding-bottom: 4px;
      }
    }

    .recorder-desc-tooltip {
      max-width: 360px;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre-wrap;
    }

    .desc-example {
      margin: 0 0 8px;
      padding: 10px 12px;
      background: #f5f7fa;
      border-radius: 4px;
      font-size: 12px;
      line-height: 1.55;
      color: #606266;
      white-space: pre-wrap;
      word-break: break-word;
    }
  }

  .optimize-section {
    margin-bottom: 15px;
    padding: 12px;
    background: #fdf6ec;
    border-radius: 6px;
    border: 1px solid #f0c78a;
    display: flex;
    align-items: center;
    gap: 12px;

    &.optimize-options {
      flex-wrap: wrap;
      align-items: flex-start;
    }

    .optimize-hint {
      color: #e6a23c;
      font-size: 13px;
    }
  }

  .steps-section {
    margin-top: 15px;

    h5 {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 0 0 10px;
    }
  }

}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
  padding-top: 15px;
  border-top: 1px solid #e4e7ed;
}

.steps-table {
  :deep(.el-textarea__inner) {
    font-family: 'Consolas', monospace;
    font-size: 12px;
  }
}
</style>
