from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE `project` SET `default_headers` = JSON_ARRAY() WHERE `default_headers` IS NULL;
        UPDATE `environment` SET `default_headers` = JSON_ARRAY() WHERE `default_headers` IS NULL;
        UPDATE `api_definition` SET `global_header_policy` = JSON_OBJECT() WHERE `global_header_policy` IS NULL;
        UPDATE `api_test_case` SET `global_header_policy` = JSON_OBJECT() WHERE `global_header_policy` IS NULL;
    """


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        UPDATE `project` SET `default_headers` = NULL WHERE `default_headers` = JSON_ARRAY();
        UPDATE `environment` SET `default_headers` = NULL WHERE `default_headers` = JSON_ARRAY();
        UPDATE `api_definition` SET `global_header_policy` = NULL WHERE `global_header_policy` = JSON_OBJECT();
        UPDATE `api_test_case` SET `global_header_policy` = NULL WHERE `global_header_policy` = JSON_OBJECT();
    """
