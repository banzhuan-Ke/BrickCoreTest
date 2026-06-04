import http from '../request'

/**
 * 定时任务API模块 (Web自动化)
 * 对应后端 /schedule/* 接口
 */

export const scheduleApi = {
    // 获取定时任务列表
    async getList(params) {
        return await http.get('/schedule/jobs', { params })
    },
    // 创建定时任务
    async create(data) {
        return await http.post('/schedule/jobs', data)
    },
    // 更新定时任务
    async update(job_id, data) {
        return await http.put(`/schedule/jobs/${job_id}`, data)
    },
    // 删除定时任务
    async delete(job_id) {
        return await http.delete(`/schedule/jobs/${job_id}`)
    },
    // 切换任务状态(启用/停用)
    async toggle(job_id) {
        return await http.post(`/schedule/jobs/${job_id}/switch`)
    },
    // 获取任务执行记录
    async getRecords(job_id, params) {
        return await http.get(`/schedule/jobs/${job_id}/records`, { params })
    }
}
