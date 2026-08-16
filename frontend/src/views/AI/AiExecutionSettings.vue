<template>
  <div class="ai-execution-settings">
    <el-alert
      v-if="!compactHint"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
      title="定位器自愈与 AI Act 策略由 Backend 按项目配置；Runner 仅读取派发结果。Runner .env 的 AI_HEAL_ENABLED / AI_ACT_ENABLED 仅作运维熔断。"
    />
    <el-alert
      v-if="!projectId"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
      title="请先在顶栏或「项目管理」中选择项目，再配置本页。"
    />
    <el-alert
      v-else-if="!compactHint"
      type="success"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
      :title="`当前项目：${projectName}`"
      description="以下设置仅作用于该项目，保存后立即生效。"
    />

    <el-tabs v-if="section === 'all'" v-model="innerTab" class="exec-sub-tabs">
      <el-tab-pane label="自愈与 AI Act" name="heal" />
      <el-tab-pane label="录制与调试" name="recording" />
      <el-tab-pane label="失败分析" name="failure" />
      <el-tab-pane label="压测 AI" name="perf" />
      <el-tab-pane label="功能用例" name="cases" />
    </el-tabs>

    <el-alert
      v-if="projectId && !canEdit"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px;"
      title="当前为只读：查看策略请保留；保存需要「项目设置-编辑」或「AI 模型配置-编辑」。"
    />
    <el-form
      v-loading="execSettingsLoading"
      label-width="200px"
      style="max-width: 720px;"
      :disabled="!projectId || !canEdit"
    >
      <template v-if="activeSection === 'heal'">
        <p v-if="compactHint" class="section-lead">控制本项目 UI 执行时是否启用定位器自愈与 AI Act 兜底。</p>
        <el-divider content-position="left">定位器自愈</el-divider>
        <el-form-item label="启用定位器自愈">
          <el-switch v-model="execSettings.locator_heal_enabled" />
          <div class="form-tip">关闭后，本项目所有 UI 执行均不会调用 LLM 自愈</div>
        </el-form-item>
        <el-form-item label="执行时默认开启">
          <el-switch
            v-model="execSettings.locator_heal_default_on_execute"
            :disabled="!execSettings.locator_heal_enabled"
          />
        </el-form-item>
        <el-form-item label="允许运行弹窗覆盖">
          <el-switch
            v-model="execSettings.locator_heal_allow_run_override"
            :disabled="!execSettings.locator_heal_enabled"
          />
          <div class="form-tip">关闭后，测试人员不能在单次运行中改开关</div>
        </el-form-item>
        <el-divider content-position="left">AI Act 兜底</el-divider>
        <el-form-item label="启用 AI Act">
          <el-switch v-model="execSettings.ai_act_enabled" />
          <div class="form-tip">自愈仍失败时，按 intent/操作名称由 LLM 重新规划并执行一步</div>
        </el-form-item>
        <el-form-item label="执行时默认开启">
          <el-switch
            v-model="execSettings.ai_act_default_on_execute"
            :disabled="!execSettings.ai_act_enabled"
          />
        </el-form-item>
        <el-form-item label="允许运行弹窗覆盖">
          <el-switch
            v-model="execSettings.ai_act_allow_run_override"
            :disabled="!execSettings.ai_act_enabled"
          />
        </el-form-item>
        <el-form-item label="单用例最大次数">
          <el-input-number
            v-model="execSettings.ai_act_max_per_case"
            :min="1"
            :max="10"
            :disabled="!execSettings.ai_act_enabled"
          />
        </el-form-item>
      </template>

      <template v-else-if="activeSection === 'recording'">
        <p v-if="compactHint" class="section-lead">Web 录制与交互调试的项目级默认值（环境级可覆盖起始 URL）。</p>
        <el-form-item label="默认起始 URL">
          <el-input
            v-model="execSettings.default_start_url"
            placeholder="https://app.example.com/login"
            clearable
          />
          <div class="form-tip">用例步骤无 open_url 时，AI 录制与交互调试预填此地址；环境级配置优先于项目级</div>
        </el-form-item>
        <el-form-item label="录制定位策略">
          <el-select v-model="execSettings.recording_locator_strategy" style="width: 100%;">
            <el-option label="语义优先（testid / role / 区域链式）" value="semantic_first" />
            <el-option label="结构路径优先（nth-of-type 链，适合稳定后台）" value="structure_path_first" />
            <el-option label="绝对 XPath 优先" value="xpath_first" />
          </el-select>
          <div class="form-tip">影响 AI 录制落库时默认选中的定位器；LocatorSelector 中仍可手改</div>
        </el-form-item>
        <el-form-item>
          <template #label>
            <span class="label-with-tip">
              调试单步最大超时
              <el-tooltip
                placement="top"
                :show-after="200"
                content="仅交互调试「执行本步 / 执行勾选 / 工具条执行」生效：步骤等待与就绪探测等封顶到此秒数，失败更快反馈。正式跑用例仍用步骤自身超时与环境倍率。需关闭并重新打开调试会话后生效。"
              >
                <el-icon class="label-tip-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <el-input-number
            v-model="execSettings.debug_max_step_timeout_seconds"
            :min="1"
            :max="120"
            :step="1"
          />
          <span class="form-unit">秒</span>
          <div class="form-tip">
            默认 5 秒；过短可能导致慢站调试误失败，过长则失败反馈变慢
          </div>
        </el-form-item>
      </template>

      <template v-else-if="activeSection === 'failure'">
        <p v-if="compactHint" class="section-lead">报告页失败 AI 分析入口与运行弹窗覆盖策略。</p>
        <el-form-item label="启用失败 AI 分析">
          <el-switch v-model="execSettings.failure_analysis_enabled" />
          <div class="form-tip">关闭后，报告页不展示 AI 分析入口，且 API 拒绝分析请求</div>
        </el-form-item>
        <el-form-item label="报告默认展示">
          <el-switch
            v-model="execSettings.failure_analysis_default_on_report"
            :disabled="!execSettings.failure_analysis_enabled"
          />
        </el-form-item>
        <el-form-item label="允许运行弹窗覆盖">
          <el-switch
            v-model="execSettings.failure_analysis_allow_run_override"
            :disabled="!execSettings.failure_analysis_enabled"
          />
        </el-form-item>
      </template>

      <template v-else-if="activeSection === 'perf'">
        <p v-if="compactHint" class="section-lead">
          压测报告 AI 分析总开关与启动弹窗默认勾选策略。
          绑定模型请到「AI 配置 → 场景绑定」中的「性能测试」分组（压测单次报告分析 / 压测增强报告分析）。
        </p>
        <el-form-item label="启用压测 AI 分析">
          <el-switch v-model="execSettings.perf_ai_analysis_enabled" />
          <div class="form-tip">关闭后，启动弹窗不可勾选，报告页仍可手动尝试（API 会拒绝）或仅展示已有结果</div>
        </el-form-item>
        <el-form-item label="启动时默认勾选">
          <el-switch
            v-model="execSettings.perf_ai_analysis_default_on_run"
            :disabled="!execSettings.perf_ai_analysis_enabled"
          />
          <div class="form-tip">开启后，执行压测弹窗默认勾选「执行完成后 AI 分析」</div>
        </el-form-item>
        <el-form-item label="允许启动弹窗覆盖">
          <el-switch
            v-model="execSettings.perf_ai_analysis_allow_run_override"
            :disabled="!execSettings.perf_ai_analysis_enabled"
          />
        </el-form-item>
      </template>

      <template v-else-if="activeSection === 'cases'">
        <p v-if="compactHint" class="section-lead">需求功能用例生成时的参考条数 / AI 自定软区间系数。</p>
        <el-form-item label="默认 AI 自定条数">
          <el-switch v-model="execSettings.requirement_case.auto_count_enabled_default" />
          <div class="form-tip">打开需求生成页时，默认勾选「AI 自定条数」（建议保持关闭）</div>
        </el-form-item>
        <el-form-item label="绝对下限">
          <el-input-number
            v-model="execSettings.requirement_case.auto_count_min_floor"
            :min="1"
            :max="50"
          />
        </el-form-item>
        <el-form-item label="绝对上限">
          <el-input-number
            v-model="execSettings.requirement_case.auto_count_max_cap"
            :min="5"
            :max="100"
          />
          <div class="form-tip">AI 返回超过此值时：保留前 N 条入库并在报告标记截断</div>
        </el-form-item>
        <el-form-item label="软下限系数">
          <el-input-number
            v-model="execSettings.requirement_case.auto_count_min_ratio"
            :min="0.3"
            :max="1"
            :step="0.1"
            :precision="2"
          />
          <div class="form-tip">soft_min ≈ max(绝对下限, 建议条数 × 系数)</div>
        </el-form-item>
        <el-form-item label="软上限系数">
          <el-input-number
            v-model="execSettings.requirement_case.auto_count_max_ratio"
            :min="1"
            :max="3"
            :step="0.1"
            :precision="2"
          />
          <div class="form-tip">soft_max ≈ min(绝对上限, 建议条数 × 系数)</div>
        </el-form-item>
        <el-form-item label="参考条数硬上限">
          <el-input-number
            v-model="execSettings.requirement_case.fixed_count_hard_max"
            :min="10"
            :max="100"
          />
          <div class="form-tip">「参考条数」模式下输入框允许的最大值</div>
        </el-form-item>
      </template>

      <el-form-item>
        <el-button
          type="primary"
          :loading="execSettingsSaving"
          :disabled="!projectId || !canEdit"
          @click="saveExecutionSettings"
        >保存本页设置</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { projectSettingsApi } from '@/api/modules/sys.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'
import { validateDefaultStartUrl } from '@/utils/caseDescription.js'

const props = defineProps({
  /** heal | recording | failure | perf | cases | all（all 时展示内部分页） */
  section: {
    type: String,
    default: 'all',
    validator: (v) => ['heal', 'recording', 'failure', 'perf', 'cases', 'all'].includes(v),
  },
  /** 在项目设置页内嵌时隐藏重复的项目提示 */
  compactHint: { type: Boolean, default: false },
  /** 未传时按当前登录权限推断 */
  canEdit: { type: Boolean, default: undefined },
})

const uStore = UserStore()
const proStore = ProjectStore()
const projectId = computed(() => proStore.projectInfo?.id || null)
const projectName = computed(() => proStore.projectInfo?.name || `#${projectId.value}`)
const canEdit = computed(() => {
  if (typeof props.canEdit === 'boolean') return props.canEdit
  return uStore.hasPermission('project_settings:edit') || uStore.hasPermission('ai_config:edit')
})
const innerTab = ref('heal')
const activeSection = computed(() => (props.section === 'all' ? innerTab.value : props.section))

const execSettings = reactive({
  locator_heal_enabled: true,
  locator_heal_default_on_execute: true,
  locator_heal_allow_run_override: true,
  ai_act_enabled: false,
  ai_act_default_on_execute: false,
  ai_act_allow_run_override: true,
  ai_act_max_per_case: 3,
  recording_locator_strategy: 'semantic_first',
  default_start_url: '',
  debug_max_step_timeout_seconds: 5,
  failure_analysis_enabled: true,
  failure_analysis_default_on_report: true,
  failure_analysis_allow_run_override: true,
  perf_ai_analysis_enabled: false,
  perf_ai_analysis_default_on_run: false,
  perf_ai_analysis_allow_run_override: true,
  requirement_case: {
    auto_count_enabled_default: false,
    auto_count_min_floor: 4,
    auto_count_max_cap: 30,
    auto_count_min_ratio: 0.7,
    auto_count_max_ratio: 1.5,
    fixed_count_hard_max: 50
  }
})
const execSettingsLoading = ref(false)
const execSettingsSaving = ref(false)

const loadExecutionSettings = async () => {
  const pid = projectId.value
  if (!pid) return
  execSettingsLoading.value = true
  try {
    const res = await projectSettingsApi.getExecutionSettings(pid)
    if (res.data?.code === 200 && res.data.data) {
      const data = res.data.data
      const { requirement_case: rc, ...rest } = data
      Object.assign(execSettings, rest)
      if (rc && typeof rc === 'object') {
        Object.assign(execSettings.requirement_case, rc)
      }
    }
  } catch (e) {
    console.error(e)
  } finally {
    execSettingsLoading.value = false
  }
}

const SECTION_PAYLOAD_KEYS = {
  heal: [
    'locator_heal_enabled',
    'locator_heal_default_on_execute',
    'locator_heal_allow_run_override',
    'ai_act_enabled',
    'ai_act_default_on_execute',
    'ai_act_allow_run_override',
    'ai_act_max_per_case',
  ],
  recording: ['default_start_url', 'recording_locator_strategy', 'debug_max_step_timeout_seconds'],
  failure: [
    'failure_analysis_enabled',
    'failure_analysis_default_on_report',
    'failure_analysis_allow_run_override',
  ],
  perf: [
    'perf_ai_analysis_enabled',
    'perf_ai_analysis_default_on_run',
    'perf_ai_analysis_allow_run_override',
  ],
  cases: ['requirement_case'],
}

const buildSavePayload = () => {
  const section = activeSection.value
  if (props.section === 'all') {
    return {
      locator_heal_enabled: execSettings.locator_heal_enabled,
      locator_heal_default_on_execute: execSettings.locator_heal_default_on_execute,
      locator_heal_allow_run_override: execSettings.locator_heal_allow_run_override,
      ai_act_enabled: execSettings.ai_act_enabled,
      ai_act_default_on_execute: execSettings.ai_act_default_on_execute,
      ai_act_allow_run_override: execSettings.ai_act_allow_run_override,
      ai_act_max_per_case: execSettings.ai_act_max_per_case,
      recording_locator_strategy: execSettings.recording_locator_strategy,
      default_start_url: execSettings.default_start_url,
      debug_max_step_timeout_seconds: execSettings.debug_max_step_timeout_seconds,
      failure_analysis_enabled: execSettings.failure_analysis_enabled,
      failure_analysis_default_on_report: execSettings.failure_analysis_default_on_report,
      failure_analysis_allow_run_override: execSettings.failure_analysis_allow_run_override,
      perf_ai_analysis_enabled: execSettings.perf_ai_analysis_enabled,
      perf_ai_analysis_default_on_run: execSettings.perf_ai_analysis_default_on_run,
      perf_ai_analysis_allow_run_override: execSettings.perf_ai_analysis_allow_run_override,
      requirement_case: { ...execSettings.requirement_case },
    }
  }
  const keys = SECTION_PAYLOAD_KEYS[section] || []
  const payload = {}
  for (const key of keys) {
    if (key === 'requirement_case') {
      payload.requirement_case = { ...execSettings.requirement_case }
    } else {
      payload[key] = execSettings[key]
    }
  }
  return payload
}

const saveExecutionSettings = async () => {
  const pid = projectId.value
  if (!pid) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!canEdit.value) {
    ElMessage.warning('无编辑权限')
    return
  }
  if (activeSection.value === 'recording' || props.section === 'all') {
    const urlCheck = validateDefaultStartUrl(execSettings.default_start_url)
    if (!urlCheck.ok) {
      ElMessage.warning(urlCheck.error)
      return
    }
  }
  execSettingsSaving.value = true
  try {
    const res = await projectSettingsApi.updateExecutionSettings(pid, buildSavePayload())
    if (res.data?.code === 200) {
      ElMessage.success('设置已保存')
      const data = res.data.data
      if (data && typeof data === 'object') {
        const { requirement_case: rc, ...rest } = data
        Object.assign(execSettings, rest)
        if (rc && typeof rc === 'object') {
          Object.assign(execSettings.requirement_case, rc)
        }
      }
      await proStore.refreshProjectGlobals()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    execSettingsSaving.value = false
  }
}

watch(projectId, (pid) => {
  if (pid) loadExecutionSettings()
}, { immediate: true })
</script>

<style scoped>
.label-with-tip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.label-tip-icon {
  font-size: 14px;
  color: #909399;
  cursor: help;
  vertical-align: middle;
}
.label-tip-icon:hover {
  color: var(--el-color-primary);
}
.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
  width: 100%;
}
.form-unit {
  margin-left: 8px;
  color: #606266;
  font-size: 13px;
}
.section-lead {
  margin: 0 0 12px;
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}
.exec-sub-tabs {
  margin-bottom: 8px;
}
</style>
