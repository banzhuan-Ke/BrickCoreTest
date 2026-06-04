import http from '../request'

/**
 * API Token 授权管理
 */
export const httpAuthConfigApi = {
    async getList(params) {
        return await http.get('/api-module/auth-config', { params })
    },
    async create(data) {
        return await http.post('/api-module/auth-config', data)
    },
    async getDetail(configId, projectId) {
        return await http.get(`/api-module/auth-config/${configId}`, { params: { project_id: projectId } })
    },
    async update(configId, data, projectId) {
        return await http.put(`/api-module/auth-config/${configId}`, data, { params: { project_id: projectId } })
    },
    async delete(configId, projectId) {
        return await http.delete(`/api-module/auth-config/${configId}`, { params: { project_id: projectId } })
    },
    async refresh(configId, projectId) {
        return await http.post(`/api-module/auth-config/${configId}/refresh`, null, { params: { project_id: projectId } })
    },
    async clearCache(configId, projectId) {
        return await http.post(`/api-module/auth-config/${configId}/clear-cache`, null, { params: { project_id: projectId } })
    },
    async getCustomCodeTemplate() {
        return await http.get('/api-module/auth-config/template/custom-code')
    },
    async testPreview(data) {
        return await http.post('/api-module/auth-config/test-preview', data, {
            timeout: 35000
        })
    }
}
