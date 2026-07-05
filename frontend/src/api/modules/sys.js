import http from '../request'

/**
 * 系统管理API模块
 * 对应后端 /sys/* 接口
 */

// ========== 用户管理 ==========
export const userApi = {
    // 登录
    async login(data) {
        return await http.post('/sys/users/login', data)
    },
    // 注册
    async register(data) {
        return await http.post('/sys/users/register', data)
    },
    // 校验token
    async verifyToken(params) {
        return await http.post('/sys/users/verify', params)
    },
    // 刷新token
    async refreshToken(params) {
        return await http.post('/sys/users/refresh', params)
    },
    // 创建用户
    async create(data) {
        return await http.post('/sys/users', data)
    },
    // 获取用户列表
    async getList(params) {
        return await http.get('/sys/users', { params })
    },
    // 更新用户
    async update(user_id, data) {
        return await http.put(`/sys/users/${user_id}`, data)
    },
    // 删除用户
    async delete(user_id) {
        return await http.delete(`/sys/users/${user_id}`)
    },
    // 启用/停用用户
    async toggleActive(user_id) {
        return await http.put(`/sys/users/${user_id}/active`)
    },
    // 获取当前用户信息（个人中心）
    async getProfile() {
        return await http.get('/sys/users/profile')
    },
    // 更新个人资料
    async updateProfile(data) {
        return await http.put('/sys/users/profile', data)
    },
    // 修改密码
    async changePassword(data) {
        return await http.put('/sys/users/profile/password', data)
    },
    
    // ===== 兼容旧命名（大驼峰）=====
    LoginApi(data) { return this.login(data) },
    RegisterApi(data) { return this.register(data) },
    createUser(data) { return this.create(data) },
    verifyToken(params) { return this.verifyToken(params) },
    updateUser(user_id, data) { return this.update(user_id, data) },
    getUserList(params) { return this.getList(params) },
    deleteUser(user_id) { return this.delete(user_id) },
    toggleActive(user_id) { return this.toggleActive(user_id) }
}

// ========== 角色管理 ==========
export const roleApi = {
    // 获取角色列表
    async getList(params) {
        return await http.get('/sys/roles', { params })
    },
    // 创建角色
    async create(data) {
        return await http.post('/sys/roles', data)
    },
    // 更新角色
    async update(role_id, data) {
        return await http.put(`/sys/roles/${role_id}`, data)
    },
    // 删除角色
    async delete(role_id) {
        return await http.delete(`/sys/roles/${role_id}`)
    },
    // 获取权限列表
    async getPermissions() {
        return await http.get('/sys/roles/permissions')
    },
    
    // ===== 兼容旧命名 =====
    getRoleList(params) { return this.getList(params) },
    createRole(data) { return this.create(data) },
    updateRole(role_id, data) { return this.update(role_id, data) },
    deleteRole(role_id) { return this.delete(role_id) }
}

// ========== 邀请码管理 ==========
export const inviteCodeApi = {
    async getList(params) {
        return await http.get('/sys/invite-codes', { params })
    },
    async create(data) {
        return await http.post('/sys/invite-codes', data)
    },
    async update(invite_id, data) {
        return await http.put(`/sys/invite-codes/${invite_id}`, data)
    },
    async delete(invite_id) {
        return await http.delete(`/sys/invite-codes/${invite_id}`)
    },
}

// ========== 项目管理 ==========
export const projectApi = {
    // 获取项目列表
    async getList(params) {
        return await http.get('/sys/projects', { params })
    },
    // 创建项目
    async create(data) {
        return await http.post('/sys/projects', data)
    },
    // 更新项目
    async update(project_id, data) {
        return await http.put(`/sys/projects/${project_id}`, data)
    },
    // 删除项目
    async delete(project_id) {
        return await http.delete(`/sys/projects/${project_id}`)
    },
    async getDetail(project_id) {
        return await http.get(`/sys/projects/${project_id}`)
    },
    async setDefault(project_id) {
        return await http.put(`/sys/projects/${project_id}/default`)
    },
    async clearDefault() {
        return await http.delete('/sys/projects/default')
    },

    // ===== 项目成员 =====
    async getMembers(project_id, params) {
        return await http.get(`/sys/projects/${project_id}/members`, { params })
    },
    async addMember(project_id, data) {
        return await http.post(`/sys/projects/${project_id}/members`, data)
    },
    async updateMember(project_id, member_id, data) {
        return await http.put(`/sys/projects/${project_id}/members/${member_id}`, data)
    },
    async removeMember(project_id, member_id) {
        return await http.delete(`/sys/projects/${project_id}/members/${member_id}`)
    },
    async transferOwner(project_id, data) {
        return await http.post(`/sys/projects/${project_id}/members/transfer-owner`, data)
    },
    async getMemberRoles(project_id) {
        return await http.get(`/sys/projects/${project_id}/members/roles`)
    },
    
    // ===== 兼容旧命名 =====
    getProjectList(params) { return this.getList(params) },
    createProject(data) { return this.create(data) },
    updateProject(project_id, data) { return this.update(project_id, data) },
    deleteProject(project_id) { return this.delete(project_id) },
    getProjectDetail(project_id) { return this.getDetail(project_id) },
    setDefaultProject(project_id) { return this.setDefault(project_id) }
}

// ========== 环境管理 ==========
export const envApi = {
    // 获取环境列表
    async getList(params) {
        return await http.get('/sys/envs', { params })
    },
    // 创建环境
    async create(data) {
        return await http.post('/sys/envs', data)
    },
    // 更新环境
    async update(env_id, data) {
        return await http.put(`/sys/envs/${env_id}`, data)
    },
    // 删除环境
    async delete(env_id) {
        return await http.delete(`/sys/envs/${env_id}`)
    },
    
    // ===== 兼容旧命名 =====
    getEnvironmentList(params) { return this.getList(params) },
    getEnvList(params) { return this.getList(params) },
    createEnvironment(data) { return this.create(data) },
    createEnv(data) { return this.create(data) },
    updateEnvironment(env_id, data) { return this.update(env_id, data) },
    updateEnv(env_id, data) { return this.update(env_id, data) },
    deleteEnvironment(env_id) { return this.delete(env_id) },
    deleteEnv(env_id) { return this.delete(env_id) }
}

// ========== 设备管理 ==========
export const deviceApi = {
    // 获取设备列表
    async getList(params, config = {}) {
        return await http.get('/sys/devices', { params, ...config })
    },
    // 创建设备
    async create(data) {
        return await http.post('/sys/devices', data)
    },
    // 获取设备详情
    async getDetail(device_id) {
        return await http.get(`/sys/devices/${device_id}`)
    },
    // 更新设备
    async update(device_id, data) {
        return await http.put(`/sys/devices/${device_id}`, data)
    },
    // 删除设备
    async delete(device_id) {
        return await http.delete(`/sys/devices/${device_id}`)
    },
    async stop(device_id) {
        return await http.post(`/sys/devices/${device_id}/stop`)
    },
    // WebSocket订阅日志
    wsLogUrl(device_id) {
        return `${import.meta.env.VITE_WS_URL}/sys/devices/${device_id}/ws/log`
    },
    // WebSocket订阅屏幕
    wsScreenUrl(device_id) {
        return `${import.meta.env.VITE_WS_URL}/sys/devices/${device_id}/ws/screen`
    },
    // WebSocket订阅状态
    wsStatusUrl(device_id) {
        return `${import.meta.env.VITE_WS_URL}/sys/devices/${device_id}/ws/status`
    },
    
    // ===== 兼容旧命名 =====
    getDeviceList(params, config) { return this.getList(params, config) },
    getDeviceDetail(device_id) { return this.getDetail(device_id) },
    createDevice(data) { return this.create(data) },
    updateDevice(device_id, data) { return this.update(device_id, data) },
    deleteDevice(device_id) { return this.delete(device_id) },
    stopDevice(device_id) { return this.stop(device_id) },
}

// ========== 文件管理 ==========
export const fileApi = {
    /**
     * 上传头像（multipart/form-data）
     * @param {File} file - 图片文件
     * @returns {Promise<string>} 头像访问URL
     */
    async uploadAvatar(file) {
        const formData = new FormData()
        formData.append('file', file)
        const res = await http.post('/sys/files/upload-avatar', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        })
        return res.data?.data || ''
    },

    /**
     * 获取单个文件的预签名 URL
     * @param {string} filename - 文件名
     * @returns {Promise<string>} 预签名 URL
     */
    async getPresignedUrl(filename) {
        const res = await http.post('/sys/files/presigned-url', { filename })
        return res.data
    },

    /**
     * 批量获取预签名 URL
     * @param {string[]} filenames - 文件名列表
     * @returns {Promise<Object>} {filename: url} 映射
     */
    async getBatchPresignedUrls(filenames) {
        const res = await http.post('/sys/files/batch-presigned-urls', { filenames })
        // 后端返回 {code: 200, data: {...}, message: "success"}
        return res.data?.data || {}
    },

    _isPresignedUrl(url) {
        return url && typeof url === 'string' && url.includes('X-Amz-Signature=')
    },

    /** 对象存储直链（需换预签名才能在浏览器展示） */
    _needsPresignedUrl(url) {
        if (!url || typeof url !== 'string' || this._isPresignedUrl(url)) return false
        const cleanUrl = url.split('?')[0]
        if (/\.(png|jpe?g|gif|webm)$/i.test(cleanUrl)) return true
        return cleanUrl.includes('aliyuncs.com') || cleanUrl.includes('/minio/')
    },

    _collectReportFilenames(runInfo) {
        const names = []
        const push = (url) => {
            const fn = this._extractFilename(url)
            if (fn) names.push(fn)
        }
        if (this._needsPresignedUrl(runInfo.img)) push(runInfo.img)
        if (this._needsPresignedUrl(runInfo.video_url)) push(runInfo.video_url)
        if (runInfo.steps?.length) {
            runInfo.steps.forEach((step) => {
                const shot = step.screenshot || step.image
                if (this._needsPresignedUrl(shot)) push(shot)
            })
        }
        return [...new Set(names)]
    },

    _applyPresignedToUrl(url, urlMap) {
        if (!this._needsPresignedUrl(url)) return url
        const filename = this._extractFilename(url)
        return (filename && urlMap[filename]) ? urlMap[filename] : url
    },

    /**
     * 处理报告数据中的图片 URL
     * 将 MinIO 对象 URL 替换为预签名 URL（供浏览器加载）
     */
    async processReportUrls(runInfo) {
        if (!runInfo) return runInfo

        const uniqueUrls = this._collectReportFilenames(runInfo)
        if (uniqueUrls.length === 0) {
            return runInfo
        }

        try {
            const urlMap = await this.getBatchPresignedUrls(uniqueUrls)
            if (runInfo.img) {
                runInfo.img = this._applyPresignedToUrl(runInfo.img, urlMap)
            }
            if (runInfo.video_url) {
                runInfo.video_url = this._applyPresignedToUrl(runInfo.video_url, urlMap)
            }
            if (runInfo.steps?.length) {
                runInfo.steps.forEach((step) => {
                    if (step.screenshot) {
                        step.screenshot = this._applyPresignedToUrl(step.screenshot, urlMap)
                    }
                    if (step.image) {
                        step.image = this._applyPresignedToUrl(step.image, urlMap)
                    }
                })
            }
        } catch (error) {
            console.error('[FileApi] 处理预签名 URL 失败:', error)
        }

        return runInfo
    },

    /**
     * 从完整 URL 中提取文件名
     * @param {string} url - 完整 URL
     * @returns {string} 文件名
     */
    _extractFilename(url) {
        if (!url) return ''
        // 处理 http://192.168.x.x:9200/bucket/filename?sign=xxx 格式
        // 去掉查询参数后再匹配文件名
        const cleanUrl = url.split('?')[0]
        const match = cleanUrl.match(/\/([^\/]+\.(?:png|jpg|jpeg|gif|webm))$/)
        return match ? match[1] : ''
    }
}

// ========== 资产收藏 ==========
export const assetFavoriteApi = {
    async list(projectId) {
        return await http.get('/sys/asset-favorites', { params: { project_id: projectId } })
    },
    async add(projectId, data) {
        return await http.post('/sys/asset-favorites', data, { params: { project_id: projectId } })
    },
    async remove(projectId, assetType, assetId) {
        return await http.delete('/sys/asset-favorites', {
            params: { project_id: projectId, asset_type: assetType, asset_id: assetId },
        })
    },
}

// ========== 项目内搜索 ==========
export const searchApi = {
    async search(projectId, q, limit = 8) {
        return await http.get('/sys/search', { params: { project_id: projectId, q, limit } })
    },
}

// ========== 首页看板 ==========
export const dashboardApi = {
    // 获取看板统计数据
    async getDashboard(params) {
        return await http.get('/sys/dashboard', { params })
    }
}

// ========== MCP 接入 ==========
export const mcpApi = {
    async getInfo() {
        return await http.get('/sys/mcp/info')
    },
    async getConfig() {
        return await http.get('/sys/mcp/config')
    },
    async updateConfig(data) {
        return await http.put('/sys/mcp/config', data)
    }
}

// ========== SSE 解析配置 ==========
export const streamParserConfigApi = {
    async getBuiltinParsers() {
        return await http.get('/sys/stream-parser-configs/builtin-parsers')
    },
    async getList(params) {
        return await http.get('/sys/stream-parser-configs', { params })
    },
    async getDetail(configId) {
        return await http.get(`/sys/stream-parser-configs/${configId}`)
    },
    async create(data) {
        return await http.post('/sys/stream-parser-configs', data)
    },
    async update(configId, data) {
        return await http.put(`/sys/stream-parser-configs/${configId}`, data)
    },
    async delete(configId) {
        return await http.delete(`/sys/stream-parser-configs/${configId}`)
    },
    async test(data) {
        return await http.post('/sys/stream-parser-configs/test', data)
    }
}

// ========== 登录页配置 ==========
const LOGIN_PAGE_API_TIMEOUT = 30000

export const loginPageApi = {
    async getPublicConfig() {
        return await http.get('/sys/login-page/public', { timeout: LOGIN_PAGE_API_TIMEOUT })
    },
    async getConfig() {
        return await http.get('/sys/login-page/config', { timeout: LOGIN_PAGE_API_TIMEOUT })
    },
    async updateConfig(data) {
        return await http.put('/sys/login-page/config', data, { timeout: LOGIN_PAGE_API_TIMEOUT })
    },
    async uploadBackground(file, theme) {
        const formData = new FormData()
        formData.append('file', file)
        return await http.post(`/sys/login-page/upload-background?theme=${theme}`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
            timeout: LOGIN_PAGE_API_TIMEOUT,
        })
    },
}

// ========== 平台全局设置 ==========
export const platformSettingsApi = {
    async getConfig() {
        return await http.get('/sys/platform-settings/config')
    },
    async updateConfig(data) {
        return await http.put('/sys/platform-settings/config', data)
    },
}

// ========== 操作日志 ==========
export const operationLogApi = {
    async getList(params) {
        return await http.get('/sys/operation-logs', { params })
    },
    async batchDelete(ids) {
        return await http.delete('/sys/operation-logs', { data: { ids } })
    },
    async purgeNoiseLogs(batchSize = 500) {
        return await http.delete('/sys/operation-logs/noise', {
            params: { batch_size: batchSize },
            timeout: 120000,
        })
    },
}

// ========== 通知配置 ==========
export const notificationApi = {
    async getConfigList(project_id) {
        return await http.get('/sys/notifications/config', { params: { project_id } })
    },
    async createConfig(project_id, data) {
        return await http.post('/sys/notifications/config', data, { params: { project_id } })
    },
    async updateConfig(config_id, data) {
        return await http.put(`/sys/notifications/config/${config_id}`, data)
    },
    async deleteConfig(config_id) {
        return await http.delete(`/sys/notifications/config/${config_id}`)
    },
    async testConfig(config_id) {
        return await http.post(`/sys/notifications/config/${config_id}/test`)
    },
    async getSmtpConfig() {
        return await http.get('/sys/notifications/smtp')
    },
    async updateSmtpConfig(data) {
        return await http.put('/sys/notifications/smtp', data)
    },
    async getLogList(params) {
        return await http.get('/sys/notifications/logs', { params })
    },
    async batchDeleteLogs(ids) {
        return await http.delete('/sys/notifications/logs', { data: { ids } })
    }
}

// ========== 模块管理（已废弃，请使用 catalogApi）==========
import { catalogApi } from './catalog'

/** @deprecated 请使用 catalogApi */
export const moduleApi = {
    getList(params) { return catalogApi.getList(params) },
    create(data) { return catalogApi.create(data) },
    update(module_id, data) { return catalogApi.update(module_id, data) },
    delete(module_id) { return catalogApi.delete(module_id) },
    getDetail(module_id) { return catalogApi.getDetail(module_id) },
    getModuleList(params) { return catalogApi.getList(params) },
    createModule(data) { return catalogApi.create(data) },
    updateModule(module_id, data) { return catalogApi.update(module_id, data) },
    deleteModule(module_id) { return catalogApi.delete(module_id) },
    getModuleDetail(module_id) { return catalogApi.getDetail(module_id) },
    getListByProject(params) { return catalogApi.getList(params) }
}
