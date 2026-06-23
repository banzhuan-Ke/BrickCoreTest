import {defineStore} from 'pinia'
import {useDark} from '@vueuse/core'
import {applyUiTheme, UI_THEMES, isValidUiTheme} from '@/utils/theme'

/** 界面风格单独存 localStorage，与登录会话解耦，退出登录不丢失 */
export function readUiThemeFromStorage() {
    const dedicated = localStorage.getItem('uiTheme')
    if (isValidUiTheme(dedicated)) {
        return dedicated
    }
    try {
        const raw = localStorage.getItem('userInfo')
        if (raw) {
            const parsed = JSON.parse(raw)
            const legacy = parsed?.uiTheme
            if (isValidUiTheme(legacy)) {
                localStorage.setItem('uiTheme', legacy)
                return legacy
            }
        }
    } catch {
        // ignore
    }
    return UI_THEMES.pro
}

export const UserStore = defineStore('uStore', {
    // 全局的状态(数据)
    state: () => {
        return {
            // 保存用户token
            token: "",
            // 保存用户信息
            username: "",
            userInfo: null,
            // 侧边菜单是否折叠
            isCollapse: false,
            // 选项卡记录
            tabs: [],
            // 表示用户是否登录
            isAuthenticated: false,
            // 用户权限列表
            permissions: [],
            // 暗黑模式存储的变量
            darkMode: useDark().value,
            // 界面风格：classic 经典 | pro 清新 Pro
            uiTheme: readUiThemeFromStorage(),
        }
    },
    actions: {
        // 保存路由信息到tabs中的方法
        addTabs(route) {
            // 查找该路由地方已经保存
            const res = this.tabs.find((item, index) => {
                return route.path === item.path
            })
            // 如果没有保存，则进行保存
            if (!res) {
                this.tabs.push({
                    name: route.meta.title,
                    path: route.path,
                    icon: route.meta.icon
                })
            }
        },
        // 删除tabs中的路由信息
        deleteTabs(path) {
            this.tabs = this.tabs.filter((item) => {
                return item.path !== path
            })
        },
        // 清空所有标签
        clearAllTabs() {
            this.tabs = []
        },
        // 判断是否有指定权限
        hasPermission(perm) {
            const userInfo = this.userInfo
            if (userInfo && userInfo.is_superuser) return true
            const perms = this.permissions || []
            return perms.includes(perm)
        },
        // 判断是否有任意一个权限
        hasAnyPermission(perms) {
            const userInfo = this.userInfo
            if (userInfo && userInfo.is_superuser) return true
            const list = this.permissions || []
            return perms.some(p => list.includes(p))
        },
        // 切换界面风格
        setUiTheme(theme) {
            this.uiTheme = isValidUiTheme(theme) ? theme : UI_THEMES.classic
            localStorage.setItem('uiTheme', this.uiTheme)
            applyUiTheme(this.uiTheme, this.darkMode)
        },
        // 切换暗黑模式方法（仅经典风格生效）
        toggleDarkMode() {
            if (this.uiTheme === UI_THEMES.pro) return
            const dark = useDark()
            this.darkMode = !this.darkMode
            dark.value = this.darkMode
            localStorage.setItem('darkMode', this.darkMode)
            applyUiTheme(this.uiTheme, this.darkMode)
        },
        // 应用当前主题到 document（启动时调用）
        syncThemeToDocument() {
            applyUiTheme(this.uiTheme, this.darkMode)
        },
        /** 退出登录：清会话数据，保留界面风格/暗黑模式 */
        clearSession() {
            this.token = ""
            this.username = ""
            this.userInfo = null
            this.tabs = []
            this.isAuthenticated = false
            this.permissions = []
            this.uiTheme = readUiThemeFromStorage()
            this.syncThemeToDocument()
        },
    },
    // 持久化存储配置
    persist: {
        // 持久化存储开启
        enabled: true,
        // 用户状态信息持久化配置
        strategies: [
            {
                // 存储键名
                key: 'userInfo',
                // 使用localStorage
                storage: localStorage,
                // 指定要持久化的字段
                paths: ['token', 'username', 'userInfo', 'isAuthenticated', 'isCollapse', 'permissions']
            }
        ]
    }
})