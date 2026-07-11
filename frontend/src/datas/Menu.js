// 使用 Element Plus 图标（矢量图标，风格统一）
// 图标名称参考：https://element-plus.org/zh-CN/component/icon.html

// 菜单分组配置 - 按功能模块重新组织
export const MenuGroups = [
    {
        title: '数据看板',
        icon: 'DataLine',
        expanded: false,
        items: [
            {
                name: '首页看板',
                path: '/dashboard',
                icon: 'Odometer',
                permission: 'project:view'
            }
        ]
    },
    {
        title: '项目配置',
        icon: 'SetUp',
        expanded: false,
        items: [
            {
                name: '项目管理',
                path: '/project',
                icon: 'FolderOpened',
                permission: 'project:view'
            },
            {
                name: '环境配置',
                path: '/environment',
                icon: 'OfficeBuilding',
                permission: 'environment:view'
            },
            {
                name: '测试目录',
                path: '/catalog',
                icon: 'Grid',
                permission: 'module:view'
            },
        ]
    },
    {
        title: 'Web 自动化',
        icon: 'Mouse',
        expanded: false,
        items: [
            {
                name: '用例管理',
                path: '/case',
                icon: 'DocumentChecked',
                permission: 'ui_case:view'
            },
            {
                name: '步骤片段',
                path: '/ui-fragments',
                icon: 'Collection',
                permission: 'ui_case:view'
            },
            {
                name: '测试文件',
                path: '/ui-test-files',
                icon: 'FolderOpened',
                permission: 'ui_case:view'
            },
            {
                name: '套件管理',
                path: '/suite',
                icon: 'Collection',
                permission: 'ui_suite:view'
            },
            {
                name: '执行计划',
                path: '/task',
                icon: 'Calendar',
                permission: 'ui_task:view'
            },
            {
                name: '定时任务',
                path: '/cronjob',
                icon: 'AlarmClock',
                permission: 'ui_cron:view'
            },
            {
                name: '执行记录',
                path: '/record',
                icon: 'List',
                permission: 'ui_record:view'
            },
            {
                name: '设备管理',
                path: '/device',
                icon: 'Monitor',
                permission: 'device:view'
            },
        ]
    },
    {
        title: 'App 自动化',
        icon: 'Iphone',
        expanded: false,
        items: [
            {
                name: '用例管理',
                path: '/app-case',
                icon: 'Cellphone',
                permission: 'app_case:view'
            },
            {
                name: '元素库',
                path: '/app-elements',
                icon: 'CollectionTag',
                anyPermissions: ['app_element:view', 'app_case:view']
            },
            {
                name: '元素探查',
                path: '/app-inspector',
                icon: 'Aim',
                anyPermissions: ['app_element:view', 'app_case:view']
            },
            {
                name: '套件管理',
                path: '/app-suite',
                icon: 'Collection',
                permission: 'app_suite:view'
            },
            {
                name: '执行计划',
                path: '/app-plan',
                icon: 'Calendar',
                permission: 'app_plan:view'
            },
            {
                name: '定时任务',
                path: '/app-cron',
                icon: 'Clock',
                permission: 'app_plan:view'
            },
            {
                name: '步骤片段',
                path: '/app-fragments',
                icon: 'CollectionTag',
                permission: 'app_case:view'
            },
            {
                name: '执行记录',
                path: '/app-record',
                icon: 'List',
                permission: 'app_record:view'
            },
        ]
    },
    {
        title: '接口自动化',
        icon: 'Connection',
        expanded: false,
        items: [
            {
                name: '接口管理',
                path: '/api-module',
                icon: 'Link',
                permission: 'api_manage:view'
            },
            {
                name: '用例管理',
                path: '/api-case',
                icon: 'Document',
                permission: 'api_case:view'
            },
            {
                name: '测试文件',
                path: '/api-test-files',
                icon: 'FolderOpened',
                permission: 'api_manage:view'
            },
            {
                name: '套件管理',
                path: '/api-suite',
                icon: 'Folder',
                permission: 'api_suite:view'
            },
            {
                name: '测试计划',
                path: '/api-plan',
                icon: 'Calendar',
                permission: 'api_plan:view'
            },
            {
                name: '定时任务',
                path: '/api-cron',
                icon: 'Timer',
                permission: 'api_cron:view'
            },
            {
                name: '执行记录',
                path: '/api-run-records',
                icon: 'Histogram',
                permission: 'api_record:view'
            },
            {
                name: 'Mock 服务',
                path: '/api-mock',
                icon: 'MagicStick',
                permission: 'api_mock:view'
            },
            {
                name: 'Header 模板',
                path: '/api-header-templates',
                icon: 'Tickets',
                permission: 'api_manage:view'
            },
            {
                name: 'Token 授权',
                path: '/api-auth',
                icon: 'Key',
                permission: 'api_auth:view'
            },
            {
                name: '数据工厂',
                path: '/api-data-factory',
                icon: 'Coin',
                permission: 'data_factory:view'
            },
        ]
    },
    {
        title: '迭代资料库',
        icon: 'DocumentChecked',
        expanded: false,
        items: [
            {
                name: '资料检索',
                path: '/ai-knowledge/search',
                icon: 'Search',
                permission: 'ai_test:view'
            },
            {
                name: '资料问答',
                path: '/ai-knowledge/qa',
                icon: 'ChatDotRound',
                permission: 'ai_test:view'
            },
            {
                name: '迭代文件夹',
                path: '/ai-knowledge/folders',
                icon: 'FolderOpened',
                permission: 'ai_test:view'
            },
            {
                name: '输出模板',
                path: '/ai-knowledge/templates',
                icon: 'Document',
                permission: 'ai_test:view'
            },
            {
                name: '模板变量',
                path: '/ai-knowledge/variables',
                icon: 'Tickets',
                permission: 'ai_test:view'
            },
            {
                name: '报告向导',
                path: '/ai-knowledge/reports',
                icon: 'EditPen',
                permission: 'ai_test:view'
            },
            {
                name: '生成记录',
                path: '/ai-knowledge/records',
                icon: 'List',
                permission: 'ai_test:view'
            },
            {
                name: '生成配置',
                path: '/ai-knowledge/settings',
                icon: 'Setting',
                permission: 'ai_test:view'
            },
        ]
    },
    {
        title: 'AI 测试',
        icon: 'Cpu',
        expanded: false,
        items: [
            {
                name: 'AI 工作台',
                path: '/ai-test',
                icon: 'ChatDotSquare',
                permission: 'ai_test:view'
            },
            {
                name: '需求测试中心',
                path: '/ai-testing',
                icon: 'Cpu',
                permission: 'ai_test:view'
            },
            {
                name: '功能用例库',
                path: '/ai-functional-cases',
                icon: 'DocumentChecked',
                permission: 'ai_test:view'
            },
            {
                name: '模型使用情况',
                path: '/ai-usage',
                icon: 'DataLine',
                permission: 'ai_test:view'
            },
        ]
    },
    {
        title: '智能浏览器',
        icon: 'Monitor',
        expanded: false,
        items: [
            {
                name: '用例库',
                path: '/browser-lab/cases',
                icon: 'Document',
                permission: 'ai_test:view'
            },
            {
                name: '执行任务',
                path: '/browser-lab/run',
                icon: 'VideoPlay',
                permission: 'ai_test:view'
            },
            {
                name: '执行记录',
                path: '/browser-lab/records',
                icon: 'List',
                permission: 'ai_test:view'
            },
        ]
    },
    {
        title: '性能测试',
        icon: 'TrendCharts',
        expanded: false,
        items: [
            {
                name: '场景管理',
                path: '/perf-scenes',
                icon: 'Edit',
                permission: 'perf_scene:view'
            },
            {
                name: '定时压测',
                path: '/perf-cron',
                icon: 'AlarmClock',
                permission: 'perf_cron:view'
            },
            {
                name: '执行机',
                path: '/perf-workers',
                icon: 'Monitor',
                permission: 'perf_scene:view'
            },
            {
                name: '执行记录',
                path: '/perf-records',
                icon: 'List',
                permission: 'perf_record:view'
            }
        ]
    },
    {
        title: '帮助中心',
        icon: 'Reading',
        expanded: false,
        items: [
            {
                name: '文档中心',
                path: '/docs',
                icon: 'Notebook',
                permission: 'docs:view',
                noProjectRequired: true
            }
        ]
    },
    {
        title: '系统管理',
        icon: 'Tools',
        expanded: false,
        items: [
            {
                name: '用户管理',
                path: '/user',
                icon: 'UserFilled',
                permission: 'user:view'
            },
            {
                name: '角色权限',
                path: '/role',
                icon: 'User',
                permission: 'role:view'
            },
            {
                name: '操作日志',
                path: '/operation-log',
                icon: 'DocumentChecked',
                permission: 'operation_log:view'
            },
            {
                name: '平台配置',
                path: '/platform-config',
                icon: 'Setting',
                anyPermissions: [
                    'ai_config:view',
                    'smtp_config:view',
                    'notification_config:view',
                    'mcp_config:view',
                    'login_page_config:view',
                    'device:edit'
                ]
            },
            {
                name: '推送记录',
                path: '/notification-logs',
                icon: 'List',
                permission: 'notification_log:view'
            },
            {
                name: '接口文档',
                path: import.meta.env.VITE_SWAGGER_URL,
                icon: 'Document',
                external: true
            }
        ]
    }
]

// 兼容旧代码，保留 MenuList 导出
export const MenuList = MenuGroups.flatMap(group => group.items)

/** 侧边栏分组展开状态（sessionStorage，重新登录后恢复默认） */
export const MENU_EXPANDED_SESSION_KEY = 'brickcore_menu_expanded_groups'

export function resetMenuExpandedSession() {
  try {
    sessionStorage.removeItem(MENU_EXPANDED_SESSION_KEY)
    localStorage.removeItem(MENU_EXPANDED_SESSION_KEY)
  } catch {
    /* ignore */
  }
}
