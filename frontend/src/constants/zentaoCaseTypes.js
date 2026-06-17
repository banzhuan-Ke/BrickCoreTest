/** 禅道 Web 端「用例类型」枚举（与 backend zentao_case_types.py 保持一致） */
export const ZENTAO_CASE_TYPES = [
  '场景测试',
  '功能测试',
  '性能测试',
  '配置相关',
  '安装部署',
  '安全相关',
  '接口测试',
  '其他',
  '自动化测试'
]

export const DEFAULT_ZENTAO_CASE_TYPE = '功能测试'

/** 生成阶段测试设计维度（存 extra.test_design，非禅道 type） */
export const TEST_DESIGN_TYPES = [
  '正向流程',
  '异常/反向',
  '边界值',
  '接口校验',
  '其他'
]
