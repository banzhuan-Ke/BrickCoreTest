/**
 * 根据当前路由构建平台助手 page_context（C-1 页面上下文感知）
 */
function parseId(value) {
  if (value == null || value === '') return null
  const n = parseInt(String(value), 10)
  return Number.isFinite(n) && n > 0 ? n : null
}

export function buildAssistantPageContext(route) {
  if (!route?.name) return null

  const ctx = {
    page: route.name,
    page_label: route.meta?.title || route.name
  }
  const p = route.params || {}
  const q = route.query || {}

  switch (route.name) {
    case 'apiSuiteDetail':
      ctx.suite_id = parseId(p.suiteId)
      break
    case 'apiPlanEdit':
      ctx.plan_id = parseId(p.planId)
      ctx.page_hint = 'api_plans'
      break
    case 'editCase':
      ctx.ui_case_id = parseId(p.id)
      break
    case 'editTask':
      ctx.task_id = parseId(p.id)
      break
    case 'editSuite':
      ctx.ui_suite_id = parseId(p.id)
      ctx.page_hint = 'ui_suites'
      break
    case 'apiReport':
      ctx.api_run_record_id = parseId(p.recordId)
      break
    case 'suiteReport':
      ctx.ui_suite_run_id = parseId(p.id)
      break
    case 'taskReport':
      ctx.ui_task_run_id = parseId(p.id)
      break
    case 'perfSceneEdit':
      ctx.perf_scene_id = parseId(p.id)
      ctx.page_hint = 'perf_scenes'
      break
    case 'perfReport':
      ctx.perf_record_id = parseId(p.recordId)
      break
    case 'apiModule':
      ctx.page_hint = 'api_definitions'
      break
    case 'apiCase':
      ctx.page_hint = 'api_test_cases'
      break
    case 'apiSuite':
      ctx.page_hint = 'api_suites'
      break
    case 'apiRunRecords':
      ctx.page_hint = 'api_run_records'
      break
    case 'apiPlan':
      ctx.page_hint = 'api_plans'
      break
    case 'apiMock':
      ctx.page_hint = 'mock_apis'
      break
    case 'apiDataFactory':
      ctx.page_hint = 'data_factory'
      break
    case 'apiCron':
      ctx.page_hint = 'cron_jobs'
      break
    case 'aiRequirements':
    case 'aiTestAnalysis':
      ctx.page_hint = 'requirements'
      break
    case 'aiFunctionalCases':
      ctx.page_hint = 'functional_cases'
      break
    case 'aiQaEval':
      ctx.page_hint = 'qa_eval'
      break
    case 'caseList':
    case 'taskList':
      ctx.page_hint = 'ui_cases'
      break
    case 'suiteList':
    case 'addSuite':
      ctx.page_hint = 'ui_suites'
      break
    case 'recordList':
      ctx.page_hint = 'ui_run_records'
      break
    case 'cronjob':
      ctx.page_hint = 'cron_jobs'
      break
    case 'device':
      ctx.page_hint = 'online_devices'
      break
    case 'perfSceneList':
    case 'perfSceneAdd':
      ctx.page_hint = 'perf_scenes'
      break
    case 'perfRecordList':
      ctx.page_hint = 'perf_scenes'
      break
    case 'perfCronJobs':
      ctx.page_hint = 'cron_jobs'
      break
    case 'perfWorkerList':
      ctx.page_hint = 'perf_workers'
      break
    default:
      break
  }

  // 通用 query 参数（部分页面可能带 id）
  if (!ctx.api_id && q.api_id) ctx.api_id = parseId(q.api_id)
  if (!ctx.requirement_id && q.requirement_id) ctx.requirement_id = parseId(q.requirement_id)
  if (!ctx.requirement_id && q.req_id) ctx.requirement_id = parseId(q.req_id)
  if (!ctx.suite_id && q.suite_id) ctx.suite_id = parseId(q.suite_id)
  if (!ctx.task_id && q.task_id) ctx.task_id = parseId(q.task_id)
  if (!ctx.template_id && q.template_id) ctx.template_id = parseId(q.template_id)
  if (!ctx.datasource_id && q.datasource_id) ctx.datasource_id = parseId(q.datasource_id)

  return ctx
}

export function formatPageContextLabel(ctx) {
  if (!ctx?.page_label) return ''
  const parts = [ctx.page_label]
  if (ctx.api_id) parts.push(`接口#${ctx.api_id}`)
  if (ctx.suite_id) parts.push(`套件#${ctx.suite_id}`)
  if (ctx.plan_id) parts.push(`计划#${ctx.plan_id}`)
  if (ctx.requirement_id) parts.push(`需求#${ctx.requirement_id}`)
  if (ctx.task_id) parts.push(`UI计划#${ctx.task_id}`)
  if (ctx.ui_case_id) parts.push(`用例#${ctx.ui_case_id}`)
  if (ctx.ui_suite_id) parts.push(`UI套件#${ctx.ui_suite_id}`)
  if (ctx.api_run_record_id) parts.push(`执行记录#${ctx.api_run_record_id}`)
  if (ctx.perf_scene_id) parts.push(`压测场景#${ctx.perf_scene_id}`)
  if (ctx.template_id) parts.push(`SQL模板#${ctx.template_id}`)
  if (ctx.datasource_id) parts.push(`数据源#${ctx.datasource_id}`)
  return parts.join(' · ')
}
