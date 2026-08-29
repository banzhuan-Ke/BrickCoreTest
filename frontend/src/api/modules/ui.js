import http from '../request'

/**
 * Web自动化测试API模块
 * 对应后端 /ui/* 接口
 */

// ========== 用例管理 ==========
export const uiCaseApi = {
    // 获取用例列表
    async getList(params) {
        return await http.get('/ui/cases', { params })
    },
    // 创建用例
    async create(data) {
        return await http.post('/ui/cases', data)
    },
    // 获取用例详情
    async getDetail(case_id) {
        return await http.get(`/ui/cases/${case_id}`)
    },
    async getExecutionHints(case_id, params = {}) {
        return await http.get(`/ui/cases/${case_id}/execution-hints`, { params })
    },
    // 更新用例
    async update(case_id, data) {
        return await http.put(`/ui/cases/${case_id}`, data)
    },
    // 删除用例
    async delete(case_id) {
        return await http.delete(`/ui/cases/${case_id}`)
    },
    // 复制用例
    async copy(case_id, data = null) {
        return await http.post(`/ui/cases/${case_id}/copy`, data || {})
    },
    // 批量删除
    async batchDelete(data) {
        return await http.post('/ui/cases/batch-delete', data)
    },
    async batchUpdateCatalog(data) {
        return await http.post('/ui/cases/batch-update-catalog', data)
    },
    // 批量导出 UI 用例（返回 blob）
    async exportCases(data) {
        return await http.post('/ui/cases/export', data, { responseType: 'blob' })
    },
    // 批量导入 UI 用例
    async importCases(formData) {
        return await http.post('/ui/cases/import', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        })
    },
    
    // ===== 兼容旧命名 =====
    getCaseList(params) { return this.getList(params) },
    createCase(data) { return this.create(data) },
    getCaseDetail(case_id) { return this.getDetail(case_id) },
    updateCase(case_id, data) { return this.update(case_id, data) },
    deleteCase(case_id) { return this.delete(case_id) },
    copyCase(case_id) { return this.copy(case_id) }
}

// ========== 步骤片段 ==========
export const uiFragmentApi = {
    async getList(params) {
        return await http.get('/ui/fragments', { params })
    },
    list(params) {
        return this.getList(params)
    },
    async getDetail(fragment_id, project_id) {
        return await http.get(`/ui/fragments/${fragment_id}`, { params: { project_id } })
    },
    async create(data) {
        return await http.post('/ui/fragments', data)
    },
    async update(fragment_id, data, project_id) {
        return await http.put(`/ui/fragments/${fragment_id}`, data, { params: { project_id } })
    },
    async delete(fragment_id, project_id, force = false) {
        return await http.delete(`/ui/fragments/${fragment_id}`, { params: { project_id, force } })
    },
    async getReferences(fragment_id, project_id) {
        return await http.get(`/ui/fragments/${fragment_id}/references`, { params: { project_id } })
    },
    async previewExpand(fragment_id, data) {
        return await http.post(`/ui/fragments/${fragment_id}/expand`, data)
    },
}

// ========== 套件管理 ==========
export const uiSuiteApi = {
    // 获取套件列表
    async getList(params) {
        return await http.get('/ui/suites', { params })
    },
    // 创建套件
    async create(data) {
        return await http.post('/ui/suites', data)
    },
    // 获取套件详情
    async getDetail(suite_id) {
        return await http.get(`/ui/suites/${suite_id}`)
    },
    // 更新套件
    async update(suite_id, data) {
        return await http.put(`/ui/suites/${suite_id}`, data)
    },
    // 删除套件
    async delete(suite_id) {
        return await http.delete(`/ui/suites/${suite_id}`)
    },
    // 获取套件下的用例
    async getCases(suite_id) {
        return await http.get(`/ui/suites/${suite_id}/cases`)
    },
    // 更新套件用例（排序、增删）
    async updateCases(suite_id, data) {
        return await http.put(`/ui/suites/${suite_id}/cases`, data)
    },
    // 批量复制用例到其他套件
    async batchCopyCases(suite_id, data) {
        return await http.post(`/ui/suites/${suite_id}/cases/copy`, data)
    },
    // 删除套件中的用例
    async deleteCase(suite_id, case_id) {
        return await http.delete(`/ui/suites/${suite_id}/cases/${case_id}`)
    },
    // 添加用例到套件
    async addCase(suite_id, data) {
        return await http.post(`/ui/suites/${suite_id}/cases`, data)
    },
    // 更新用例排序
    async updateCaseOrder(suite_id, data) {
        return await http.post(`/ui/suites/${suite_id}/cases/sort`, data)
    },
    
    // ===== 兼容旧命名 =====
    getSuiteList(params) { return this.getList(params) },
    createSuite(data) { return this.create(data) },
    getSuiteDetail(suite_id) { return this.getDetail(suite_id) },
    updateSuite(suite_id, data) { return this.update(suite_id, data) },
    deleteSuite(suite_id) { return this.delete(suite_id) },
    getSuiteCases(suite_id) { return this.getCases(suite_id) },
    updateSuiteCases(suite_id, data) { return this.updateCases(suite_id, data) },
    // 套件用例管理额外兼容
    getSuiteCaseList(suite_id) { return this.getCases(suite_id) },
    addSuiteCase(suite_id, data) { return http.post(`/ui/suites/${suite_id}/cases`, data) },
    deleteSuiteCase(suite_id, case_id) { return http.delete(`/ui/suites/${suite_id}/cases/${case_id}`) },
    updateSuiteCaseOrder(suite_id, data) { return http.post(`/ui/suites/${suite_id}/cases/sort`, data) },
    // 执行相关（直接使用 http）
    runSuite(suite_id, data) { return http.post(`/ui/exec/suites/${suite_id}`, data) }
}

// ========== 任务/计划管理 ==========
export const uiTaskApi = {
    // 获取任务列表
    async getList(params, config = {}) {
        return await http.get('/ui/tasks', { params, ...config })
    },
    // 创建任务
    async create(data) {
        return await http.post('/ui/tasks', data)
    },
    // 获取任务详情
    async getDetail(task_id) {
        return await http.get(`/ui/tasks/${task_id}`)
    },
    // 更新任务
    async update(task_id, data) {
        return await http.put(`/ui/tasks/${task_id}`, data)
    },
    // 删除任务
    async delete(task_id) {
        return await http.delete(`/ui/tasks/${task_id}`)
    },
    // 获取任务下的套件
    async getSuites(task_id) {
        return await http.get(`/ui/tasks/${task_id}/suites`)
    },
    // 更新任务套件
    async updateSuites(task_id, data) {
        return await http.put(`/ui/tasks/${task_id}/suites`, data)
    },
    
    // ===== 兼容旧命名 =====
    getTaskList(params, config) { return this.getList(params, config) },
    createTask(data) { return this.create(data) },
    getTaskDetail(task_id) { return this.getDetail(task_id) },
    updateTask(task_id, data) { return this.update(task_id, data) },
    deleteTask(task_id) { return this.delete(task_id) },
    getTaskSuites(task_id) { return this.getSuites(task_id) },
    deleteTaskSuite(task_id, suite_id) { 
        // 旧接口删除任务下的套件
        return http.delete(`/ui/tasks/${task_id}/suites/${suite_id}`) 
    },
    // 添加套件到任务
    addTaskSuite(task_id, suite_id) { 
        return http.post(`/ui/tasks/${task_id}/suites`, { suite_id }) 
    },
    // 执行相关（直接使用 http）
    runTask(task_id, data) { return http.post(`/ui/exec/tasks/${task_id}`, data) }
}

// ========== 执行管理 ==========
export const uiExecApi = {
    // 执行用例
    async runCase(case_id, data) {
        return await http.post(`/ui/exec/cases/${case_id}`, data)
    },
    // 步骤级调试（执行前 N 步）
    async debugCase(case_id, data) {
        return await http.post(`/ui/exec/cases/${case_id}/debug`, data, { timeout: 120000 })
    },
    // 执行套件
    async runSuite(suite_id, data) {
        return await http.post(`/ui/exec/suites/${suite_id}`, data)
    },
    // 执行任务
    async runTask(task_id, data) {
        return await http.post(`/ui/exec/tasks/${task_id}`, data)
    },
    // 停止 UI 计划执行
    async stopPlan(record_id) {
        return await http.post(`/ui/exec/stop/${record_id}`)
    },
    // 停止 UI 套件执行
    async stopSuite(record_id) {
        return await http.post(`/ui/exec/stop/suite/${record_id}`)
    },
    // 停止 UI 用例执行
    async stopCase(record_id) {
        return await http.post(`/ui/exec/stop/case/${record_id}`)
    },
    // 兼容旧调用
    async stop(record_id) {
        return this.stopPlan(record_id)
    }
}

// ========== 交互调试 ==========
export const uiDebugApi = {
    async createSession(data) {
        return await http.post('/ui/debug/sessions', data)
    },
    async getSession(sessionId) {
        return await http.get(`/ui/debug/sessions/${sessionId}`)
    },
    async getActiveSession(params) {
        return await http.get('/ui/debug/sessions/active', { params })
    },
    async runSteps(sessionId, data) {
        return await http.post(`/ui/debug/sessions/${sessionId}/run`, data, { timeout: 120000 })
    },
    async resolveRunSegments(sessionId, data) {
        return await http.post(`/ui/debug/sessions/${sessionId}/resolve-run-segments`, data)
    },
    async closeSession(sessionId) {
        return await http.post(`/ui/debug/sessions/${sessionId}/close`)
    },
    async compareSteps(sessionId, data) {
        return await http.post(`/ui/debug/sessions/${sessionId}/compare-steps`, data)
    },
    async syncSteps(sessionId, data, config = {}) {
        return await http.post(`/ui/debug/sessions/${sessionId}/sync-steps`, data, {
            timeout: 120000,
            ...config,
        })
    },
    async highlightStep(sessionId, data) {
        return await http.post(`/ui/debug/sessions/${sessionId}/highlight`, data, { timeout: 60000 })
    },
    async verifyLocator(sessionId, data) {
        return await http.post(`/ui/debug/sessions/${sessionId}/verify-locator`, data, { timeout: 60000 })
    },
    async setPickMode(sessionId, data) {
        return await http.post(`/ui/debug/sessions/${sessionId}/pick-mode`, data, { timeout: 60000 })
    },
    async clearHighlight(sessionId) {
        return await http.post(`/ui/debug/sessions/${sessionId}/clear-highlight`, {}, { timeout: 60000 })
    },
    async setHotkeys(sessionId, data) {
        return await http.post(`/ui/debug/sessions/${sessionId}/hotkeys`, data, { timeout: 30000 })
    },
    async selectStep(sessionId, data) {
        // 选中同步失败不弹全局「请求失败」（如偶发冲突），由调用方静默处理
        return await http.post(`/ui/debug/sessions/${sessionId}/select-step`, data, {
            timeout: 30000,
            skipErrorHandler: true,
        })
    },
}

/** Web 定位助手（编辑态生成候选） */
export const locatorAssistApi = {
    async suggest(data) {
        return await http.post('/ui/locator-assist/suggest', data, { timeout: 120000 })
    },
}

// ========== 执行记录 ==========
export const uiRecordApi = {
    // 获取任务执行记录
    async getTaskRecords(params) {
        return await http.get('/ui/records/tasks', { params })
    },
    // 获取套件执行记录
    async getSuiteRecords(params) {
        return await http.get('/ui/records/suites', { params })
    },
    // 获取用例执行记录
    async getCaseRecords(params) {
        return await http.get('/ui/records/cases', { params })
    },
    // 获取任务记录详情
    async getTaskRecordDetail(record_id) {
        return await http.get(`/ui/records/tasks/${record_id}`)
    },
    // 获取套件记录详情
    async getSuiteRecordDetail(record_id) {
        return await http.get(`/ui/records/suites/${record_id}`)
    },
    // 获取用例记录详情
    async getCaseRecordDetail(record_id) {
        return await http.get(`/ui/records/cases/${record_id}`)
    },
    // 导出报告
    // options: { include_images, image_mode, include_video }
    async exportReport(record_id, type = 'task', options = {}) {
        const params = new URLSearchParams({ record_type: type })
        if (options.include_images !== undefined) params.append('include_images', options.include_images)
        if (options.image_mode) params.append('image_mode', options.image_mode)
        if (options.include_video !== undefined) params.append('include_video', options.include_video)
        
        return await http.get(`/ui/records/export/${record_id}?${params.toString()}`, {
            responseType: 'blob',
            timeout: 120000
        })
    },
    async exportReportAsync(record_id, type = 'task', options = {}) {
        const params = new URLSearchParams({ record_type: type })
        if (options.include_images !== undefined) params.append('include_images', options.include_images)
        if (options.image_mode) params.append('image_mode', options.image_mode)
        if (options.include_video !== undefined) params.append('include_video', options.include_video)
        return await http.post(`/ui/records/export-async/${record_id}?${params.toString()}`)
    },
    async getExportStatus(task_id) {
        return await http.get(`/ui/records/export-status/${task_id}`)
    },
    
    // ===== 兼容旧命名 =====
    getTaskRecordList(params) { return this.getTaskRecords(params) },
    getSuiteRecordList(params) { return this.getSuiteRecords(params) },
    getCaseRecordList(params) { return this.getCaseRecords(params) },
    // 额外兼容（不带 List 后缀）
    getTaskRecord(params) { return this.getTaskRecords(params) },
    getSuiteRecord(params) { return this.getSuiteRecords(params) },
    getCaseRecord(params) { return this.getCaseRecords(params) },
    deleteTaskRecord(record_id, params = {}) { 
        return http.delete(`/ui/records/tasks/${record_id}`, { params }) 
    },
    deleteSuiteRecord(record_id, params = {}) { 
        return http.delete(`/ui/records/suites/${record_id}`, { params }) 
    },
    batchDeleteTaskRecords(record_ids, permanent = false) {
        return http.post('/ui/records/tasks/batch-delete', { record_ids, permanent })
    },
    batchDeleteSuiteRecords(record_ids, permanent = false) {
        return http.post('/ui/records/suites/batch-delete', { record_ids, permanent })
    },
    deleteCaseRecord(record_id, params = {}) {
        return http.delete(`/ui/records/cases/${record_id}`, { params })
    },
    batchDeleteCaseRecords(record_ids, permanent = false) {
        return http.post('/ui/records/cases/batch-delete', { record_ids, permanent })
    },
    batchRestoreCaseRecords(record_ids) {
        return http.post('/ui/records/cases/batch-restore', { record_ids })
    },
    restoreCaseRecord(record_id) {
        return http.post(`/ui/records/cases/${record_id}/restore`)
    },
    exportTaskReport(record_id) { return this.exportReport(record_id, 'task') },
    exportSuiteReport(record_id) { return this.exportReport(record_id, 'suite') },
    async sendTaskReport(record_id, data = {}) {
        return await http.post(`/ui/records/tasks/${record_id}/send-report`, data, { timeout: 120000 })
    },
}
