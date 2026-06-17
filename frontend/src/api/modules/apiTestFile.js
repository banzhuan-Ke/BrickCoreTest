import http from '../request'

/**
 * 接口自动化测试文件（MinIO api-test-files，按项目隔离）
 */
export const apiTestFileApi = {
    async getList(params) {
        return await http.get('/api-module/files', { params })
    },
    async getDetail(fileId, projectId) {
        return await http.get(`/api-module/files/${fileId}`, { params: { project_id: projectId } })
    },
    async upload(projectId, file, onProgress) {
        const form = new FormData()
        form.append('file', file)
        return await http.post(`/api-module/files/upload?project_id=${projectId}`, form, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress: onProgress,
        })
    },
    async delete(fileId, projectId, force = false) {
        return await http.delete(`/api-module/files/${fileId}`, { params: { project_id: projectId, force } })
    },
    async getReferences(fileId, projectId) {
        return await http.get(`/api-module/files/${fileId}/references`, { params: { project_id: projectId } })
    },
    async getDownloadUrl(fileId, projectId) {
        return await http.get(`/api-module/files/${fileId}/download-url`, { params: { project_id: projectId } })
    },
    async getPreviewContent(fileId, projectId) {
        return await http.get(`/api-module/files/${fileId}/preview-content`, { params: { project_id: projectId } })
    },
}
