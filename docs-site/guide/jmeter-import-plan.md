# JMeter JMX 导入平台方案

## 背景与目标

团队已有 JMeter `.jmx` 脚本时，需要快速迁移到平台，复用接口定义、接口用例、套件、环境变量和性能测试能力。

本方案只覆盖 **JMeter -> 平台**：安全读取可转换的 HTTP 测试资产，先给出预览和告警，用户确认后才创建平台数据。第一期不做平台导出 JMX，也不承诺 JMeter 测试计划的 1:1 运行时语义还原。

## 设计原则

- 以“可解释的转换”优先于“尽量不报错地导入”。
- 复杂控制器、脚本和插件必须明确告警，禁止静默忽略或伪转换。
- XML 先解析为中间表示，再生成预览和入库数据；不要在解析阶段直接写数据库。
- 复用现有 Swagger、Postman、cURL 导入的上传、目录选择、结果报告和权限模式。
- 入口放在 **接口自动化 -> 接口管理 -> 导入**，压测场景为可选派生产物。

## 导入范围

### 第一期开箱即用

| JMeter 元素 | 平台产物 | 转换规则 |
| --- | --- | --- |
| Test Plan | 导入批次元数据 | 用作预览标题、来源和导入报告上下文 |
| Thread Group | 接口测试套件 | 保留名称和请求顺序 |
| HTTP Request Defaults | 环境 Host / 接口 `base_url` 候选 | 在预览中由用户确认采用方式 |
| HTTP Request / HTTPSamplerProxy | API 定义 + API 测试用例 | 映射方法、路径、Query、Header、Body、超时和名称 |
| HTTP Header Manager | 接口 Header 或用例 Header 覆盖 | 按节点作用域继承并扁平化 |
| Response Assertion | 用例断言 | 支持状态码、包含文本、JSONPath 相等或存在等可映射规则 |
| JSON Extractor | 用例变量提取器 | 转为 JSONPath extractor |
| Regular Expression Extractor | 用例变量提取器 | 仅在平台支持对应规则时转换，否则告警 |
| CSV Data Set Config | CSV 绑定待办 | 导入变量名和文件引用，要求用户另行上传 CSV |
| Simple Controller | 套件分组或 journey 串行阶段 | 保留分组名称和顺序 |

### 仅告警，不自动转换

- JSR223、BeanShell、Groovy、JavaScript 等任意脚本。
- If、While、ForEach、Runtime、Throughput、Interleave、Switch 等控制器。
- Listener、第三方 Plugin、自定义 Sampler。
- Cookie、缓存、DNS 管理器的完整 JMeter 运行时语义。
- 外部 CSV、证书、上传文件的本地路径和文件内容。
- JDBC、MQ、WebSocket、gRPC 等非 HTTP 采样器。

每一条未转换项都必须展示 JMX 节点路径、类型和原因；允许用户继续导入已支持的 HTTP 部分。

## 产物模型与变量规则

```text
JMX Test Plan
  -> 导入批次预览
  -> HTTP Sampler
       -> ApiDefinition
       -> ApiTestCase
  -> Thread Group
       -> ApiTestSuite
       -> (可选) PerfScene / journey
```

默认一个 HTTP Sampler 生成一条 API 定义和一条用例，以保留采样器级参数、断言和提取器。预览页可提供“按 Method + Path 合并 API”的选项：相同接口合并后保留多个用例，差异放入用例覆盖字段。

JMeter 变量与平台变量的转换规则如下：

```text
${token}       -> ${{token}}
${__P(host)}   -> 告警：函数不自动转换
${__time()}    -> 告警：函数不自动转换
```

CSV 变量转换为 `${{csv.column}}`，导入报告必须指出需上传、绑定的 CSV 文件。

## Thread Group 到性能场景

仅当 Thread Group 不含未支持控制器且循环策略可识别时，提供“生成性能场景”选项：

| JMeter 配置 | 平台性能配置 |
| --- | --- |
| Number of Threads | `concurrent_users` |
| Ramp-Up Period | `ramp_up_seconds` |
| Scheduler + Duration | `fixed` + `duration_seconds` |
| 固定 Loop Count | `loop` + `loop_count` |
| HTTP 请求顺序 | journey 串行步骤 |

包含复杂定时器、吞吐控制器或条件控制器时，只创建接口套件，性能场景选项禁用并说明原因。

## 用户流程

1. 用户选择项目、目标目录并上传 `.jmx`。
2. 后端安全解析 XML，返回预览，不创建业务数据。
3. 前端展示可导入 API、用例、套件、性能场景数量，以及冲突、未支持节点和 CSV/变量待办。
4. 用户选择冲突策略：新建、按 Method + Path 合并、跳过已有接口；可选择是否创建性能场景。
5. 用户确认后，后端在事务内创建 API、用例、套件及顺序关联。
6. 返回导入报告：创建、合并、跳过、失败、警告和待补充资源明细。
7. 用户前往套件或性能场景，补齐环境变量和 CSV 后执行。

## 后端方案

### 模块与接口

建议新增：

```text
backend/app/modules/jmeter/
  jmx_parser.py        # 安全 XML 读取和 hashTree 遍历
  jmx_normalizer.py    # JMeter 节点转中间表示 IR
  jmx_mapper.py        # IR 转平台产物预览
  jmx_importer.py      # 去重、事务、落库和导入报告
  models.py            # 请求、预览、告警响应模型
```

建议接口：

```text
POST /api-module/apis/import/jmeter/preview
POST /api-module/apis/import/jmeter/commit
```

`preview` 接收文件、项目、目录和初始策略，返回转换结果但不落库。`commit` 接收短期 preview token 与用户确认的策略，重新校验权限和 token 后执行真实导入。

### 中间表示

中间表示必须可序列化，以支持预览、单元测试和不同 JMeter 版本兼容：

```json
{
  "test_plan_name": "订单压测",
  "thread_groups": [
    {
      "name": "下单链路",
      "threads": 20,
      "ramp_up_seconds": 10,
      "duration_seconds": 60,
      "samplers": [
        {
          "source_path": "/Test Plan/Thread Group[1]/HTTP Request[2]",
          "name": "创建订单",
          "method": "POST",
          "path": "/orders",
          "headers": {"Content-Type": "application/json"},
          "body": {"sku": "${{sku}}"},
          "assertions": [],
          "extractors": [],
          "warnings": []
        }
      ],
      "warnings": []
    }
  ],
  "unsupported_nodes": []
}
```

### 安全、事务与幂等

- 使用禁用 DTD/外部实体的 XML 解析器，拒绝 XXE。
- 限制文件大小、最大节点数、最大层级和单字段长度。
- 只接受 `.jmx`，校验 XML 根节点与 JMeter `hashTree` 结构。
- 不执行 JMX 内脚本、函数或外部文件引用；日志不得输出完整敏感 Header 或请求 Body。
- `commit` 校验项目成员权限、目录归属和 preview token。
- API、Case、Suite、关联顺序在同一数据库事务中写入。
- 标记 `source="jmeter"`，记录 JMX 节点路径作为来源元数据。
- 去重键默认 `project_id + method + path`；支持跳过、合并为新用例、始终新建。
- “严格模式”下任一阻断错误整体回滚；普通模式保留逐项失败报告。

## 前端方案

复用现有导入向导的上传、项目目录选择和结果页，新增 JMeter 预览面板：

- 左侧：Test Plan、Thread Group、Sampler 节点树。
- 中间：将创建的 API、用例、套件、性能场景，可按组取消勾选。
- 右侧：节点映射、冲突策略和未支持项。
- 顶部：可导入数量、警告数量、阻断错误数量。
- 完成页：创建、合并、跳过、失败统计，以及前往套件/性能场景入口。

前端不直接解析 JMX 后创建业务对象，XML 解析和规则判定以服务端结果为准。

## 验收标准

### 功能

- 含 HTTP Request、Header Manager、JSON Extractor、Response Assertion、Simple Controller 的 JMX 能生成正确顺序的 API、用例和套件。
- `${var}` 正确转换为 `${{var}}`；JMeter 函数不被错误转换并会告警。
- CSV Data Set Config 不读取任意本地路径，导入结果提示用户上传 CSV。
- 简单 Thread Group 可选生成性能场景，线程数、Ramp-Up、循环/持续时间映射正确。
- JSR223 或复杂 Controller 脚本仍可导入其中支持的 HTTP 部分，并在报告中列出未转换节点。

### 安全与稳定性

- 带 DTD、外部实体、超大 XML、过深 hashTree 的文件被拒绝。
- 非项目成员无法预览或确认导入。
- 重复提交 commit 不重复创建资产。
- 严格模式不产生部分业务数据。
- 导入报告不泄露无权访问的项目数据。

## 分期与估算

### 第一阶段：HTTP 导入 MVP，预计 5-8 人日

- JMX 上传、安全解析、IR 和 preview token。
- HTTP Sampler、Header Manager、HTTP Defaults、基础断言、JSON Extractor。
- API/Case/Suite 创建、冲突策略、导入报告。
- 单元测试、接口测试、典型 JMX 回归样本。

### 第二阶段：性能场景生成，预计 3-5 人日

- 简单 Thread Group 到 PerfScene/journey 转换。
- CSV 绑定辅助、变量迁移提示。
- 性能场景预览与导入后校验。

### 第三阶段：按真实脚本扩展

- 正则提取器和更多响应断言。
- 半自动处理更多 Controller。
- 导入历史、JMX 版本比较和重复导入更新策略。

## 非目标

- 不执行 JMeter Groovy、BeanShell、JSR223 脚本。
- 不导入 Listener 结果和历史采样数据。
- 不承诺 Cookie、缓存、定时器、控制器的完整 JMeter 语义。
- 不在第一期提供平台 -> JMX 导出。

这些约束用于确保导入结果可解释、可验证，避免复杂脚本被误认为已完成迁移。
