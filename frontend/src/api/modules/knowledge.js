import http from '../request'

/** 资料库上传（解析已异步，仅等待上传） */
const KNOWLEDGE_UPLOAD_TIMEOUT_MS = 120000
/** 入队类操作（解析/索引/摘要后台任务），接口应快速返回 */
const KNOWLEDGE_QUEUE_TIMEOUT_MS = 30000
/** 重新解析等仍可能较慢的同步入口 */
const KNOWLEDGE_PARSE_TIMEOUT_MS = 180000
/** 列表/轮询（索引进行中后端可能短暂繁忙） */
const KNOWLEDGE_LIST_TIMEOUT_MS = 60000
/** 质量回顾 PPT / Bug 工作簿等较大文件下载 */
const KNOWLEDGE_DOWNLOAD_TIMEOUT_MS = 180000

function unwrap(res) {
    const body = res?.data
    if (body?.code === 200) {
        return { data: body.data, message: body.message || 'success' }
    }
    const detail = body?.detail || body?.message || '请求失败'
    throw new Error(typeof detail === 'string' ? detail : '请求失败')
}

function unwrapBlob(res, label = '下载') {
    if (res?.status >= 200 && res?.status < 300 && res.data instanceof Blob) {
        return res.data
    }
    throw new Error(`${label}失败`)
}

/**
 * 迭代测试资料库 API（/ai/knowledge）
 * 统一解包 StandardResponse，返回 { data, message } 或 Blob
 */
export const knowledgeApi = {
    async getMeta() {
        return unwrap(await http.get('/ai/knowledge/meta'))
    },
    async getSettings(projectId) {
        return unwrap(await http.get('/ai/knowledge/settings', {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async updateSettings(data, projectId) {
        return unwrap(await http.put('/ai/knowledge/settings', data, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async updateDocumentEmbedMode(docId, embedMode, projectId) {
        return unwrap(await http.put(`/ai/knowledge/documents/${docId}/embed-mode`, { embed_mode: embedMode }, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async reindexDocumentRag(docId, projectId) {
        return unwrap(await http.post(`/ai/knowledge/documents/${docId}/reindex-rag`, null, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: KNOWLEDGE_QUEUE_TIMEOUT_MS
        }))
    },
    async reindexDocumentVector(docId, projectId) {
        return unwrap(await http.post(`/ai/knowledge/documents/${docId}/reindex-vector`, null, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: KNOWLEDGE_QUEUE_TIMEOUT_MS
        }))
    },
    async reindexDocumentAll(docId, projectId) {
        return unwrap(await http.post(`/ai/knowledge/documents/${docId}/reindex-all`, null, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: KNOWLEDGE_QUEUE_TIMEOUT_MS
        }))
    },
    async rebuildDocumentDigest(docId, projectId, aiConfigId) {
        return unwrap(await http.post(`/ai/knowledge/documents/${docId}/rebuild-digest`, null, {
            params: {
                ...(projectId != null ? { project_id: projectId } : {}),
                ...(aiConfigId != null ? { ai_config_id: aiConfigId } : {})
            },
            timeout: KNOWLEDGE_QUEUE_TIMEOUT_MS
        }))
    },
    async listFolders(projectId) {
        return unwrap(await http.get('/ai/knowledge/folders', {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: KNOWLEDGE_LIST_TIMEOUT_MS
        }))
    },
    async getFolderReportInputSlots(folderId, projectId, reportKind = 'iteration_report') {
        return unwrap(await http.get(`/ai/knowledge/folders/${folderId}/report-input-slots`, {
            params: {
                ...(projectId != null ? { project_id: projectId } : {}),
                report_kind: reportKind
            }
        }))
    },
    async createFolder(data, projectId) {
        return unwrap(await http.post('/ai/knowledge/folders', data, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async updateFolder(folderId, data, projectId) {
        return unwrap(await http.put(`/ai/knowledge/folders/${folderId}`, data, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async deleteFolder(folderId, projectId) {
        return unwrap(await http.delete(`/ai/knowledge/folders/${folderId}`, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async listDocuments(projectId, params = {}) {
        return unwrap(await http.get('/ai/knowledge/documents', {
            params: { project_id: projectId, ...params },
            timeout: KNOWLEDGE_LIST_TIMEOUT_MS
        }))
    },
    async uploadDocument(projectId, file, fields = {}) {
        const form = new FormData()
        form.append('file', file)
        if (fields.doc_type) form.append('doc_type', fields.doc_type)
        if (fields.folder_id != null) form.append('folder_id', String(fields.folder_id))
        if (fields.title) form.append('title', fields.title)
        const q = projectId != null ? `?project_id=${projectId}` : ''
        return unwrap(await http.post(`/ai/knowledge/documents/upload${q}`, form, {
            timeout: KNOWLEDGE_UPLOAD_TIMEOUT_MS,
            onUploadProgress: fields.onUploadProgress
        }))
    },
    async getDocument(docId, projectId) {
        return unwrap(await http.get(`/ai/knowledge/documents/${docId}`, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: KNOWLEDGE_LIST_TIMEOUT_MS
        }))
    },
    async previewDocument(docId, projectId) {
        return unwrap(await http.get(`/ai/knowledge/documents/${docId}/preview`, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: KNOWLEDGE_PARSE_TIMEOUT_MS
        }))
    },
    async fetchDocumentImageThumbnails(docId, projectId, { maxEdge = 320 } = {}) {
        return unwrap(await http.get(`/ai/knowledge/documents/${docId}/image-thumbnails`, {
            params: {
                ...(projectId != null ? { project_id: projectId } : {}),
                max_edge: maxEdge
            },
            timeout: KNOWLEDGE_PARSE_TIMEOUT_MS
        }))
    },
    async listDocumentChunks(docId, projectId, params = {}) {
        return unwrap(await http.get(`/ai/knowledge/documents/${docId}/chunks`, {
            params: { ...(projectId != null ? { project_id: projectId } : {}), ...params },
            timeout: 60000
        }))
    },
    async downloadDocument(docId, projectId) {
        const res = await http.get(`/ai/knowledge/documents/${docId}/download`, {
            params: projectId != null ? { project_id: projectId } : {},
            responseType: 'blob',
            timeout: KNOWLEDGE_DOWNLOAD_TIMEOUT_MS
        })
        return unwrapBlob(res, '文档下载')
    },
    async deleteDocument(docId, projectId) {
        return unwrap(await http.delete(`/ai/knowledge/documents/${docId}`, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async reparseDocumentsBatch({ folderId, documentIds, imageMode } = {}, projectId) {
        return unwrap(await http.post('/ai/knowledge/documents/reparse', {
            folder_id: folderId ?? null,
            document_ids: documentIds ?? null,
            image_mode: imageMode ?? null
        }, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: KNOWLEDGE_QUEUE_TIMEOUT_MS
        }))
    },
    async reparseDocument(docId, projectId, { imageMode } = {}) {
        return unwrap(await http.post(`/ai/knowledge/documents/${docId}/reparse`, null, {
            params: {
                ...(projectId != null ? { project_id: projectId } : {}),
                ...(imageMode ? { image_mode: imageMode } : {})
            },
            timeout: KNOWLEDGE_PARSE_TIMEOUT_MS
        }))
    },
    async stopDocumentImageParse(docId, projectId) {
        return unwrap(await http.post(`/ai/knowledge/documents/${docId}/image-parse/stop`, null, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: KNOWLEDGE_QUEUE_TIMEOUT_MS
        }))
    },
    async reparseDocumentImage(docId, imageIndex, projectId, { scope = 'auto' } = {}) {
        return unwrap(await http.post(`/ai/knowledge/documents/${docId}/images/${imageIndex}/reparse`, null, {
            params: {
                ...(projectId != null ? { project_id: projectId } : {}),
                scope
            },
            timeout: KNOWLEDGE_PARSE_TIMEOUT_MS
        }))
    },
    async setDefaultTemplate(docId, projectId) {
        return unwrap(await http.post(`/ai/knowledge/templates/${docId}/set-default`, null, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async getTemplateVariables(projectId) {
        return unwrap(await http.get('/ai/knowledge/templates/variables', {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async createTemplateVariable(data, projectId) {
        return unwrap(await http.post('/ai/knowledge/templates/variables', data, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async updateTemplateVariable(varId, data, projectId) {
        return unwrap(await http.put(`/ai/knowledge/templates/variables/${varId}`, data, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async deleteTemplateVariable(varId, projectId) {
        return unwrap(await http.delete(`/ai/knowledge/templates/variables/${varId}`, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async listBuiltinTemplates() {
        return unwrap(await http.get('/ai/knowledge/templates/default/list'))
    },
    async getTemplateDefaults(projectId) {
        return unwrap(await http.get('/ai/knowledge/templates/defaults', {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async updateTemplateDefaults(mappings, projectId) {
        return unwrap(await http.put('/ai/knowledge/templates/defaults', { mappings }, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async downloadDefaultTemplate(kind = 'iteration_report') {
        const res = await http.get('/ai/knowledge/templates/default/download', {
            params: { kind },
            responseType: 'blob',
            timeout: KNOWLEDGE_DOWNLOAD_TIMEOUT_MS
        })
        return unwrapBlob(res, '模板下载')
    },
    async validateTemplate(docId, projectId) {
        return unwrap(await http.post(`/ai/knowledge/documents/${docId}/validate-template`, null, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: KNOWLEDGE_PARSE_TIMEOUT_MS
        }))
    },
    async listRecentExecRecords(projectId, limit = 30) {
        return unwrap(await http.get('/ai/knowledge/exec-records/recent', {
            params: { project_id: projectId, limit }
        }))
    },
    async listIterationReports(projectId, params = {}) {
        return unwrap(await http.get('/ai/knowledge/iteration-reports', {
            params: { project_id: projectId, ...params }
        }))
    },
    async createIterationReport(data, projectId) {
        return unwrap(await http.post('/ai/knowledge/iteration-reports', data, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 60000
        }))
    },
    async getIterationReport(reportId, projectId) {
        return unwrap(await http.get(`/ai/knowledge/iteration-reports/${reportId}`, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async retryIterationReport(reportId, projectId) {
        return unwrap(await http.post(`/ai/knowledge/iteration-reports/${reportId}/retry`, null, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 60000
        }))
    },
    async deleteIterationReport(reportId, projectId) {
        return unwrap(await http.delete(`/ai/knowledge/iteration-reports/${reportId}`, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async estimateKnowledgeRefs(data, projectId) {
        return unwrap(await http.post('/ai/knowledge/refs/estimate', data, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 60000
        }))
    },
    async retrieveKnowledge(data, projectId) {
        return unwrap(await http.post('/ai/knowledge/retrieve', data, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 120000
        }))
    },
    async askKnowledge(data, projectId) {
        return unwrap(await http.post('/ai/knowledge/qa', data, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 180000
        }))
    },
    async listQaRecords(projectId, params = {}) {
        return unwrap(await http.get('/ai/knowledge/qa/records', {
            params: { project_id: projectId, ...params },
            timeout: KNOWLEDGE_LIST_TIMEOUT_MS
        }))
    },
    async getQaRecord(recordId, projectId) {
        return unwrap(await http.get(`/ai/knowledge/qa/records/${recordId}`, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: KNOWLEDGE_LIST_TIMEOUT_MS
        }))
    },
    async deleteQaRecord(recordId, projectId) {
        return unwrap(await http.delete(`/ai/knowledge/qa/records/${recordId}`, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async batchDeleteQaRecords(recordIds, projectId) {
        return unwrap(await http.post('/ai/knowledge/qa/records/batch-delete', {
            record_ids: recordIds
        }, {
            params: projectId != null ? { project_id: projectId } : {}
        }))
    },
    async archiveFromRequirement(data, projectId) {
        return unwrap(await http.post('/ai/knowledge/documents/archive-from-requirement', data, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 120000
        }))
    },
    async archiveFromText(data, projectId) {
        return unwrap(await http.post('/ai/knowledge/documents/archive-from-text', data, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 120000
        }))
    },
    async inspectReportTemplate(projectId, params = {}) {
        return unwrap(await http.get('/ai/knowledge/iteration-reports/template-inspect', {
            params: { project_id: projectId, ...params }
        }))
    },
    async previewIterationReport(data, projectId) {
        return unwrap(await http.post('/ai/knowledge/iteration-reports/preview', data, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 60000
        }))
    },
    async downloadIterationReport(reportId, projectId, attachment = 'main') {
        const res = await http.get(`/ai/knowledge/iteration-reports/${reportId}/download`, {
            params: {
                ...(projectId != null ? { project_id: projectId } : {}),
                attachment
            },
            responseType: 'blob',
            timeout: KNOWLEDGE_DOWNLOAD_TIMEOUT_MS
        })
        return unwrapBlob(res, '报告下载')
    }
}
