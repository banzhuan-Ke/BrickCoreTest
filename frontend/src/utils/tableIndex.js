import { unref } from 'vue'

/** Element Plus 分页表格序号：(page - 1) * size + index + 1 */
export function paginatedTableIndex(index, page, size) {
  const p = Number(unref(page)) || 1
  const s = Number(unref(size)) || 10
  return (p - 1) * s + index + 1
}

/** 绑定 reactive 分页对象（含 page、size 字段） */
export function makeTableRowIndex(pageState) {
  return (index) => paginatedTableIndex(index, pageState.page, pageState.size)
}

/** 绑定 page / size 的 ref 或 reactive */
export function makeTableRowIndexRefs(pageRef, sizeRef) {
  return (index) => paginatedTableIndex(index, pageRef, sizeRef)
}
