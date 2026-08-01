# 压测 Worker 协议（稳定子集）

性能测试的**场景配置、调度、进度聚合与报告**在平台侧开源；**施压循环与流式读包**由闭源执行机（BrickCoreRunner / BrickCorePerf）实现。本文描述平台与 Worker 之间可对接的**任务与上报契约**，便于运维排查与第三方按协议编写兼容执行器。

> **能力由执行机提供**：无在线 Worker 时平台拒绝启动压测，不会降级为本机直跑。

## 生命周期

```text
注册 → 心跳（idle/busy）→ 领取任务 → 秒级上报 → 最终报告 →（可选）注销
```

| 步骤 | 方法 / 路径（相对 Backend） | 说明 |
|------|------------------------------|------|
| 注册 | `POST /perf/workers/register` | 返回 `worker_id`；需项目鉴权 |
| 心跳 | `POST /perf/workers/heartbeat` | 刷新在线；可带 `status` / `current_record_id` |
| 领任务 | `GET /perf/workers/{worker_id}/task` | 长轮询；有任务则返回 JSON |
| 停测检查 | `GET /perf/workers/records/{record_id}/stop-check` | Worker 侧轮询是否应停止 |
| 请求全局停 | `POST /perf/workers/{record_id}/request-stop` | 错误率超限等 |
| 秒级上报 | `POST /perf/workers/{record_id}/report` | 聚合实时曲线 |
| 最终报告 | `POST /perf/workers/{record_id}/final` | 一次任务结束必报 |
| 注销 | `POST /perf/workers/unregister` | 主动下线 |

鉴权（注册与上报）：`Authorization: Bearer <JWT>`、`X-Runner-Token` 或 `X-Internal-Token`（与平台 `INTERNAL_API_KEY` 一致）之一。详见 [性能测试 · 执行机](./perf-testing.md)。

## 任务载荷（领任务返回）

平台下发的任务为 JSON 对象，稳定字段如下（其余为扩展，可忽略）：

| 字段 | 类型 | 含义 |
|------|------|------|
| `record_id` | int | 执行记录 ID |
| `sync_start_epoch` | float | 建议统一开压的 Unix 时间（秒），减少派发抖动 |
| `assigned_concurrent` | int | 本节点承担的并发用户数 |
| `worker_index` / `total_workers` | int | 分片序号与总节点数 |
| `env_host` | string | 环境 Host |
| `target_host` | string \| null | 场景覆盖 Host |
| `project_global_vars` / `env_global_vars` / `merged_variables` | object | 变量合并结果 |
| `scene_snapshot` | object | 见下 |

### `scene_snapshot`

| 字段 | 含义 |
|------|------|
| `scene_items` | 用例列表（含 `case_id`、权重、断言、`api`、合并后的 headers 等） |
| `config` | 场景配置副本（已按节点缩放过 `concurrent_users` / 梯度 `steps`） |
| `csv_data` / `csv_strategy` | CSV 参数化（可空） |
| `journey` | 业务链路规范化配置（非链路模式为 `null`） |

`config.mode` 常见值：`fixed`、`loop`、`stepping`、流式突发、`journey_fixed`、`journey_loop` 等（与平台场景编辑一致）。

## 秒级上报（`WorkerReportData`）

| 字段 | 类型 | 含义 |
|------|------|------|
| `worker_id` | int | 节点 ID |
| `token` | string | 注册时节点令牌 |
| `timestamp` | int | Unix 秒 |
| `qps` / `avg_rt` / `p95_rt` / `error_rate` | number | 该秒指标 |
| `active_users` | int | 活跃虚拟用户 |
| `total_req` / `success` / `fail` | int | 累计请求计数（节点视角） |

## 最终报告（`WorkerFinalReport`）

| 字段 | 含义 |
|------|------|
| `total_requests` / `success_count` / `fail_count` | 总量 |
| `qps` / `duration` / `error_rate` | 汇总 |
| `avg_response_time` 及 min/max/median/p90/p95/p99/std | 响应时间（ms） |
| `total_bytes_received` / `total_bytes_sent` | 流量 |
| `error_breakdown` | 错误分类 |
| `case_aggregations` | 按用例聚合 |
| `time_series_data` | 秒级序列（供多机合并） |
| `phase_metrics` | 流式阶段指标（可空） |
| `request_details` | 明细（受 `request_detail_level` 约束） |
| `rt_samples` / `success_rt_samples` | 蓄水池样本，多机合并真分位（旧客户端可省略） |

平台在收齐各节点 `final`（或超时/停止宽限）后做分布式 finalize，写入执行记录并触发通知 / AI 分析编排。

## 无 Worker 时的平台行为

| 入口 | 行为 |
|------|------|
| 场景「执行」 | HTTP **503**，提示安装并上线 BrickCoreRunner / BrickCorePerf |
| 后台编排 `run_perf_scene` | 记录 `failed`，`error_breakdown.stop_reason` 说明无可用 Worker |
| 容量不足 | 启动前 **400** 或执行中失败，说明需要并发与当前总容量 |

## 相关文档

- [性能测试使用说明](./perf-testing.md)
- [执行器安装指南](./runner-install-guide.md)
