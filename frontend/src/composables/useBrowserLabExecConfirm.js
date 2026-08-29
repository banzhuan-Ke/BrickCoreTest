import { shallowRef } from 'vue'

const dialogRef = shallowRef(null)

/** 在 BrowserLabLayout 挂载 BrowserLabExecConfirmDialog 后注册 */
export function registerBrowserLabExecConfirmDialog(inst) {
  dialogRef.value = inst
}

/**
 * 打开执行确认弹窗
 * @returns {Promise<{ device_id: string, execForm: object } | null>}
 */
export function openBrowserLabExecConfirm(context) {
  if (!dialogRef.value?.open) {
    return Promise.reject(new Error('执行确认弹窗未就绪'))
  }
  return dialogRef.value.open(context)
}
