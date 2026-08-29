/**
 * 敏捷迭代 · 功能优先工作流（Phase 0–4）
 * Phase 3（自动化渐进）全部可选，不计入进度、不阻塞 Phase 4。
 */

export const AGILE_PHASES = [
  {
    id: 'phase0',
    title: 'Phase 0：迭代启动',
    subtitle: '第 0–1 天',
    steps: [
      {
        id: 'release_testing',
        title: '版本进入测试中',
        desc: '创建版本后将状态切为「测试中」，表示迭代正式开测。',
        optional: false
      },
      {
        id: 'link_requirements',
        title: '关联迭代需求',
        desc: '从需求测试中心选择或手工填写编号/链接，便于追溯。',
        optional: false
      },
      {
        id: 'requirement_review',
        title: '需求可测性评审',
        desc: '确认需求可测、验收清晰；可在「需求评审」菜单发起。',
        optional: true
      }
    ]
  },
  {
    id: 'phase1',
    title: 'Phase 1：功能设计',
    subtitle: '第 1–3 天 · 主战场',
    steps: [
      {
        id: 'functional_cases',
        title: '维护功能用例',
        desc: '在功能用例库编写或从需求测试中心生成用例（功能测试是真源）。',
        optional: false
      },
      {
        id: 'add_scope',
        title: '纳入版本测试范围',
        desc: '将本迭代要测的功能用例纳入版本范围。',
        optional: false
      },
      {
        id: 'scope_risk_owner',
        title: '配置风险与负责人',
        desc: '高/严重风险项须指定负责人，用于门禁与分工。',
        optional: false
      },
      {
        id: 'case_review_start',
        title: '发起用例评审',
        desc: '范围定稿后发起评审，默认纳入全部范围用例。',
        optional: false
      },
      {
        id: 'case_review_pass',
        title: '用例评审通过',
        desc: '评审结论为已通过，方可进入测试计划执行阶段。',
        optional: false
      }
    ]
  },
  {
    id: 'phase2',
    title: 'Phase 2：功能执行',
    subtitle: '第 3–8 天 · 手工测试主路径',
    steps: [
      {
        id: 'plan_created',
        title: '已建功能测试计划',
        desc: '从范围创建计划（默认不含自动化项），纳入功能手工用例。',
        optional: false
      },
      {
        id: 'plan_env_set',
        title: '已设执行环境',
        desc: '在计划详情绑定参考环境，运行与门禁将据此校验。',
        optional: false
      },
      {
        id: 'run_started',
        title: '已创建至少一次运行',
        desc: '创建计划运行批次，在运行页填写手工结果。',
        optional: false
      },
      {
        id: 'required_done',
        title: '必测项已全部执行',
        desc: '质量预览中必测项完成率 100%，作为发布门禁输入。',
        optional: false
      },
      {
        id: 'defects_triaged',
        title: '无未关闭 Blocker/Critical',
        desc: '处理或关闭阻塞/严重缺陷，避免带伤发布。',
        optional: false
      }
    ]
  },
  {
    id: 'phase3',
    title: 'Phase 3：自动化渐进',
    subtitle: '有余力时 · 可选 · 不阻塞发布',
    steps: [
      {
        id: 'mapping_started',
        title: '已开始映射自动化',
        desc: '将功能用例映射到 UI/App/接口/压测资产。',
        optional: true
      },
      {
        id: 'mapping_core_done',
        title: '核心用例已映射',
        desc: '高/严重风险范围项均已关联自动化资产。',
        optional: true
      },
      {
        id: 'auto_items_added',
        title: '计划含自动化项',
        desc: '从范围补齐自动化计划项，或创建计划时开启「含自动化项」。',
        optional: true
      },
      {
        id: 'auto_dispatched',
        title: '已派发并同步',
        desc: '在运行页派发自动化并看到结果回写。',
        optional: true
      }
    ]
  },
  {
    id: 'phase4',
    title: 'Phase 4：发布收口',
    subtitle: '迭代末 · 质量快照与状态变更',
    steps: [
      {
        id: 'quality_previewed',
        title: '已刷新质量预览',
        desc: '查看实时门禁指标，确认必测、缺陷与高风险覆盖。',
        optional: false
      },
      {
        id: 'snapshot_created',
        title: '已生成合格快照',
        desc: '生成 pass 快照，或由授权人批准豁免（有条件通过）。',
        optional: false
      },
      {
        id: 'ready_status',
        title: '已进入就绪',
        desc: '变更版本状态为「就绪」，仍走现有门禁确认。',
        optional: false
      },
      {
        id: 'released',
        title: '已发布',
        desc: '变更版本状态为「已发布」，完成迭代收口。',
        optional: false
      }
    ]
  }
]

const STEP_ORDER = AGILE_PHASES.flatMap((p) => p.steps.map((s) => s.id))

function pickEarliest(times = []) {
  const valid = times.filter(Boolean).map(String)
  if (!valid.length) return null
  return [...valid].sort()[0]
}

function pickLatest(times = []) {
  const valid = times.filter(Boolean).map(String)
  if (!valid.length) return null
  return [...valid].sort().reverse()[0]
}

export function formatWorkflowTime(value) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 19)
}

function highRiskScopes(scopes = []) {
  return scopes.filter((s) => ['high', 'critical'].includes(s.risk_level))
}

function isMapped(status) {
  return status && status !== 'none'
}

function phaseOf(stepId) {
  return AGILE_PHASES.find((p) => p.steps.some((s) => s.id === stepId))
}

function stepDone(id, ctx) {
  const { release, requirements, scopes, reviews, phase2, phase3, qualityPreview } = ctx
  switch (id) {
    case 'release_testing':
      return release?.status && release.status !== 'draft'
    case 'link_requirements':
      return (requirements?.length || 0) > 0
    case 'requirement_review':
      return !!ctx.requirementReviewDone
    case 'functional_cases':
      return (scopes?.length || 0) > 0 || !!ctx.functionalCasesAck
    case 'add_scope':
      return (scopes?.length || 0) > 0
    case 'scope_risk_owner': {
      if (!(scopes?.length || 0)) return false
      const highs = highRiskScopes(scopes)
      if (!highs.length) return true
      return highs.every((s) => s.owner_id)
    }
    case 'case_review_start':
      return (reviews?.length || 0) > 0
    case 'case_review_pass':
      return (reviews || []).some((r) => r.status === 'approved')
    case 'plan_created':
      return !!phase2?.hasManualPlan
    case 'plan_env_set':
      return !!phase2?.hasPlanEnv
    case 'run_started':
      return (phase2?.runsCount || 0) > 0
    case 'required_done': {
      const m = ctx.qualityMetrics
      if (!m || !m.required_total) return false
      return m.required_done >= m.required_total
    }
    case 'defects_triaged': {
      const m = ctx.qualityMetrics
      if (m) {
        return (m.blocker_open || 0) === 0 && (m.critical_open || 0) === 0
      }
      return (phase2?.blockerOpen || 0) === 0 && (phase2?.criticalOpen || 0) === 0
    }
    case 'mapping_started':
      return (scopes || []).some((s) => isMapped(s.automation_status))
    case 'mapping_core_done': {
      const highs = highRiskScopes(scopes)
      if (!highs.length) return (scopes || []).some((s) => isMapped(s.automation_status))
      return highs.every((s) => isMapped(s.automation_status))
    }
    case 'auto_items_added':
      return !!phase3?.hasAutomationItems
    case 'auto_dispatched':
      return !!phase3?.hasAutoDispatched
    case 'quality_previewed':
      return !!qualityPreview || !!ctx.qualityPreviewedAck
    case 'snapshot_created': {
      const snap = qualityPreview?.latest_snapshot
      if (!snap) return false
      if (qualityPreview?.has_valid_waiver) return true
      return snap.conclusion === 'pass' && !qualityPreview?.snapshot_stale
    }
    case 'ready_status':
      return ['ready', 'released'].includes(release?.status)
    case 'released':
      return release?.status === 'released'
    default:
      return false
  }
}

function stepCompletedAt(id, ctx) {
  const {
    release,
    requirements,
    scopes,
    reviews,
    phase2,
    phase3,
    qualityPreview,
    workflowMarkTimes
  } = ctx
  const markTime = (key) => workflowMarkTimes?.[key] || null

  switch (id) {
    case 'release_testing':
      return release?.status && release.status !== 'draft' ? release.update_time : null
    case 'link_requirements':
      return pickEarliest((requirements || []).map((r) => r.create_time))
    case 'requirement_review':
      return markTime('requirement_review')
    case 'functional_cases':
      return markTime('functional_cases') || pickEarliest((scopes || []).map((s) => s.create_time))
    case 'add_scope':
      return pickEarliest((scopes || []).map((s) => s.create_time))
    case 'scope_risk_owner': {
      if (!(scopes?.length || 0)) return null
      const highs = highRiskScopes(scopes)
      if (!highs.length) return pickLatest((scopes || []).map((s) => s.update_time))
      if (!highs.every((s) => s.owner_id)) return null
      return pickLatest(highs.map((s) => s.update_time || s.create_time))
    }
    case 'case_review_start':
      return pickEarliest((reviews || []).map((r) => r.create_time))
    case 'case_review_pass': {
      const approved = (reviews || []).filter((r) => r.status === 'approved')
      return pickEarliest(
        approved.map((r) => r.final_decision_at || r.update_time || r.create_time)
      )
    }
    case 'plan_created':
      return phase2?.firstPlanCreateTime || null
    case 'plan_env_set':
      return phase2?.firstPlanEnvTime || null
    case 'run_started':
      return phase2?.firstRunStartedAt || null
    case 'required_done':
      return phase2?.requiredDoneAt || null
    case 'defects_triaged':
      return phase2?.defectsTriagedAt || markTime('quality_preview') || null
    case 'mapping_started': {
      const mapped = (scopes || []).filter((s) => isMapped(s.automation_status))
      return pickEarliest(mapped.map((s) => s.update_time || s.create_time))
    }
    case 'mapping_core_done': {
      const highs = highRiskScopes(scopes)
      const target = highs.length
        ? highs.filter((s) => isMapped(s.automation_status))
        : (scopes || []).filter((s) => isMapped(s.automation_status))
      if (!target.length) return null
      return pickLatest(target.map((s) => s.update_time || s.create_time))
    }
    case 'auto_items_added':
      return phase3?.autoItemsAt || null
    case 'auto_dispatched':
      return phase3?.autoDispatchedAt || null
    case 'quality_previewed':
      return markTime('quality_preview') || qualityPreview?.previewed_at || null
    case 'snapshot_created': {
      const snap = qualityPreview?.latest_snapshot
      if (!snap) return null
      if (qualityPreview?.has_valid_waiver && snap.waiver_approved_at) return snap.waiver_approved_at
      if (snap.conclusion === 'pass' && !qualityPreview?.snapshot_stale) return snap.create_time
      if (qualityPreview?.has_valid_waiver) return snap.waiver_approved_at || snap.create_time
      return null
    }
    case 'ready_status':
      return ['ready', 'released'].includes(release?.status) ? release.update_time : null
    case 'released':
      return release?.status === 'released'
        ? release.actual_release_at || release.update_time
        : null
    default:
      return null
  }
}

/**
 * @returns {{
 *   phases: Array,
 *   progress: number,
 *   phase1Ready: boolean,
 *   phase2Ready: boolean,
 *   phase3Progress: number,
 *   phase4Ready: boolean,
 *   nextStepId: string|null,
 *   activePhaseId: string|null
 * }}
 */
export function computeAgileWorkflow(ctx) {
  const phase1Ready = stepDone('case_review_pass', ctx)
  const phase2Ready =
    phase1Ready &&
    stepDone('plan_created', ctx) &&
    stepDone('plan_env_set', ctx) &&
    stepDone('run_started', ctx) &&
    stepDone('required_done', ctx) &&
    stepDone('defects_triaged', ctx)

  const phases = AGILE_PHASES.map((phase) => {
    let collapsed = false
    if (phase.id === 'phase2' && !phase1Ready) collapsed = true
    if (phase.id === 'phase3' && !phase1Ready) collapsed = true
    if (phase.id === 'phase4' && !phase2Ready) collapsed = true
    return {
      ...phase,
      collapsed,
      steps: phase.steps.map((step) => ({
        ...step,
        done: stepDone(step.id, ctx),
        completedAt: stepDone(step.id, ctx) ? stepCompletedAt(step.id, ctx) : null
      }))
    }
  })

  let nextStepId = null
  for (const id of STEP_ORDER) {
    const phase = phaseOf(id)
    if (phase?.id === 'phase2' && !phase1Ready) continue
    if (phase?.id === 'phase3') continue // 可选，不抢 next
    if (phase?.id === 'phase4' && !phase2Ready) continue
    const step = phases.flatMap((p) => p.steps).find((s) => s.id === id)
    if (step && !step.done && !step.optional) {
      nextStepId = id
      break
    }
  }

  // 进度仅计必选步骤（不含 Phase 3）
  const requiredIds = STEP_ORDER.filter((id) => {
    const phase = phaseOf(id)
    if (phase?.id === 'phase3') return false
    if (phase?.id === 'phase2' && !phase1Ready) return false
    if (phase?.id === 'phase4' && !phase2Ready) return false
    const step = AGILE_PHASES.flatMap((p) => p.steps).find((s) => s.id === id)
    return step && !step.optional
  })
  const doneRequired = requiredIds.filter((id) => stepDone(id, ctx)).length
  const progress = requiredIds.length
    ? Math.round((doneRequired / requiredIds.length) * 100)
    : 0

  const phase3Steps = AGILE_PHASES.find((p) => p.id === 'phase3')?.steps || []
  const phase3Done = phase3Steps.filter((s) => stepDone(s.id, ctx)).length
  const phase3Progress = phase3Steps.length
    ? Math.round((phase3Done / phase3Steps.length) * 100)
    : 0

  const phase4Ready =
    phase2Ready &&
    stepDone('quality_previewed', ctx) &&
    stepDone('snapshot_created', ctx) &&
    stepDone('ready_status', ctx) &&
    stepDone('released', ctx)

  const activePhaseId = !phase1Ready
    ? 'phase1'
    : !phase2Ready
      ? 'phase2'
      : 'phase4'

  return {
    phases,
    progress,
    phase1Ready,
    phase2Ready,
    phase3Progress,
    phase4Ready,
    nextStepId,
    activePhaseId
  }
}

export function workflowStorageKey(releaseId, key) {
  return `tm_agile_wf_${releaseId}_${key}`
}

export function workflowMarkTimeKey(releaseId, key) {
  return workflowStorageKey(releaseId, `${key}_at`)
}

export function listUnmappedScopes(scopes = [], { highRiskOnly = false } = {}) {
  let rows = scopes || []
  if (highRiskOnly) {
    rows = highRiskScopes(rows)
  }
  return rows.filter((s) => !isMapped(s.automation_status))
}

export function automationCoverageStats(scopes = []) {
  const all = scopes || []
  const mapped = all.filter((s) => isMapped(s.automation_status)).length
  const highs = highRiskScopes(all)
  const highMapped = highs.filter((s) => isMapped(s.automation_status)).length
  return {
    total: all.length,
    mapped,
    percent: all.length ? Math.round((mapped / all.length) * 100) : 0,
    highTotal: highs.length,
    highMapped,
    highPercent: highs.length ? Math.round((highMapped / highs.length) * 100) : 100
  }
}
