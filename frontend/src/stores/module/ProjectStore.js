import {defineStore} from 'pinia'
import http from "@/api/index.js"

export const ProjectStore = defineStore('proStore', {
    state: () => {
        return {
            // 当前选中的项目
            projectInfo: {},
            //是否禁用菜单
            isDisabled: true,
            //项目环境列表
            envList: [],
            // 统一测试目录列表
            catalogList: [],
            //任务列表
            taskList: [],
            //设备列表
            deviceList: []
        }
    },
    getters: {
        /** @deprecated 请使用 catalogList */
        moduleList: (state) => state.catalogList
    },
    actions: {
        /** 切换/应用当前项目并加载关联数据 */
        async applyProject(pro) {
            if (!pro?.id) return false
            this.projectInfo = {
                id: pro.id,
                name: pro.name,
                global_vars: pro.global_vars && typeof pro.global_vars === 'object' ? pro.global_vars : {},
                default_headers: Array.isArray(pro.default_headers) ? pro.default_headers : [],
            }
            this.isDisabled = false
            await Promise.all([
                this.getEnvironmentList(),
                this.getCatalogList(),
                this.getTaskList(),
                this.getDeviceList(),
                this.refreshProjectGlobals(),
            ])
            return true
        },
        /** 刷新当前项目的 global_vars（供变量插入等使用） */
        async refreshProjectGlobals() {
            if (!this.projectInfo?.id) return
            try {
                const response = await http.projectApi.getProjectDetail(this.projectInfo.id)
                const data = response.data?.data ?? response.data
                if (data && typeof data === 'object') {
                    this.projectInfo = {
                        ...this.projectInfo,
                        name: data.name ?? this.projectInfo.name,
                        global_vars: data.global_vars && typeof data.global_vars === 'object' ? data.global_vars : {},
                        default_headers: Array.isArray(data.default_headers) ? data.default_headers : [],
                    }
                }
            } catch {
                /* 忽略，保留已有缓存 */
            }
        },
        // 获取项目环境列表
        async getEnvironmentList() {
            const response = await http.environmentApi.getEnvironmentList({
                project_id: this.projectInfo.id,
            })
            if (response.status === 200) {
                this.envList = response.data
            }
        },
        // 获取统一测试目录列表
        async getCatalogList() {
            const response = await http.catalogApi.getList({
                project_id: this.projectInfo.id
            })
            if (response.status === 200) {
                this.catalogList = response.data
            }
        },
        /** @deprecated 请使用 getCatalogList */
        async getModuleList() {
            return this.getCatalogList()
        },
        // 获取任务列表
        async getTaskList() {
            const response = await http.taskApi.getTaskList({
                project_id: this.projectInfo.id
            })
            if (response.status === 200) {
                // 后端返回 {total, data} 分页格式，提取 data 数组
                this.taskList = response.data.data || []
            }
        },
        // 获取设备列表
        async getDeviceList() {
            const response = await http.deviceApi.getDeviceList()
            if (response.status === 200) {
                this.deviceList = response.data
            }
        },
        // 获取在线设备列表
        async getOnlineDevice() {
            const response = await http.deviceApi.getDeviceList({status: '在线'})
            if (response.status === 200) {
                this.deviceList = response.data
            }
        }
    },
    persist: {
        // 是否开启持久化
        enabled: true,
        // 用户状态信息持久化配置
        strategies: [
            {
                key: 'projectStore',
                storage: localStorage
            }
        ]
    }
})
