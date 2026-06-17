// 使用 Element Plus 图标（矢量图标，风格统一）
// 图标名称参考：https://element-plus.org/zh-CN/component/icon.html

// 菜单分组配置 - 按功能模块重新组织
export const MenuGroups = [
    {
        title: '数据看板',
        icon: 'DataLine',
        expanded: true,
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
        expanded: true,
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
        title: 'UI 自动化',
        icon: 'Mouse',
        expanded: true,
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
        title: '接口自动化',
        icon: 'Connection',
        expanded: true,
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
        title: 'AI 测试',
        icon: 'Cpu',
        expanded: true,
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
                name: '问答准确性评测',
                path: '/ai-qa-eval',
                icon: 'ChatLineRound',
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
        expanded: true,
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
        expanded: true,
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
        expanded: true,
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
        expanded: true,
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
