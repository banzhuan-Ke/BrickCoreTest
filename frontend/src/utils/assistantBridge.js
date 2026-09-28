/**
 * 小测对外桥：其它页面（如技能清单「快速使用」）打开面板并启动 Skill / Chip。
 * 不直接 skills/run 落库，统一走 Chip 直出表单或约定话术。
 */
export const ASSISTANT_OPEN_SKILL_EVENT = 'brickcore:assistant-open-skill'

/**
 * @param {{ skillCode: string, skillName?: string }} payload
 */
export function openAssistantSkill(payload) {
  if (typeof window === 'undefined') return
  const skillCode = String(payload?.skillCode || '').trim()
  if (!skillCode) return
  window.dispatchEvent(
    new CustomEvent(ASSISTANT_OPEN_SKILL_EVENT, {
      detail: {
        skillCode,
        skillName: payload?.skillName || ''
      }
    })
  )
}
