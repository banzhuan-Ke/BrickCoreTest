import pika
import json
import time
from app.core.platform.config import MQ_CONFIG
from pika.exceptions import AMQPConnectionError


class MQProducer:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.reconnect()

    def reconnect(self):
        """
        尝试重新连接到RabbitMQ服务器
        """
        while True:
            try:
                # 连接到RabbitMQ服务器
                self.connection = pika.BlockingConnection(pika.ConnectionParameters(
                    host=MQ_CONFIG.get('host'), port=MQ_CONFIG.get('port'),
                    credentials=pika.credentials.PlainCredentials(username=MQ_CONFIG.get('username'),
                                                                  password=MQ_CONFIG.get('password')),
                    # 设置心跳检测
                    heartbeat=600,
                    # 设置阻塞连接超时时间
                    blocked_connection_timeout=300,
                    # 尝试连接的次数
                    connection_attempts=3,
                    # 重试连接的延迟时间（秒）
                    retry_delay=5)
                )
                # 创建一个通道
                self.channel = self.connection.channel()
                print("mq连接成功")
                # 连接成功，退出循环
                break
            except pika.exceptions.AMQPConnectionError as e:
                print(f"连接错误 {e}，等待5秒后重新连接...")
                # 等待5秒后重试连接
                time.sleep(5)

    def send_test_task(self, env_config, run_case, device_id):
        """
        :param env_config: 运行用例的环境数据
        :param run_case: 运行用例的套件数据
        :param device_id: 指定执行的设备
        :return:
        """
        data = {
            'env_config': env_config,
            'run_suite': run_case
        }
        msg = json.dumps(data, ensure_ascii=False).encode('utf-8')
        if self.connection is None or self.channel is None or self.connection.is_closed or self.channel.is_closed:
            # 重新连接
            self.reconnect()
        # 连接到通道
        self.channel = self.connection.channel()
        # 声明队列device_id
        self.channel.queue_declare(queue=device_id, durable=True)
        # 提交消息到队列device_id中
        self.channel.basic_publish(exchange='', routing_key=device_id, body=msg,
                                   properties=pika.BasicProperties(delivery_mode=2))

    def send_stop_task(
        self,
        device_id,
        plan_execution_id=None,
        suite_execution_id=None,
        record_session_id=None,
        case_execution_id=None,
        debug_session_id=None,
    ):
        """
        发送停止执行消息到指定设备
        
        :param device_id: 目标设备ID
        :param plan_execution_id: 计划执行记录ID
        :param suite_execution_id: 套件执行记录ID
        :param record_session_id: 录制会话ID
        :param case_execution_id: 单用例执行记录ID
        :param debug_session_id: UI 交互调试会话ID
        """
        data = {
            "action": "stop",
            "plan_execution_id": plan_execution_id,
            "suite_execution_id": suite_execution_id,
            "record_session_id": record_session_id,
            "case_execution_id": case_execution_id,
            "debug_session_id": debug_session_id,
        }
        msg = json.dumps(data, ensure_ascii=False).encode('utf-8')
        if self.connection is None or self.channel is None or self.connection.is_closed or self.channel.is_closed:
            self.reconnect()
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=device_id, durable=True)
        self.channel.basic_publish(exchange='', routing_key=device_id, body=msg,
                                   properties=pika.BasicProperties(delivery_mode=2))

    def close(self):
        """关闭mq对象"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
