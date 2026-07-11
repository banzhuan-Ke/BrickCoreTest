function ok(data = {}) {
  return Promise.resolve({ data: { code: 200, data, items: Array.isArray(data) ? data : [] }, message: 'CE unavailable' })
}
export const knowledgeApi = {
  listFolders() {
    return ok([])
  },
  listDocuments() {
    return ok({ total: 0, list: [] })
  },
  getMeta() {
    return ok({ enabled: false })
  },
  archiveFromText() {
    return Promise.reject(new Error('CE ?????????????'))
  },
  archiveFromRequirement() {
    return Promise.reject(new Error('CE ?????????????'))
  },
  estimateRefs() {
    return ok({ refs: [], count: 0 })
  },
  retrieve() {
    return ok({ items: [] })
  },
  ask() {
    return Promise.reject(new Error('CE ?????????????'))
  }
}
