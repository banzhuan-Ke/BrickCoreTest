import http from '../request'

/**
 * API自动化测试API模块
 * 对应后端 /api-module/* 接口
 */

// ========== 接口定义管理 ==========
export const httpApi = {
    // 获取接口列表
    async getList(params) {
        return await http.get('/api-module/definition', { params })
    },
    // 创建接口
    async create(data) {
        return await http.post('/api-module/definition', data)
    },
    // 获取接口详情
    async getDetail(api_id) {
        return await http.get(`/api-module/definition/${api_id}`)
    },
    // 更新接口
    async update(api_id, data) {
        return await http.put(`/api-module/definition/${api_id}`, data)
    },
    // 删除接口
    async delete(api_id) {
        return await http.delete(`/api-module/definition/${api_id}`)
    },
    // 批量删除接口
    async batchDelete(api_ids) {
        return await http.post('/api-module/definition/batch-delete', api_ids)
    },
    // 检测接口关联用例同步状态
    async syncCheck(api_id) {
        return await http.get(`/api-module/definition/${api_id}/sync-check`)
    },
    // 接口关联用例列表
    async getLinkedCases(api_id, params = {}) {
        return await http.get(`/api-module/definition/${api_id}/linked-cases`, { params })
    },
    // 调试接口（后端默认 30s；axios 需略大于后端 timeout，避免先被 10s 全局超时截断）
    async debug(data) {
        const payload = { timeout: 30, ...data }
        const sec = Number(payload.timeout) || 30
        return await http.post('/api-module/debug', payload, {
            timeout: sec * 1000 + 5000
        })
    },
    // 上传接口调试文件
    async uploadBodyFile(file) {
        const formData = new FormData()
        formData.append('file', file)
        return await http.post('/api-module/files/upload', formData)
    },
    // 解析cURL（预览）
    async parseCurl(data) {
        return await http.post('/api-module/import/curl/parse', data)
    },
    // 导入cURL（保存）
    async importCurl(data) {
        return await http.post('/api-module/import/curl', data)
    },
    // 导入Swagger文件
    async importSwagger(project_id, file, catalog_id) {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('project_id', project_id)
        if (catalog_id) formData.append('catalog_id', catalog_id)
        return await http.post('/api-module/import/swagger', formData)
    },
    // 导入Postman文件
    async importPostman(project_id, file, catalog_id) {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('project_id', project_id)
        if (catalog_id) formData.append('catalog_id', catalog_id)
        return await http.post('/api-module/import/postman', formData)
    }
}

// ========== 接口用例管理 ==========
export const httpCaseApi = {
    // 获取用例列表
    async getList(params) {
        return await http.get('/api-module/case', { params })
    },
    // 创建用例
    async create(data) {
        return await http.post('/api-module/case', data)
    },
    // 获取用例详情
    async getDetail(case_id) {
        return await http.get(`/api-module/case/${case_id}`)
    },
    // 更新用例
    async update(case_id, data) {
        return await http.put(`/api-module/case/${case_id}`, data)
    },
    // 删除用例
    async delete(case_id) {
        return await http.delete(`/api-module/case/${case_id}`)
    },
    // 批量删除用例
    async batchDelete(case_ids) {
        return await http.post('/api-module/case/batch-delete', case_ids)
    },
    // 复制用例
    async copy(case_id) {
        return await http.post(`/api-module/case/${case_id}/copy`)
    },
    // 批量导出用例（返回 blob）
    async exportCases(data) {
        return await http.post('/api-module/case/export', data, { responseType: 'blob' })
    },
    // 批量导入用例
    async importCases(formData) {
        return await http.post('/api-module/case/import', formData)
    },
    async previewVariables(data) {
        return await http.post('/api-module/variables/preview', data)
    },
    async batchUpdateCatalog(data) {
        return await http.post('/api-module/case/batch-update-catalog', data)
    },
}

// ========== 接口套件管理 ==========
export const httpSuiteApi = {
    // 获取套件列表
    async getList(params) {
        return await http.get('/api-module/suite', { params })
    },
    // 创建套件
    async create(data) {
        return await http.post('/api-module/suite', data)
    },
    // 获取套件详情
    async getDetail(suite_id) {
        return await http.get(`/api-module/suite/${suite_id}`)
    },
    // 更新套件
    async update(suite_id, data) {
        return await http.put(`/api-module/suite/${suite_id}`, data)
    },
    // 删除套件
    async delete(suite_id) {
        return await http.delete(`/api-module/suite/${suite_id}`)
    },
    // 批量删除套件
    async batchDelete(suite_ids) {
        return await http.post('/api-module/suite/batch-delete', suite_ids)
    },
    // 获取套件用例列表
    async getCases(suite_id) {
        return await http.get(`/api-module/suite/${suite_id}/cases`)
    },
    // 更新套件用例
    async updateCases(suite_id, data) {
        return await http.put(`/api-module/suite/${suite_id}/cases`, data)
    }
}

// ========== 执行管理 ==========
export const httpExecApi = {
    // 执行用例（单条，超时 120s）
    async runCase(case_id, data) {
        return await http.post(`/api-module/exec/cases/${case_id}`, data, { timeout: 120000 })
    },
    // 执行套件（同步，不推荐用于用例较多的套件）
    async runSuite(suite_id, data) {
        return await http.post(`/api-module/exec/suites/${suite_id}`, data, { timeout: 120000 })
    },
    // 异步执行套件（后台执行，立即返回 record_id）
    async runSuiteAsync(suite_id, data) {
        return await http.post(`/api-module/exec/suites/${suite_id}/async-run`, data)
    },
    // 批量执行用例（超时 120s）
    async runBatch(data) {
        return await http.post('/api-module/exec/batch-run', data, { timeout: 120000 })
    }
}

// ========== 执行记录 ==========
export const httpRecordApi = {
    // 获取用例执行记录
    async getCaseRecords(params) {
        return await http.get('/api-module/records/cases', { params })
    },
    // 获取套件执行记录
    async getSuiteRecords(params) {
        return await http.get('/api-module/records/suites', { params })
    },
    // 获取统一执行记录（套件+计划合并）
    async getAllRecords(params) {
        return await http.get('/api-module/records/all', { params })
    },
    // 获取用例记录详情
    async getCaseRecordDetail(record_id) {
        return await http.get(`/api-module/records/cases/${record_id}`)
    },
    // 获取套件记录详情
    async getSuiteRecordDetail(record_id) {
        return await http.get(`/api-module/records/suites/${record_id}`)
    },
    // 导出套件执行报告(HTML)
    async exportSuiteReport(record_id) {
        return await http.get(`/api-module/records/suites/${record_id}/report`, {
            responseType: 'blob'
        })
    },
    // 发送 API 测试报告邮件
    async sendSuiteReport(record_id) {
        return await http.post(`/api-module/records/suites/${record_id}/send-report`)
    },
    // 批量删除套件执行记录
    async batchDeleteSuiteRecords(record_ids) {
        return await http.post('/api-module/records/suites/batch-delete', record_ids)
    },
    // 批量删除计划执行记录
    async batchDeletePlanRecords(record_ids) {
        return await http.post('/api-module/plan-records/batch-delete', record_ids)
    }
}

// ========== 定时任务 ==========
export const httpCronApi = {
    // 获取定时任务列表
    async getList(params) {
        return await http.get('/api-module/cron', { params })
    },
    // 创建定时任务
    async create(data) {
        return await http.post('/api-module/cron', data)
    },
    // 更新定时任务
    async update(cron_id, data) {
        return await http.put(`/api-module/cron/${cron_id}`, data)
    },
    // 删除定时任务
    async delete(cron_id) {
        return await http.delete(`/api-module/cron/${cron_id}`)
    },
    // 批量删除定时任务
    async batchDelete(cron_ids) {
        return await http.post('/api-module/cron/batch-delete', cron_ids)
    },
    // 切换任务状态
    async toggle(cron_id) {
        return await http.post(`/api-module/cron/${cron_id}/toggle`)
    }
}

// ========== 测试计划 ==========
export const httpPlanApi = {
    // 获取计划列表（分页）
    async getList(params) {
        return await http.get('/api-module/plan', { params })
    },
    // 获取计划详情（含 items）
    async getDetail(plan_id) {
        return await http.get(`/api-module/plan/${plan_id}`)
    },
    // 创建计划
    async create(data) {
        return await http.post('/api-module/plan', data)
    },
    // 更新计划基本信息
    async update(plan_id, data) {
        return await http.put(`/api-module/plan/${plan_id}`, data)
    },
    // 删除计划（软删除）
    async delete(plan_id) {
        return await http.delete(`/api-module/plan/${plan_id}`)
    },
    // 批量删除计划
    async batchDelete(plan_ids) {
        return await http.post('/api-module/plan/batch-delete', plan_ids)
    },
    // 获取计划 Items
    async getItems(plan_id) {
        return await http.get(`/api-module/plan/${plan_id}/items`)
    },
    // 全量更新计划 Items（保存排序+内容）
    async updateItems(plan_id, data) {
        return await http.put(`/api-module/plan/${plan_id}/items`, data)
    },
    // 追加整个套件
    async addSuite(plan_id, data) {
        return await http.post(`/api-module/plan/${plan_id}/items/add-suite`, data)
    },
    // 批量追加用例
    async addCases(plan_id, data) {
        return await http.post(`/api-module/plan/${plan_id}/items/add-cases`, data)
    },
    // 删除单个 Item
    async removeItem(plan_id, item_id) {
        return await http.delete(`/api-module/plan/${plan_id}/items/${item_id}`)
    },
    // 执行测试计划（同步，保留兼容）
    async runPlan(plan_id, data) {
        return await http.post(`/api-module/plan/${plan_id}/run`, data, { timeout: 120000 })
    },
    // 异步执行测试计划（后台执行，立即返回 record_id）
    async runPlanAsync(plan_id, data) {
        return await http.post(`/api-module/plan/${plan_id}/async-run`, data)
    },
    // 获取计划执行记录列表
    async getPlanRecords(plan_id, params) {
        return await http.get(`/api-module/plan/${plan_id}/records`, { params })
    },
    // 获取计划执行记录详情
    async getPlanRecordDetail(plan_id, record_id) {
        return await http.get(`/api-module/plan/${plan_id}/records/${record_id}`)
    },
    // 通过 record_id 直接获取计划执行记录详情（无需 plan_id，用于报告页）
    async getPlanRecordById(record_id) {
        return await http.get(`/api-module/plan-records/${record_id}`)
    },
    // 批量删除计划执行记录
    async batchDeletePlanRecords(record_ids) {
        return await http.post('/api-module/plan-records/batch-delete', record_ids)
    },
    // 导出计划执行报告(HTML)
    async exportPlanReport(record_id) {
        return await http.get(`/api-module/plan-records/${record_id}/report`, {
            responseType: 'blob'
        })
    },
    // 发送计划测试报告邮件
    async sendPlanReport(record_id) {
        return await http.post(`/api-module/plan-records/${record_id}/send-report`)
    },
    async saveAsTemplate(plan_id, data) {
        return await http.post(`/api-module/plan/${plan_id}/save-as-template`, data)
    },
    async createFromTemplate(template_id, data) {
        return await http.post(`/api-module/plan/from-template/${template_id}`, data)
    },
    async getTemplates(params) {
        return await http.get('/api-module/plan', { params: { ...params, templates_only: true } })
    },
}

/**
 * Mock 接口管理
 */
export const httpMockApi = {
    async getList(params) {
        return await http.get('/api-module/mock', { params })
    },
    async create(data) {
        return await http.post('/api-module/mock', data)
    },
    async getDetail(id) {
        return await http.get(`/api-module/mock/${id}`)
    },
    async update(id, data) {
        return await http.put(`/api-module/mock/${id}`, data)
    },
    async delete(id) {
        return await http.delete(`/api-module/mock/${id}`)
    },
    async toggle(id) {
        return await http.post(`/api-module/mock/${id}/toggle`)
    }
}
