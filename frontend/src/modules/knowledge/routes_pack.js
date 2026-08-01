/** CE：定制文档页签可见，实现由 stub 锁定（无行业包 API） */
export const knowledgePackChildRoutes = [
  {
    path: 'pro-custom',
    name: 'knowledgePackWizard',
    component: () => import('./views/KnowledgePackWizard.vue'),
    meta: { title: '定制文档', permission: 'knowledge:view' }
  }
]
export default knowledgePackChildRoutes
