import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'BrickCore 使用文档',
  description: 'BrickCore 平台使用说明',
  lang: 'zh-CN',
  themeConfig: {
    nav: [
      { text: '首页', link: '/' },
      { text: '功能演示', link: '/guide/product-demo' },
      { text: '平台概览', link: '/guide/quick-start' },
    ],
    sidebar: {
      '/guide/': [
        {
          text: '快速开始',
          items: [
            { text: '使用说明', link: '/' },
            { text: '平台概览', link: '/guide/quick-start' },
            { text: '亮点功能', link: '/guide/highlights' },
            { text: '版本更新记录', link: '/guide/release-notes' },
            { text: '功能演示', link: '/guide/product-demo' },
            { text: 'Docker 部署', link: '/guide/docker-deploy' },
            { text: '项目与环境', link: '/guide/project-setup' },
            { text: '测试目录', link: '/guide/test-catalog' },
          ]
        },
        {
          text: '功能模块',
          items: [
            { text: 'UI 自动化', link: '/guide/ui-automation' },
            { text: '接口自动化', link: '/guide/api-automation' },
            { text: 'Token 授权', link: '/guide/api-auth' },
            { text: '性能测试', link: '/guide/perf-testing' },
            { text: '压测 Worker 协议', link: '/guide/perf-worker-protocol' },
            { text: '测试管理', link: '/guide/test-management' },
            { text: '测试管理扩展包', link: '/guide/brickcore-tm-pack' },
            { text: 'AI 测试', link: '/guide/ai-testing' },
            { text: '迭代资料库', link: '/guide/knowledge-base' },
            { text: '智能浏览器', link: '/guide/browser-lab' },
            { text: '平台内 AI 助手', link: '/guide/platform-assistant' },
            { text: 'MCP 外部接入', link: '/guide/mcp-server' },
          ]
        }
      ]
    },
    footer: {
      message: 'BrickCore 使用文档',
      copyright: 'Copyright © 2026 BrickCore'
    }
  }
})
