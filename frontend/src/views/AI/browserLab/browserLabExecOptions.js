/** 智能浏览器执行/用例默认选项与说明文案 */

export const BROWSER_LAB_EXEC_DEFAULTS = {
  max_steps: 25,
  use_vision: true,
  generate_gif: true,
  enable_browser_restart: true,
  max_browser_restarts: 2,
  max_repeat_steps: 3
}

export const BROWSER_LAB_EXEC_TIPS = {
  maxSteps: 'Agent 最多执行的推理步数（含点击、输入等）；复杂流程可适当加大，简单验证可减小以省 Token。',
  maxRepeat:
    '同一操作（如重复搜索、重复点击同一按钮）连续出现 N 步后自动停止，避免无效重试浪费 Token；换策略（如点编辑、读 DOM）不会计入同一操作。',
  restart:
    '截图/CDP 失败时重启浏览器 session 并从中断 URL 续跑；会丢失登录 Cookie，任务描述宜含账号密码。',
  summary: [
    'Vision：每步向模型发送页面截图，适合图标/复杂布局；DOM 够用时可关闭以提速省 Token。DeepSeek 会自动关闭 Vision。',
    '回放 GIF：任务结束后生成步骤回放；调试阶段可关闭以减轻截图压力。',
    'CDP 续跑：无头环境截图偶发失败时自动重启浏览器继续；续跑阶段不生成 GIF，最后一轮才生成。',
    '重复上限：仅限制「原地重复」；Agent 更换操作方式仍可继续，直到达到最大步数或完成任务。',
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
    max_repeat_steps: source.max_repeat_steps ?? BROWSER_LAB_EXEC_DEFAULTS.max_repeat_steps
  }
}

export function browserLabExecConfigPayload(form) {
  return {
    max_steps: form.max_steps,
    use_vision: form.use_vision,
    generate_gif: form.generate_gif,
    enable_browser_restart: form.enable_browser_restart,
    max_browser_restarts: form.enable_browser_restart ? form.max_browser_restarts : 0,
    max_repeat_steps: form.max_repeat_steps
  }
}
