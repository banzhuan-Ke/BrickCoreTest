<template>
  <PageCard>
    <template #title>
      <b>技能与助手</b>
    </template>
    <template #main>
      <div class="skills-page" v-loading="loading">
        <div class="toolbar">
          <el-select v-model="days" style="width: 120px" @change="load">
            <el-option label="近 7 天" :value="7" />
            <el-option label="近 30 天" :value="30" />
            <el-option label="近 90 天" :value="90" />
          </el-select>
          <el-checkbox
            v-model="onlyCurrentProject"
            :disabled="!proStore.projectInfo?.id"
            @change="load"
          >
            仅当前项目{{ currentProjectLabel || '（请先选择项目）' }}
          </el-checkbox>
          <el-button @click="load">刷新</el-button>
          <el-button link type="primary" @click="router.push('/ai-usage')">模型使用情况</el-button>
          <el-button
            v-if="uStore.hasPermission('ai_config:view')"
            link
            type="primary"
            @click="router.push('/ai-assistant-traces')"
          >
            回合追踪
          </el-button>
        </div>

        <el-alert
          v-if="loadErrors.manifests"
          title="技能清单加载失败；统计与执行记录仍可能正常，请刷新或查看后端日志"
          type="error"
          show-icon
          :closable="false"
          class="cap-alert"
        />
        <el-alert
          v-if="capMessage"
          :title="capMessage"
          :type="capabilities.ready ? 'success' : 'warning'"
          show-icon
          :closable="false"
          class="cap-alert"
        />

        <section class="section">
          <h3 class="section-title">能力亮点</h3>
          <p class="section-desc">{{ highlights.blurb || '统计当前包内技能与可编排工具规模。' }}</p>
          <el-row :gutter="12">
            <el-col :xs="12" :sm="6">
              <div class="stat-card highlight-card">
                <div class="stat-label">内置技能</div>
                <div class="stat-value">{{ highlights.skill_count ?? summary.skill_count ?? 0 }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card highlight-card">
                <div class="stat-label">小测可调工具</div>
                <div class="stat-value">{{ highlights.assistant_tool_count ?? 0 }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card highlight-card">
                <div class="stat-label">MCP 工具</div>
                <div class="stat-value">{{ highlights.mcp_tool_count ?? 0 }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card highlight-card">
                <div class="stat-label">MCP 工具组</div>
                <div class="stat-value">{{ highlights.mcp_group_count ?? 0 }}</div>
              </div>
            </el-col>
          </el-row>
        </section>

        <section class="section">
          <h3 class="section-title">小测助手</h3>
          <p class="section-desc">{{ agent.name || '小测' }} · 当前模式 {{ modeLabel }}</p>
          <div class="mode-row">
            <div
              v-for="m in agent.modes || []"
              :key="m.code"
              class="mode-item"
              :class="{ active: m.code === capabilities.mode }"
            >
              <div class="mode-label">{{ modeDisplayLabel(m) }}</div>
              <div class="mode-summary">{{ m.summary }}</div>
            </div>
          </div>
          <ul class="notes">
            <li v-for="(n, i) in agent.notes || []" :key="i">{{ n }}</li>
          </ul>
        </section>

        <section class="section">
          <h3 class="section-title">近 {{ days }} 日汇总</h3>
          <el-row :gutter="12">
            <el-col :xs="12" :sm="6">
              <div class="stat-card">
                <div class="stat-label">已登记技能</div>
                <div class="stat-value">{{ summary.skill_count ?? 0 }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card">
                <div class="stat-label">执行次数</div>
                <div class="stat-value">{{ summary.calls ?? 0 }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card">
                <div class="stat-label">Token 消耗</div>
                <div class="stat-value">{{ formatTokenNum(summary.tokens_used) }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card">
                <div class="stat-label">失败次数</div>
                <div class="stat-value danger">{{ summary.failed_calls ?? 0 }}</div>
              </div>
            </el-col>
          </el-row>
        </section>

        <section class="section">
          <h3 class="section-title">效果运营（赞踩 × 提示词版本）</h3>
          <p class="section-desc">
            小测点赞/点踩与各技能所用提示词标识、版本的成本对照；不含提示词正文。
            「提示词标识」是包内 Prompt 模板的稳定编码（如 knowledge_qa），用来对照同一技能换版前后的效果。
          </p>
          <el-row :gutter="12" class="effect-row">
            <el-col :xs="12" :sm="6">
              <div class="stat-card">
                <div class="stat-label">有用</div>
                <div class="stat-value">{{ effect.feedback?.up ?? 0 }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card">
                <div class="stat-label">不准</div>
                <div class="stat-value danger">{{ effect.feedback?.down ?? 0 }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card">
                <div class="stat-label">有用率</div>
                <div class="stat-value">{{ formatRate(effect.feedback?.up_rate) }}</div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card">
                <div class="stat-label">平均轮次</div>
                <div class="stat-value">{{ effect.avg_rounds ?? '—' }}</div>
              </div>
            </el-col>
          </el-row>
          <el-table
            v-if="(effect.by_prompt_version || []).length"
            :data="effect.by_prompt_version"
            size="small"
            stripe
            border
            class="prompt-table"
            max-height="280"
          >
            <el-table-column prop="skill_code" label="技能" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ skillDisplayName(row.skill_code) }}</template>
            </el-table-column>
            <el-table-column prop="prompt_key" label="提示词标识" min-width="140" show-overflow-tooltip />
            <el-table-column label="版本" width="100">
              <template #default="{ row }">{{ promptVersionLabel(row.prompt_version) }}</template>
            </el-table-column>
            <el-table-column prop="calls" label="调用" width="80" align="right" />
            <el-table-column label="Token" width="100" align="right">
              <template #default="{ row }">{{ formatTokenNum(row.tokens_used) }}</template>
            </el-table-column>
            <el-table-column label="成功率" width="90" align="right">
              <template #default="{ row }">{{ formatRate(row.success_rate) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无提示词版本执行记录" :image-size="64" />
        </section>

        <section class="section">
          <h3 class="section-title">技能清单</h3>
          <p class="section-desc">
            当前包内清单与调用统计；历史记录中未登记的技能会标「历史」。开关 / 编辑提示词不在本页。
            「快速使用」会打开小测并走预览确认，不会在本页直接写入。
          </p>
          <el-empty v-if="!skills.length" :description="skillsEmptyDesc" :image-size="72" />
          <el-row v-else :gutter="12">
            <el-col v-for="sk in skills" :key="sk.code" :xs="24" :sm="12" :lg="8">
              <div class="skill-card">
                <div class="skill-head">
                  <span class="skill-name">{{ sk.name || sk.code }}</span>
                  <span class="skill-tags">
                    <el-tag v-if="sk.source === 'historical'" size="small" type="warning">历史</el-tag>
                  </span>
                </div>
                <div class="skill-code" :title="sk.code">编码 {{ sk.code }} · 版本 {{ sk.version || '-' }}</div>
                <p class="skill-desc">{{ sk.description || '—' }}</p>
                <div class="skill-meta">
                  <el-tag
                    v-for="em in sk.entry_modes || []"
                    :key="em"
                    size="small"
                    effect="plain"
                    class="entry-tag"
                  >{{ entryLabel(em) }}</el-tag>
                </div>
                <div class="skill-stats">
                  调用 {{ sk.stats?.calls ?? 0 }} · 成功 {{ sk.stats?.success_calls ?? 0 }} ·
                  失败 {{ sk.stats?.failed_calls ?? 0 }} · Token {{ formatTokenNum(sk.stats?.tokens_used) }}
                </div>
                <div class="skill-actions">
                  <el-button
                    type="primary"
                    size="small"
                    :disabled="!canQuickUse(sk)"
                    :title="quickUseDisabledReason(sk) || '打开小测并启动该技能'"
                    @click="handleQuickUse(sk)"
                  >
                    快速使用
                  </el-button>
                </div>
              </div>
            </el-col>
          </el-row>
        </section>

        <section class="section">
          <h3 class="section-title">执行记录</h3>
          <p class="section-desc">按时间倒序；默认每页 20 条。可按技能、状态、入口、模式筛选。</p>
          <div class="runs-toolbar">
            <el-select
              v-model="runFilters.skillCode"
              clearable
              filterable
              placeholder="全部技能"
              style="width: 200px"
              @change="onRunFilterChange"
            >
              <el-option
                v-for="opt in skillFilterOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
            <el-select
              v-model="runFilters.status"
              clearable
              placeholder="全部状态"
              style="width: 120px"
              @change="onRunFilterChange"
            >
              <el-option label="成功" value="success" />
              <el-option label="失败" value="failed" />
              <el-option label="进行中" value="running" />
              <el-option label="预览" value="preview" />
            </el-select>
            <el-select
              v-model="runFilters.entrySource"
              clearable
              placeholder="全部入口"
              style="width: 120px"
              @change="onRunFilterChange"
            >
              <el-option label="小测" value="assistant" />
              <el-option label="MCP" value="mcp" />
              <el-option label="页面" value="page" />
              <el-option label="接口" value="api" />
              <el-option label="任务" value="job" />
            </el-select>
            <el-select
              v-model="runFilters.runMode"
              clearable
              placeholder="全部模式"
              style="width: 120px"
              @change="onRunFilterChange"
            >
              <el-option label="直接执行" value="direct" />
              <el-option label="预览" value="preview" />
              <el-option label="确认" value="confirm" />
            </el-select>
            <el-button @click="loadRuns">刷新记录</el-button>
          </div>
          <el-table
            v-loading="runsLoading"
            :data="recentRuns"
            stripe
            size="small"
            empty-text="近段暂无技能执行记录"
          >
            <el-table-column prop="create_time" label="时间" min-width="160">
              <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
            </el-table-column>
            <el-table-column label="技能" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                <span :title="row.skill_code">{{ skillDisplayName(row.skill_code) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="入口" width="90">
              <template #default="{ row }">{{ entryLabel(row.entry_source) }}</template>
            </el-table-column>
            <el-table-column label="模式" width="90">
              <template #default="{ row }">{{ runModeLabel(row.run_mode) }}</template>
            </el-table-column>
            <el-table-column label="Token" width="90">
              <template #default="{ row }">{{ formatTokenNum(row.tokens_used) }}</template>
            </el-table-column>
            <el-table-column prop="username" label="用户" width="100" show-overflow-tooltip />
            <el-table-column prop="input_summary" label="输入摘要" min-width="180" show-overflow-tooltip />
            <el-table-column prop="error_message" label="错误" min-width="140" show-overflow-tooltip />
          </el-table>
          <div class="runs-pager">
            <el-pagination
              v-model:current-page="runPage"
              v-model:page-size="runPageSize"
              :total="runTotal"
              :page-sizes="[20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              background
              @current-change="loadRuns"
              @size-change="onRunPageSizeChange"
            />
          </div>
        </section>
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { aiAssistantApi } from '@/api/modules/ai_assistant.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'
import { openAssistantSkill } from '@/utils/assistantBridge.js'

const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()

const loading = ref(false)
const runsLoading = ref(false)
const days = ref(30)
const onlyCurrentProject = ref(false)
const capabilities = ref({})
const agent = ref({ name: '小测', modes: [], notes: [] })
const skills = ref([])
const summary = ref({})
const highlights = ref({})
const effect = ref({ feedback: {}, by_prompt_version: [], avg_rounds: null })
const recentRuns = ref([])
const runTotal = ref(0)
const runPage = ref(1)
const runPageSize = ref(20)
const runFilters = ref({
  skillCode: '',
  status: '',
  entrySource: '',
  runMode: ''
})
const loadErrors = ref({})
const loadSeq = ref(0)
const runsSeq = ref(0)

/** 兜底中文名（清单未加载或历史编码时用） */
const SKILL_NAME_FALLBACK = {
  ui_failure_analysis: '失败分析',
  knowledge_qa: '资料库问答',
  project_health_digest: '项目健康摘要',
  requirement_to_test_points: '需求→测试点',
  api_definition_to_cases: '接口定义→用例',
  test_points_to_functional_cases: '测试点→功能用例',
  mock_response_generate: 'Mock 响应生成',
  perf_scene_from_nl: '一句话压测场景',
  browser_lab_to_ui_case: '智能浏览器→UI 用例',
  ui_steps_from_nl: '自然语言→UI 步骤',
  report_narrative: '报告叙事',
  qa_eval_assist: '问答评测跑批',
  curl_to_cases: 'curl→接口用例',
  ui_locator_suggest: '元素→定位建议',
  platform_howto: '平台怎么用'
}

const MODE_LABEL_FALLBACK = {
  lite: '精简模式',
  standard: '标准模式（多轮）'
}

const currentProjectLabel = computed(() => {
  const p = proStore.projectInfo
  if (!p?.id) return ''
  return p.name ? `（${p.name}）` : `（#${p.id}）`
})

const skillNameByCode = computed(() => {
  const map = { ...SKILL_NAME_FALLBACK }
  for (const sk of skills.value || []) {
    if (sk?.code && sk?.name) map[sk.code] = sk.name
  }
  return map
})

const modeLabel = computed(() => {
  const mode = capabilities.value?.mode || 'lite'
  const hit = (agent.value.modes || []).find((m) => m.code === mode)
  return modeDisplayLabel(hit || { code: mode, label: MODE_LABEL_FALLBACK[mode] })
})

const capMessage = computed(() => {
  const c = capabilities.value || {}
  const msg = (c.message || '').trim()
  if (msg && msg !== 'ok') {
    return msg
      .replace(/\bAssist\b/gi, '小测扩展包')
      .replace(/\bstandard\b/gi, '标准模式')
      .replace(/\blite\b/gi, '精简模式')
  }
  if (!c.installed) return '小测扩展包未安装：可查看介绍，技能不可执行。'
  if (!c.ready) return c.reason || '小测扩展包未就绪：清单可看，执行需就绪。'
  return `小测扩展包已就绪（${c.version || '—'}）· 当前为${modeLabel.value}`
})

const skillsEmptyDesc = computed(() => {
  const c = capabilities.value || {}
  if (loadErrors.value?.manifests) return '技能清单加载失败，请刷新重试或查看后端日志'
  if (!c.installed) return '扩展包未安装，暂无技能清单'
  return '暂无技能清单'
})

const skillFilterOptions = computed(() => {
  const opts = []
  const seen = new Set()
  for (const sk of skills.value || []) {
    if (!sk?.code || seen.has(sk.code)) continue
    seen.add(sk.code)
    opts.push({ value: sk.code, label: sk.name || skillDisplayName(sk.code) })
  }
  return opts
})

function modeDisplayLabel(m) {
  if (!m) return '-'
  const raw = (m.label || '').trim()
  if (raw && !/^(Lite|Standard)/i.test(raw)) return raw
  return MODE_LABEL_FALLBACK[m.code] || raw || m.code || '-'
}

function skillDisplayName(code) {
  if (!code) return '-'
  return skillNameByCode.value[code] || code
}

/** RunRecord / 效果表里的 prompt_version 展示（platform=包内置模板） */
function promptVersionLabel(v) {
  if (v == null || v === '') return '—'
  const s = String(v)
  if (s === 'platform') return '平台内置'
  return s
}

function entryLabel(em) {
  const map = {
    assistant: '小测',
    api: '接口',
    mcp: 'MCP',
    page: '页面',
    job: '任务'
  }
  return map[em] || em || '-'
}

function requiredPermForSkill(sk) {
  if (sk?.required_permission) return sk.required_permission
  if (sk?.requires_ai_execute) return 'ai_test:execute'
  return ''
}

function canQuickUse(sk) {
  if (!sk?.code || sk.source === 'historical') return false
  if (!capabilities.value?.ready) return false
  if (!proStore.projectInfo?.id) return false
  if (sk.can_quick_use === false) return false
  const perm = requiredPermForSkill(sk)
  if (perm && !uStore.hasPermission(perm)) return false
  return true
}

function quickUseDisabledReason(sk) {
  if (sk?.source === 'historical') return '历史未登记技能，无法快捷启动'
  if (!capabilities.value?.ready) return '小测扩展包未就绪'
  if (!proStore.projectInfo?.id) return '请先选择项目'
  if (sk?.can_quick_use === false) return '当前环境不可快捷启动'
  const perm = requiredPermForSkill(sk)
  if (perm && !uStore.hasPermission(perm)) return `需要 ${perm} 权限`
  return ''
}

function handleQuickUse(sk) {
  const reason = quickUseDisabledReason(sk)
  if (reason) {
    ElMessage.warning(reason)
    return
  }
  openAssistantSkill({
    skillCode: sk.code,
    skillName: sk.name || sk.code
  })
}

function runModeLabel(m) {
  const map = {
    preview: '预览',
    confirm: '确认',
    direct: '直接执行'
  }
  return map[m] || m || '-'
}

function statusLabel(s) {
  const map = {
    success: '成功',
    failed: '失败',
    running: '进行中',
    preview: '预览',
    completed: '已完成'
  }
  return map[s] || s || '-'
}

function statusType(s) {
  if (s === 'success' || s === 'completed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'running' || s === 'preview') return 'warning'
  return 'info'
}

function formatTokenNum(n) {
  const v = Number(n || 0)
  if (!Number.isFinite(v) || v < 0) return '0'
  if (v >= 1_000_000) {
    const m = v / 1_000_000
    return `${m >= 10 ? m.toFixed(0) : m.toFixed(1)}M`
  }
  if (v >= 1000) {
    const k = v / 1000
    return `${k >= 10 ? k.toFixed(0) : k.toFixed(1)}K`
  }
  return String(Math.round(v))
}

function formatRate(v) {
  if (v == null || v === '') return '—'
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${(n * 100).toFixed(1)}%`
}

function formatTime(iso) {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString()
  } catch {
    return iso
  }
}

function currentFilterProjectId({ warn = false } = {}) {
  if (onlyCurrentProject.value && !proStore.projectInfo?.id) {
    onlyCurrentProject.value = false
    if (warn) ElMessage.warning('请先选择项目后再筛选「仅当前项目」')
  }
  const canSeeGlobalEffect = uStore.hasPermission('ai_config:view')
  let projectId =
    onlyCurrentProject.value && proStore.projectInfo?.id
      ? proStore.projectInfo.id
      : null
  if (projectId == null && !canSeeGlobalEffect && proStore.projectInfo?.id) {
    projectId = proStore.projectInfo.id
  }
  return { projectId, canSeeGlobalEffect }
}

function onRunFilterChange() {
  runPage.value = 1
  loadRuns()
}

function onRunPageSizeChange() {
  runPage.value = 1
  loadRuns()
}

async function loadRuns() {
  const seq = ++runsSeq.value
  runsLoading.value = true
  try {
    const { projectId } = currentFilterProjectId()
    const res = await aiAssistantApi.getSkillRuns({
      days: days.value,
      projectId,
      skillCode: runFilters.value.skillCode || null,
      status: runFilters.value.status || null,
      entrySource: runFilters.value.entrySource || null,
      runMode: runFilters.value.runMode || null,
      page: runPage.value,
      size: runPageSize.value
    })
    if (seq !== runsSeq.value) return
    if (res?.data?.code !== 200) {
      const detail = res?.data?.detail || res?.data?.message
      throw new Error(typeof detail === 'string' ? detail : '加载执行记录失败')
    }
    const data = res.data.data || {}
    recentRuns.value = data.items || []
    runTotal.value = Number(data.total || 0)
  } catch (e) {
    if (seq !== runsSeq.value) return
    recentRuns.value = []
    runTotal.value = 0
    const msg =
      e?.message ||
      e?.data?.message ||
      (typeof e?.data?.detail === 'string' ? e.data.detail : '') ||
      '加载执行记录失败'
    if (msg) ElMessage.error(msg)
  } finally {
    if (seq === runsSeq.value) runsLoading.value = false
  }
}

async function load() {
  const seq = ++loadSeq.value
  loading.value = true
  try {
    const { projectId, canSeeGlobalEffect } = currentFilterProjectId({ warn: true })
    const effectPromise =
      projectId != null || canSeeGlobalEffect
        ? aiAssistantApi.getFeedbackSummary({ days: days.value, projectId }).catch(() => null)
        : Promise.resolve(null)
    const [res, effectRes] = await Promise.all([
      aiAssistantApi.getSkillsOverview({
        days: days.value,
        projectId,
        recentLimit: 1
      }),
      effectPromise
    ])
    if (seq !== loadSeq.value) return
    if (res?.data?.code !== 200) {
      const detail = res?.data?.detail || res?.data?.message
      throw new Error(typeof detail === 'string' ? detail : '加载失败')
    }
    const data = res.data.data || {}
    capabilities.value = data.capabilities || {}
    agent.value = data.agent || { name: '小测', modes: [], notes: [] }
    skills.value = data.skills || []
    summary.value = data.summary || {}
    highlights.value = data.highlights || {}
    loadErrors.value = data.errors || {}
    if (effectRes?.data?.code === 200) {
      effect.value = effectRes.data.data || { feedback: {}, by_prompt_version: [] }
    } else {
      effect.value = { feedback: {}, by_prompt_version: [], avg_rounds: null }
    }
    const err = data.errors || {}
    if (err.manifests) {
      ElMessage.warning('技能清单加载失败；统计与执行记录仍可能正常')
    } else if (err.stats) {
      ElMessage.warning('部分统计查询失败，数字可能不完整，请查看后端日志')
    }
    runPage.value = 1
    await loadRuns()
  } catch (e) {
    if (seq !== loadSeq.value) return
    const msg =
      e?.message ||
      e?.data?.message ||
      (typeof e?.data?.detail === 'string' ? e.data.detail : '') ||
      '加载技能概览失败'
    if (msg && msg !== '加载技能概览失败') {
      ElMessage.error(msg)
    } else if (!e?.data && !e?.status) {
      ElMessage.error(msg)
    }
  } finally {
    if (seq === loadSeq.value) loading.value = false
  }
}

watch(
  () => proStore.projectInfo?.id,
  (nid, oid) => {
    if (!onlyCurrentProject.value) return
    if (nid === oid) return
    load()
  }
)

onMounted(() => {
  load()
})
</script>

<style scoped>
.skills-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.cap-alert {
  margin: 0;
}
.section-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
}
.section-desc {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.mode-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 10px;
  margin-bottom: 10px;
}
.mode-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--el-fill-color-blank);
}
.mode-item.active {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}
.mode-label {
  font-weight: 600;
  margin-bottom: 4px;
}
.mode-summary {
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
}
.notes {
  margin: 0;
  padding-left: 18px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.stat-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px 16px;
  background: var(--el-bg-color);
}
.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.stat-value {
  font-size: 22px;
  font-weight: 600;
  line-height: 1.2;
}
.stat-value.danger {
  color: var(--el-color-danger);
}
.effect-row {
  margin-bottom: 12px;
}
.prompt-table {
  width: 100%;
}
.skill-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 12px;
  height: calc(100% - 12px);
  background: var(--el-bg-color);
}
.skill-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.skill-name {
  font-weight: 600;
  font-size: 15px;
}
.skill-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}
.skill-code {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.skill-desc {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  min-height: 40px;
}
.skill-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.entry-tag {
  margin: 0;
}
.skill-stats {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
}
.skill-actions {
  display: flex;
  justify-content: flex-end;
}
.highlight-card {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-7);
}
.runs-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.runs-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
