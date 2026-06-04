"""
通知服务 - 统一封装邮件、钉钉、企微发送逻辑
"""
import json
import hmac
import hashlib
import base64
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from datetime import datetime
from typing import List, Optional

import httpx
import smtplib

from app.models.sys import NotificationConfig, SystemSmtpConfig, Project, NotificationLog
from app.models.http import ApiSuiteRunRecord, ApiRunRecord, ApiPlanRunRecord
from app.models.perf import PerfRecord
from app.models.ui import UiPlanExecution, UiSuiteExecution, UiCaseExecution
from app.core.api_report_export import generate_api_html_report
from app.core.report_export import generate_html_report, ImageExportOptions


class NotificationService:
    """统一通知服务"""

    @staticmethod
    async def _log(
        project_id: Optional[int],
        channel_type: str,
        notify_type: str,
        title: str,
        content_summary: dict,
        recipients: List[str],
        status: str,
        error_msg: str = "",
        related_id: Optional[int] = None,
        related_type: str = ""
    ):
        """记录推送日志"""
        try:
            await NotificationLog.create(
                project_id=project_id,
                channel_type=channel_type,
                notify_type=notify_type,
                title=title,
                content_summary=content_summary,
                recipients=recipients,
                status=status,
                error_msg=error_msg,
                related_id=related_id,
                related_type=related_type
            )
        except Exception as e:
            print(f"[NotificationService] 写入推送日志失败: {e}")

    @staticmethod
    async def send_alert(project_id: int, title: str, content: dict, related_id: Optional[int] = None, related_type: str = ""):
        """
        执行失败告警入口
        content 结构示例:
        {
            "execution_type": "API套件/UI计划/UI套件",
            "name": "套件名称",
            "status": "failed",
            "total": 10,
            "success": 8,
            "failed": 2,
            "pass_rate": 80.0,
            "duration": 12.5,
            "run_by": "admin",
            "link": "http://xxx/records/123"
        }
        """
        configs = await NotificationConfig.filter(project_id=project_id, enabled=True).all()
        if not configs:
            return

        for cfg in configs:
            status_flag = "failed"
            error_text = ""
            recipients = []
            try:
                if cfg.channel_type == "email":
                    recipients = cfg.config.get("recipients", [])
                    if not recipients:
                        raise ValueError("未配置收件人")
                    await NotificationService._send_email_alert(cfg, title, content)
                elif cfg.channel_type == "dingtalk":
                    await NotificationService._send_dingtalk_alert(cfg, title, content)
                elif cfg.channel_type == "wechat":
                    await NotificationService._send_wechat_alert(cfg, title, content)
                status_flag = "success"
            except Exception as e:
                error_text = str(e)
                print(f"[NotificationService] 发送告警失败 ({cfg.channel_type}): {e}")
            finally:
                await NotificationService._log(
                    project_id=project_id,
                    channel_type=cfg.channel_type,
                    notify_type="alert",
                    title=title,
                    content_summary=content,
                    recipients=recipients if cfg.channel_type == "email" else [cfg.config.get("webhook_url", "")],
                    status=status_flag,
                    error_msg=error_text,
                    related_id=related_id,
                    related_type=related_type
                )

    @staticmethod
    async def send_api_report(
        project_id: int,
        record_id: int,
        recipients: Optional[List[str]] = None,
        record_type: str = "suite",
    ):
        """发送 API 测试报告邮件（支持套件/计划执行记录）"""
        if record_type == "plan":
            record = await ApiPlanRunRecord.get_or_none(id=record_id)
            if not record:
                raise ValueError("执行记录不存在")
            plan = await record.plan
            from app.routers.http.utils import api_run_result_to_case_display
            from app.core.api_report_export import sum_plan_item_results_http_ms, sum_http_response_time_ms

            plan_items = []
            all_case_results = []
            for item in (record.item_results or []):
                item_copy = dict(item)
                case_list = [
                    api_run_result_to_case_display(cr)
                    for cr in (item.get("case_results") or [])
                ]
                item_copy["case_results"] = case_list
                plan_items.append(item_copy)
                all_case_results.extend(case_list)
            report_record = {
                "id": record.id,
                "suite_name": plan.name if plan else "未知计划",
                "status": record.status,
                "trigger_type": record.trigger_type,
                "total_cases": record.total_cases,
                "success_cases": record.success_cases,
                "failed_cases": record.failed_cases,
                "skipped_cases": 0,
                "error_cases": 0,
                "start_time": record.start_time,
                "end_time": record.end_time,
                "duration": record.duration or 0,
                "http_duration": sum_plan_item_results_http_ms(plan_items) or None,
                "env_name": record.env_name,
                "run_by": record.run_by,
            }
            html_content = generate_api_html_report(
                report_record, all_case_results, plan_items=plan_items, report_type="plan"
            )
            filename = f"api_plan_report_{record_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            report_name = report_record["suite_name"]
            related_type = "api_plan_run_record"
            body_label = "计划名称"
        else:
            record = await ApiSuiteRunRecord.get_or_none(id=record_id)
            if not record:
                raise ValueError("执行记录不存在")

            suite = await record.suite
            case_records = await ApiRunRecord.filter(suite_run_record_id=record_id).order_by("id").all()

            all_case_results = []
            from app.core.api_report_export import resolve_http_response_time

            for cr in case_records:
                case = await cr.case
                req_detail = cr.request_detail or {}
                case_item = {
                    "record_id": cr.id,
                    "case_id": cr.case_id,
                    "case_name": case.name if case else "未知",
                    "status": cr.status,
                    "response_status": cr.response_status,
                    "response_time": cr.response_time,
                    "response_body": cr.response_body,
                    "response_headers": cr.response_headers,
                    "assertions": cr.assertions_result,
                    "assertions_result": cr.assertions_result,
                    "extracted_vars": cr.extracted_vars,
                    "extractor_results": (cr.request_detail or {}).get("extractor_results") or [],
                    "error_msg": cr.error_msg,
                    "start_time": cr.start_time,
                    "request_detail": cr.request_detail or {},
                    "request_url": cr.request_url,
                    "request_headers": cr.request_headers,
                    "request_body": cr.request_body,
                }
                http_ms = resolve_http_response_time(case_item)
                if http_ms is not None:
                    case_item["http_response_time"] = http_ms
                all_case_results.append(case_item)

            report_record = {
                "id": record.id,
                "suite_name": suite.name if suite else "未知套件",
                "status": record.status,
                "trigger_type": record.trigger_type,
                "total_cases": record.total_cases,
                "success_cases": record.success_cases,
                "failed_cases": record.failed_cases,
                "skipped_cases": record.skipped_cases,
                "error_cases": 0,
                "start_time": record.start_time,
                "end_time": record.end_time,
                "duration": record.duration,
                "http_duration": sum_http_response_time_ms(all_case_results) or None,
                "env_name": record.env_name,
                "run_by": record.run_by,
                "hooks_result": getattr(record, "hooks_result", None) or {},
            }
            html_content = generate_api_html_report(report_record, all_case_results)
            filename = f"api_report_{record_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            report_name = report_record["suite_name"]
            related_type = "api_suite_run_record"
            body_label = "套件名称"

        subject = f"[API测试报告] {report_name} - {record.status}"
        body_html = f"""
        <h3>API 测试执行报告</h3>
        <p><b>{body_label}：</b>{report_name}</p>
        <p><b>执行状态：</b>{record.status}</p>
        <p><b>总用例数：</b>{record.total_cases}</p>
        <p><b>成功：</b>{record.success_cases} / <b>失败：</b>{record.failed_cases}</p>
        <p><b>执行人：</b>{record.run_by}</p>
        <p>详细报告请查看附件。</p>
        """

        to_list = recipients
        if not to_list:
            email_cfg = await NotificationConfig.filter(
                project_id=project_id, channel_type="email", enabled=True
            ).first()
            if email_cfg:
                to_list = email_cfg.config.get("recipients", [])

        if not to_list:
            raise ValueError("未配置邮件收件人")

        status_flag = "failed"
        error_text = ""
        try:
            await NotificationService._send_email(
                to=to_list,
                subject=subject,
                body_html=body_html,
                attachments=[(filename, html_content, "text/html")]
            )
            status_flag = "success"
        except Exception as e:
            error_text = str(e)
            raise
        finally:
            await NotificationService._log(
                project_id=project_id,
                channel_type="email",
                notify_type="report",
                title=subject,
                content_summary={"name": report_name, "status": record.status},
                recipients=to_list,
                status=status_flag,
                error_msg=error_text,
                related_id=record_id,
                related_type=related_type,
            )

    @staticmethod
    async def send_ui_report(plan_execution_id: int):
        """发送 UI 测试报告邮件（计划级别）"""
        record = await UiPlanExecution.get_or_none(id=plan_execution_id, is_del=False).prefetch_related('task')
        if not record:
            raise ValueError("计划执行记录不存在")

        project = await record.project
        project_id = project.id if project else None

        # 查询计划下的所有套件执行记录
        suite_records_db = await UiSuiteExecution.filter(plan_execution=plan_execution_id, is_del=False).prefetch_related('suite')
        suite_records = []
        for sr in suite_records_db:
            suite_records.append({
                "id": sr.id,
                "suite_name": sr.suite.name if sr.suite else "未知套件",
                "status": sr.status,
                "case_count": sr.case_count,
                "success": sr.success,
                "fail": sr.fail,
                "error": sr.error,
                "skip": sr.skip,
                "no_run": sr.no_run,
                "pass_rate": sr.pass_rate,
                "execution_log": sr.execution_log,
                "duration": sr.duration,
                "start_time": sr.start_time
            })

        # 查询所有用例执行记录
        case_records = []
        for sr in suite_records_db:
            case_records_db = await UiCaseExecution.filter(suite_execution=sr.id, is_del=False).prefetch_related('case')
            for cr in case_records_db:
                case_records.append({
                    "id": cr.id,
                    "case_name": cr.case.name if cr.case else "未知用例",
                    "status": cr.status,
                    "result_data": cr.result_data,
                    "suite_execution_id": sr.id,
                    "start_time": cr.start_time
                })

        record_data = {
            "id": record.id,
            "task_name": record.task.name if record.task else "未知计划",
            "username": record.username,
            "start_time": record.start_time,
            "duration": record.duration,
            "status": record.status,
            "case_count": record.case_count,
            "success": record.success,
            "fail": record.fail,
            "error": record.error,
            "skip": record.skip,
            "no_run": record.no_run,
            "pass_rate": record.pass_rate,
            "env": record.env,
            "execution_log": record.execution_log
        }

        img_options = ImageExportOptions(include_images=False, image_mode="none", include_video=False)
        html_content = generate_html_report(record_data, "task", suite_records, case_records, img_options)
        filename = f"ui_report_{plan_execution_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        subject = f"[UI测试报告] {record_data['task_name']} - {record.status}"
        body_html = f"""
        <h3>UI 测试执行报告</h3>
        <p><b>计划名称：</b>{record_data['task_name']}</p>
        <p><b>执行状态：</b>{record.status}</p>
        <p><b>总用例数：</b>{record.case_count}</p>
        <p><b>成功：</b>{record.success} / <b>失败：</b>{record.fail}</p>
        <p><b>执行人：</b>{record.username}</p>
        <p>详细报告请查看附件。</p>
        """

        # 读取邮件收件人
        email_cfg = await NotificationConfig.filter(
            project_id=project_id, channel_type="email", enabled=True
        ).first()
        to_list = email_cfg.config.get("recipients", []) if email_cfg else []
        if not to_list:
            raise ValueError("未配置邮件收件人")

        status_flag = "failed"
        error_text = ""
        try:
            await NotificationService._send_email(
                to=to_list,
                subject=subject,
                body_html=body_html,
                attachments=[(filename, html_content, "text/html")]
            )
            status_flag = "success"
        except Exception as e:
            error_text = str(e)
            raise
        finally:
            await NotificationService._log(
                project_id=project_id,
                channel_type="email",
                notify_type="report",
                title=subject,
                content_summary={"task_name": record_data['task_name'], "status": record.status},
                recipients=to_list,
                status=status_flag,
                error_msg=error_text,
                related_id=plan_execution_id,
                related_type="ui_plan_execution"
            )

    @staticmethod
    async def send_perf_report(
        project_id: int,
        record_id: int,
        recipients: Optional[List[str]] = None,
    ):
        """发送性能测试报告邮件"""
        record = await PerfRecord.get_or_none(id=record_id)
        if not record:
            raise ValueError("执行记录不存在")
        if record.project_id != project_id:
            raise ValueError("记录与项目不匹配")

        scene = await record.scene
        scene_name = scene.name if scene else "未知场景"

        from app.routers.perf.records import _generate_perf_html_report

        html_content = _generate_perf_html_report(record, scene)
        filename = f"perf_report_{record_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        subject = f"[性能测试报告] {scene_name} - {record.status}"
        body_html = f"""
        <h3>性能测试执行报告</h3>
        <p><b>场景名称：</b>{scene_name}</p>
        <p><b>执行状态：</b>{record.status}</p>
        <p><b>QPS：</b>{round(record.qps or 0, 2)} &nbsp; <b>平均 RT：</b>{round(record.avg_response_time or 0, 2)} ms</p>
        <p><b>错误率：</b>{round(record.error_rate or 0, 2)}% &nbsp; <b>总请求：</b>{record.total_requests or 0}</p>
        <p><b>执行人：</b>{record.run_by or '-'} &nbsp; <b>时长：</b>{round(record.duration or 0, 2)}s</p>
        <p>详细报告请查看附件。</p>
        """

        to_list = recipients
        if not to_list:
            email_cfg = await NotificationConfig.filter(
                project_id=project_id, channel_type="email", enabled=True
            ).first()
            if email_cfg:
                to_list = email_cfg.config.get("recipients", [])

        if not to_list:
            raise ValueError("未配置邮件收件人")

        status_flag = "failed"
        error_text = ""
        try:
            await NotificationService._send_email(
                to=to_list,
                subject=subject,
                body_html=body_html,
                attachments=[(filename, html_content, "text/html")],
            )
            status_flag = "success"
        except Exception as e:
            error_text = str(e)
            raise
        finally:
            await NotificationService._log(
                project_id=project_id,
                channel_type="email",
                notify_type="report",
                title=subject,
                content_summary={"name": scene_name, "status": record.status, "qps": record.qps},
                recipients=to_list,
                status=status_flag,
                error_msg=error_text,
                related_id=record_id,
                related_type="perf_record",
            )

    @staticmethod
    async def maybe_auto_push_perf_report(record_id: int):
        """压测结束后按项目配置自动推送报告（成功/失败/停止均推送）"""
        record = await PerfRecord.get_or_none(id=record_id)
        if not record:
            return
        if record.status not in ("success", "failed", "stopped"):
            return

        email_cfg = await NotificationConfig.filter(
            project_id=record.project_id,
            channel_type="email",
            enabled=True,
            perf_auto_push_report=True,
        ).first()
        if not email_cfg:
            return

        try:
            await NotificationService.send_perf_report(
                project_id=record.project_id,
                record_id=record_id,
            )
        except Exception as e:
            print(f"[AutoReport] Perf report auto push failed: {e}")

    @staticmethod
    async def _send_email(to: List[str], subject: str, body_html: str, attachments: Optional[List[tuple]] = None):
        """底层邮件发送"""
        smtp = await SystemSmtpConfig.first()
        if not smtp:
            raise ValueError("未配置全局 SMTP")

        msg = MIMEMultipart()
        msg["From"] = f"{Header(smtp.sender, 'utf-8').encode()} <{smtp.username}>"
        msg["To"] = ", ".join(to)
        msg["Subject"] = Header(subject, "utf-8").encode()

        msg.attach(MIMEText(body_html, "html", "utf-8"))

        if attachments:
            for filename, content, mime_type in attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(content.encode("utf-8") if isinstance(content, str) else content)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)

        server = None
        try:
            if smtp.use_tls:
                server = smtplib.SMTP_SSL(smtp.host, smtp.port, timeout=10)
            else:
                server = smtplib.SMTP(smtp.host, smtp.port, timeout=10)
                server.starttls()

            server.login(smtp.username, smtp.password)
            # sendmail 的 from_addr 必须是纯邮箱地址（ASCII），不能包含中文显示名
            from_addr = smtp.username
            server.sendmail(from_addr, to, msg.as_string())
        finally:
            if server:
                server.quit()

    @staticmethod
    async def _send_email_alert(cfg: NotificationConfig, title: str, content: dict):
        """发送邮件告警"""
        recipients = cfg.config.get("recipients", [])
        if not recipients:
            return

        body = NotificationService._build_alert_body(content, is_html=True)
        await NotificationService._send_email(to=recipients, subject=title, body_html=body)

    @staticmethod
    async def _send_dingtalk_alert(cfg: NotificationConfig, title: str, content: dict):
        """发送钉钉告警"""
        config = cfg.config or {}
        webhook = config.get("webhook_url")
        if not webhook:
            return

        secret = config.get("secret", "")
        if secret:
            timestamp = str(int(datetime.now().timestamp() * 1000))
            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(
                secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256
            ).digest()
            sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
            webhook = f"{webhook}&timestamp={timestamp}&sign={sign}"

        text = NotificationService._build_alert_body(content, is_html=False)
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text
            }
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json=payload)
            resp.raise_for_status()
            result = resp.json()
            if result.get("errcode") != 0:
                raise RuntimeError(f"钉钉发送失败: {result}")

    @staticmethod
    async def _send_wechat_alert(cfg: NotificationConfig, title: str, content: dict):
        """发送企业微信告警"""
        config = cfg.config or {}
        webhook = config.get("webhook_url")
        if not webhook:
            return

        text = NotificationService._build_alert_body(content, is_html=False)
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": text
            }
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json=payload)
            resp.raise_for_status()
            result = resp.json()
            if result.get("errcode") != 0:
                raise RuntimeError(f"企微发送失败: {result}")

    @staticmethod
    def _build_alert_body(content: dict, is_html: bool = False) -> str:
        """组装告警内容"""
        t = content.get("execution_type", "")
        name = content.get("name", "")
        status = content.get("status", "")
        total = content.get("total", 0)
        success = content.get("success", 0)
        failed = content.get("failed", 0)
        pass_rate = content.get("pass_rate", 0)
        duration = content.get("duration", 0)
        run_by = content.get("run_by", "")
        link = content.get("link", "")
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if is_html:
            body = f"""
            <h3 style="color:#f56c6c">⚠️ 测试执行失败告警</h3>
            <p><b>执行类型：</b>{t}</p>
            <p><b>执行名称：</b>{name}</p>
            <p><b>执行状态：</b><span style="color:#f56c6c">{status}</span></p>
            <p><b>总用例数：</b>{total} &nbsp; <b>成功：</b>{success} &nbsp; <b>失败：</b>{failed}</p>
            <p><b>通过率：</b>{pass_rate}% &nbsp; <b>耗时：</b>{duration:.2f}s</p>
            <p><b>执行人：</b>{run_by} &nbsp; <b>时间：</b>{time_str}</p>
            """
            if link:
                body += f'<p><a href="{link}">查看详情</a></p>'
            return body
        else:
            md = f"""### ⚠️ 测试执行失败告警
**执行类型：** {t}
**执行名称：** {name}
**执行状态：** {status}
**总用例数：** {total}　**成功：** {success}　**失败：** {failed}
**通过率：** {pass_rate}%　**耗时：** {duration:.2f}s
**执行人：** {run_by}　**时间：** {time_str}
"""
            if link:
                md += f"\n[查看详情]({link})"
            return md
