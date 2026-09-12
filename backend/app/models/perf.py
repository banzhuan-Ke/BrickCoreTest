"""
性能测试模型
"""
from tortoise import fields, models


class PerfScene(models.Model):
    """性能测试场景"""
    id = fields.IntField(pk=True, description="场景ID")
    name = fields.CharField(max_length=100, description="场景名称")
    description = fields.TextField(null=True, description="场景描述")
    project = fields.ForeignKeyField("models.Project", related_name="perf_scenes", description="所属项目")
    catalog = fields.ForeignKeyField(
        "models.TestCatalog", null=True, related_name="perf_scenes", description="所属目录"
    )

    # 场景项：关联的 API 用例列表
    # [{case_id, weight, delay_ms, delay_mode, delay_ms_min, delay_ms_max}]
    # delay_mode: fixed（默认，用 delay_ms）| random（均匀抽样 delay_ms_min~delay_ms_max）
    scene_items = fields.JSONField(default=list, description="场景用例项")

    # 压测配置
    # {
    #   "concurrent_users": 10,       # 并发用户数
    #   "ramp_up_seconds": 5,         # Ramp-up 时间（秒）
    #   "duration_seconds": 60,       # 持续时间（秒）
    #   "target_host": "http://xxx"   # 可选，覆盖环境 host
    # }
    config = fields.JSONField(default=dict, description="压测配置")

    # CSV 参数化数据（历史兼容：优先 csv_dataset_id；无绑定时回退本字段）
    # 结构: [{"username":"user1","password":"pass1"}, {...}]
    csv_data = fields.JSONField(default=list, null=True, description="CSV数据(JSON数组，遗留)")

    # CSV 配置（场景级策略；数据本体在 CsvDataset）
    # {
    #   "enabled": false,
    #   "strategy": "round_robin",  # round_robin / unique / random
    #   "file_name": "users.csv",
    #   "columns": ["username", "password"],
    #   "row_count": 1000
    # }
    csv_config = fields.JSONField(default=dict, description="CSV配置")

    # 绑定的项目级 CSV 数据集（可多场景共用）
    csv_dataset_id = fields.IntField(null=True, description="绑定的 CSV 数据集ID")

    # 基线钉选：报告自动对比该记录，并可按阈值告警
    baseline_record_id = fields.IntField(null=True, description="钉选基线执行记录ID")
    baseline_policy = fields.JSONField(default=dict, description="基线阈值策略")

    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "perf_scene"
        table_description = "性能测试场景"


class PerfRecord(models.Model):
    """性能测试执行记录"""
    id = fields.IntField(pk=True, description="记录ID")
    scene = fields.ForeignKeyField("models.PerfScene", related_name="records", description="关联场景")
    project = fields.ForeignKeyField("models.Project", related_name="perf_records", description="所属项目")

    # 执行状态: pending / running / success / failed / stopped
    status = fields.CharField(max_length=20, default="pending", description="执行状态")
    trigger_type = fields.CharField(max_length=20, default="manual", description="触发方式")

    # 执行时快照（避免场景被修改后影响历史报告）
    config_snapshot = fields.JSONField(default=dict, description="配置快照")
    scene_items_snapshot = fields.JSONField(default=list, description="场景项快照")

    # 聚合指标
    total_requests = fields.IntField(default=0, description="总请求数")
    success_count = fields.IntField(default=0, description="成功数")
    fail_count = fields.IntField(default=0, description="失败数")
    qps = fields.FloatField(default=0, description="QPS")
    avg_response_time = fields.FloatField(default=0, description="平均响应时间(ms)")
    min_response_time = fields.FloatField(default=0, description="最小响应时间(ms)")
    max_response_time = fields.FloatField(default=0, description="最大响应时间(ms)")
    median_response_time = fields.FloatField(default=0, description="中位数响应时间(ms)")
    p90_response_time = fields.FloatField(default=0, description="P90响应时间(ms)")
    p95_response_time = fields.FloatField(default=0, description="P95响应时间(ms)")
    p99_response_time = fields.FloatField(default=0, description="P99响应时间(ms)")
    std_dev_response_time = fields.FloatField(default=0, description="响应时间标准差(ms)")
    error_rate = fields.FloatField(default=0, description="错误率(%)")
    received_kb_per_sec = fields.FloatField(default=0, description="接收数据速率(KB/s)")
    sent_kb_per_sec = fields.FloatField(default=0, description="发送数据速率(KB/s)")
    error_breakdown = fields.JSONField(default=dict, description="错误分类统计")

    # 时间序列数据（每秒聚合，用于 echarts 趋势图）
    # 结构：[{timestamp, qps, avg_rt, error_rate, active_users, total_req, success, fail}]
    time_series_data = fields.JSONField(default=list, description="秒级时序数据")

    # 接口维度聚合
    # 结构：{case_id: {name, total, success, fail, avg_rt, min_rt, max_rt, p95_rt, p99_rt}}
    case_aggregations = fields.JSONField(default=dict, description="接口维度聚合")

    # SSE 问答阶段压测
    phase_metrics = fields.JSONField(default=dict, null=True, description="阶段指标聚合")
    request_details = fields.JSONField(default=list, null=True, description="请求阶段明细")

    # AI 分析结果：{status, summary, highlights, risks, recommendations, error, generated_at}
    ai_analysis = fields.JSONField(null=True, description="AI 分析结果")

    started_at = fields.DatetimeField(null=True, description="开始时间")
    ended_at = fields.DatetimeField(null=True, description="结束时间")
    duration = fields.FloatField(default=0, description="实际执行时长(秒)")

    # 分布式执行信息
    # {
    #   "is_distributed": false,
    #   "workers": [{"worker_id": 1, "assigned_concurrent": 100, "host": "192.168.1.10"}]
    # }
    distribution_info = fields.JSONField(default=dict, description="分布式执行信息")

    # 关联定时任务（用于追溯定时压测的执行历史）
    cron_job_id = fields.CharField(max_length=100, null=True, description="定时任务ID")

    run_by = fields.CharField(max_length=50, description="执行人")

    class Meta:
        table = "perf_record"
        table_description = "性能测试执行记录"


class PerfWorker(models.Model):
    """性能测试 Worker 节点"""
    id = fields.IntField(pk=True, description="节点ID")
    name = fields.CharField(max_length=100, description="节点名称")

    # 注册信息
    host = fields.CharField(max_length=100, description="IP/主机名")
    port = fields.IntField(default=0, description="HTTP服务端口")
    token = fields.CharField(max_length=100, description="认证令牌")

    # 能力
    max_concurrent = fields.IntField(default=100, description="最大并发数")
    agent_kind = fields.CharField(
        max_length=32,
        default="",
        description="来源: perf_slim | runner_client | 空=旧客户端",
    )
    engine_version = fields.CharField(
        max_length=50,
        default="",
        description="压测引擎版本（与 RUNNER_VERSION 对齐）",
    )

    # 状态: idle / busy / offline
    status = fields.CharField(max_length=20, default="idle", description="状态")

    # 心跳
    last_heartbeat = fields.DatetimeField(auto_now=True)

    # 当前任务
    current_record_id = fields.IntField(null=True, description="当前执行记录ID")

    project = fields.ForeignKeyField("models.Project", related_name="perf_workers", description="所属项目")

    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "perf_worker"
        table_description = "性能测试Worker节点"


class PerfJourneyTemplate(models.Model):
    """业务链路模板（项目级，可复用到多个压测场景）"""
    id = fields.IntField(pk=True, description="模板ID")
    project = fields.ForeignKeyField(
        "models.Project", related_name="perf_journey_templates", description="所属项目"
    )
    name = fields.CharField(max_length=100, description="模板名称")
    description = fields.TextField(null=True, description="描述")
    journey = fields.JSONField(default=dict, description="链路配置（与 PerfScene.config.journey 同结构）")
    source_scene_id = fields.IntField(null=True, description="来源场景ID")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "perf_journey_template"
        table_description = "性能测试业务链路模板"


class CsvDataset(models.Model):
    """项目级 CSV 参数化数据集（可被多个压测场景绑定）。"""
    id = fields.IntField(pk=True, description="数据集ID")
    project = fields.ForeignKeyField(
        "models.Project", related_name="csv_datasets", description="所属项目"
    )
    name = fields.CharField(max_length=100, description="数据集名称")
    description = fields.TextField(null=True, description="描述")
    # 行数据: [{"col":"v"}, ...]
    row_data = fields.JSONField(default=list, null=True, description="CSV行数据")
    columns = fields.JSONField(default=list, description="列名列表")
    file_name = fields.CharField(max_length=255, default="", description="来源文件名")
    row_count = fields.IntField(default=0, description="行数")
    # 从场景遗留字段迁出时记录来源场景
    source_scene_id = fields.IntField(null=True, description="迁出来源场景ID")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, default="", description="创建人")

    class Meta:
        table = "perf_csv_dataset"
        table_description = "性能测试 CSV 数据集"


class PerfComparisonReport(models.Model):
    """性能测试增强报告（对比 / 汇总，2–20 条）"""
    id = fields.IntField(pk=True, description="增强报告ID")
    project = fields.ForeignKeyField(
        "models.Project", related_name="perf_comparison_reports", description="所属项目"
    )
    title = fields.CharField(max_length=200, description="报告标题")
    kind = fields.CharField(
        max_length=20,
        default="compare",
        description="报告类型: compare=对比 / merge=汇总 / hybrid=合并+对比",
    )
    record_ids = fields.JSONField(default=list, description="参与对比的执行记录ID列表")
    reference_record_id = fields.IntField(description="基准记录ID")
    snapshot = fields.JSONField(default=dict, description="对比快照（指标矩阵等）")
    ai_analysis = fields.JSONField(null=True, description="AI 分析结果")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "perf_comparison_report"
        table_description = "性能测试增强报告"


class PerfCronJob(models.Model):
    """性能测试定时任务"""
    id = fields.CharField(pk=True, max_length=100, description="任务ID")
    name = fields.CharField(max_length=100, description="任务名称")
    project = fields.ForeignKeyField("models.Project", related_name="perf_cron_jobs", description="所属项目")
    scene = fields.ForeignKeyField("models.PerfScene", related_name="cron_jobs", description="关联场景")

    # 定时配置
    run_type = fields.CharField(max_length=20, description="类型: Interval/date/crontab")
    interval = fields.IntField(default=3600, description="间隔(秒)")
    run_date = fields.DatetimeField(null=True, description="固定执行时间")
    crontab = fields.JSONField(default=dict, description="cron表达式")

    # 环境
    env_id = fields.IntField(description="执行环境ID")
    use_workers = fields.BooleanField(
        default=True,
        description="已废弃：施压一律派发 Worker，字段仅兼容旧数据",
    )

    # 执行记录关联
    last_run_record_id = fields.IntField(null=True, description="最后一次执行记录ID")
    last_run_time = fields.DatetimeField(null=True, description="最后一次执行时间")
    last_run_status = fields.CharField(max_length=20, null=True, description="最后一次执行状态")

    state = fields.BooleanField(default=False, description="是否启用")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, description="创建人")

    class Meta:
        table = "perf_cron_job"
        table_description = "性能测试定时任务"


class SutServer(models.Model):
    """被测服务器（被测监控采集器端）"""
    id = fields.IntField(pk=True, description="服务器ID")
    project = fields.ForeignKeyField(
        "models.Project", related_name="sut_servers", description="所属项目"
    )
    agent_uid = fields.CharField(max_length=64, null=True, description="采集器本地稳定身份")
    name = fields.CharField(max_length=100, description="展示名称")
    hostname = fields.CharField(max_length=255, default="", description="主机名")
    role = fields.CharField(max_length=64, default="", description="角色标签")
    token_hash = fields.CharField(max_length=128, description="Token 哈希")
    monitoring_enabled = fields.BooleanField(default=True, description="是否启用监控采样")
    schedule_json = fields.JSONField(null=True, description="免监控/仅监控时段配置")
    agent_settings_json = fields.JSONField(
        null=True,
        description="采集器运行参数（interval_sec/upload_every_sec/buffer_hours）；空=本机配置",
    )
    config_rev = fields.IntField(default=1, description="监控配置版本（日程/开关变更递增）")
    force_from_ms = fields.BigIntField(
        null=True, description="压测强制采集起始 epoch ms（补传按窗口判定）"
    )
    force_until_ms = fields.BigIntField(
        null=True, description="压测强制采集截止 epoch ms（覆盖 pause 日程）"
    )
    last_heartbeat_at = fields.DatetimeField(null=True, description="最近心跳")
    last_metrics_at = fields.DatetimeField(null=True, description="最近成功接收指标")
    host_info = fields.JSONField(default=dict, description="主机探测摘要")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, default="", description="创建人")

    class Meta:
        table = "sut_server"
        table_description = "被测服务器"


class SutApplication(models.Model):
    """被测应用（业务系统边界；压测选目标入口）"""
    id = fields.IntField(pk=True, description="应用ID")
    project = fields.ForeignKeyField(
        "models.Project", related_name="sut_applications", description="所属项目"
    )
    name = fields.CharField(max_length=100, description="应用名称")
    roles_json = fields.JSONField(default=list, description="角色清单，如 [esp, mysql]")
    remark = fields.CharField(max_length=500, default="", description="备注")
    is_del = fields.BooleanField(default=False, description="是否删除")
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)
    create_by = fields.CharField(max_length=50, default="", description="创建人")

    class Meta:
        table = "sut_application"
        table_description = "被测应用"


class SutAppEnvBinding(models.Model):
    """被测应用 × 环境 → 角色→采集器绑定"""
    id = fields.IntField(pk=True, description="绑定ID")
    application = fields.ForeignKeyField(
        "models.SutApplication", related_name="env_bindings", description="被测应用"
    )
    environment = fields.ForeignKeyField(
        "models.Environment", related_name="sut_app_bindings", description="环境"
    )
    bindings_json = fields.JSONField(
        default=list, description='[{role, server_ids: []}, ...]'
    )
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "sut_app_env_binding"
        table_description = "被测应用环境绑定"
        unique_together = (("application", "environment"),)


class SutMetricChunk(models.Model):
    """被测服务器近实时指标批次"""
    id = fields.IntField(pk=True, description="批次ID")
    server = fields.ForeignKeyField(
        "models.SutServer", related_name="metric_chunks", description="被测服务器"
    )
    start_ms = fields.BigIntField(description="批次起始 epoch ms")
    end_ms = fields.BigIntField(description="批次结束 epoch ms")
    points_json = fields.JSONField(default=list, description="采样点数组")
    received_at = fields.DatetimeField(auto_now_add=True, description="入库时间")

    class Meta:
        table = "sut_metric_chunk"
        table_description = "被测服务器指标 chunk"
        unique_together = (("server", "start_ms"),)


class PerfRecordSutMetric(models.Model):
    """压测记录的被测资源快照（M3 写入；M1 占位建表）"""
    id = fields.IntField(pk=True, description="ID")
    record = fields.ForeignKeyField(
        "models.PerfRecord", related_name="sut_metrics", description="压测记录"
    )
    server = fields.ForeignKeyField(
        "models.SutServer", related_name="record_snapshots", null=True, description="被测服务器"
    )
    server_snapshot_json = fields.JSONField(default=dict, description="当时服务器快照")
    series_json = fields.JSONField(default=list, description="降采样曲线")
    summary_json = fields.JSONField(default=dict, description="汇总指标")
    source = fields.CharField(max_length=32, default="agent", description="agent|vm|grafana_link")
    status = fields.CharField(max_length=32, default="no_data", description="complete|partial|no_data|offline|failed")
    coverage = fields.FloatField(null=True, description="覆盖率 0~1")
    grafana_url = fields.CharField(max_length=1024, null=True, description="Grafana 深链")
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "perf_record_sut_metric"
        table_description = "压测记录被测资源快照"
        unique_together = (("record", "server"),)
