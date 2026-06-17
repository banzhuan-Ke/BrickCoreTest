import http from '../request'

export const docsApi = {
    getCatalog() {
        return http.get('/sys/docs/catalog')
    },
    getBuiltin(docId) {
        return http.get(`/sys/docs/builtin/${docId}`)
    },
    updateBuiltin(entryId, data) {
        return http.put(`/sys/docs/builtin/${entryId}`, data)
    },
    deleteBuiltin(entryId) {
        return http.delete(`/sys/docs/builtin/${entryId}`)
    },
    restoreBuiltin(entryId) {
        return http.post(`/sys/docs/builtin/${entryId}/restore`)
    },
    syncBuiltinFromFiles() {
        return http.post('/sys/docs/builtin/sync-from-files')
    },
    listManage() {
        return http.get('/sys/docs/manage')
    },
    getArticle(docId) {
        return http.get(`/sys/docs/articles/${docId}`)
    },
    listArticles(params = {}) {
        return http.get('/sys/docs/articles', { params })
    },
    createArticle(data) {
        return http.post('/sys/docs/articles', data)
    },
    updateArticle(docId, data) {
        return http.put(`/sys/docs/articles/${docId}`, data)
    },
    deleteArticle(docId) {
        return http.delete(`/sys/docs/articles/${docId}`)
    },
    uploadFile(file, onProgress) {
        const form = new FormData()
        form.append('file', file)
        return http.post('/sys/docs/upload', form, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress: onProgress
        })
    }
}
