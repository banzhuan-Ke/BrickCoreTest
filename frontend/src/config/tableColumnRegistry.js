/**
 * 全站列表页列配置注册表
 * pageId 唯一；version 变更时自动合并用户已存偏好
 */

function col(key, label, opts = {}) {
  return { key, label, ...opts }
}

/** @type {Record<string, { pageId: string, version: number, columns: object[], defaultVisible: string[] }>} */
export const TABLE_COLUMN_REGISTRY = {
  'ai.functional_cases': {
    pageId: 'ai.functional_cases',
    version: 2,
    columns: [
      col('id', 'ID', { width: 70, required: true }),
      col('zentao_case_id_display', '禅道ID', { width: 88 }),
      col('product', '所属产品', { width: 110, prop: 'product' }),
      col('module', '所属模块', { width: 130, prop: 'module' }),
      col('related_story', '关联需求', { minWidth: 140, prop: 'related_story' }),
      col('title', '用例标题', { minWidth: 220, required: true, prop: 'title' }),
      col('precondition', '前置条件', { minWidth: 140, prop: 'precondition' }),
      col('steps_text', '步骤', { minWidth: 200 }),
      col('expects_text', '预期', { minWidth: 200 }),
      col('priority', '优先级', { width: 72, prop: 'priority', align: 'center' }),
      col('type', '用例类型', { width: 96, prop: 'type' }),
      col('stage', '适用阶段', { width: 120, prop: 'stage' }),
      col('source_type', '来源', { width: 100 }),
      col('ui_import_status', 'UI自动化', { width: 96, align: 'center' }),
      col('create_by', '创建人', { width: 88, prop: 'create_by' }),
      col('update_by', '修改人', { width: 88 }),
      col('create_time', '创建时间', { width: 168, prop: 'create_time' }),
      col('update_time', '更新时间', { width: 168, prop: 'update_time' })
    ],
    defaultVisible: [
      'id', 'zentao_case_id_display', 'product', 'module', 'related_story', 'title',
      'priority', 'source_type', 'ui_import_status', 'create_by', 'update_by', 'create_time'
    ]
  },

  'ai.requirements.list': {
    pageId: 'ai.requirements.list',
    version: 1,
    columns: [
      col('id', 'ID', { width: 70, required: true, prop: 'id' }),
      col('name', '需求名称', { minWidth: 160, required: true, prop: 'name' }),
      col('source_type', '类型', { width: 80 }),
      col('image_count', '图片', { width: 70, align: 'center', prop: 'image_count' }),
      col('case_count', '用例数', { width: 80, align: 'center', prop: 'case_count' }),
      col('parse_status', '状态', { width: 90 }),
      col('create_time', '创建时间', { width: 170, prop: 'create_time' })
    ],
    defaultVisible: ['id', 'name', 'source_type', 'image_count', 'case_count', 'parse_status', 'create_time']
  },

  'api.cases': {
    pageId: 'api.cases',
    version: 2,
    columns: [
      col('index', '序号', { width: 60, required: true }),
      col('name', '用例名称', { minWidth: 170, required: true }),
      col('priority', '优先级', { width: 80 }),
      col('api_info', '关联接口', { minWidth: 220 }),
      col('assertions', '断言数', { width: 80 }),
      col('request_override', '请求覆盖', { width: 130 }),
      col('catalog_name', '所属目录', { width: 120 }),
      col('create_by', '创建人', { width: 100 }),
      col('update_by', '修改人', { width: 100 }),
      col('update_time', '更新时间', { width: 150 })
    ],
    defaultVisible: ['index', 'name', 'priority', 'api_info', 'assertions', 'request_override', 'catalog_name', 'update_time']
  },

  'api.list': {
    pageId: 'api.list',
    version: 1,
    columns: [
      col('index', '序号', { width: 60, required: true }),
      col('name', '接口名称', { minWidth: 140, required: true, prop: 'name' }),
      col('method', '方法', { width: 80 }),
      col('path', '路径', { minWidth: 200, prop: 'path' }),
      col('catalog_name', '目录', { width: 120 }),
      col('version', '版本', { width: 70 }),
      col('update_time', '修改时间', { width: 168, prop: 'update_time' })
    ],
    defaultVisible: ['index', 'name', 'method', 'path', 'catalog_name', 'version', 'update_time']
  },

  'api.plans': {
    pageId: 'api.plans',
    version: 1,
    columns: [
      col('index', '序号', { width: 60, required: true }),
      col('name', '计划名称', { minWidth: 150, required: true }),
      col('catalog_name', '所属目录', { width: 120 }),
      col('item_count', '条目', { width: 110, align: 'center' }),
      col('parallel', '执行模式', { width: 100, align: 'center' }),
      col('env_name', '默认环境', { width: 130 }),
      col('last_run', '最近执行', { width: 150, align: 'center' }),
      col('run_count', '执行次数', { width: 88, align: 'center' }),
      col('cron_jobs', '定时任务', { width: 88, align: 'center' }),
      col('description', '描述', { minWidth: 180 }),
      col('create_by', '创建人', { width: 100, prop: 'create_by' }),
      col('update_by', '修改人', { width: 100 }),
      col('create_time', '创建时间', { width: 160 })
    ],
    defaultVisible: ['index', 'name', 'catalog_name', 'item_count', 'parallel', 'env_name', 'last_run', 'create_by']
  },

  'api.suites': {
    pageId: 'api.suites',
    version: 1,
    columns: [
      col('index', '序号', { width: 60, required: true }),
      col('name', '套件名称', { minWidth: 150, required: true, prop: 'name' }),
      col('catalog_name', '所属目录', { width: 120 }),
      col('case_count', '用例数', { width: 90, align: 'center' }),
      col('update_time', '修改时间', { width: 168, prop: 'update_time' })
    ],
    defaultVisible: ['index', 'name', 'catalog_name', 'case_count', 'update_time']
  },

  'api.run_records': {
    pageId: 'api.run_records',
    version: 2,
    columns: [
      col('index', '序号', { width: 50, required: true }),
      col('record_type', '类型', { width: 80 }),
      col('name', '名称', { minWidth: 150, required: true, prop: 'name' }),
      col('status', '执行状态', { width: 100 }),
      col('trigger_type', '触发方式', { width: 100 }),
      col('case_stats', '用例统计', { width: 200 }),
      col('env_name', '执行环境', { width: 120, prop: 'env_name' }),
      col('start_time', '开始时间', { width: 160 }),
      col('duration', '执行总耗时(ms)', { width: 120 }),
      col('http_duration', '接口总耗时(ms)', { width: 120 }),
      col('run_by', '执行人', { width: 100 })
    ],
    defaultVisible: ['index', 'record_type', 'name', 'status', 'case_stats', 'env_name', 'start_time', 'duration', 'run_by']
  },

  'api.cron_jobs': {
    pageId: 'api.cron_jobs',
    version: 1,
    columns: [
      col('index', '序号', { width: 50, required: true }),
      col('name', '任务名称', { minWidth: 150, required: true, prop: 'name' }),
      col('target', '执行目标', { minWidth: 160 }),
      col('run_type', '执行类型', { width: 100 }),
      col('schedule', '执行计划', { minWidth: 150 }),
      col('state', '状态', { width: 80 }),
      col('last_run', '最近执行', { width: 130 }),
      col('create_by', '创建人', { width: 100, prop: 'create_by' }),
      col('update_by', '修改人', { width: 100 }),
      col('create_time', '创建时间', { width: 160 })
    ],
    defaultVisible: ['index', 'name', 'target', 'run_type', 'schedule', 'state', 'last_run', 'create_by']
  },

  'ui.cases': {
    pageId: 'ui.cases',
    version: 2,
    columns: [
      col('index', '序号', { width: 70, required: true }),
      col('name', '用例名称', { minWidth: 160, required: true, prop: 'name' }),
      col('run_count', '运行次数'),
      col('status', '最近运行结果', { width: 120 }),
      col('step_count', '步骤数'),
      col('username', '创建人'),
      col('level', '用例级别', { width: 100 }),
      col('source_functional_case', '来源功能用例', { minWidth: 160 }),
      col('create_time', '创建时间', { width: 180 }),
      col('update_time', '更新时间', { minWidth: 180, prop: 'update_time' })
    ],
    defaultVisible: ['index', 'name', 'run_count', 'status', 'step_count', 'level', 'update_time']
  },

  'ui.suites': {
    pageId: 'ui.suites',
    version: 2,
    columns: [
      col('index', '序号', { width: 80, required: true }),
      col('name', '套件名称', { minWidth: 160, required: true, prop: 'name' }),
      col('suite_type', '套件类型', { width: 100 }),
      col('catalog_name', '所属目录', { width: 120 }),
      col('suite_step_count', '前置步骤', { width: 100 }),
      col('case_count', '用例数', { width: 100 }),
      col('run_count', '执行次数', { width: 100 }),
      col('status', '状态', { width: 120 }),
      col('username', '创建人', { width: 100 }),
      col('create_time', '创建时间', { width: 160 })
    ],
    defaultVisible: ['index', 'name', 'suite_type', 'catalog_name', 'case_count', 'run_count', 'status', 'username', 'create_time']
  },

  'execution.records': {
    pageId: 'execution.records',
    version: 2,
    columns: [
      col('index', '序号', { width: 70, required: true }),
      col('name', '名称', { minWidth: 160, required: true }),
      col('browser_type', '浏览器'),
      col('base_url', 'Base_url', { minWidth: 100 }),
      col('status', '执行状态', { width: 100 }),
      col('case_count', '用例总数'),
      col('success', '成功'),
      col('fail', '失败'),
      col('error', '错误'),
      col('skip', '跳过'),
      col('no_run', '未运行'),
      col('pass_rate', '通过率', { minWidth: 100 }),
      col('username', '执行人'),
      col('run_time', '执行时间', { minWidth: 150 }),
      col('duration', '执行耗时')
    ],
    defaultVisible: ['index', 'name', 'browser_type', 'base_url', 'status', 'case_count', 'success', 'fail', 'pass_rate', 'username', 'run_time', 'duration']
  },

  'perf.scenes': {
    pageId: 'perf.scenes',
    version: 1,
    columns: [
      col('index', '序号', { width: 60, required: true }),
      col('name', '场景名称', { minWidth: 160, required: true, prop: 'name' }),
      col('mode', '模式', { width: 100 }),
      col('concurrency', '并发', { width: 80, align: 'center' }),
      col('update_time', '修改时间', { width: 168, prop: 'update_time' })
    ],
    defaultVisible: ['index', 'name', 'mode', 'concurrency', 'update_time']
  },

  'perf.records': {
    pageId: 'perf.records',
    version: 1,
    columns: [
      col('scene_name', '场景', { minWidth: 140, required: true }),
      col('status', '状态', { width: 90 }),
      col('tps', 'TPS', { width: 90 }),
      col('duration', '耗时', { width: 100 }),
      col('run_time', '执行时间', { width: 168 })
    ],
    defaultVisible: ['scene_name', 'status', 'tps', 'duration', 'run_time']
  },

  'perf.cron_jobs': {
    pageId: 'perf.cron_jobs',
    version: 1,
    columns: [
      col('index', '序号', { width: 50, required: true }),
      col('name', '任务名称', { minWidth: 150, required: true, prop: 'name' }),
      col('target', '执行目标', { minWidth: 160 }),
      col('schedule', '执行计划', { minWidth: 150 }),
      col('state', '状态', { width: 80 }),
      col('last_run', '最近执行', { width: 130 })
    ],
    defaultVisible: ['index', 'name', 'target', 'schedule', 'state', 'last_run']
  },

  'project.list': {
    pageId: 'project.list',
    version: 1,
    columns: [
      col('index', '序号', { width: 90, required: true }),
      col('name', '项目名称', { minWidth: 160, required: true, prop: 'name' }),
      col('username', '创建人', { width: 100, prop: 'username' }),
      col('my_role', '我的角色', { width: 110 }),
      col('create_time', '创建时间', { width: 168 }),
      col('update_time', '更新时间', { width: 168 })
    ],
    defaultVisible: ['index', 'name', 'username', 'my_role', 'create_time', 'update_time']
  },

  'operation.log': {
    pageId: 'operation.log',
    version: 1,
    columns: [
      col('index', '序号', { width: 70, required: true }),
      col('username', '操作人', { width: 120, prop: 'username' }),
      col('action', '操作行为', { width: 140, prop: 'action' }),
      col('module', '所属模块', { width: 110, prop: 'module' }),
      col('path_name', '路径名称', { minWidth: 160, prop: 'path_name' }),
      col('method_path', '请求方法/路径', { minWidth: 200 }),
      col('status_code', '状态码', { width: 90 }),
      col('ip', 'IP地址', { width: 130, prop: 'ip' }),
      col('create_time', '操作时间', { width: 170, required: true, prop: 'create_time' }),
      col('params', '参数', { width: 80 })
    ],
    defaultVisible: ['index', 'username', 'action', 'module', 'path_name', 'method_path', 'status_code', 'ip', 'create_time']
  },

  'device.runners': {
    pageId: 'device.runners',
    version: 1,
    columns: [
      col('name', '名称', { minWidth: 140, required: true, prop: 'name' }),
      col('status', '状态', { width: 90 }),
      col('version', '版本', { width: 100 }),
      col('last_heartbeat', '最近心跳', { width: 168 })
    ],
    defaultVisible: ['name', 'status', 'version', 'last_heartbeat']
  }
}

export function getTableColumnPageConfig(pageId) {
  return TABLE_COLUMN_REGISTRY[pageId] || null
}

export function getDefaultColumnState(pageId) {
  const cfg = getTableColumnPageConfig(pageId)
  if (!cfg) return { version: 0, order: [], visible: [] }
  const allKeys = cfg.columns.map(c => c.key)
  const visibleSet = new Set(cfg.defaultVisible)
  const order = [
    ...cfg.defaultVisible,
    ...allKeys.filter(k => !visibleSet.has(k))
  ]
  return {
    version: cfg.version,
    order,
    visible: [...cfg.defaultVisible]
  }
}
