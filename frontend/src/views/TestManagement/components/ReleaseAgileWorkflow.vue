<template>
  <el-card class="agile-workflow" shadow="never">
    <div class="wf-header">
      <div>
        <h3 class="wf-title">敏捷迭代向导 · 功能优先</h3>
        <p class="wf-sub">
          Phase 0–4：功能用例为主轴；Phase 3 自动化可选，不阻塞发布收口。
        </p>
      </div>
      <div class="wf-progress">
        <span class="wf-pct">{{ progress }}%</span>
        <el-progress :percentage="progress" :stroke-width="8" style="width: 140px" />
        <el-tag v-if="phase4Ready" type="success" size="small">已发布收口</el-tag>
        <el-tag v-else-if="phase2Ready" type="success" size="small">可进入发布准备</el-tag>
        <el-tag v-else-if="phase1Ready" type="warning" size="small">执行中</el-tag>
        <el-tag v-else type="info" size="small">设计中</el-tag>
        <el-tag v-if="phase1Ready && phase3Progress > 0" type="info" size="small" effect="plain">
          自动化 {{ phase3Progress }}%
        </el-tag>
      </div>
    </div>

    <div
      v-for="phase in phases"
      :key="phase.id"
      class="wf-phase"
      :class="{ collapsed: phase.collapsed }"
    >
      <div class="wf-phase-head">
        <span class="wf-phase-title">{{ phase.title }}</span>
        <span class="wf-phase-sub">{{ phase.subtitle }}</span>
        <el-tag v-if="phase.collapsed" size="small" type="info" effect="plain">
          {{
            phase.id === 'phase4'
              ? '执行通过后展开'
              : phase.id === 'phase3'
                ? '评审通过后可选'
                : '评审通过后展开'
          }}
        </el-tag>
      </div>
      <div v-if="!phase.collapsed" class="wf-steps">
        <div
          v-for="step in phase.steps"
          :key="step.id"
          class="wf-step"
          :class="{
            done: step.done,
            next: step.id === nextStepId,
            optional: step.optional
          }"
        >
          <div class="wf-step-icon">
            <el-icon v-if="step.done" color="#67c23a"><CircleCheckFilled /></el-icon>
            <span v-else class="wf-step-num">{{ stepIndex(step.id) }}</span>
          </div>
          <div class="wf-step-body">
            <div class="wf-step-title">
              {{ step.title }}
              <el-tag v-if="step.optional" size="small" type="info" effect="plain">可选</el-tag>
              <el-tag
                v-if="step.id === 'required_done' && requiredProgress"
                size="small"
                type="warning"
                effect="plain"
              >{{ requiredProgress }}</el-tag>
            </div>
            <div class="wf-step-desc">{{ step.desc }}</div>
            <div v-if="step.done && step.completedAt" class="wf-step-time">
              完成于 {{ formatWorkflowTime(step.completedAt) }}
            </div>
            <div class="wf-step-actions">
              <el-button
                v-for="act in actionsFor(step)"
                :key="act.key"
                size="small"
                :type="step.id === nextStepId && !step.done ? 'primary' : 'default'"
                :plain="step.id !== nextStepId || step.done"
                @click="emit('action', act.event, act.payload)"
              >
                {{ act.label }}
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { AGILE_PHASES, computeAgileWorkflow, formatWorkflowTime } from '@/utils/releaseAgileWorkflow'

const props = defineProps({
  release: { type: Object, default: null },
  requirements: { type: Array, default: () => [] },
  scopes: { type: Array, default: () => [] },
  reviews: { type: Array, default: () => [] },
  requirementReviewDone: { type: Boolean, default: false },
  functionalCasesAck: { type: Boolean, default: false },
  qualityPreviewedAck: { type: Boolean, default: false },
  phase2: { type: Object, default: () => ({}) },
  phase3: { type: Object, default: () => ({}) },
  qualityMetrics: { type: Object, default: null },
  qualityPreview: { type: Object, default: null },
  workflowMarkTimes: { type: Object, default: () => ({}) },
  primaryPlanId: { type: Number, default: null },
  canEdit: { type: Boolean, default: false }
})

const emit = defineEmits(['action'])

const ctx = computed(() => ({
  release: props.release,
  requirements: props.requirements,
  scopes: props.scopes,
  reviews: props.reviews,
  requirementReviewDone: props.requirementReviewDone,
  functionalCasesAck: props.functionalCasesAck,
  qualityPreviewedAck: props.qualityPreviewedAck,
  phase2: props.phase2,
  phase3: props.phase3,
  qualityMetrics: props.qualityMetrics,
  qualityPreview: props.qualityPreview,
  workflowMarkTimes: props.workflowMarkTimes
}))

const wf = computed(() => computeAgileWorkflow(ctx.value))
const phases = computed(() => wf.value.phases)
const progress = computed(() => wf.value.progress)
const phase1Ready = computed(() => wf.value.phase1Ready)
const phase2Ready = computed(() => wf.value.phase2Ready)
const phase3Progress = computed(() => wf.value.phase3Progress)
const phase4Ready = computed(() => wf.value.phase4Ready)
const nextStepId = computed(() => wf.value.nextStepId)

const stepOrder = AGILE_PHASES.flatMap((p) => p.steps.map((s) => s.id))
const stepIndex = (id) => stepOrder.indexOf(id) + 1

const requiredProgress = computed(() => {
  const m = props.qualityMetrics
  if (!m?.required_total) return ''
  return `${m.required_done || 0}/${m.required_total}`
})

const actionsFor = (step) => {
  const id = step.id
  const done = step.done
  const editable = props.canEdit
  const releaseStatus = props.release?.status
  const planId = props.primaryPlanId
  const list = []
  const push = (key, label, event, payload) => list.push({ key, label, event, payload })

  switch (id) {
    case 'release_testing':
      if (!done && editable && releaseStatus === 'draft') {
        push('to_testing', '进入测试中', 'transition', { status: 'testing' })
      }
      break
    case 'link_requirements':
      if (editable) push('add_req', done ? '继续添加需求' : '关联需求', 'requirements', null)
      push('ai_testing', '打开需求测试中心', 'nav', { path: '/ai-testing' })
      break
    case 'requirement_review':
      push('req_review', '需求评审', 'req_reviews', null)
      if (!done) push('mark_req_review', '标记已完成', 'mark', { key: 'requirement_review' })
      break
    case 'functional_cases':
      push('cases', '功能用例库', 'nav', { path: '/ai-functional-cases' })
      push('ai_testing', '需求测试中心', 'nav', { path: '/ai-testing' })
      if (!done) push('mark_cases', '已维护用例', 'mark', { key: 'functional_cases' })
      break
    case 'add_scope':
      if (editable) push('scope', done ? '继续纳入' : '纳入用例', 'scopes_pick', null)
      break
    case 'scope_risk_owner':
      if (editable) push('scopes_tab', done ? '查看范围' : '配置风险/负责人', 'scopes_tab', null)
      break
    case 'case_review_start':
      if (editable) push('review', done ? '查看评审' : '发起评审', 'reviews', null)
      break
    case 'case_review_pass':
      if (done) push('open_review', '打开评审', 'open_review', null)
      else push('reviews_tab', '查看评审进度', 'reviews', null)
      break
    case 'plan_created':
      if (editable) {
        push('create_plan', done ? '查看计划' : '从范围创建计划', 'create_plan', null)
        if (!done) {
          push('tpl_smoke', '一键冒烟', 'create_plan_template', {
            plan_type: 'smoke',
            include_automation: false
          })
          push('tpl_reg', '一键回归', 'create_plan_template', {
            plan_type: 'regression',
            include_automation: false
          })
        }
      }
      if (planId) push('open_plan', '打开计划', 'open_plan', { planId })
      break
    case 'plan_env_set':
      if (planId) push('set_env', done ? '查看环境' : '设置环境', 'open_plan', { planId, tab: 'items' })
      else if (editable) push('create_plan', '先创建计划', 'create_plan', null)
      break
    case 'run_started':
      if (planId) push('create_run', done ? '查看运行' : '创建运行', 'open_plan', { planId, tab: 'runs' })
      else if (editable) push('create_plan', '先创建计划', 'create_plan', null)
      break
    case 'required_done':
      if (planId) push('fill_results', '填写结果', 'open_run', { planId })
      push('quality', '查看质量', 'quality_tab', null)
      break
    case 'defects_triaged':
      push('defects', done ? '查看缺陷' : '处理缺陷', 'defects_tab', null)
      break
    case 'mapping_started':
    case 'mapping_core_done':
      push('scopes_map', '查看未映射', 'unmapped_scopes', null)
      push('map_next', done ? '继续映射' : '映射下一例', 'map_next', null)
      break
    case 'auto_items_added':
      if (planId) push('gen_auto', done ? '查看计划' : '补齐自动化项', 'gen_automation', { planId })
      else if (editable) {
        push('tpl_reg_auto', '创建含自动化回归计划', 'create_plan_template', {
          plan_type: 'regression',
          include_automation: true
        })
      }
      break
    case 'auto_dispatched':
      if (planId) push('dispatch', done ? '查看运行' : '打开运行派发', 'open_run', { planId })
      break
    case 'quality_previewed':
      push('refresh_q', done ? '再次刷新' : '刷新质量预览', 'refresh_quality', null)
      push('quality_tab2', '打开质量 Tab', 'quality_tab', null)
      break
    case 'snapshot_created':
      if (editable) push('mk_snap', done ? '重新生成快照' : '生成快照', 'create_snapshot', null)
      push('quality_tab3', '质量 Tab', 'quality_tab', null)
      break
    case 'ready_status':
      if (editable && !['ready', 'released', 'archived'].includes(releaseStatus)) {
        push('to_ready', '变更为就绪', 'transition', { status: 'ready' })
      }
      break
    case 'released':
      if (editable && releaseStatus === 'ready') {
        push('to_released', '确认发布', 'transition', { status: 'released' })
      } else if (editable && !['released', 'archived'].includes(releaseStatus)) {
        push('to_ready_first', '先进入就绪', 'transition', { status: 'ready' })
      }
      break
    default:
      break
  }
  return list
}
</script>

<style scoped>
.agile-workflow {
  margin-bottom: 16px;
  border: 1px solid var(--el-border-color-lighter);
}
.wf-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.wf-title {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
}
.wf-sub {
  margin: 0;
  color: #909399;
  font-size: 13px;
}
.wf-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.wf-pct {
  font-size: 20px;
  font-weight: 600;
  color: var(--el-color-primary);
  min-width: 42px;
}
.wf-phase {
  margin-bottom: 16px;
}
.wf-phase:last-child {
  margin-bottom: 0;
}
.wf-phase.collapsed .wf-phase-head {
  opacity: 0.75;
}
.wf-phase-head {
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.wf-phase-title {
  font-weight: 600;
}
.wf-phase-sub {
  color: #909399;
  font-size: 12px;
}
.wf-steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.wf-step {
  display: flex;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  background: #fafafa;
}
.wf-step.next {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}
.wf-step.done {
  background: #f6ffed;
  border-color: #e1f3d8;
}
.wf-step-icon {
  width: 28px;
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 2px;
}
.wf-step-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #e4e7ed;
  color: #606266;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.wf-step.next .wf-step-num {
  background: var(--el-color-primary);
  color: #fff;
}
.wf-step-title {
  font-weight: 500;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.wf-step-desc {
  color: #606266;
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 4px;
}
.wf-step-time {
  color: #909399;
  font-size: 12px;
  margin-bottom: 8px;
}
.wf-step-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
