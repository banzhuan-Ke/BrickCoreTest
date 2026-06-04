from tortoise import fields, models


class Case(models.Model):
    """测试用例的模型定义"""
    id = fields.IntField(pk=True, description="用例id", max_length=100, auto_increment=True)
    name = fields.CharField(max_length=50, description="用例名称")
    project = fields.ForeignKeyField("models.Project", related_name="cases", description="所属项目")
    create_time = fields.DatetimeField(auto_now_add=True, description="创建时间")
    update_time = fields.DatetimeField(auto_now=True, description="更新时间")
    steps = fields.JSONField(description="用例执行步骤", default=list)
    level = fields.CharField(description="用例等级", default='1', choices=[("0", "高"), ("1", "中"), ("2", "低")],
                             max_length=50)
    username = fields.CharField(max_length=50, description="创建人")
    is_del = fields.BooleanField(description="是否删除", default=False)

    class Meta:
        table = "case"
        table_description = "测试用例"
