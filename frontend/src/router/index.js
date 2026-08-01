import {createWebHashHistory, createRouter} from 'vue-router'
import NProgress from "nprogress"
import 'nprogress/nprogress.css'
import {UserStore} from "@/stores/module/UserStore"
import { knowledgePackChildRoutes } from '../modules/knowledge/routes_pack.js'

const routes = [
    {
        path: '/',
        redirect: '/login',
        name: 'index',
        meta: {
            title: '平台登录',
            noTab: true
        }
    },
    {
        path: '/login',
        component: () => import('../views/Login/Login.vue'),
        name: 'login',
        meta: {
            title: '平台登录',
            noTab: true
        }
    },
    {
        path: '/register',
        component: () => import('../views/Register/Register.vue'),
        name: 'register',
        meta: {
            title: '平台注册',
            noTab: true
        }
    },

    {
        path: '/home',
        name: 'home',
        redirect: '/dashboard',
        component: () => import('../views/Home/Home.vue'),
        children: [
            {
                path: '/dashboard',
                component: () => import('../views/Dashboard/Dashboard.vue'),
                name: 'dashboard',
                meta: {
                    title: '首页看板',
                    icon: 'Odometer',
                    permission: 'project:view'
                }
            },
            {
                path: '/docs',
                name: 'docsCenter',
                component: () => import('../views/Docs/DocsCenter.vue'),
                meta: {
                    title: '文档中心',
                    icon: 'Notebook',
                    permission: 'docs:view'
                }
            },
            {
                path: '/project',
                component: () => import('../views/Project/Project.vue'),
                name: 'projectList',
                meta: {
                    title: '项目管理',
                    icon: 'FolderOpened',
                    permission: 'project:view'
                }
            },
            {
                path: '/project-settings',
                name: 'projectSettings',
                component: () => import('../views/Project/ProjectSettings.vue'),
                meta: {
                    title: '项目设置',
                    icon: 'Tools',
                    anyPermissions: [
                        'project_settings:view',
                        'ai_config:view',
                        'notification_config:view'
                    ]
                }
            },
            {
                path: '/environment',
                name: 'environmentList',
                component: () => import('../views/Environment/Environment.vue'),
                meta: {
                    title: '测试环境',
                    icon: 'OfficeBuilding',
                    permission: 'environment:view'
                }
            },
            {
                path: '/catalog',
                name: 'catalogList',
                component: () => import('../views/Module/Module.vue'),
                meta: {
                    title: '测试目录',
                    icon: 'Grid',
                    permission: 'module:view'
                }
            },
            {
                path: '/module',
                redirect: '/catalog',
                name: 'moduleList'
            },
            {
                path: '/notification-config',
                redirect: { path: '/project-settings', query: { tab: 'notify' } }
            },
            {
                path: '/smtp-config',
                redirect: { path: '/platform-config', query: { tab: 'notify' } }
            },
            {
                path: '/mcp-config',
                redirect: { path: '/platform-config', query: { tab: 'mcp' } }
            },
            {
                path: '/login-page-config',
                redirect: { path: '/platform-config', query: { tab: 'login' } }
            },
            {
                path: '/runner-release-config',
                redirect: { path: '/platform-config', query: { tab: 'runner' } }
            },
            {
                path: '/stream-parser-config',
                redirect: { path: '/platform-config', query: { tab: 'stream-parser' } }
            },
            {
                path: '/platform-config',
                name: 'platformConfig',
                component: () => import('../views/System/PlatformConfig.vue'),
                meta: {
                    title: '平台配置',
                    icon: 'Setting',
                    anyPermissions: [
                        'ai_config:view',
                        'smtp_config:view',
                        'mcp_config:view',
                        'login_page_config:view',
                        'platform_settings:view',
                        'device:edit'
                    ]
                }
            },
            {
                path: '/notification-logs',
                name: 'notificationLogs',
                component: () => import('../views/System/NotificationLog.vue'),
                meta: {
                    title: '推送记录',
                    icon: 'List',
                    permission: 'notification_log:view'
                }
            },
            {
                path: '/api-module',
                name: 'apiModule',
                component: () => import('../views/ApiModule/ApiList.vue'),
                meta: {
                    title: '接口管理',
                    icon: 'Connection',
                    permission: 'api_manage:view'
                }
            },
            {
                path: '/api-case',
                name: 'apiCase',
                component: () => import('../views/ApiModule/ApiCaseList.vue'),
                meta: {
                    title: '接口用例',
                    icon: 'Document',
                    permission: 'api_case:view'
                }
            },
            {
                path: '/api-test-files',
                name: 'apiTestFileList',
                component: () => import('../views/ApiModule/ApiTestFileList.vue'),
                meta: {
                    title: '测试文件',
                    icon: 'FolderOpened',
                    permission: 'api_manage:view'
                }
            },
            {
                path: '/api-suite',
                name: 'apiSuite',
                component: () => import('../views/ApiModule/ApiSuiteList.vue'),
                meta: {
                    title: '接口套件',
                    icon: 'Collection',
                    permission: 'api_suite:view'
                }
            },
            {
                path: '/api-suite/:suiteId',
                name: 'apiSuiteDetail',
                component: () => import('../views/ApiModule/ApiSuiteDetail.vue'),
                meta: {
                    title: '套件详情',
                    icon: 'Collection',
                    permission: 'api_suite:view'
                }
            },
            {
                path: '/api-run-records',
                name: 'apiRunRecords',
                component: () => import('../views/ApiModule/ApiRunRecords.vue'),
                meta: {
                    title: '接口执行记录',
                    icon: 'List',
                    permission: 'api_record:view'
                }
            },
            {
                path: '/api-mock',
                name: 'apiMock',
                component: () => import('../views/ApiModule/MockList.vue'),
                meta: {
                    title: 'Mock 服务',
                    icon: 'MagicStick',
                    permission: 'api_mock:view'
                }
            },
            {
                path: '/api-header-templates',
                name: 'apiHeaderTemplates',
                component: () => import('../views/ApiModule/ApiHeaderTemplates.vue'),
                meta: {
                    title: 'Header 模板',
                    icon: 'Tickets',
                    permission: 'api_manage:view'
                }
            },
            {
                path: '/api-auth',
                name: 'apiAuth',
                component: () => import('../views/ApiModule/ApiAuthConfig.vue'),
                meta: {
                    title: 'Token 授权',
                    icon: 'Key',
                    permission: 'api_auth:view'
                }
            },
            {
                path: '/api-data-factory',
                name: 'apiDataFactory',
                component: () => import('../views/ApiModule/DataFactory.vue'),
                meta: {
                    title: '数据工厂',
                    icon: 'Coin',
                    permission: 'data_factory:view'
                }
            },
            {
                path: '/api-module/report/:recordId',
                name: 'apiReport',
                component: () => import('../views/ApiModule/ApiReportPage.vue'),
                meta: {
                    title: '接口执行报告',
                    icon: 'DocumentCopy',
                    permission: 'api_record:view'
                }
            },
            {
                path: '/api-plan',
                name: 'apiPlan',
                component: () => import('../views/ApiModule/ApiPlanList.vue'),
                meta: {
                    title: '测试计划',
                    icon: 'Calendar',
                    permission: 'api_plan:view'
                }
            },
            {
                path: '/api-plan/:planId',
                name: 'apiPlanEdit',
                component: () => import('../views/ApiModule/ApiPlanEdit.vue'),
                meta: {
                    title: '编辑测试计划',
                    icon: 'Edit',
                    permission: 'api_plan:view'
                }
            },
            {
                path: '/api-cron',
                name: 'apiCron',
                component: () => import('../views/ApiModule/ApiCronJobs.vue'),
                meta: {
                    title: '接口定时任务',
                    icon: 'AlarmClock',
                    permission: 'api_cron:view'
                }
            },
            {
                path: '/case',
                name: 'caseList',
                component: () => import('../views/Case/Case.vue'),
                meta: {
                    title: '测试用例',
                    icon: 'DocumentChecked',
                    permission: 'ui_case:view'
                }
            },
            {
                path: '/case/add',
                component: () => import('../views/Case/CaseAdd.vue'),
                name: "addCase",
                meta: {
                    title: '新建用例',
                    icon: 'Edit',
                    permission: 'ui_case:edit'
                }
            },
            {
                path: '/case/edit/:id',
                component: () => import('../views/Case/CaseEdit.vue'),
                name: "editCase",
                meta: {
                    title: '编辑用例',
                    icon: 'Edit',
                    permission: 'ui_case:edit'
                }
            },
            {
                path: '/ui-fragments',
                name: 'uiFragmentList',
                component: () => import('../views/Case/UiFragmentList.vue'),
                meta: {
                    title: '步骤片段',
                    icon: 'Collection',
                    permission: 'ui_case:view'
                }
            },
            {
                path: '/ui-fragments/new',
                name: 'uiFragmentNew',
                component: () => import('../views/Case/UiFragmentEdit.vue'),
                meta: {
                    title: '新建片段',
                    icon: 'Plus',
                    permission: 'ui_case:edit'
                }
            },
            {
                path: '/ui-fragments/edit/:id',
                name: 'uiFragmentEdit',
                component: () => import('../views/Case/UiFragmentEdit.vue'),
                meta: {
                    title: '编辑片段',
                    icon: 'Edit',
                    permission: 'ui_case:edit'
                }
            },
            {
                path: '/ui-test-files',
                name: 'uiTestFileList',
                component: () => import('../views/Case/UiTestFileList.vue'),
                meta: {
                    title: '测试文件',
                    icon: 'FolderOpened',
                    permission: 'ui_case:view'
                }
            },
            {
                path: '/suite',
                name: 'suiteList',
                component: () => import('../views/Suite/Suite.vue'),
                meta: {
                    title: '测试套件',
                    icon: 'Collection',
                    permission: 'ui_suite:view'
                }
            },
            {
                path: '/suite/add',
                name: 'addSuite',
                component: () => import('../views/Suite/SuiteAdd.vue'),
                meta: {
                    title: '新建套件',
                    icon: 'CircleCheck',
                    permission: 'ui_suite:edit'
                }
            },
            {
                path: '/suite/edit/:id',
                name: 'editSuite',
                component: () => import('../views/Suite/SuiteEdit.vue'),
                meta: {
                    title: '套件编辑',
                    icon: 'Edit',
                    permission: 'ui_suite:edit'
                }
            },
            {
                path: '/task',
                name: 'taskList',
                component: () => import('../views/Task/Task.vue'),
                meta: {
                    title: '测试计划',
                    icon: 'Calendar',
                    permission: 'ui_task:view'
                }
            },
            {
                path: '/task/edit/:id',
                name: 'editTask',
                component: () => import('../views/Task/TaskEdit.vue'),
                meta: {
                    title: '编辑计划',
                    icon: 'Edit',
                    permission: 'ui_task:edit'
                }
            },
            {
                path: '/cronjob',
                name: 'cronjob',
                component: () => import('../views/Cronjob/Cronjob.vue'),
                meta: {
                    title: '定时任务',
                    icon: 'AlarmClock',
                    permission: 'ui_cron:view'
                }
            },
            {
                path: '/record',
                name: 'recordList',
                component: () => import('../views/Record/Record.vue'),
                meta: {
                    title: '执行记录',
                    icon: 'List',
                    permission: 'ui_record:view'
                }
            },
            {
                path: '/record/report/suite/:id',
                name: 'suiteReport',
                component: () => import('../views/Report/SuiteReportNew.vue'),
                meta: {
                    title: '套件报告',
                    icon: 'DocumentCopy',
                    permission: 'ui_record:view'
                }
            },
            {
                path: '/record/report/task/:id',
                name: 'taskReport',
                component: () => import('../views/Report/TaskReportNew.vue'),
                meta: {
                    title: '计划报告',
                    icon: 'DocumentCopy',
                    permission: 'ui_record:view'
                }
            },
            {
                path: '/app-case',
                name: 'appCaseList',
                component: () => import('../views/App/AppCase.vue'),
                meta: { title: 'App 用例', icon: 'Cellphone', permission: 'app_case:view' }
            },
            {
                path: '/app-case/add',
                name: 'appCaseAdd',
                component: () => import('../views/App/AppCaseEdit.vue'),
                meta: { title: '新建 App 用例', icon: 'Plus', permission: 'app_case:edit' }
            },
            {
                path: '/app-case/edit/:id',
                name: 'appCaseEdit',
                component: () => import('../views/App/AppCaseEdit.vue'),
                meta: { title: '编辑 App 用例', icon: 'Edit', permission: 'app_case:edit' }
            },
            {
                path: '/app-elements',
                name: 'appElements',
                component: () => import('../views/App/AppElement.vue'),
                meta: {
                    title: 'App 元素库',
                    icon: 'CollectionTag',
                    anyPermissions: ['app_element:view', 'app_case:view']
                }
            },
            {
                path: '/app-inspector',
                name: 'appInspector',
                component: () => import('../views/App/AppInspector.vue'),
                meta: {
                    title: '元素探查',
                    icon: 'Aim',
                    anyPermissions: ['app_element:view', 'app_case:view']
                }
            },
            {
                path: '/app-suite',
                name: 'appSuiteList',
                component: () => import('../views/App/AppSuite.vue'),
                meta: { title: 'App 套件', icon: 'Collection', permission: 'app_suite:view' }
            },
            {
                path: '/app-suite/add',
                name: 'appSuiteAdd',
                component: () => import('../views/App/AppSuiteEdit.vue'),
                meta: { title: '新建 App 套件', icon: 'Plus', permission: 'app_suite:edit' }
            },
            {
                path: '/app-suite/edit/:id',
                name: 'appSuiteEdit',
                component: () => import('../views/App/AppSuiteEdit.vue'),
                meta: { title: '编辑 App 套件', icon: 'Edit', permission: 'app_suite:edit' }
            },
            {
                path: '/app-plan',
                name: 'appPlanList',
                component: () => import('../views/App/AppPlan.vue'),
                meta: { title: 'App 计划', icon: 'Calendar', permission: 'app_plan:view' }
            },
            {
                path: '/app-plan/edit/:id',
                name: 'appPlanEdit',
                component: () => import('../views/App/AppPlanEdit.vue'),
                meta: { title: '编辑 App 计划', icon: 'Edit', permission: 'app_plan:edit' }
            },
            {
                path: '/app-cron',
                name: 'appCronList',
                component: () => import('../views/App/AppCron.vue'),
                meta: { title: 'App 定时任务', icon: 'Clock', permission: 'app_plan:view' }
            },
            {
                path: '/app-fragments',
                name: 'appFragmentList',
                component: () => import('../views/App/AppFragmentList.vue'),
                meta: { title: 'App 步骤片段', icon: 'CollectionTag', permission: 'app_case:view' }
            },
            {
                path: '/app-fragments/new',
                name: 'appFragmentNew',
                component: () => import('../views/App/AppFragmentEdit.vue'),
                meta: { title: '新建 App 片段', icon: 'Plus', permission: 'app_case:edit' }
            },
            {
                path: '/app-fragments/edit/:id',
                name: 'appFragmentEdit',
                component: () => import('../views/App/AppFragmentEdit.vue'),
                meta: { title: '编辑 App 片段', icon: 'Edit', permission: 'app_case:edit' }
            },
            {
                path: '/app-record',
                name: 'appRecordList',
                component: () => import('../views/App/AppRecord.vue'),
                meta: { title: 'App 执行记录', icon: 'List', permission: 'app_record:view' }
            },
            {
                path: '/app-record/report/suite/:id',
                name: 'appSuiteReport',
                component: () => import('../views/App/AppSuiteReport.vue'),
                meta: { title: 'App 套件报告', icon: 'DocumentCopy', permission: 'app_record:view' }
            },
            {
                path: '/app-record/report/plan/:id',
                name: 'appPlanReport',
                component: () => import('../views/App/AppPlanReport.vue'),
                meta: { title: 'App 计划报告', icon: 'DocumentCopy', permission: 'app_record:view' }
            },
            {
                path: '/device',
                name: 'device',
                component: () => import('../views/Device/Device.vue'),
                meta: {
                    title: '设备管理',
                    icon: 'Monitor',
                    permission: 'device:view'
                }
            },
            {
                path: '/profile',
                name: 'profile',
                component: () => import('../views/Profile/Profile.vue'),
                meta: {
                    title: '个人中心',
                    icon: 'User',
                    noTab: true
                }
            },
            {
                path: '/user',
                name: 'user',
                component: () => import('../views/User/User.vue'),
                meta: {
                    title: '用户管理',
                    icon: 'UserFilled',
                    permission: 'user:view'
                }
            },
            {
                path: '/role',
                name: 'role',
                component: () => import('../views/Role/Role.vue'),
                meta: {
                    title: '角色管理',
                    icon: 'User',
                    permission: 'role:view'
                }
            },
            {
                path: '/operation-log',
                name: 'operationLog',
                component: () => import('../views/OperationLog/OperationLog.vue'),
                meta: {
                    title: '操作日志',
                    icon: 'DocumentChecked',
                    permission: 'operation_log:view'
                }
            },
            {
                path: '/ai-testing',
                component: () => import('../views/AI/testing/AiTestingLayout.vue'),
                meta: {
                    title: '需求测试中心',
                    icon: 'Cpu',
                    permission: 'ai_test:view'
                },
                children: [
                    {
                        path: '',
                        name: 'aiTestingHub',
                        component: () => import('../views/AI/testing/AiTestingRequirementList.vue'),
                        meta: { title: '需求测试中心', permission: 'ai_test:view' }
                    },
                    {
                        path: 'test-points',
                        redirect: '/ai-testing'
                    },
                    {
                        path: 'schemes',
                        redirect: '/ai-testing'
                    }
                ]
            },
            {
                path: '/ai-testing/requirements/:reqId',
                name: 'aiTestingWorkspace',
                component: () => import('../views/AI/testing/AiRequirementWorkspace.vue'),
                props: route => ({ reqId: route.params.reqId }),
                meta: {
                    title: '需求工作台',
                    permission: 'ai_test:view'
                }
            },
            {
                path: '/ai-test-analysis',
                redirect: to => ({
                    path: to.query.reqId
                        ? `/ai-testing/requirements/${to.query.reqId}`
                        : '/ai-testing',
                    query: {
                        tab: to.query.pointId ? 'points' : 'mindmap',
                        pointId: to.query.pointId
                    }
                })
            },
            {
                path: '/ai-requirements',
                redirect: to => ({
                    path: to.query.reqId
                        ? `/ai-testing/requirements/${to.query.reqId}`
                        : '/ai-testing',
                    query: {
                        tab: 'cases',
                        pointId: to.query.pointId,
                        sourceRef: to.query.sourceRef
                    }
                })
            },
            {
                path: '/ai-functional-cases',
                name: 'aiFunctionalCases',
                component: () => import('../views/AI/AiFunctionalCaseLibrary.vue'),
                meta: {
                    title: '功能用例库',
                    icon: 'DocumentChecked',
                    permission: 'ai_test:view'
                }
            },
            {
                path: '/ai-test',
                name: 'aiTest',
                component: () => import('../views/AI/AITest.vue'),
                meta: {
                    title: 'AI 测试工作台',
                    icon: 'ChatDotSquare',
                    permission: 'ai_test:view'
                }
            },
            {
                path: '/ai-config',
                redirect: (to) => {
                    const inner = to.query?.tab
                    if (inner === 'execution') {
                        return { path: '/project-settings', query: { tab: 'execution' } }
                    }
                    if (inner && ['scene', 'prompt', 'embed', 'config'].includes(inner)) {
                        return { path: '/platform-config', query: { tab: 'ai', sub: inner } }
                    }
                    return { path: '/platform-config', query: { tab: 'ai' } }
                }
            },
            {
                path: '/ai-usage',
                name: 'aiUsage',
                component: () => import('../views/AI/AiUsage.vue'),
                meta: {
                    title: '模型使用情况',
                    icon: 'DataLine',
                    permission: 'ai_test:view'
                }
            },
            {
                path: '/browser-lab',
                component: () => import('../views/AI/browserLab/BrowserLabLayout.vue'),
                meta: { title: '智能浏览器', icon: 'Monitor', permission: 'ai_test:view' },
                redirect: '/browser-lab/cases',
                children: [
                    {
                        path: 'cases',
                        name: 'browserLabCases',
                        component: () => import('../views/AI/browserLab/BrowserLabCases.vue'),
                        meta: { title: '用例库', permission: 'ai_test:view' }
                    },
                    {
                        path: 'run',
                        name: 'browserLabRun',
                        component: () => import('../views/AI/browserLab/BrowserLabRun.vue'),
                        meta: { title: '执行任务', permission: 'ai_test:view' }
                    },
                    {
                        path: 'records',
                        name: 'browserLabRecords',
                        component: () => import('../views/AI/browserLab/BrowserLabRecords.vue'),
                        meta: { title: '执行记录', permission: 'ai_test:view' }
                    }
                ]
            },
            {
                path: '/browser-lab/report/:taskId',
                name: 'browserLabReport',
                component: () => import('../views/AI/browserLab/BrowserLabReport.vue'),
                meta: { title: '执行报告', permission: 'ai_test:view' }
            },
            {
                path: '/browser-lab/gif/:taskId',
                name: 'browserLabGifPreview',
                component: () => import('../views/AI/browserLab/BrowserLabGifPreview.vue'),
                meta: { title: '回放 GIF', permission: 'ai_test:view' }
            },
            {
                path: '/ai-browser-lab',
                redirect: '/browser-lab/run'
            },
            {
                path: '/ai-knowledge',
                component: () => import('../modules/knowledge/views/KnowledgeLayout.vue'),
                meta: { title: '迭代资料库', icon: 'DocumentChecked', permission: 'knowledge:view' },
                redirect: '/ai-knowledge/folders',
                children: [
                    {
                        path: 'search',
                        name: 'knowledgeSearch',
                        component: () => import('../modules/knowledge/views/KnowledgeSearch.vue'),
                        meta: { title: '资料检索', permission: 'knowledge:view' }
                    },
                    {
                        path: 'qa',
                        name: 'knowledgeQa',
                        component: () => import('../modules/knowledge/views/KnowledgeQa.vue'),
                        meta: { title: '资料问答', permission: 'knowledge:view' }
                    },
                    {
                        path: 'folders',
                        name: 'knowledgeFolders',
                        component: () => import('../modules/knowledge/views/KnowledgeFolders.vue'),
                        meta: { title: '迭代文件夹', permission: 'knowledge:view' }
                    },
                    {
                        path: 'folders/:folderId',
                        name: 'knowledgeFolderDetail',
                        component: () => import('../modules/knowledge/views/KnowledgeFolderDetail.vue'),
                        meta: { title: '文件夹详情', permission: 'knowledge:view' }
                    },
                    {
                        path: 'templates',
                        name: 'knowledgeTemplates',
                        component: () => import('../modules/knowledge/views/KnowledgeTemplates.vue'),
                        meta: { title: '输出模板', permission: 'knowledge:view' }
                    },
                    {
                        path: 'variables',
                        name: 'knowledgeTemplateVariables',
                        component: () => import('../modules/knowledge/views/KnowledgeTemplateVariables.vue'),
                        meta: { title: '模板变量', permission: 'knowledge:view' }
                    },
                    {
                        path: 'reports',
                        name: 'knowledgeReportWizard',
                        component: () => import('../modules/knowledge/views/KnowledgeReportWizard.vue'),
                        meta: { title: '报告向导', permission: 'knowledge:view' }
                    },
                    {
                        path: 'records',
                        name: 'knowledgeReportRecords',
                        component: () => import('../modules/knowledge/views/KnowledgeReportRecords.vue'),
                        meta: { title: '生成记录', permission: 'knowledge:view' }
                    },
                    {
                        path: 'settings',
                        name: 'knowledgeSettings',
                        component: () => import('../modules/knowledge/views/KnowledgeSettings.vue'),
                        meta: { title: '生成配置', permission: 'knowledge:view' }
                    },
                    ...knowledgePackChildRoutes
                ]
            },
            {
                path: '/perf-scenes',
                name: 'perfSceneList',
                component: () => import('../views/Perf/PerfSceneList.vue'),
                meta: {
                    title: '性能测试场景',
                    icon: 'Edit',
                    permission: 'perf_scene:view'
                }
            },
            {
                path: '/perf-scene/add',
                name: 'perfSceneAdd',
                component: () => import('../views/Perf/PerfSceneEdit.vue'),
                meta: {
                    title: '新建场景',
                    icon: 'Edit',
                    permission: 'perf_scene:edit'
                }
            },
            {
                path: '/perf-scene/edit/:id',
                name: 'perfSceneEdit',
                component: () => import('../views/Perf/PerfSceneEdit.vue'),
                meta: {
                    title: '编辑场景',
                    icon: 'Edit',
                    permission: 'perf_scene:edit'
                }
            },
            {
                path: '/perf-cron',
                name: 'perfCronJobs',
                component: () => import('../views/Perf/PerfCronJobs.vue'),
                meta: {
                    title: '定时压测',
                    icon: 'AlarmClock',
                    permission: 'perf_cron:view'
                }
            },
            {
                path: '/perf-workers',
                name: 'perfWorkerList',
                component: () => import('../views/Perf/PerfWorkerList.vue'),
                meta: {
                    title: '执行机',
                    icon: 'Monitor',
                    permission: 'perf_scene:view'
                }
            },
            {
                path: '/perf-records',
                name: 'perfRecordList',
                component: () => import('../views/Perf/PerfRecordList.vue'),
                meta: {
                    title: '性能测试记录',
                    icon: 'List',
                    permission: 'perf_record:view'
                }
            },
            {
                path: '/perf-comparisons',
                name: 'perfComparisonList',
                component: () => import('../views/Perf/PerfComparisonList.vue'),
                meta: {
                    title: '压测增强报告',
                    icon: 'TrendCharts',
                    permission: 'perf_record:view'
                }
            },
            {
                path: '/perf-comparisons/:reportId',
                name: 'perfComparisonReport',
                component: () => import('../views/Perf/PerfComparisonReport.vue'),
                meta: {
                    title: '增强报告详情',
                    icon: 'TrendCharts',
                    permission: 'perf_record:view'
                }
            },
            {
                path: '/perf-report/:recordId',
                name: 'perfReport',
                component: () => import('../views/Perf/PerfReport.vue'),
                meta: {
                    title: '性能测试报告',
                    icon: 'TrendCharts',
                    permission: 'perf_record:view'
                }
            },
        ]
    },
    // 错误页面404
    {
        path: '/:path(.*)*',
        name: '404',
        component: () => import( /* webpackChunkName: "about" */ '../views/Error/404.vue'),
        meta: {
            title: '404',
            noTab: true
        }
    },
]

const router = createRouter({
    history: createWebHashHistory(), routes
})

// 右上角螺旋加载提示
NProgress.configure({showSpinner: true, trickleSpeed: 200})
// 前置路由导航守卫
router.beforeEach(async (to, from, next) => {
    // 启动进度条动画
    NProgress.start()
    // 判断是否需要保存路由访问记录
    const uStore = UserStore()
    // 路由访问的记录title保存到pinia中，去除noTab
    if (to.meta.title && !to.meta.noTab) {
        uStore.addTabs(to)
    }
    // 获取用户是否登录的状态
    let isAuthenticated = uStore.$state.isAuthenticated
    if (!isAuthenticated && to.name !== 'login' && to.name !== 'register') {
        // 停止进度条动画
        NProgress.done()
        // 将用户重定向到登录页面
        return next({name: 'login'})
    }
    // 防御旧 localStorage 中没有 permissions 字段的情况
    if (!uStore.permissions) {
        uStore.permissions = []
    }
    // 路由权限校验（无权限时回登录页并提示）
    const anyPerms = to.meta.anyPermissions
    if (anyPerms?.length) {
        const ok = anyPerms.some((p) => uStore.hasPermission(p))
        if (!ok) {
            NProgress.done()
            return next({ name: 'login', query: { msg: 'no_permission' } })
        }
    } else if (to.meta.permission && !uStore.hasPermission(to.meta.permission)) {
        NProgress.done()
        return next({name: 'login', query: {msg: 'no_permission'}})
    }
    next()
})
// 后置路由导航守卫
router.afterEach((to, from) => {
    // 关闭进度条动画
    NProgress.done()
    // 设置网页标题
    document.title = to.meta.title
})

export default router
