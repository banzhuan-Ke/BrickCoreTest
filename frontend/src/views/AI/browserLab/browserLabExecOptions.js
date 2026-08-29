/** 智能浏览器执行/用例默认选项与说明文案 */

export const BROWSER_LAB_EXEC_DEFAULTS = {
  max_steps: 25,
  use_vision: true,
  generate_gif: true,
  enable_browser_restart: true,
  max_browser_restarts: 2,
  max_repeat_steps: 3,
  use_action_cache: true,
  force_refresh_cache: false,
  on_replay_fail: 'fallback_agent',
  env_id: null,
  run_mode: 'runner',
  device_id: null,
  headless: true,
}

export const BROWSER_LAB_EXEC_TIPS = {
  maxSteps: 'Agent 最多执行的推理步数（含点击、输入等）；复杂流程可适当加大，简单验证可减小以省 Token。',
  maxRepeat:
    '同一操作（如重复搜索、重复点击同一按钮）连续出现 N 步后自动停止，避免无效重试浪费 Token；换策略（如点编辑、读 DOM）不会计入同一操作。',
  restart:
    '截图/CDP 失败时重启浏览器 session 并从中断 URL 续跑；会丢失登录 Cookie，账号密码请用环境变量。',
  actionCache:
    '启用后：同任务二次执行优先按已固化动作零 Token 回放；页面变更导致回放失败时可降级 Agent（每任务最多 1 次）。登录请用 ${{password}} 并选择参考环境，明文密码不会写入缓存。缓存加速演示/调试，正式回归请「导入 Web 用例」。',
  forceRefresh: '忽略已有缓存，强制走 LLM 并覆盖写入新缓存。',
  env:
    '解析任务描述 / 起始 URL 中的 ${{变量}}；动作缓存回放按此环境注入账号密码，不把密文写入缓存。',
  summary: [
    'Vision：每步向模型发送页面截图，适合图标/复杂布局；DOM 够用时可关闭以提速省 Token。DeepSeek 会自动关闭 Vision。',
    '回放 GIF：任务结束后生成步骤回放；调试阶段可关闭以减轻截图压力。',
    'CDP 续跑：无头环境截图偶发失败时自动重启浏览器继续；续跑阶段不生成 GIF，最后一轮才生成。',
    '重复上限：仅限制「原地重复」；Agent 更换操作方式仍可继续，直到达到最大步数或完成任务。',
    '动作缓存：同任务复跑可零 Token；登录用 ${{变量}} + 参考环境。勿把缓存复跑当作 CI 主路径，进计划请导入 Web 用例。',
    '单模型：全程只用一个 LLM（须支持 function calling），与需求读图的双模型流水线不同。'
  ]
}

export function mergeBrowserLabExecForm(source = {}) {
  return {
    ...source,
    max_steps: source.max_steps ?? BROWSER_LAB_EXEC_DEFAULTS.max_steps,
    use_vision: source.use_vision !== false,
    generate_gif: source.generate_gif !== false,
    enable_browser_restart: source.enable_browser_restart !== false,
    max_browser_restarts: source.max_browser_restarts ?? BROWSER_LAB_EXEC_DEFAULTS.max_browser_restarts,
    max_repeat_steps: source.max_repeat_steps ?? BROWSER_LAB_EXEC_DEFAULTS.max_repeat_steps,
    use_action_cache: source.use_action_cache !== false,
    force_refresh_cache: !!source.force_refresh_cache,
    on_replay_fail: source.on_replay_fail || BROWSER_LAB_EXEC_DEFAULTS.on_replay_fail,
    env_id: source.env_id || source.config_json?.env_id || null,
    run_mode: source.run_mode || source.config_json?.run_mode || BROWSER_LAB_EXEC_DEFAULTS.run_mode,
    device_id: source.device_id || source.config_json?.device_id || null,
    headless: source.headless ?? source.config_json?.headless ?? BROWSER_LAB_EXEC_DEFAULTS.headless,
  }
}

export function browserLabExecConfigPayload(form) {
  return {
    max_steps: form.max_steps,
    use_vision: form.use_vision,
    generate_gif: form.generate_gif,
    enable_browser_restart: form.enable_browser_restart,
    max_browser_restarts: form.enable_browser_restart ? form.max_browser_restarts : 0,
    max_repeat_steps: form.max_repeat_steps,
    use_action_cache: form.use_action_cache !== false,
    force_refresh_cache: !!form.force_refresh_cache,
    on_replay_fail: form.on_replay_fail || 'fallback_agent',
    env_id: form.env_id || null,
    run_mode: form.run_mode || 'runner',
    device_id: form.run_mode === 'runner' ? (form.device_id || null) : null,
    headless: form.headless !== false,
  }
}

export function cacheStatusLabel(status) {
  return (
    {
      cache_hit: '缓存命中',
      cache_miss: '缓存未命中',
      cache_written: '已写入缓存',
      cache_refreshed: '回放失败已刷新',
      cache_replay_failed: '回放失败已降级',
      cache_expired: '缓存已超期',
      cache_stale: '缓存已失效',
      schema_mismatch: '缓存版本不兼容',
      cache_missing_vars: '缺少变量未命中',
      force_refresh: '强制刷新',
      stopped: '回放已停止',
      disabled: '缓存关闭'
    }[status] || status || '-'
  )
}

export function cacheStatusTag(status) {
  return (
    {
      cache_hit: 'success',
      cache_miss: 'info',
      cache_written: 'success',
      cache_refreshed: 'warning',
      cache_replay_failed: 'warning',
      cache_expired: 'warning',
      cache_stale: 'warning',
      schema_mismatch: 'warning',
      cache_missing_vars: 'warning',
      force_refresh: 'warning',
      stopped: 'info',
      disabled: 'info'
    }[status] || 'info'
  )
}
