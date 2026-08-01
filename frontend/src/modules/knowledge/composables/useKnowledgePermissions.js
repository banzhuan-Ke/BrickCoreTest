import { computed } from 'vue'
import { UserStore } from '@/stores/module/UserStore.js'

/** 迭代资料库权限：view 只读 / edit 管理 / execute 问答与报告生成 */
export function useKnowledgePermissions() {
  const u = UserStore()
  const canView = computed(() => u.hasPermission('knowledge:view'))
  const canEdit = computed(() => u.hasPermission('knowledge:edit'))
  const canExecute = computed(() => u.hasPermission('knowledge:execute'))
  /** 资料库内上传、解析、文件夹等管理操作（仅 edit，不含 execute） */
  const canManage = computed(() => canEdit.value)
  return { canView, canEdit, canExecute, canManage }
}
