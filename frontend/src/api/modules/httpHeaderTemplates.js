import http from '../request'

/**
 * Header 模板管理
 */
export const httpHeaderTemplatesApi = {
  async getList(params) {
    return await http.get('/api-module/header-templates', { params })
  },
  async getOptions(projectId) {
    return await http.get('/api-module/header-templates/options', { params: { project_id: projectId } })
  },
  async getDetail(templateId, projectId) {
    return await http.get(`/api-module/header-templates/${templateId}`, { params: { project_id: projectId } })
  },
  async create(data) {
    return await http.post('/api-module/header-templates', data)
  },
  async update(templateId, data, projectId) {
    return await http.put(`/api-module/header-templates/${templateId}`, data, { params: { project_id: projectId } })
  },
  async delete(templateId, projectId) {
    return await http.delete(`/api-module/header-templates/${templateId}`, { params: { project_id: projectId } })
  },
  async setDefault(templateId, projectId) {
    return await http.post(`/api-module/header-templates/${templateId}/set-default`, null, {
      params: { project_id: projectId },
    })
  },
  async previewImport(data) {
    return await http.post('/api-module/header-templates/preview-import', data)
  },
}
