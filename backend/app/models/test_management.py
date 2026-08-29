"""
测试管理交付闭环 — Phase 1 模型（版本 / 范围 / 资产映射）
"""
from tortoise import fields, models


class TestRelease(models.Model):
    """可交付的版本 / 迭代"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="test_releases",
        description="所属项目",
    )
    release_key = fields.CharField(max_length=64, description="项目内版本键，如 2026.08.0")
    name = fields.CharField(max_length=200, description="版本名称")
    description = fields.TextField(null=True, description="说明")
    status = fields.CharField(
        max_length=32,
        default="draft",
        description="draft/testing/ready/released/archived",
    )
    owner_id = fields.IntField(null=True, description="测试负责人用户 ID")
    planned_start_at = fields.DatetimeField(null=True, description="计划开始")
    planned_release_at = fields.DatetimeField(null=True, description="计划发布")
    actual_release_at = fields.DatetimeField(null=True, description="实际发布")
    external_url = fields.CharField(max_length=500, null=True, description="外部迭代/发布单链接")
    quality_status = fields.CharField(
        max_length=32,
        null=True,
        description="最近质量判定冗余：pass/conditional_pass/failed/blocked",
    )

    is_del = fields.BooleanField(default=False)
    delete_seq = fields.IntField(
        default=0,
        description="软删序号：活跃行为 0，软删后写为自身 id，避免唯一键冲突",
    )
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "test_release"
        table_description = "测试管理-版本"
        unique_together = (("project", "release_key", "delete_seq"),)
        indexes = (("project_id", "is_del"),)


class TestReleaseRequirement(models.Model):
    """版本关联的外部需求 / 工作项"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="test_release_requirements",
        description="所属项目",
    )
    release = fields.ForeignKeyField(
        "models.TestRelease",
        related_name="requirements",
        description="所属版本",
    )
    requirement_key = fields.CharField(max_length=128, description="外部需求编号")
    title = fields.CharField(max_length=500, default="", description="标题")
    url = fields.CharField(max_length=500, null=True, description="外部链接")
    note = fields.TextField(null=True, description="备注")
    ai_requirement_id = fields.IntField(null=True, description="关联 AI 需求 ID")
    source_type = fields.CharField(
        max_length=16,
        default="external",
        description="ai=项目需求 external=外部手工",
    )

    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "test_release_requirement"
        table_description = "测试管理-版本需求"


class TestReleaseScope(models.Model):
    """版本纳入的功能测试用例"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="test_release_scopes",
        description="所属项目",
    )
    release = fields.ForeignKeyField(
        "models.TestRelease",
        related_name="scopes",
        description="所属版本",
    )
    functional_case_id = fields.IntField(description="功能用例库 ID")
    scope_status = fields.CharField(
        max_length=32,
        default="planned",
        description="planned/ready/blocked/not_applicable/completed",
    )
    risk_level = fields.CharField(
        max_length=32,
        default="medium",
        description="low/medium/high/critical",
    )
    requirement_key = fields.CharField(max_length=128, null=True, description="需求编号冗余")
    automation_status = fields.CharField(
        max_length=32,
        default="none",
        description="none/partial/covered/unstable",
    )
    owner_id = fields.IntField(null=True, description="该项负责人用户 ID")
    note = fields.TextField(null=True, description="范围说明")

    is_del = fields.BooleanField(default=False)
    delete_seq = fields.IntField(
        default=0,
        description="软删序号：活跃行为 0，软删后写为自身 id",
    )
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "test_release_scope"
        table_description = "测试管理-版本范围"
        unique_together = (("release", "functional_case_id", "delete_seq"),)
        indexes = (("project_id", "functional_case_id", "is_del"),)


class TestAssetLink(models.Model):
    """功能用例 ↔ 自动化资产映射"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="test_asset_links",
        description="所属项目",
    )
    functional_case_id = fields.IntField(description="功能用例库 ID")
    asset_type = fields.CharField(
        max_length=32,
        description="ui_case/app_case/api_case/perf_scene",
    )
    asset_id = fields.IntField(description="自动化资产主键")
    link_type = fields.CharField(
        max_length=32,
        default="primary",
        description="primary/partial/regression",
    )
    coverage_note = fields.TextField(null=True, description="覆盖说明")
    health_status = fields.CharField(
        max_length=32,
        default="unknown",
        description="unknown/healthy/unstable/broken",
    )

    is_del = fields.BooleanField(default=False)
    delete_seq = fields.IntField(
        default=0,
        description="软删序号：活跃行为 0，软删后写为自身 id",
    )
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "test_asset_link"
        table_description = "测试管理-资产映射"
        unique_together = (("functional_case_id", "asset_type", "asset_id", "delete_seq"),)
        indexes = (("project_id", "functional_case_id", "is_del"),)


# ========== Phase 2：评审 / 计划 / 手工运行 ==========


class CaseReviewTemplate(models.Model):
    """用例评审检查清单模板"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="case_review_templates",
        description="所属项目",
    )
    name = fields.CharField(max_length=200, description="模板名称")
    description = fields.TextField(null=True, description="说明")
    checklist = fields.JSONField(
        default=list,
        description="检查项 [{key,label,required}]",
    )
    is_default = fields.BooleanField(default=False, description="是否默认模板")

    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "case_review_template"
        table_description = "测试管理-评审模板"


class CaseReview(models.Model):
    """用例评审批次"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="case_reviews",
        description="所属项目",
    )
    release = fields.ForeignKeyField(
        "models.TestRelease",
        related_name="case_reviews",
        null=True,
        on_delete=fields.SET_NULL,
        description="关联版本（可选）",
    )
    template = fields.ForeignKeyField(
        "models.CaseReviewTemplate",
        related_name="reviews",
        null=True,
        on_delete=fields.SET_NULL,
        description="评审模板",
    )
    title = fields.CharField(max_length=200, description="评审标题")
    status = fields.CharField(
        max_length=32,
        default="pending",
        description="pending/in_review/approved/changes_requested/cancelled",
    )
    due_at = fields.DatetimeField(null=True, description="截止日期")
    reviewer_ids = fields.JSONField(default=list, description="必选评审人用户 ID 列表")
    summary = fields.TextField(null=True, description="评审总结")
    final_decision = fields.CharField(
        max_length=32,
        null=True,
        description="版本负责人最终裁定 approved/changes_requested/rejected",
    )
    final_decision_by = fields.IntField(null=True, description="最终裁定人用户 ID")
    final_decision_at = fields.DatetimeField(null=True, description="最终裁定时间")
    final_comment = fields.TextField(null=True, description="最终裁定说明")
    checklist_snapshot = fields.JSONField(default=list, description="发起时模板清单快照")

    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "case_review"
        table_description = "测试管理-评审批次"


class CaseReviewItem(models.Model):
    """评审批次中的单条用例"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="case_review_items",
        description="所属项目",
    )
    review = fields.ForeignKeyField(
        "models.CaseReview",
        related_name="items",
        description="所属评审",
    )
    functional_case_id = fields.IntField(description="功能用例库 ID")
    decision = fields.CharField(
        max_length=32,
        default="pending",
        description="聚合结论 pending/approved/changes_requested/rejected",
    )
    comment = fields.TextField(null=True, description="最新意见摘要")
    checklist_result = fields.JSONField(default=dict, description="清单勾选结果")
    owner_decision = fields.CharField(
        max_length=32,
        null=True,
        description="版本负责人单条裁定 approved/changes_requested/rejected",
    )
    owner_decision_by = fields.IntField(null=True, description="单条裁定人用户 ID")
    owner_decision_at = fields.DatetimeField(null=True, description="单条裁定时间")
    owner_comment = fields.TextField(null=True, description="单条裁定说明")
    decisions_json = fields.JSONField(
        default=list,
        description="各评审人结论 [{reviewer_id,decision,comment,at}]",
    )

    is_del = fields.BooleanField(default=False)
    delete_seq = fields.IntField(
        default=0,
        description="软删序号：活跃行为 0，软删后写为自身 id",
    )
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "case_review_item"
        table_description = "测试管理-评审项"
        unique_together = (("review", "functional_case_id", "delete_seq"),)


class TestPlan(models.Model):
    """版本下的测试计划（管理层，非自动化模块计划）"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="tm_test_plans",
        description="所属项目",
    )
    release = fields.ForeignKeyField(
        "models.TestRelease",
        related_name="plans",
        description="所属版本",
    )
    name = fields.CharField(max_length=200, description="计划名称")
    plan_type = fields.CharField(
        max_length=32,
        default="regression",
        description="smoke/regression/acceptance/performance/custom",
    )
    environment_id = fields.IntField(null=True, description="默认环境 ID")
    entry_criteria = fields.TextField(null=True, description="进入标准")
    exit_criteria = fields.TextField(null=True, description="退出标准")
    status = fields.CharField(
        max_length=32,
        default="draft",
        description="draft/ready/running/completed/cancelled",
    )
    description = fields.TextField(null=True, description="说明")

    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tm_test_plan"
        table_description = "测试管理-测试计划"


class TestPlanItem(models.Model):
    """测试计划项"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="tm_test_plan_items",
        description="所属项目",
    )
    plan = fields.ForeignKeyField(
        "models.TestPlan",
        related_name="items",
        description="所属计划",
    )
    item_type = fields.CharField(
        max_length=32,
        default="functional_manual",
        description="functional_manual/ui_case/app_case/api_case/perf_scene",
    )
    source_scope_id = fields.IntField(null=True, description="来源范围项 ID")
    functional_case_id = fields.IntField(null=True, description="功能用例 ID")
    asset_id = fields.IntField(null=True, description="自动化资产 ID")
    title = fields.CharField(max_length=500, default="", description="项标题快照")
    execution_mode = fields.CharField(
        max_length=32,
        default="manual",
        description="manual/automation",
    )
    order_no = fields.IntField(default=0, description="排序")
    required = fields.BooleanField(default=True, description="是否必测")

    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tm_test_plan_item"
        table_description = "测试管理-计划项"


class TestPlanRun(models.Model):
    """一次不可变的计划运行"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="tm_test_plan_runs",
        description="所属项目",
    )
    plan = fields.ForeignKeyField(
        "models.TestPlan",
        related_name="runs",
        description="所属计划",
    )
    release_id = fields.IntField(description="版本 ID 快照")
    environment_id = fields.IntField(null=True, description="运行环境")
    status = fields.CharField(
        max_length=32,
        default="running",
        description="running/completed/cancelled",
    )
    trigger_source = fields.CharField(max_length=32, default="web", description="触发来源")
    snapshot_json = fields.JSONField(default=dict, description="版本/环境/规则快照")
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)

    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tm_test_plan_run"
        table_description = "测试管理-计划运行"


class TestPlanRunItem(models.Model):
    """计划运行项结果投影"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="tm_test_plan_run_items",
        description="所属项目",
    )
    run = fields.ForeignKeyField(
        "models.TestPlanRun",
        related_name="items",
        description="所属运行",
    )
    plan_item_id = fields.IntField(null=True, description="来源计划项 ID")
    item_type = fields.CharField(max_length=32, default="functional_manual")
    functional_case_id = fields.IntField(null=True)
    asset_id = fields.IntField(null=True)
    title = fields.CharField(max_length=500, default="")
    execution_mode = fields.CharField(max_length=32, default="manual")
    required = fields.BooleanField(default=True)
    order_no = fields.IntField(default=0)

    status = fields.CharField(
        max_length=32,
        default="pending",
        description="pending/running/done/blocked",
    )
    result_status = fields.CharField(
        max_length=32,
        default="not_run",
        description="not_run/passed/failed/blocked/skipped/cancelled/error",
    )
    assignee_id = fields.IntField(null=True, description="执行人")
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    result_message = fields.TextField(null=True, description="结果说明")
    evidence_json = fields.JSONField(default=dict, description="证据摘要")
    original_record_type = fields.CharField(max_length=32, null=True)
    original_record_id = fields.IntField(null=True)
    attempt_count = fields.IntField(default=0, description="尝试次数")

    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tm_test_plan_run_item"
        table_description = "测试管理-运行项"


class TestPlanRunItemAttempt(models.Model):
    """运行项复测历史"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="tm_run_item_attempts",
        description="所属项目",
    )
    run_item = fields.ForeignKeyField(
        "models.TestPlanRunItem",
        related_name="attempts",
        description="所属运行项",
    )
    attempt_no = fields.IntField(description="第几次尝试")
    result_status = fields.CharField(max_length=32, description="结果")
    result_message = fields.TextField(null=True)
    evidence_json = fields.JSONField(default=dict)
    operator = fields.CharField(max_length=50, default="")
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "tm_test_plan_run_item_attempt"
        table_description = "测试管理-运行项尝试"


# ========== Phase 3：缺陷 ==========


class TestDefect(models.Model):
    """站内缺陷台账"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="test_defects",
        description="所属项目",
    )
    release = fields.ForeignKeyField(
        "models.TestRelease",
        related_name="defects",
        null=True,
        on_delete=fields.SET_NULL,
        description="归属版本",
    )
    defect_key = fields.CharField(max_length=64, description="项目内编号")
    title = fields.CharField(max_length=500, description="标题")
    description = fields.TextField(null=True, description="描述")
    severity = fields.CharField(
        max_length=32,
        default="major",
        description="blocker/critical/major/minor",
    )
    priority = fields.CharField(
        max_length=8,
        default="p2",
        description="p0/p1/p2/p3",
    )
    status = fields.CharField(
        max_length=32,
        default="open",
        description="open/in_progress/resolved/verified/closed/rejected",
    )
    found_in = fields.CharField(max_length=128, null=True, description="发现版本")
    fixed_in = fields.CharField(max_length=128, null=True, description="修复版本")
    assignee_id = fields.IntField(null=True, description="负责人")
    reporter_id = fields.IntField(null=True, description="提报人")
    handler_id = fields.IntField(null=True, description="当前处理人")
    attributor_id = fields.IntField(null=True, description="缺陷归属人（引入问题者）")
    external_system = fields.CharField(max_length=64, null=True)
    external_key = fields.CharField(max_length=128, null=True)
    external_url = fields.CharField(max_length=500, null=True)
    resolution_type = fields.CharField(max_length=32, null=True, description="处理方案类型")
    resolution_detail = fields.TextField(null=True, description="处理说明")
    root_cause = fields.TextField(null=True, description="产生原因")
    attachments = fields.JSONField(
        default=list,
        description="附件 [{uid,name,key,bucket,mime,size,kind}]",
    )

    is_del = fields.BooleanField(default=False)
    delete_seq = fields.IntField(
        default=0,
        description="软删序号：活跃行为 0，软删后写为自身 id",
    )
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "test_defect"
        table_description = "测试管理-缺陷"
        unique_together = (("project", "defect_key", "delete_seq"),)
        indexes = (("project_id", "status", "is_del"),)


class TestDefectLink(models.Model):
    """缺陷关联证据"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="test_defect_links",
        description="所属项目",
    )
    defect = fields.ForeignKeyField(
        "models.TestDefect",
        related_name="links",
        description="缺陷",
    )
    link_type = fields.CharField(
        max_length=32,
        description="run_item/functional_case/requirement/asset/external",
    )
    run_item_id = fields.IntField(null=True)
    functional_case_id = fields.IntField(null=True)
    requirement_id = fields.IntField(null=True, description="关联需求 AiRequirement ID")
    asset_type = fields.CharField(max_length=32, null=True)
    asset_id = fields.IntField(null=True)
    external_url = fields.CharField(max_length=500, null=True)
    note = fields.TextField(null=True)

    is_del = fields.BooleanField(default=False)
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "test_defect_link"
        table_description = "测试管理-缺陷关联"


class TestDefectComment(models.Model):
    """缺陷处理评论"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="test_defect_comments",
        description="所属项目",
    )
    defect = fields.ForeignKeyField(
        "models.TestDefect",
        related_name="comments",
        description="缺陷",
    )
    body = fields.TextField(description="评论内容")
    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "test_defect_comment"
        table_description = "测试管理-缺陷评论"
        indexes = (("defect_id", "is_del"),)


class TestDefectActivity(models.Model):
    """缺陷活动时间线（状态/指派/关联等）"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="test_defect_activities",
        description="所属项目",
    )
    defect = fields.ForeignKeyField(
        "models.TestDefect",
        related_name="activities",
        description="缺陷",
    )
    action = fields.CharField(
        max_length=32,
        description="created/status_change/assignee_change/comment/link_add/link_remove",
    )
    from_value = fields.CharField(max_length=255, null=True)
    to_value = fields.CharField(max_length=255, null=True)
    note = fields.TextField(null=True)
    actor = fields.CharField(max_length=50, default="")
    create_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "test_defect_activity"
        table_description = "测试管理-缺陷活动"
        indexes = (("defect_id", "create_time"),)


# ========== Phase 3 补全：需求可测性评审 ==========


class RequirementReview(models.Model):
    """AI 需求可测性评审批次"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="requirement_reviews",
        description="所属项目",
    )
    requirement_id = fields.IntField(description="AiRequirement ID")
    status = fields.CharField(
        max_length=32,
        default="pending",
        description="pending/in_review/approved/changes_requested/rejected",
    )
    reviewer_ids = fields.JSONField(default=list, description="评审人用户 ID")
    round = fields.IntField(default=1, description="评审轮次")
    ai_assist_summary = fields.TextField(null=True, description="AI 辅助摘要")
    summary = fields.TextField(null=True, description="人工总结")
    decisions_json = fields.JSONField(
        default=list,
        description="各评审人结论 [{reviewer_id,decision,comment,at}]",
    )

    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "requirement_review"
        table_description = "测试管理-需求可测性评审"


class RequirementReviewItem(models.Model):
    """需求评审逐条意见"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="requirement_review_items",
        description="所属项目",
    )
    review = fields.ForeignKeyField(
        "models.RequirementReview",
        related_name="items",
        description="所属评审批次",
    )
    section_id = fields.CharField(max_length=64, null=True, description="章节 ID")
    category = fields.CharField(
        max_length=64,
        default="other",
        description="scope_unclear/acceptance_missing/...",
    )
    severity = fields.CharField(max_length=32, default="medium")
    comment = fields.TextField(null=True)
    suggested_fix = fields.TextField(null=True)

    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "requirement_review_item"
        table_description = "测试管理-需求评审意见"


# ========== Phase 4：质量门禁快照 ==========


class ReleaseQualitySnapshot(models.Model):
    """版本质量门禁结论快照（可审计）"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="release_quality_snapshots",
        description="所属项目",
    )
    release = fields.ForeignKeyField(
        "models.TestRelease",
        related_name="quality_snapshots",
        description="所属版本",
    )
    conclusion = fields.CharField(
        max_length=32,
        description="pass/conditional_pass/failed/blocked",
    )
    metrics_json = fields.JSONField(default=dict, description="汇总指标")
    rules_json = fields.JSONField(default=dict, description="门禁阈值")
    checks_json = fields.JSONField(default=list, description="逐项判定")
    plan_run_ids = fields.JSONField(default=list, description="纳入统计的运行 ID")
    waiver_reason = fields.TextField(null=True, description="豁免原因")
    waiver_approved_by = fields.CharField(max_length=50, null=True, description="豁免批准人")
    waiver_approved_at = fields.DatetimeField(null=True, description="豁免批准时间")
    note = fields.TextField(null=True, description="备注")

    is_del = fields.BooleanField(default=False)
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "release_quality_snapshot"
        table_description = "测试管理-版本质量快照"
        indexes = (("project_id", "release_id", "is_del"),)


class TestReleaseAiSummary(models.Model):
    """版本 AI 测试总结缓存"""

    id = fields.IntField(pk=True)
    project = fields.ForeignKeyField(
        "models.Project",
        related_name="test_release_ai_summaries",
        description="所属项目",
    )
    release = fields.ForeignKeyField(
        "models.TestRelease",
        related_name="ai_summary",
        unique=True,
        description="所属版本",
    )
    summary_json = fields.JSONField(default=dict, description="AI 总结结构化结果")
    create_by = fields.CharField(max_length=50, default="")
    update_by = fields.CharField(max_length=50, null=True)
    create_time = fields.DatetimeField(auto_now_add=True)
    update_time = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "test_release_ai_summary"
        table_description = "测试管理-版本 AI 总结"
        indexes = (("project_id", "release_id"),)

