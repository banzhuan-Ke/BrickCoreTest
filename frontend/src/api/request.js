import axios from 'axios'
import {UserStore} from "@/stores/module/UserStore.js"
import {ElNotification} from 'element-plus'
import router from "@/router"

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
            window.localStorage.removeItem('token')
            ElNotification({
                message: '当前路由地址错误，您访问的接口不存在：' + response.config.url,
                type: 'error',
                duration: 1500
            })
            return Promise.reject(response)
        }
        if (response.status >= 400 && ![401, 403, 404].includes(response.status)) {
            if (response.config?.skipErrorHandler) {
                return Promise.reject(response)
            }
            const detail = response.data?.detail
            const message =
                typeof detail === 'string' && detail
                    ? detail
                    : response.status === 500
                      ? '服务器内部错误，请稍后重试'
                      : '请求失败，请检查参数后重试'
            ElNotification({
                title: response.status === 400 ? '请求错误' : response.status === 500 ? '服务错误' : '请求失败',
                message,
                type: 'error',
                duration: 2500
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
