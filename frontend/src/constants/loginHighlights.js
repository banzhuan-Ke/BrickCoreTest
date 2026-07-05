/** 登录/注册页左侧亮点文案（写死，不走后台配置） */
export const LOGIN_HIGHLIGHTS = {
  welcome: '欢迎使用',
  brandName: 'BrickCore',
  tagline: 'AI 驱动测试全流程，Web / App / 接口 / 性能一体化',
  items: [
    {
      title: 'AI 测试助手',
      desc: '用例生成、需求分析、智能问答；Web / 接口用例快速产出',
    },
    { title: '功能→Web 闭环', desc: 'AI 串联功能用例到 Web 自动化，减少手工转写' },
    { title: 'Web 自动化', desc: '智能录制、元素自愈，Playwright 套件与计划执行' },
    {
      title: 'App 自动化（Pro）',
      desc: 'Android 真机 / WiFi / 模拟器：u2 原生、图像模板、H5 探查、计划与定时任务',
    },
    { title: '接口自动化', desc: '用例编排、套件计划与自动化报告' },
    { title: '性能与数据', desc: '分布式压测、Mock 与全局变量断言' },
  ],
}

export const REGISTER_HIGHLIGHTS = {
  ...LOGIN_HIGHLIGHTS,
  welcome: '加入平台',
  tagline: '注册即可体验 AI 用例生成与 Web / App 自动化执行',
}
