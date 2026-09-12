/**
 * 加载项目 CSV 数据集列，供 VarInsertButton.extraGroups 插入 ${{csv.列名}}
 */
import { ref, watch } from 'vue'
import { perfCsvDatasetApi } from '@/api/modules/perf'

export function useCsvInsertGroups(projectIdRef) {
  const csvExtraGroups = ref([])
  const loading = ref(false)

  async function reload() {
    const pid = Number(typeof projectIdRef === 'function' ? projectIdRef() : projectIdRef?.value ?? projectIdRef)
    if (!pid) {
      csvExtraGroups.value = []
      return
    }
    loading.value = true
    try {
      const res = await perfCsvDatasetApi.getList({ project_id: pid })
      const raw = res?.data || res || {}
      const list = raw.data || []
      const groups = []
      for (const ds of list) {
        const cols = ds.columns || []
        if (!cols.length) continue
        groups.push({
          group: `CSV · ${ds.name}`,
          items: cols.map((col) => ({
            key: `csv.${col}`,
            preview: ds.file_name || '',
            description: `数据集 #${ds.id} · ${ds.row_count || 0} 行`,
          })),
        })
      }
      csvExtraGroups.value = groups
    } catch {
      csvExtraGroups.value = []
    } finally {
      loading.value = false
    }
  }

  watch(
    () => (typeof projectIdRef === 'function' ? projectIdRef() : projectIdRef?.value ?? projectIdRef),
    () => {
      reload()
    },
    { immediate: true }
  )

  return { csvExtraGroups, csvGroupsLoading: loading, reloadCsvGroups: reload }
}
