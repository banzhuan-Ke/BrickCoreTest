"""Runner 中间件 ACL 命令白名单"""
from app.core.runner_middleware import _REDIS_COMMANDS


def test_redis_acl_includes_select_for_db_switch():
    assert "+select" in _REDIS_COMMANDS


def test_redis_acl_includes_pubsub_commands():
    for cmd in ("+subscribe", "+unsubscribe", "+psubscribe", "+punsubscribe"):
        assert cmd in _REDIS_COMMANDS
