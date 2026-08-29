import axios from 'axios'
import {UserStore} from "@/stores/module/UserStore.js"
import {ElNotification} from 'element-plus'
import router from "@/router"

/** 从 FastAPI / Tortoise 错误体提取可读文案（detail 可能是 string / array / object） */
function formatApiErrorMessage(response) {
    const data = response?.data
    const detail = data?.detail
    if (typeof detail === 'string' && detail.trim()) {
        return detail
    }
    if (Array.isArray(detail) && detail.length) {
        const parts = detail
            .map((item) => {
                if (typeof item === 'string') return item
                if (item && typeof item === 'object') {
                    return item.msg || item.message || item.detail || ''
                }
                return ''
            })
            .filter(Boolean)
        if (parts.length) return parts.slice(0, 3).join('；')
    }
    if (detail && typeof detail === 'object') {
        if (detail.code === 'tm_premium_required' || detail.code === 'tm_premium_incompatible') {
            return detail.message || '请安装测试管理扩展包 brickcore_tm'
        }
        const msg = detail.msg || detail.message || detail.detail
        if (typeof msg === 'string' && msg.trim()) return msg
    }
    const errors = data?.errors
    if (Array.isArray(errors) && errors.length) {
        const parts = errors
            .map((e) => (typeof e === 'string' ? e : e?.msg || e?.message || ''))
            .filter(Boolean)
        if (parts.length) return parts.slice(0, 3).join('；')
    }
    if (response?.status === 500) return '服务器内部错误，请稍后重试'
    return '请求失败，请检查参数后重试'
}

function isTmPremiumDetail(detail) {
    return (
        detail &&
        typeof detail === 'object' &&
        (detail.code === 'tm_premium_required' || detail.code === 'tm_premium_incompatible')
    )
}

/** 未装扩展包时并行请求会连弹多条 503，会话内节流只提示一次 */
let _tmPremiumNotifyAt = 0
const TM_PREMIUM_NOTIFY_COOLDOWN_MS = 60_000

function notifyTmPremiumOnce(message) {
    const now = Date.now()
    if (now - _tmPremiumNotifyAt < TM_PREMIUM_NOTIFY_COOLDOWN_MS) return
    _tmPremiumNotifyAt = now
    ElNotification({
        title: '测试管理扩展包',
        message: message || '请安装测试管理扩展包 brickcore_tm',
        type: 'warning',
        duration: 5000,
    })
}

// 创建一个axios实例对象
const request = axios.create({
    baseURL: import.meta.env.VITE_BASE_API,
    timeout: 10000,
    headers: {'Content-Type': 'application/json;charset=utf-8'},
    validateStatus: function (status) {
        return true
    },
    withCredentials: false,
    crossDomain: true,
})

// 请求拦截器
request.interceptors.request.use(
    config => {
        // 对登录、注册、校验、刷新接口不做token校验
        const excludeUrls = ['/sys/users/login', '/sys/users/register', '/sys/users/verify', '/sys/users/refresh', '/sys/login-page/public']
        if (excludeUrls.includes(config.url)) {
            return config
        }
        const uStore = UserStore()
        // FormData 需由浏览器自动设置 multipart boundary，勿手动指定 Content-Type
        if (config.data instanceof FormData) {
            if (config.headers) {
                delete config.headers['Content-Type']
                delete config.headers['content-type']
            }
        }
        if (uStore.token) {
            config.headers['Authorization'] = 'Bearer ' + uStore.token
        } else {
            uStore.clearSession()
            window.location.href = '/'
        }
        return config
    }, function (error) {
        return Promise.reject(error)
    }
)

// 添加响应拦截器
request.interceptors.response.use(
    function (response) {
        // 2xx 状态码视为成功
        if (response.status >= 200 && response.status < 300) {
            return response
        }
        
        // 401未授权处理
        if (response.status === 401 && 
            !response.config.url.includes('/login') && 
            !response.config.url.includes('/register')) {
            window.localStorage.removeItem('token')
            ElNotification({
                title: '请求失败',
                message: 'token已过期或者未传递过去，您无权限访问接口:' + response.config.url,
                type: 'error',
                duration: 1500
            })
            router.push({ name: 'login' })
            ElNotification({
                message: '您未登录，请先进行登录！',
                type: 'warning',
                duration: 1500
            })
            return Promise.reject(response)
        }
        if (response.status === 403) {
            if (!response.config?.silent403) {
                ElNotification({
                    title: '权限不足',
                    message: response.data?.detail || '您没有权限执行该操作，请联系管理员分配权限',
                    type: 'error',
                    duration: 2000
                })
            }
            return Promise.reject(response)
        }
        if (response.status === 404) {
            const detail = formatApiErrorMessage(response)
            const path = response.config?.url || ''
            ElNotification({
                title: '资源不存在',
                message: detail !== '请求失败，请检查参数后重试'
                    ? detail
                    : `接口不存在或资源已删除：${path}`,
                type: 'error',
                duration: 3500
            })
            return Promise.reject(response)
        }
        if (response.status === 503) {
            if (response.config?.skipErrorHandler) {
                return Promise.reject(response)
            }
            const detail = response.data?.detail
            if (isTmPremiumDetail(detail)) {
                notifyTmPremiumOnce(formatApiErrorMessage(response))
                return Promise.reject(response)
            }
            ElNotification({
                title: '服务暂不可用',
                message: formatApiErrorMessage(response),
                type: 'warning',
                duration: 4000,
            })
            return Promise.reject(response)
        }
        if (response.status >= 400 && ![401, 403, 404, 503].includes(response.status)) {
            if (response.config?.skipErrorHandler) {
                return Promise.reject(response)
            }
            const message = formatApiErrorMessage(response)
            ElNotification({
                title: response.status === 400 ? '请求错误' : response.status === 500 ? '服务错误' : '请求失败',
                message,
                type: 'error',
                duration: 3500
            })
            return Promise.reject(response)
        }
        return Promise.reject(response)
    },
    function (error) {
        if (error.code === 'ERR_NETWORK' || error.message.includes('Network Error')) {
            ElNotification({
                title: '网络错误',
                message: '网络错误，请检查网络是否正常，检查后端服务状态！',
                type: 'error',
                duration: 1500
            })
        }
        return Promise.reject(error)
    }
)

export default request
