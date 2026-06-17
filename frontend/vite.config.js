import {fileURLToPath, URL} from 'node:url'
import {defineConfig, loadEnv} from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({mode}) => {
    const env = loadEnv(mode, process.cwd(), "")
    return {
        plugins: [
            vue(),
        ],
        build: {
            chunkSizeWarningLimit: 2500,
            rollupOptions: {
                output: {
                    manualChunks(id) {
                        // 勿拆 vue / element-plus：强耦合，拆包易出现「Cannot access before initialization」白屏
                        // monaco 由 MonacoEditor 异步组件按需加载，勿放入 manualChunks
                        if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender')) {
                            return 'echarts'
                        }
                    },
                },
            },
        },
        server: {
            // 是否自动打开浏览器
            open: JSON.parse(env.VITE_OPEN),
            // 本地访问
            // host: 'localhost',
            // 0.0.0.0表示监听所有网卡的请求，包括局域网和公网
            host: '0.0.0.0',
            // 是否开启热更新
            hmr: true,
            // 端口号
            port: env.VITE_PORT
        },
        css: {
            preprocessorOptions: {
                scss: {
                    api: 'modern-compiler'
                }
            }
        },
        resolve: {
            // 配置路径别名
            alias: {
                // @代替src
                '@': fileURLToPath(new URL('./src', import.meta.url)),
            }
        },
        optimizeDeps: {
            include: [
                'vue',
                'pinia',
                'vue-router',
                'pinia-plugin-persistedstate'
            ],
        }
    }
})
