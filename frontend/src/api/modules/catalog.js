import http from '../request'

/**
 * 统一测试目录 API
 * 对应后端 /sys/catalogs 接口
 */
export const catalogApi = {
    async getList(params = {}) {
        return await http.get('/sys/catalogs', { params })
    },
    async create(data) {
        return await http.post('/sys/catalogs', data)
    },
    async update(catalog_id, data) {
        return await http.put(`/sys/catalogs/${catalog_id}`, data)
    },
    async delete(catalog_id, params = {}) {
        return await http.delete(`/sys/catalogs/${catalog_id}`, { params })
    },
    async getDetail(catalog_id) {
        return await http.get(`/sys/catalogs/${catalog_id}`)
    },
    async getAssets(catalog_id, params = {}) {
        return await http.get(`/sys/catalogs/${catalog_id}/assets`, { params })
    },

    // ===== 兼容命名 =====
    getCatalogList(params) { return this.getList(params) },
    createCatalog(data) { return this.create(data) },
    updateCatalog(catalog_id, data) { return this.update(catalog_id, data) },
    deleteCatalog(catalog_id, params) { return this.delete(catalog_id, params) },
    getCatalogDetail(catalog_id) { return this.getDetail(catalog_id) }
}

/** 将扁平目录列表构建为树 */
export function buildCatalogTree(items, parentId = null) {
    if (!Array.isArray(items)) return []
    return items
        .filter(item => (item.parent_id ?? null) === parentId)
        .map(item => ({
            ...item,
            children: buildCatalogTree(items, item.id)
        }))
        .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
}

/** 收集某目录及其所有子孙目录 id */
export function collectCatalogSubtreeIds(items, rootId) {
    if (!rootId || !Array.isArray(items)) return new Set()
    const byParent = new Map()
    for (const item of items) {
        const pid = item.parent_id ?? null
        if (!byParent.has(pid)) byParent.set(pid, [])
        byParent.get(pid).push(item.id)
    }
    const ids = new Set()
    const walk = (id) => {
        ids.add(id)
        for (const childId of byParent.get(id) || []) walk(childId)
    }
    walk(rootId)
    return ids
}

/** 递归扁平化目录树（跳过 id 为 all 的节点） */
export function flattenCatalogTree(nodes, result = []) {
    if (!Array.isArray(nodes)) return result
    for (const node of nodes) {
        if (node.id !== 'all') {
            result.push(node)
        }
        if (node.children?.length) {
            flattenCatalogTree(node.children, result)
        }
    }
    return result
}
