import http from '../request'

/**
 * 性能测试 API 模块
 * 对应后端 /perf/* 接口
 */

// ========== 流式阶段解析器 ==========
export const perfStreamParserApi = {
    async getList() {
        return await http.get('/perf/stream-parsers', { silent403: true })
    },
    async getPreset(parser_id) {
        return await http.get(`/perf/stream-parsers/${parser_id}/preset`)
    },
    async test(data) {
        return await http.post('/perf/stream-parsers/test', data)
    }
}

// ========== 性能测试场景管理 ==========
export const perfSceneApi = {
    // 获取场景列表
    async getList(params) {
        return await http.get('/perf/scenes', { params })
    },
    // 创建场景
    async create(data) {
        return await http.post('/perf/scenes', data)
    },
    // 获取场景详情
    async getDetail(scene_id) {
        return await http.get(`/perf/scenes/${scene_id}`)
    },
    // 更新场景
    async update(scene_id, data) {
        return await http.put(`/perf/scenes/${scene_id}`, data)
    },
    // 删除场景
    async delete(scene_id) {
        return await http.delete(`/perf/scenes/${scene_id}`)
    },
    // 复制场景
    async clone(scene_id) {
        return await http.post(`/perf/scenes/${scene_id}/clone`)
    },
    // 上传 CSV
    async uploadCSV(scene_id, formData) {
        return await http.post(`/perf/scenes/${scene_id}/csv-upload`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        })
    },
    // 预览 CSV
    async previewCSV(scene_id) {
        return await http.get(`/perf/scenes/${scene_id}/csv-preview`)
    },
    // 删除 CSV
    async deleteCSV(scene_id) {
        return await http.delete(`/perf/scenes/${scene_id}/csv`)
    },
    // 更新 CSV 配置
    async updateCSVConfig(scene_id, data) {
        return await http.put(`/perf/scenes/${scene_id}/csv-config`, data)
    }
}

// ========== 性能测试执行 ==========
export const perfExecApi = {
    // 启动压测
    async start(scene_id, env_id, use_workers = false, request_detail_level = 'brief') {
        const level = request_detail_level === 'full' ? 'full' : 'brief'
        return await http.post(
            `/perf/exec/${scene_id}?env_id=${env_id}&use_workers=${use_workers}&request_detail_level=${level}`
        )
    },
    // 停止压测
    async stop(record_id) {
        return await http.post(`/perf/exec/${record_id}/stop`)
    },
    // 查询执行状态
    async getStatus(record_id) {
        return await http.get(`/perf/exec/${record_id}/status`)
    }
}

// ========== 性能测试记录 ==========
export const perfRecordApi = {
    // 获取记录列表
    async getList(params) {
        return await http.get('/perf/records', { params })
    },
    // 获取记录详情
    async getDetail(record_id) {
        return await http.get(`/perf/records/${record_id}`)
    },
    // 获取报告数据
    async getReport(record_id) {
        return await http.get(`/perf/records/${record_id}/report`)
    },
    // 分页获取请求明细（流式 / HTTP，支持状态筛选）
    async getRequestItems(record_id, params = {}) {
        return await http.get(`/perf/records/${record_id}/request-items`, { params })
    },
    // 批量删除记录
    async batchDelete(record_ids) {
        return await http.post('/perf/records/batch-delete', record_ids)
    },
    // 导出性能测试报告
    async exportReport(record_id) {
        return await http.get(`/perf/records/${record_id}/export`, {
            responseType: 'blob'
        })
    },
    // 导出 SSE 阶段压测 Excel
    async exportExcel(record_id) {
        return await http.get(`/perf/records/${record_id}/export-excel`, {
            responseType: 'blob'
        })
    },
    // 发送性能测试报告邮件
    async sendReport(record_id) {
        return await http.post(`/perf/records/${record_id}/send-report`)
    },
    // 报告对比
    async compare(record_ids) {
        return await http.post('/perf/records/compare', { record_ids })
    }
}

// ========== 性能测试 Worker 节点 ==========
export const perfWorkerApi = {
    // 获取 Worker 列表
    async getList(params) {
        return await http.get('/perf/workers', { params })
    },
    // 删除 Worker
    async delete(worker_id) {
        return await http.delete(`/perf/workers/${worker_id}`)
    }
}

// ========== 性能测试定时任务 ==========
export const perfCronApi = {
    // 获取定时任务列表
    async getList(params) {
        return await http.get('/perf/cron', { params })
    },
    // 创建定时任务
    async create(data) {
        return await http.post('/perf/cron', null, { params: data })
    },
    // 更新定时任务
    async update(job_id, data) {
        return await http.put(`/perf/cron/${job_id}`, null, { params: data })
    },
    // 删除定时任务
    async delete(job_id) {
        return await http.delete(`/perf/cron/${job_id}`)
    },
    // 启用/禁用
    async toggle(job_id) {
        return await http.post(`/perf/cron/${job_id}/toggle`)
    },
    // 获取详情
    async getDetail(job_id) {
        return await http.get(`/perf/cron/${job_id}`)
    },
    // 获取定时任务执行记录
    async getRecords(job_id, params) {
        return await http.get(`/perf/cron/${job_id}/records`, { params })
    }
}
