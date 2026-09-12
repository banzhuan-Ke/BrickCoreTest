/**
 * Element Plus 表格全局默认：开启边框以支持表头拖拽调列宽。
 * 须在 app.use(ElementPlus) 之前调用。
 */
import { ElTable } from 'element-plus'

export function applyElementPlusDefaults() {
  ElTable.props.border = { type: Boolean, default: true }
}
