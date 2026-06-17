import http from '../request'

/**
 * UI 自动化测试文件（MinIO ui-test-files）
 */
export const uiTestFileApi = {
    async getList(params) {
        return await http.get('/ui/files', { params })
    },
    async getDetail(fileId, projectId) {
        return await http.get(`/ui/files/${fileId}`, { params: { project_id: projectId } })
    },
    async upload(projectId, file, onProgress) {
        const form = new FormData()
        form.append('file', file)
        return await http.post(`/ui/files/upload?project_id=${projectId}`, form, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress: onProgress,
        })
    },
    async delete(fileId, projectId, force = false) {
        return await http.delete(`/ui/files/${fileId}`, { params: { project_id: projectId, force } })
    },
    async getReferences(fileId, projectId) {
        return await http.get(`/ui/files/${fileId}/references`, { params: { project_id: projectId } })
    },
    async getDownloadUrl(fileId, projectId) {
        return await http.get(`/ui/files/${fileId}/download-url`, { params: { project_id: projectId } })
    },
    async getPreviewContent(fileId, projectId) {
        return await http.get(`/ui/files/${fileId}/preview-content`, { params: { project_id: projectId } })
    },
    async migrationScan(projectId) {
        return await http.get('/ui/files/migration-scan', { params: { project_id: projectId } })
    },
}
