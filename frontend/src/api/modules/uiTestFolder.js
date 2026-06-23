import http from '../request'

/**
 * UI 自动化测试文件夹（MinIO ui-test-files，保留目录结构）
 */
export const uiTestFolderApi = {
    async getList(params) {
        return await http.get('/ui/folders', { params })
    },
    async getDetail(folderId, projectId) {
        return await http.get(`/ui/folders/${folderId}`, { params: { project_id: projectId } })
    },
    async upload(projectId, files, folderName = '', onProgress) {
        const form = new FormData()
        for (const file of files) {
            const relativePath = file.webkitRelativePath || file.name
            form.append('files', file, relativePath)
        }
        const query = new URLSearchParams({ project_id: String(projectId) })
        if (folderName) query.set('folder_name', folderName)
        return await http.post(`/ui/folders/upload?${query.toString()}`, form, {
            headers: { 'Content-Type': 'multipart/form-data' },
            onUploadProgress: onProgress,
            timeout: 600000,
        })
    },
    async delete(folderId, projectId, force = false) {
        return await http.delete(`/ui/folders/${folderId}`, { params: { project_id: projectId, force } })
    },
    async getReferences(folderId, projectId) {
        return await http.get(`/ui/folders/${folderId}/references`, { params: { project_id: projectId } })
    },
}
