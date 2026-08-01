import http from '../request'

/**
 * AI 测试模块 API
 * 对应后端 /ai/* 接口
 */

// ========== LLM 配置管理 ==========
export const aiConfigApi = {
    // 创建配置
    async create(data) {
        return await http.post('/ai/configs', data)
    },
    // 下拉选项（仅需 ai_test:execute，失败分析等场景）
    async getSelectOptions() {
        return await http.get('/ai/configs/select-options')
    },
    // 获取配置列表
    async getList(params = {}) {
        return await http.get('/ai/configs', { params })
    },
    // 获取配置详情
    async getDetail(id) {
        return await http.get(`/ai/configs/${id}`)
    },
    // 更新配置
    async update(id, data) {
        return await http.put(`/ai/configs/${id}`, data)
    },
    // 删除配置
    async delete(id) {
        return await http.delete(`/ai/configs/${id}`)
    },
    // 测试连通性
    async test(id) {
        return await http.post(`/ai/configs/${id}/test`)
    },
    // 设为默认
    async setDefault(id) {
        return await http.post(`/ai/configs/${id}/set-default`)
    },
    // 正式归属「项目设置」：/sys/project-settings/execution（旧 /ai/configs/execution-settings 仍兼容）
    async getExecutionSettings(projectId) {
        return await http.get('/sys/project-settings/execution', {
            params: projectId != null ? { project_id: projectId } : {}
        })
    },
    async updateExecutionSettings(projectId, data) {
        return await http.put('/sys/project-settings/execution', data, {
            params: projectId != null ? { project_id: projectId } : {}
        })
    },
    async getSceneBindings() {
        return await http.get('/ai/configs/scene-bindings')
    },
    async saveSceneBindings(data) {
        return await http.put('/ai/configs/scene-bindings', data)
    },
    async applySceneRecommendations() {
        return await http.post('/ai/configs/scene-bindings/apply-recommendations')
    },
    async getUsageLogs(params = {}) {
        return await http.get('/ai/usage-logs', { params })
    },
    async getUsageSummary(params = {}) {
        return await http.get('/ai/usage-logs/summary', { params })
    },
    async getUsageTrend(params = {}) {
        return await http.get('/ai/usage-logs/trend', { params })
    },
    async exportUsageLogs(params = {}) {
        return await http.get('/ai/usage-logs/export', {
            params,
            responseType: 'blob'
        })
    }
}

// ========== Embedding 配置管理 ==========
export const embedConfigApi = {
    async create(data) {
        return await http.post('/ai/embed-configs', data)
    },
    async getList(params = {}) {
        return await http.get('/ai/embed-configs', { params })
    },
    async getDetail(id) {
        return await http.get(`/ai/embed-configs/${id}`)
    },
    async update(id, data) {
        return await http.put(`/ai/embed-configs/${id}`, data)
    },
    async delete(id) {
        return await http.delete(`/ai/embed-configs/${id}`)
    },
    async test(id) {
        return await http.post(`/ai/embed-configs/${id}/test`)
    },
    async setDefault(id) {
        return await http.post(`/ai/embed-configs/${id}/set-default`)
    },
    async getSelectOptions() {
        return await http.get('/ai/embed-configs/select-options')
    }
}

// ========== Prompt 模板管理 ==========
export const aiPromptApi = {
    // 获取所有模板
    async getList() {
        return await http.get('/ai/prompts')
    },
    // 获取指定模板
    async getDetail(code) {
        return await http.get(`/ai/prompts/${code}`)
    },
    // 更新模板
    async update(code, data) {
        return await http.put(`/ai/prompts/${code}`, data)
    },
    // 重置为默认
    async reset(code) {
        return await http.post(`/ai/prompts/${code}/reset`)
    },
    // 测试 Prompt（非流式，保留用于兼容）
    async test(code, variables = {}) {
        return await http.post(`/ai/prompts/${code}/test`, { variables }, { timeout: 300000 })
    },
    // 测试 Prompt（SSE 流式输出）
    testStream(code, variables = {}, callbacks = {}) {
        const { onStart, onChunk, onDone, onError, token } = callbacks
        if (!token) {
            onError && onError('未登录，请先获取 token')
            return
        }

        fetch(`/ai/prompts/${code}/test-stream`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            },
            body: JSON.stringify({ variables })
        }).then(async (response) => {
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: '请求失败' }))
                onError && onError(err.detail || '请求失败')
                return
            }

            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            let buffer = ''

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.split('\n')
                buffer = lines.pop() // 保留未完整的一行

                for (const line of lines) {
                    const trimmed = line.trim()
                    if (!trimmed.startsWith('data: ')) continue
                    const dataStr = trimmed.slice(6)
                    if (dataStr === '[DONE]') continue

                    try {
                        const data = JSON.parse(dataStr)
                        if (data.type === 'start') {
                            onStart && onStart(data)
                        } else if (data.type === 'chunk') {
                            onChunk && onChunk(data.content)
                        } else if (data.type === 'done') {
                            onDone && onDone(data)
                        } else if (data.type === 'error') {
                            onError && onError(data.message)
                        }
                    } catch (e) {
                        console.warn('[SSE] 解析数据失败:', dataStr)
                    }
                }
            }

            // 处理 buffer 中剩余的数据
            if (buffer.trim()) {
                const trimmed = buffer.trim()
                if (trimmed.startsWith('data: ')) {
                    const dataStr = trimmed.slice(6)
                    try {
                        const data = JSON.parse(dataStr)
                        if (data.type === 'done') {
                            onDone && onDone(data)
                        } else if (data.type === 'error') {
                            onError && onError(data.message)
                        }
                    } catch (e) {
                        // ignore
                    }
                }
            }
        }).catch((err) => {
            console.error('[SSE] fetch 失败:', err)
            onError && onError(err.message || '网络请求失败')
        })
    }
}

// ========== AI 生成接口 ==========
export const aiGenerateApi = {
    // 生成 API 测试用例
    async generateApiCase(data) {
        return await http.post('/ai/generate/api-case', data, { timeout: 300000 })
    },
    // 导入 AI 生成的 API 用例
    async importApiCases(data) {
        return await http.post('/ai/generate/api-case/import', data)
    },
    // 一句话生成压测场景草稿
    async generatePerfScene(data) {
        return await http.post('/ai/generate/perf-scene', data, { timeout: 300000 })
    },
    // 确认创建 AI 压测场景
    async importPerfScene(data) {
        return await http.post('/ai/generate/perf-scene/import', data)
    },
    // 根据 SSE 样例生成解析规则草稿
    async generateStreamParserRules(data) {
        return await http.post('/ai/generate/stream-parser-rules', data, { timeout: 300000 })
    },
    // 生成 UI 测试用例步骤
    async generateUiCase(data) {
        return await http.post('/ai/generate/ui-case', data, { timeout: 300000 })
    },
    // MCP 式 Agent 探索生成 UI 步骤
    async generateUiCaseAgent(data) {
        return await http.post('/ai/generate/ui-case/agent', data, { timeout: 600000 })
    },
    async generateAppCase(data) {
        return await http.post('/ai/generate/app-case', data, { timeout: 300000 })
    },
    async suggestAppInspector(data) {
        return await http.post('/ai/generate/app-inspector-suggest', data, { timeout: 180000 })
    },
    // UI 定位器自愈
    async healLocator(data) {
        return await http.post('/ai/generate/locator-heal', data, { timeout: 120000 })
    },
    async healAppLocator(data) {
        return await http.post('/ai/generate/app-locator-heal', data, { timeout: 120000 })
    },
    async applyHealedLocatorToCase(data) {
        return await http.post('/ai/generate/locator-heal/apply-to-case', data, { timeout: 30000 })
    },
    async applyAiActToCase(data) {
        return await http.post('/ai/generate/ai-act/apply-to-case', data, { timeout: 30000 })
    },
    // 预抓取页面元素
    async fetchPage(url) {
        return await http.post('/ai/generate/fetch-page', { url }, { timeout: 30000 })
    }
}

// ========== AI 需求用例 ==========
export const aiRequirementApi = {
    async upload(file, name, projectId) {
        const form = new FormData()
        form.append('file', file)
        form.append('project_id', String(projectId))
        if (name) form.append('name', name)
        return await http.post('/ai/requirements/upload', form, { timeout: 120000 })
    },
    async getList(params = {}) {
        return await http.get('/ai/requirements', { params })
    },
    async getDetail(id, projectId) {
        return await http.get(`/ai/requirements/${id}`, { params: { project_id: projectId } })
    },
    async update(id, data, projectId) {
        return await http.put(`/ai/requirements/${id}`, data, { params: { project_id: projectId } })
    },
    async delete(id, projectId) {
        return await http.delete(`/ai/requirements/${id}`, { params: { project_id: projectId } })
    },
    async generateCases(id, data, projectId) {
        return await http.post(
            `/ai/requirements/${id}/generate-cases`,
            data,
            { params: { project_id: projectId }, timeout: 600000 }
        )
    },
    async generateCasesBatch(id, data, projectId) {
        return await http.post(
            `/ai/requirements/${id}/generate-cases-batch`,
            data,
            { params: { project_id: projectId }, timeout: 60000 }
        )
    },
    async createGenerateJob(id, data, projectId) {
        return await http.post(
            `/ai/requirements/${id}/generate-jobs`,
            data,
            { params: { project_id: projectId }, timeout: 60000 }
        )
    },
    async getGenerateJob(jobId, projectId) {
        return await http.get(`/ai/requirements/generate-jobs/${jobId}`, {
            params: { project_id: projectId }
        })
    },
    async retryGenerateBatchJob(jobId, data, projectId) {
        return await http.post(
            `/ai/requirements/generate-jobs/${jobId}/retry-batch`,
            data,
            { params: { project_id: projectId }, timeout: 600000 }
        )
    },
    async getLatestGenerateJob(reqId, projectId) {
        return await http.get(`/ai/requirements/${reqId}/generate-jobs/latest`, {
            params: { project_id: projectId }
        })
    },
    async listGenerateJobs(reqId, projectId, params = {}) {
        return await http.get(`/ai/requirements/${reqId}/generate-jobs`, {
            params: { project_id: projectId, ...params }
        })
    },
    async deleteGenerateJob(jobId, projectId) {
        return await http.delete(`/ai/requirements/generate-jobs/${jobId}`, {
            params: { project_id: projectId }
        })
    },
    async getCases(id, projectId) {
        return await http.get(`/ai/requirements/${id}/cases`, { params: { project_id: projectId } })
    },
    async updateCase(reqId, caseId, data, projectId) {
        return await http.put(
            `/ai/requirements/${reqId}/cases/${caseId}`,
            data,
            { params: { project_id: projectId } }
        )
    },
    async deleteCases(reqId, caseIds, projectId) {
        return await http.delete(`/ai/requirements/${reqId}/cases`, {
            params: { project_id: projectId },
            data: { case_ids: caseIds }
        })
    },
    importToLibrary(reqId, caseIds, projectId, options = {}) {
        return aiFunctionalCaseApi.importToLibrary(reqId, caseIds, projectId, options)
    },
    exportXlsxUrl(id, projectId) {
        const base = import.meta.env.VITE_BASE_API || ''
        return `${base}/ai/requirements/${id}/cases/export?project_id=${projectId}`
    },
    async getExportTemplate() {
        return await http.get('/ai/requirements/export-template')
    },
    getZentaoBindings(projectId, requirementId) {
        const params = { project_id: projectId }
        if (requirementId) params.requirement_id = requirementId
        return http.get('/ai/requirements/zentao-bindings', { params })
    },
    saveProjectZentaoBindings(data, projectId) {
        return http.put('/ai/requirements/zentao-bindings', data, { params: { project_id: projectId } })
    },
    saveRequirementZentaoBindings(reqId, data, projectId) {
        return http.put(`/ai/requirements/${reqId}/zentao-bindings`, data, {
            params: { project_id: projectId }
        })
    },
    reapplyZentaoBindings(reqId, projectId) {
        return http.post(`/ai/requirements/${reqId}/cases/reapply-bindings`, null, {
            params: { project_id: projectId }
        })
    },
    getDocumentStructure(reqId, projectId) {
        return http.get(`/ai/requirements/${reqId}/document-structure`, {
            params: { project_id: projectId }
        })
    },
    estimateScope(reqId, data, projectId) {
        return http.post(`/ai/requirements/${reqId}/estimate-scope`, data, {
            params: { project_id: projectId }
        })
    },
    getSectionCoverage(reqId, projectId, pendingSectionIds = null) {
        const params = { project_id: projectId }
        if (pendingSectionIds?.length) {
            params.pending_section_ids = pendingSectionIds.join(',')
        }
        return http.get(`/ai/requirements/${reqId}/section-coverage`, { params })
    },
    reparseDocument(reqId, projectId) {
        return http.post(`/ai/requirements/${reqId}/reparse-document`, null, {
            params: { project_id: projectId },
            timeout: 120000
        })
    },
    getCaseNaming(projectId, requirementId) {
        const params = { project_id: projectId }
        if (requirementId) params.requirement_id = requirementId
        return http.get('/ai/requirements/case-naming', { params })
    },
    saveCaseNaming(data, projectId) {
        return http.put('/ai/requirements/case-naming', data, { params: { project_id: projectId } })
    },
    previewCaseNaming(data, projectId, requirementId) {
        const params = { project_id: projectId }
        if (requirementId) params.requirement_id = requirementId
        return http.post('/ai/requirements/case-naming/preview', data, { params })
    },
    saveRequirementNamingMeta(reqId, data, projectId) {
        return http.put(`/ai/requirements/${reqId}/naming-meta`, data, {
            params: { project_id: projectId }
        })
    },
    recalcCaseTitles(reqId, data, projectId) {
        return http.post(`/ai/requirements/${reqId}/cases/recalc-titles`, data || {}, {
            params: { project_id: projectId }
        })
    }
}

// ========== AI 测试分析（测试点 + 测试方案） ==========
export const aiTestAnalysisApi = {
    async getRequirements(params = {}) {
        return await http.get('/ai/test-analysis/requirements', { params })
    },
    async getOverview(reqId, projectId) {
        return await http.get(`/ai/test-analysis/requirements/${reqId}/overview`, {
            params: { project_id: projectId }
        })
    },
    async getMindmap(reqId, projectId, params = {}) {
        return await http.get(`/ai/test-analysis/requirements/${reqId}/mindmap`, {
            params: { project_id: projectId, ...params }
        })
    },
    async getTestPoints(reqId, projectId, filters = {}) {
        const params = { project_id: projectId, ...filters }
        Object.keys(params).forEach(k => {
            if (params[k] === '' || params[k] === null || params[k] === undefined) delete params[k]
        })
        return await http.get(`/ai/test-analysis/requirements/${reqId}/test-points`, { params })
    },
    async generateTestPoints(reqId, data, projectId) {
        return await http.post(
            `/ai/test-analysis/requirements/${reqId}/test-points/generate`,
            data,
            { params: { project_id: projectId }, timeout: 600000 }
        )
    },
    async planTestPointBatches(reqId, data, projectId) {
        return await http.post(
            `/ai/test-analysis/requirements/${reqId}/test-points/plan-batches`,
            data,
            { params: { project_id: projectId }, timeout: 60000 }
        )
    },
    async generateTestPointsBatch(reqId, data, projectId) {
        return await http.post(
            `/ai/test-analysis/requirements/${reqId}/test-points/generate-batch`,
            data,
            { params: { project_id: projectId }, timeout: 60000 }
        )
    },
    async createFromXmind(file, options = {}, projectId) {
        const form = new FormData()
        form.append('file', file)
        form.append('project_id', String(projectId))
        if (options.name?.trim()) form.append('name', options.name.trim())
        form.append('batch_name', options.batch_name || '')
        form.append('replace_batch', options.replace_batch ? 'true' : 'false')
        return await http.post('/ai/test-analysis/requirements/create-from-xmind', form, {
            params: { project_id: projectId },
            timeout: 120000
        })
    },
    async importTestPointsXmind(reqId, file, options = {}, projectId) {
        const form = new FormData()
        form.append('file', file)
        form.append('batch_name', options.batch_name || '')
        form.append('replace_batch', options.replace_batch ? 'true' : 'false')
        return await http.post(
            `/ai/test-analysis/requirements/${reqId}/test-points/import-xmind`,
            form,
            { params: { project_id: projectId }, timeout: 120000 }
        )
    },
    async listProjectTestPoints(params = {}) {
        return await http.get('/ai/test-analysis/test-points', { params })
    },
    async listProjectSchemes(params = {}) {
        return await http.get('/ai/test-analysis/test-schemes', { params })
    },
    async updateTestPoint(reqId, pointId, data, projectId) {
        return await http.put(
            `/ai/test-analysis/requirements/${reqId}/test-points/${pointId}`,
            data,
            { params: { project_id: projectId } }
        )
    },
    async batchConfirmPoints(reqId, pointIds, projectId, status = 'confirmed') {
        return await http.put(
            `/ai/test-analysis/requirements/${reqId}/test-points/batch-status`,
            { point_ids: pointIds, status },
            { params: { project_id: projectId } }
        )
    },
    async deleteTestPoints(reqId, pointIds, projectId) {
        return await http.delete(`/ai/test-analysis/requirements/${reqId}/test-points`, {
            params: { project_id: projectId },
            data: { point_ids: pointIds }
        })
    },
    async generateCasesFromTestPoints(reqId, data, projectId) {
        return await http.post(
            `/ai/test-analysis/requirements/${reqId}/test-points/generate-cases`,
            data,
            { params: { project_id: projectId }, timeout: 600000 }
        )
    },
    async getSchemes(reqId, projectId) {
        return await http.get(`/ai/test-analysis/requirements/${reqId}/test-schemes`, {
            params: { project_id: projectId }
        })
    },
    async getScheme(reqId, schemeId, projectId) {
        return await http.get(`/ai/test-analysis/requirements/${reqId}/test-schemes/${schemeId}`, {
            params: { project_id: projectId }
        })
    },
    async generateScheme(reqId, data, projectId) {
        return await http.post(
            `/ai/test-analysis/requirements/${reqId}/test-schemes/generate`,
            data,
            { params: { project_id: projectId }, timeout: 600000 }
        )
    },
    async updateScheme(reqId, schemeId, data, projectId) {
        return await http.put(
            `/ai/test-analysis/requirements/${reqId}/test-schemes/${schemeId}`,
            data,
            { params: { project_id: projectId } }
        )
    },
    async deleteScheme(reqId, schemeId, projectId) {
        return await http.delete(`/ai/test-analysis/requirements/${reqId}/test-schemes/${schemeId}`, {
            params: { project_id: projectId }
        })
    },
    exportSchemeDocxUrl(reqId, schemeId, projectId) {
        const base = import.meta.env.VITE_BASE_API || ''
        return `${base}/ai/test-analysis/requirements/${reqId}/test-schemes/${schemeId}/export-docx?project_id=${projectId}`
    },
    async exportSchemeDocxBlob(reqId, schemeId, projectId) {
        const { UserStore } = await import('@/stores/module/UserStore.js')
        const uStore = UserStore()
        const url = this.exportSchemeDocxUrl(reqId, schemeId, projectId)
        const res = await fetch(url, { headers: { Authorization: 'Bearer ' + uStore.token } })
        if (!res.ok) {
            const err = await res.json().catch(() => ({}))
            throw new Error(err.detail || err.message || '导出失败')
        }
        return await res.blob()
    },
    exportXmindUrl(reqId, projectId, params = {}) {
        const base = import.meta.env.VITE_BASE_API || ''
        const qs = new URLSearchParams({ project_id: projectId, ...params })
        return `${base}/ai/test-analysis/requirements/${reqId}/test-points/export-xmind?${qs}`
    },
    async exportXmindBlob(reqId, projectId, params = {}) {
        const { UserStore } = await import('@/stores/module/UserStore.js')
        const uStore = UserStore()
        const url = this.exportXmindUrl(reqId, projectId, params)
        const res = await fetch(url, {
            headers: { Authorization: 'Bearer ' + uStore.token }
        })
        if (!res.ok) {
            const err = await res.json().catch(() => ({}))
            throw new Error(err.detail || err.message || '导出失败')
        }
        return await res.blob()
    }
}

// ========== AI 工作台 ==========
export const aiWorkbenchApi = {
    async getOverview(projectId) {
        return await http.get('/ai/workbench/overview', {
            params: { project_id: projectId }
        })
    }
}

// ========== 功能测试用例库 ==========
export const aiFunctionalCaseApi = {
    async getList(params = {}) {
        return await http.get('/ai/functional-cases', { params })
    },
    async getDetail(id, projectId) {
        return await http.get(`/ai/functional-cases/${id}`, { params: { project_id: projectId } })
    },
    async create(data, projectId) {
        return await http.post('/ai/functional-cases', data, { params: { project_id: projectId } })
    },
    async update(id, data, projectId) {
        return await http.put(`/ai/functional-cases/${id}`, data, { params: { project_id: projectId } })
    },
    async batchDelete(ids, projectId) {
        return await http.delete('/ai/functional-cases', {
            params: { project_id: projectId },
            data: { ids }
        })
    },
    async importZentao(file, projectId) {
        const form = new FormData()
        form.append('file', file)
        return await http.post('/ai/functional-cases/import-zentao', form, {
            params: { project_id: projectId },
            timeout: 120000
        })
    },
    async duplicateCheck(data, projectId) {
        return await http.post('/ai/functional-cases/duplicate-check', data || {}, {
            params: { project_id: projectId }
        })
    },
    async getImportBatches(projectId) {
        return await http.get('/ai/functional-cases/import-batches', {
            params: { project_id: projectId }
        })
    },
    async getFilterOptions(projectId) {
        return await http.get('/ai/functional-cases/filter-options', {
            params: { project_id: projectId }
        })
    },
    async deleteByImportBatch(importBatch, projectId) {
        return await http.delete('/ai/functional-cases/by-import-batch', {
            params: { project_id: projectId, import_batch: importBatch }
        })
    },
    exportXlsxUrl(projectId, options = {}) {
        const base = import.meta.env.VITE_BASE_API || ''
        const params = new URLSearchParams({ project_id: String(projectId) })
        const ids = options.ids
        if (ids?.length) {
            params.set('ids', ids.join(','))
        }
        const filters = options.filters || {}
        Object.entries(filters).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                params.set(key, String(value))
            }
        })
        return `${base}/ai/functional-cases/export/xlsx?${params.toString()}`
    },
    async importToLibrary(reqId, caseIds, projectId, options = {}) {
        const duplicateTitleMode = options.duplicateTitleMode || 'skip'
        return await http.post(
            `/ai/requirements/${reqId}/cases/import-to-library`,
            { case_ids: caseIds, duplicate_title_mode: duplicateTitleMode },
            { params: { project_id: projectId } }
        )
    },
    async previewToUi(data, projectId) {
        return await http.post('/ai/functional-cases/to-ui/preview', data, {
            params: { project_id: projectId },
            timeout: 600000
        })
    },
    async importUi(data, projectId) {
        return await http.post('/ai/functional-cases/import-ui', data, {
            params: { project_id: projectId },
            timeout: 120000
        })
    },
    async previewToApp(data, projectId) {
        return await http.post('/ai/functional-cases/to-app/preview', data, {
            params: { project_id: projectId },
            timeout: 600000
        })
    },
    async importApp(data, projectId) {
        return await http.post('/ai/functional-cases/import-app', data, {
            params: { project_id: projectId },
            timeout: 120000
        })
    }
}

// ========== AI 失败分析 ==========
export const aiAnalyzeApi = {
    async analyzeFailure(data, projectId) {
        return await http.post('/ai/analyze/failure', data, {
            params: { project_id: projectId },
            timeout: 120000
        })
    },
    async getByTarget(targetType, targetId, projectId) {
        return await http.get('/ai/analyze/failure/by-target', {
            params: {
                target_type: targetType,
                target_id: targetId,
                project_id: projectId
            }
        })
    },
    async getDetail(analysisId, projectId) {
        return await http.get(`/ai/analyze/failure/${analysisId}`, {
            params: { project_id: projectId }
        })
    },
    async analyzeFailureBatch(data, projectId) {
        return await http.post('/ai/analyze/failure/batch', data, {
            params: { project_id: projectId },
            timeout: 600000
        })
    },
    async generateReportSummary(data, projectId) {
        return await http.post('/ai/analyze/report-summary', data, {
            params: { project_id: projectId },
            timeout: 120000
        })
    },
    async getReportSummaryByRecord(reportType, recordId, projectId) {
        return await http.get('/ai/analyze/report-summary/by-record', {
            params: {
                report_type: reportType,
                record_id: recordId,
                project_id: projectId
            }
        })
    },
    async analyzePerfCompare(data, projectId) {
        return await http.post('/ai/analyze/perf-compare', data, {
            params: { project_id: projectId },
            timeout: 120000
        })
    },
    async analyzePerfReport(data, projectId) {
        return await http.post('/ai/analyze/perf-report', data, {
            params: { project_id: projectId },
            timeout: 120000
        })
    }
}

export const aiRecordApi = {
    // 启动录制
    async start(data) {
        return await http.post('/ai/record/start', data, { timeout: 30000 })
    },
    // 查询录制状态
    async getStatus(id) {
        return await http.get(`/ai/record/${id}`, { timeout: 10000 })
    },
    // 停止录制
    async stop(id, data = {}) {
        return await http.post(`/ai/record/${id}/stop`, data || {}, { timeout: 30000 })
    },
    async pause(id, data = {}) {
        return await http.post(`/ai/record/${id}/pause`, data || {}, { timeout: 15000 })
    },
    async resume(id, data = {}) {
        return await http.post(`/ai/record/${id}/resume`, data || {}, { timeout: 15000 })
    },
    async saveVariable(id, data) {
        return await http.post(`/ai/record/${id}/save-variable`, data, { timeout: 15000 })
    },
    // 手动转换
    async convert(id) {
        return await http.post(`/ai/record/${id}/convert`, {}, { timeout: 30000 })
    },
    // AI 优化步骤（录制会话）
    async optimize(id, payload = {}) {
        const body = typeof payload === 'string'
            ? { description: payload }
            : payload
        // 精简 + 断言双次 LLM，场景 timeout 常为 180s；前端放宽到 10min
        return await http.post(`/ai/record/${id}/optimize`, body, { timeout: 600000 })
    },
    // AI 优化用例步骤（无需录制会话）
    async optimizeSteps(payload = {}) {
        return await http.post('/ai/record/optimize-steps', payload, { timeout: 600000 })
    },
    // 应用到用例
    async apply(id) {
        return await http.post(`/ai/record/${id}/apply`, {}, { timeout: 10000 })
    }
}


// ========== 智能浏览器（browser-use） ==========
export const browserLabApi = {
    async listCases(projectId, params = {}) {
        return await http.get('/ai/browser-lab/cases', {
            params: { project_id: projectId, ...params }
        })
    },
    async getCase(caseId, projectId) {
        return await http.get(`/ai/browser-lab/cases/${caseId}`, {
            params: projectId != null ? { project_id: projectId } : {}
        })
    },
    async createCase(data, projectId) {
        return await http.post('/ai/browser-lab/cases', data, {
            params: projectId != null ? { project_id: projectId } : {}
        })
    },
    async updateCase(caseId, data, projectId) {
        return await http.put(`/ai/browser-lab/cases/${caseId}`, data, {
            params: projectId != null ? { project_id: projectId } : {}
        })
    },
    async deleteCases(ids, projectId) {
        return await http.delete('/ai/browser-lab/cases', {
            params: projectId != null ? { project_id: projectId } : {},
            data: { ids }
        })
    },
    async runCase(caseId, projectId) {
        return await http.post(`/ai/browser-lab/cases/${caseId}/run`, null, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 60000
        })
    },
    async createTask(data, projectId) {
        return await http.post('/ai/browser-lab/tasks', data, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 60000
        })
    },
    async optimizeTaskText(data, projectId) {
        return await http.post('/ai/browser-lab/optimize-task-text', data, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 120000
        })
    },
    async listTasks(projectId, params = {}) {
        return await http.get('/ai/browser-lab/tasks', {
            params: { project_id: projectId, ...params }
        })
    },
    async getTask(taskId, projectId) {
        return await http.get(`/ai/browser-lab/tasks/${taskId}`, {
            params: projectId != null ? { project_id: projectId } : {}
        })
    },
    async stopTask(taskId, projectId) {
        return await http.post(`/ai/browser-lab/tasks/${taskId}/stop`, null, {
            params: projectId != null ? { project_id: projectId } : {}
        })
    },
    async rerunTask(taskId, projectId) {
        return await http.post(`/ai/browser-lab/tasks/${taskId}/rerun`, null, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 60000
        })
    },
    async getTaskReport(taskId, projectId) {
        return await http.get(`/ai/browser-lab/tasks/${taskId}/report`, {
            params: projectId != null ? { project_id: projectId } : {}
        })
    },
    async previewUiSteps(taskId, projectId, params = {}) {
        return await http.get(`/ai/browser-lab/tasks/${taskId}/ui-steps-preview`, {
            params: { project_id: projectId, ...params }
        })
    },
    async importUiCase(taskId, data, projectId) {
        return await http.post(`/ai/browser-lab/tasks/${taskId}/import-ui-case`, data, {
            params: projectId != null ? { project_id: projectId } : {},
            timeout: 120000
        })
    },
    async deleteTask(taskId, projectId) {
        return await http.delete(`/ai/browser-lab/tasks/${taskId}`, {
            params: projectId != null ? { project_id: projectId } : {}
        })
    },
    async deleteTasks(ids, projectId) {
        return await http.delete('/ai/browser-lab/tasks', {
            params: projectId != null ? { project_id: projectId } : {},
            data: { ids }
        })
    },
    screenshotUrl(taskId, filename, projectId) {
        const base = (import.meta.env.VITE_BASE_API || '').replace(/\/$/, '')
        const q = projectId != null ? `?project_id=${projectId}` : ''
        return `${base}/ai/browser-lab/tasks/${taskId}/screenshots/${filename}${q}`
    },
    async fetchScreenshotBlob(taskId, filename, projectId) {
        const { UserStore } = await import('@/stores/module/UserStore.js')
        const token = UserStore().token
        const url = this.screenshotUrl(taskId, filename, projectId)
        const res = await fetch(url, {
            headers: token ? { Authorization: `Bearer ${token}` } : {}
        })
        if (!res.ok) throw new Error('截图加载失败')
        return await res.blob()
    },
    gifUrl(taskId, projectId) {
        const base = (import.meta.env.VITE_BASE_API || '').replace(/\/$/, '')
        const q = projectId != null ? `?project_id=${projectId}` : ''
        return `${base}/ai/browser-lab/tasks/${taskId}/gif${q}`
    },
    async fetchGifBlob(taskId, projectId) {
        const { UserStore } = await import('@/stores/module/UserStore.js')
        const token = UserStore().token
        const url = this.gifUrl(taskId, projectId)
        const res = await fetch(url, {
            headers: token ? { Authorization: `Bearer ${token}` } : {}
        })
        if (!res.ok) throw new Error('GIF 加载失败')
        return await res.blob()
    },
    streamTask(taskId, projectId, callbacks = {}) {
        const { onEvent, onDone, onError } = callbacks
        import('@/stores/module/UserStore.js').then(({ UserStore }) => {
            const token = UserStore().token
            const base = (import.meta.env.VITE_BASE_API || '').replace(/\/$/, '')
            const q = projectId != null ? `?project_id=${projectId}` : ''
            fetch(`${base}/ai/browser-lab/tasks/${taskId}/stream${q}`, {
                headers: token ? { Authorization: `Bearer ${token}` } : {}
            }).then(async (response) => {
                if (!response.ok) {
                    const err = await response.json().catch(() => ({ detail: '订阅失败' }))
                    onError && onError(err.detail || err.message || '订阅失败')
                    return
                }
                const reader = response.body.getReader()
                const decoder = new TextDecoder()
                let buffer = ''
                while (true) {
                    const { done, value } = await reader.read()
                    if (done) break
                    buffer += decoder.decode(value, { stream: true })
                    const lines = buffer.split('\n')
                    buffer = lines.pop()
                    for (const line of lines) {
                        const trimmed = line.trim()
                        if (!trimmed.startsWith('data: ')) continue
                        try {
                            const data = JSON.parse(trimmed.slice(6))
                            onEvent && onEvent(data)
                            if (data.type === 'done') {
                                onDone && onDone(data)
                                return
                            }
                            if (data.type === 'error') {
                                onError && onError(data.message)
                                return
                            }
                        } catch (e) {
                            console.warn('[browser-lab SSE]', e)
                        }
                    }
                }
                onDone && onDone({ type: 'done' })
            }).catch((e) => onError && onError(e.message || String(e)))
        })
    }
}
