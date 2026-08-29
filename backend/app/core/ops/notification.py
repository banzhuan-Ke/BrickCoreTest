"""
通知服务 - 统一封装邮件、钉钉、企微发送逻辑
"""
import asyncio
import html as html_module
import json
import hmac
import hashlib
import base64
import logging
import re
import urllib.parse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from datetime import datetime
from typing import Any, List, Optional

import httpx
import smtplib

from app.models.sys import NotificationConfig, SystemSmtpConfig, Project, NotificationLog
from app.models.http import ApiSuiteRunRecord, ApiRunRecord, ApiPlanRunRecord
from app.models.perf import PerfRecord
from app.models.ui import UiPlanExecution, UiSuiteExecution, UiCaseExecution
from app.modules.http.api_report_export import (
    generate_api_html_report,
    resolve_http_response_time,
    sum_http_response_time_ms,
    sum_plan_item_results_http_ms,
)
from app.core.shared.report_export import (
    build_email_html_report,
    email_report_attachment_note,
)

logger = logging.getLogger(__name__)


def _compose_relative_link(link_path: str, link_query: Optional[dict[str, Any]] = None) -> str:
    path = (link_path or "").strip() or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    qs = urllib.parse.urlencode({k: v for k, v in (link_query or {}).items() if v is not None})
    return f"{path}?{qs}" if qs else path


class NotificationService:
    """统一通知服务"""

    @staticmethod
    def _normalize_recipients(recipients: Optional[List[str]]) -> List[str]:
        seen = set()
        out: List[str] = []
        for raw in recipients or []:
            addr = str(raw).strip()
            if not addr or addr in seen:
                continue
            seen.add(addr)
            out.append(addr)
        return out

    @staticmethod
    def _validate_email_addresses(recipients: List[str]) -> List[str]:
        """过滤非法邮箱；全部非法时抛错。"""
        import re

        ok: List[str] = []
        bad: List[str] = []
        pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
        for addr in recipients:
            if pattern.match(addr):
                ok.append(addr)
            else:
                bad.append(addr)
        if bad and not ok:
            raise ValueError(f"邮件收件人无效：{', '.join(bad)}（需为完整邮箱，如 user@company.com）")
        if bad and ok:
            # 丢掉非法项，避免整封被 SMTP 拒收；调用方可从日志看到
            print(f"[NotificationService] 忽略无效收件人: {bad}")
        return ok

    @staticmethod
    async def _resolve_email_recipients(
        project_id: Optional[int],
        recipients: Optional[List[str]] = None,
        *,
        auto_push_field: Optional[str] = None,
    ) -> List[str]:
        """汇总邮件收件人。

        - 显式传入 recipients 时直接使用（去重）
        - 否则取项目下所有「启用」的邮件配置收件人并集
        - auto_push_field 指定时，仅汇总打开了对应自动推报告开关的邮件配置
        """
        if recipients:
            return NotificationService._normalize_recipients(recipients)
        if not project_id:
            return []
        filters = {"project_id": project_id, "channel_type": "email", "enabled": True}
        if auto_push_field:
            filters[auto_push_field] = True
        configs = await NotificationConfig.filter(**filters).all()
        collected: List[str] = []
        for cfg in configs:
            collected.extend((cfg.config or {}).get("recipients") or [])
        return NotificationService._normalize_recipients(collected)

    @staticmethod
    def _status_tone(status: str) -> tuple:
        s = (status or "").lower()
        if s in ("success", "passed", "pass", "执行完成", "ok"):
            return "#52c41a", "#f6ffed"
        if s in ("failed", "fail", "error", "失败", "错误", "stopped", "已停止"):
            return "#ff4d4f", "#fff2f0"
        if s in ("partial", "warning"):
            return "#faad14", "#fffbe6"
        return "#1890ff", "#e6f7ff"

    @staticmethod
    def _build_report_email_html(info: dict) -> str:
        """邮件正文：摘要卡片（完整详情在 HTML 附件）。"""
        esc = html_module.escape
        title = esc(str(info.get("title") or "测试执行报告"))
        name_label = esc(str(info.get("name_label") or "名称"))
        name = esc(str(info.get("name") or "-"))
        status = esc(str(info.get("status") or "-"))
        status_color, status_bg = NotificationService._status_tone(str(info.get("status") or "-"))
        total = info.get("total", 0) or 0
        success = info.get("success", 0) or 0
        failed = info.get("failed", 0) or 0
        skipped = info.get("skipped", 0) or 0
        error = info.get("error", 0) or 0
        pass_rate = info.get("pass_rate")
        if pass_rate is None and total:
            pass_rate = round(float(success) / float(total) * 100, 2)
        pass_rate = pass_rate if pass_rate is not None else 0
        duration = info.get("duration")
        duration_text = "-"
        if duration is not None:
            try:
                duration_text = f"{float(duration):.2f}s"
            except (TypeError, ValueError):
                duration_text = esc(str(duration))
        run_by = esc(str(info.get("run_by") or "-"))
        env_name = esc(str(info.get("env_name") or ""))
        extra_rows = info.get("extra_rows") or []
        note = esc(str(info.get("note") or "详细交互报告请查看附件 HTML（可在本地浏览器打开，支持按状态筛选）。"))
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        extra_html = "".join(
            f'<tr><td style="padding:8px 0;color:#8c8c8c;width:110px;">{esc(str(k))}</td>'
            f'<td style="padding:8px 0;color:#262626;font-weight:500;">{esc(str(v))}</td></tr>'
            for k, v in extra_rows
        )
        env_row = ""
        if env_name:
            env_row = (
                f'<tr><td style="padding:8px 0;color:#8c8c8c;">执行环境</td>'
                f'<td style="padding:8px 0;color:#262626;font-weight:500;">{env_name}</td></tr>'
            )

        return f"""
<div style="margin:0;padding:0;background:#f5f7fa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC','Microsoft YaHei',sans-serif;">
  <div style="max-width:640px;margin:0 auto;padding:24px 12px;">
    <div style="background:linear-gradient(135deg,#1d39c4 0%,#10239e 55%,#08979c 100%);border-radius:12px 12px 0 0;padding:22px 24px;color:#fff;">
      <div style="font-size:13px;opacity:.85;margin-bottom:6px;">BrickCore 测试报告</div>
      <div style="font-size:22px;font-weight:700;line-height:1.3;">{title}</div>
      <div style="margin-top:12px;">
        <span style="display:inline-block;padding:4px 12px;border-radius:999px;background:{status_bg};color:{status_color};font-size:12px;font-weight:700;">{status}</span>
      </div>
    </div>
    <div style="background:#fff;border-radius:0 0 12px 12px;padding:20px 24px 24px;box-shadow:0 2px 8px rgba(0,0,0,.06);">
      <table style="width:100%;border-collapse:collapse;margin-bottom:16px;font-size:14px;">
        <tr><td style="padding:8px 0;color:#8c8c8c;width:110px;">{name_label}</td><td style="padding:8px 0;color:#262626;font-weight:600;">{name}</td></tr>
        <tr><td style="padding:8px 0;color:#8c8c8c;">执行人</td><td style="padding:8px 0;color:#262626;font-weight:500;">{run_by}</td></tr>
        <tr><td style="padding:8px 0;color:#8c8c8c;">耗时</td><td style="padding:8px 0;color:#262626;font-weight:500;">{duration_text}</td></tr>
        <tr><td style="padding:8px 0;color:#8c8c8c;">通过率</td><td style="padding:8px 0;color:{status_color};font-weight:700;">{pass_rate}%</td></tr>
        {env_row}
        {extra_html}
      </table>
      <table style="width:100%;border-collapse:separate;border-spacing:8px 0;margin:8px -8px 16px;">
        <tr>
          <td style="background:#fafafa;border-radius:8px;padding:14px 8px;text-align:center;width:20%;">
            <div style="font-size:22px;font-weight:700;color:#595959;">{total}</div>
            <div style="font-size:12px;color:#8c8c8c;margin-top:4px;">总数</div>
          </td>
          <td style="background:#f6ffed;border-radius:8px;padding:14px 8px;text-align:center;width:20%;">
            <div style="font-size:22px;font-weight:700;color:#52c41a;">{success}</div>
            <div style="font-size:12px;color:#8c8c8c;margin-top:4px;">成功</div>
          </td>
          <td style="background:#fff2f0;border-radius:8px;padding:14px 8px;text-align:center;width:20%;">
            <div style="font-size:22px;font-weight:700;color:#ff4d4f;">{failed}</div>
            <div style="font-size:12px;color:#8c8c8c;margin-top:4px;">失败</div>
          </td>
          <td style="background:#fffbe6;border-radius:8px;padding:14px 8px;text-align:center;width:20%;">
            <div style="font-size:22px;font-weight:700;color:#faad14;">{error}</div>
            <div style="font-size:12px;color:#8c8c8c;margin-top:4px;">错误</div>
          </td>
          <td style="background:#f5f5f5;border-radius:8px;padding:14px 8px;text-align:center;width:20%;">
            <div style="font-size:22px;font-weight:700;color:#8c8c8c;">{skipped}</div>
            <div style="font-size:12px;color:#8c8c8c;margin-top:4px;">跳过</div>
          </td>
        </tr>
      </table>
      <div style="background:#e6f4ff;border:1px solid #91caff;border-radius:8px;padding:12px 14px;color:#0958d9;font-size:13px;line-height:1.6;">
        {note}
      </div>
      <div style="margin-top:16px;color:#bfbfbf;font-size:12px;">发送时间：{time_str}</div>
    </div>
  </div>
</div>
""".strip()

    @staticmethod
    def _build_report_im_markdown(info: dict) -> str:
        """钉钉/企微 Markdown 摘要（无法附带 HTML 文件）。"""
        title = info.get("title") or "测试执行报告"
        name_label = info.get("name_label") or "名称"
        name = info.get("name") or "-"
        status = info.get("status") or "-"
        total = info.get("total", 0) or 0
        success = info.get("success", 0) or 0
        failed = info.get("failed", 0) or 0
        error = info.get("error", 0) or 0
        skipped = info.get("skipped", 0) or 0
        pass_rate = info.get("pass_rate")
        if pass_rate is None and total:
            pass_rate = round(float(success) / float(total) * 100, 2)
        pass_rate = pass_rate if pass_rate is not None else 0
        duration = info.get("duration")
        try:
            duration_text = f"{float(duration):.2f}s" if duration is not None else "-"
        except (TypeError, ValueError):
            duration_text = str(duration)
        run_by = info.get("run_by") or "-"
        env_name = info.get("env_name") or ""
        extra_lines = ""
        for k, v in (info.get("extra_rows") or []):
            extra_lines += f"\n**{k}：** {v}"
        env_line = f"\n**执行环境：** {env_name}" if env_name else ""
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""### 📋 {title}
**{name_label}：** {name}
**执行状态：** {status}
**用例：** 共 {total}　成功 {success}　失败 {failed}　错误 {error}　跳过 {skipped}
**通过率：** {pass_rate}%　**耗时：** {duration_text}
**执行人：** {run_by}{env_line}{extra_lines}
**时间：** {time_str}

> IM 渠道仅推送摘要；完整 HTML 报告请勾选邮件渠道发送。
""".strip()

    @staticmethod
    async def _load_report_configs(
        project_id: Optional[int],
        *,
        config_ids: Optional[List[int]] = None,
        auto_push_field: Optional[str] = None,
    ) -> List[NotificationConfig]:
        if not project_id:
            return []
        if config_ids is not None:
            if not config_ids:
                return []
            configs = await NotificationConfig.filter(
                project_id=project_id, id__in=config_ids, enabled=True
            ).all()
            by_id = {c.id: c for c in configs}
            # 保持调用方勾选顺序
            return [by_id[i] for i in config_ids if i in by_id]
        filters = {"project_id": project_id, "channel_type": "email", "enabled": True}
        if auto_push_field:
            filters[auto_push_field] = True
        return await NotificationConfig.filter(**filters).all()

    @staticmethod
    async def _send_im_markdown(cfg: NotificationConfig, title: str, markdown_text: str):
        """向钉钉/企微/飞书推送报告摘要。"""
        if cfg.channel_type == "dingtalk":
            config = cfg.config or {}
            webhook = config.get("webhook_url")
            if not webhook:
                raise ValueError("未配置钉钉 Webhook")
            secret = config.get("secret", "")
            if secret:
                timestamp = str(int(datetime.now().timestamp() * 1000))
                string_to_sign = f"{timestamp}\n{secret}"
                hmac_code = hmac.new(
                    secret.encode("utf-8"),
                    string_to_sign.encode("utf-8"),
                    digestmod=hashlib.sha256,
                ).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
                webhook = f"{webhook}&timestamp={timestamp}&sign={sign}"
            payload = {"msgtype": "markdown", "markdown": {"title": title, "text": markdown_text}}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook, json=payload)
                resp.raise_for_status()
                result = resp.json()
                if result.get("errcode") != 0:
                    raise RuntimeError(f"钉钉发送失败: {result}")
            return

        if cfg.channel_type == "wechat":
            webhook = (cfg.config or {}).get("webhook_url")
            if not webhook:
                raise ValueError("未配置企微 Webhook")
            payload = {"msgtype": "markdown", "markdown": {"content": markdown_text}}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook, json=payload)
                resp.raise_for_status()
                result = resp.json()
                if result.get("errcode") != 0:
                    raise RuntimeError(f"企微发送失败: {result}")
            return

        if cfg.channel_type == "feishu":
            webhook = (cfg.config or {}).get("webhook_url")
            if not webhook:
                raise ValueError("未配置飞书 Webhook")
            # 飞书自定义机器人常用 text；去掉 markdown 符号以免显得更乱
            plain = (
                markdown_text.replace("### ", "")
                .replace("**", "")
                .replace("> ", "")
            )
            payload = {"msg_type": "text", "content": {"text": plain}}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook, json=payload)
                resp.raise_for_status()
                result = resp.json()
                code = result.get("code", result.get("StatusCode", -1))
                if code not in (0, "0"):
                    raise RuntimeError(f"飞书发送失败: {result}")
            return

        raise ValueError(f"不支持的通知渠道: {cfg.channel_type}")

    @staticmethod
    async def _dispatch_report(
        project_id: Optional[int],
        *,
        subject: str,
        report_info: dict,
        attachment: Optional[tuple] = None,
        recipients: Optional[List[str]] = None,
        config_ids: Optional[List[int]] = None,
        auto_push_field: Optional[str] = None,
        related_id: Optional[int] = None,
        related_type: str = "",
    ) -> dict:
        """按配置分发报告：邮件带 HTML 附件，IM 仅摘要。"""
        configs = await NotificationService._load_report_configs(
            project_id, config_ids=config_ids, auto_push_field=auto_push_field
        )
        # 兼容：未勾选配置且未开自动推时，仍按「全部启用邮件」发（旧行为）
        if not configs and config_ids is None and not auto_push_field:
            configs = await NotificationService._load_report_configs(project_id)

        if not configs and not recipients:
            raise ValueError("未选择通知渠道，或项目下没有启用的通知配置")

        body_html = NotificationService._build_report_email_html(report_info)
        im_md = NotificationService._build_report_im_markdown(report_info)
        channel_counts: dict = {}
        errors: List[str] = []
        email_recipients: List[str] = []
        email_requested = False

        # 显式 recipients：只走邮件
        if recipients:
            email_requested = True
            to_list = NotificationService._validate_email_addresses(
                NotificationService._normalize_recipients(recipients)
            )
            if not to_list:
                raise ValueError("未配置邮件收件人")
            status_flag = "failed"
            error_text = ""
            try:
                await NotificationService._send_email(
                    to=to_list,
                    subject=subject,
                    body_html=body_html,
                    attachments=[attachment] if attachment else None,
                )
                status_flag = "success"
                channel_counts["email"] = channel_counts.get("email", 0) + 1
                email_recipients = to_list
            except Exception as e:
                error_text = str(e)
                errors.append(f"email: {e}")
                raise
            finally:
                await NotificationService._log(
                    project_id=project_id,
                    channel_type="email",
                    notify_type="report",
                    title=subject,
                    content_summary={
                        "name": report_info.get("name"),
                        "status": report_info.get("status"),
                    },
                    recipients=to_list,
                    status=status_flag,
                    error_msg=error_text,
                    related_id=related_id,
                    related_type=related_type,
                )
            return {
                "channels": channel_counts,
                "errors": errors,
                "email_recipients": email_recipients,
                "email_ok": True,
            }

        email_cfgs = [c for c in configs if c.channel_type == "email"]
        im_cfgs = [c for c in configs if c.channel_type in ("dingtalk", "wechat", "feishu")]
        email_requested = bool(email_cfgs)
        email_ok = False

        if email_cfgs:
            to_list: List[str] = []
            for cfg in email_cfgs:
                to_list.extend((cfg.config or {}).get("recipients") or [])
            try:
                to_list = NotificationService._validate_email_addresses(
                    NotificationService._normalize_recipients(to_list)
                )
            except ValueError as e:
                errors.append(f"email: {e}")
                to_list = []
            if not to_list:
                if not any(x.startswith("email:") for x in errors):
                    errors.append("email: 已选邮件渠道但未配置有效收件人")
            else:
                status_flag = "failed"
                error_text = ""
                try:
                    await NotificationService._send_email(
                        to=to_list,
                        subject=subject,
                        body_html=body_html,
                        attachments=[attachment] if attachment else None,
                    )
                    status_flag = "success"
                    channel_counts["email"] = 1
                    email_recipients = to_list
                    email_ok = True
                except Exception as e:
                    error_text = str(e)
                    errors.append(f"email: {e}")
                finally:
                    await NotificationService._log(
                        project_id=project_id,
                        channel_type="email",
                        notify_type="report",
                        title=subject,
                        content_summary={
                            "name": report_info.get("name"),
                            "status": report_info.get("status"),
                            "recipients": to_list,
                        },
                        recipients=to_list,
                        status=status_flag,
                        error_msg=error_text,
                        related_id=related_id,
                        related_type=related_type,
                    )

        for cfg in im_cfgs:
            status_flag = "failed"
            error_text = ""
            try:
                await NotificationService._send_im_markdown(cfg, subject, im_md)
                status_flag = "success"
                channel_counts[cfg.channel_type] = channel_counts.get(cfg.channel_type, 0) + 1
            except Exception as e:
                error_text = str(e)
                errors.append(f"{cfg.channel_type}: {e}")
            finally:
                await NotificationService._log(
                    project_id=project_id,
                    channel_type=cfg.channel_type,
                    notify_type="report",
                    title=subject,
                    content_summary={
                        "name": report_info.get("name"),
                        "status": report_info.get("status"),
                    },
                    recipients=NotificationService._log_recipients_for_channel(
                        cfg.channel_type, recipients, cfg
                    ),
                    status=status_flag,
                    error_msg=error_text,
                    related_id=related_id,
                    related_type=related_type,
                )

        # 勾了邮件却没发出去：直接失败，避免「钉钉成功 → 前端仍提示成功」造成误判
        if email_requested and not email_ok:
            raise ValueError(
                "邮件未发送成功："
                + ("；".join([e for e in errors if e.startswith("email:")]) or "未知原因")
                + "。请检查：系统 SMTP、通知配置里的收件人是否为完整邮箱、垃圾箱。"
            )

        if not channel_counts:
            raise ValueError("报告发送失败：" + ("；".join(errors) if errors else "无可用渠道"))

        return {
            "channels": channel_counts,
            "errors": errors,
            "email_recipients": email_recipients,
            "email_ok": email_ok,
        }

    @staticmethod
    def format_dispatch_detail(result: dict) -> str:
        labels = {"email": "邮件", "dingtalk": "钉钉", "wechat": "企微", "feishu": "飞书"}
        parts = []
        for k, n in (result.get("channels") or {}).items():
            parts.append(f"{labels.get(k, k)}×{n}" if n > 1 else labels.get(k, k))
        text = "报告已发送：" + ("、".join(parts) if parts else "完成")
        recipients = result.get("email_recipients") or []
        if recipients:
            shown = ", ".join(recipients[:5])
            if len(recipients) > 5:
                shown += f" 等{len(recipients)}人"
            text += f"；邮件收件人：{shown}"
        errs = [e for e in (result.get("errors") or []) if not str(e).startswith("email:")]
        if errs:
            text += f"（其它渠道部分失败：{'；'.join(errs)}）"
        return text

    @staticmethod
    def _sanitize_log_content(payload: dict) -> dict:
        safe = dict(payload or {})
        if safe.get("assignee_mobile"):
            safe["assignee_mobile"] = "***"
        return safe

    @staticmethod
    async def _platform_public_base() -> str:
        from app.core.platform import config as platform_config

        base = (platform_config.BASE_URL or "").strip().rstrip("/")
        if base:
            return base
        try:
            from app.models.sys import SystemMcpConfig

            row = await SystemMcpConfig.first()
            if row and (row.base_url or "").strip():
                return row.base_url.strip().rstrip("/")
        except Exception:
            pass
        return ""

    @staticmethod
    def _ensure_absolute_link(link: str, *, base: str = "") -> str:
        s = (link or "").strip()
        if not s or s.startswith(("http://", "https://")):
            return s
        root = (base or "").strip().rstrip("/")
        if not root:
            from app.core.platform import config as platform_config

            root = (platform_config.BASE_URL or "").strip().rstrip("/")
        if not root:
            return s if s.startswith("/") else f"/{s}"
        path = s if s.startswith("/") else f"/{s}"
        return f"{root}{path}"

    @staticmethod
    async def resolve_public_link(
        link_path: str,
        link_query: Optional[dict[str, Any]] = None,
    ) -> str:
        rel = _compose_relative_link(link_path, link_query)
        if rel.startswith(("http://", "https://")):
            return rel
        base = await NotificationService._platform_public_base()
        if not base:
            logger.warning("未配置 BASE_URL，外发通知链接将为相对路径")
        return NotificationService._ensure_absolute_link(rel, base=base)

    @staticmethod
    def _mask_webhook_url(url: str) -> str:
        s = str(url or "")
        return (s[:48] + "…") if len(s) > 48 else s

    @staticmethod
    def _log_recipients_for_channel(channel_type: str, recipients: List[str], cfg: Any = None) -> List[str]:
        if channel_type == "email":
            return recipients
        if recipients:
            return [NotificationService._mask_webhook_url(r) for r in recipients]
        if cfg is not None:
            return [NotificationService._mask_webhook_url((cfg.config or {}).get("webhook_url", ""))]
        return recipients

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
    def _alert_field_for_scope(alert_scope: str) -> str:
        """alert_scope: api | ui | perf | app"""
        mapping = {
            "api": "api_alert_on_failure",
            "ui": "ui_alert_on_failure",
            "perf": "perf_alert_on_failure",
            "app": "app_alert_on_failure",
        }
        return mapping.get((alert_scope or "").strip().lower(), "ui_alert_on_failure")

    @staticmethod
    async def send_project_notice(
        project_id: int,
        title: str,
        content: dict,
        related_id: Optional[int] = None,
        related_type: str = "",
    ):
        """项目级通用通知：推送到所有已启用渠道，不依赖各模块「失败告警」开关。

        用于质量门禁快照/豁免等与执行失败无关的事件。
        """
        configs = await NotificationConfig.filter(project_id=project_id, enabled=True).all()
        if not configs:
            return
        for cfg in configs:
            status_flag = "failed"
            error_text = ""
            recipients: List[str] = []
            if cfg.channel_type == "email":
                recipients = cfg.config.get("recipients", []) or []
                if not recipients:
                    continue
            try:
                if cfg.channel_type == "email":
                    await NotificationService._send_email_alert(cfg, title, content)
                elif cfg.channel_type == "dingtalk":
                    await NotificationService._send_dingtalk_alert(cfg, title, content)
                elif cfg.channel_type == "wechat":
                    await NotificationService._send_wechat_alert(cfg, title, content)
                elif cfg.channel_type == "feishu":
                    await NotificationService._send_feishu_alert(cfg, title, content)
                else:
                    continue
                status_flag = "success"
            except Exception as e:
                error_text = str(e)
                print(f"[NotificationService] 发送项目通知失败 ({cfg.channel_type}): {e}")
            finally:
                await NotificationService._log(
                    project_id=project_id,
                    channel_type=cfg.channel_type,
                    notify_type="notice",
                    title=title,
                    content_summary=content,
                    recipients=NotificationService._log_recipients_for_channel(
                        cfg.channel_type, recipients, cfg
                    ),
                    status=status_flag,
                    error_msg=error_text,
                    related_id=related_id,
                    related_type=related_type,
                )

    @staticmethod
    async def send_assignment_message(
        project_id: int,
        title: str,
        content: dict,
        *,
        assignee_email: Optional[str] = None,
        assignee_mobile: Optional[str] = None,
        channel_types: Optional[List[str]] = None,
        email_allowed: bool = True,
        related_id: Optional[int] = None,
        related_type: str = "assignment",
    ) -> List[dict]:
        """测试管理指派外发：邮件仅发给被指派人；IM 走项目 Webhook，可按手机号 @。

        channel_types=None 不限渠道；[] 表示不推送任何渠道。
        email_allowed=False 时跳过邮件（个人偏好/DND），IM 群广播不受影响。
        返回各渠道推送结果 [{channel, status, error?}, ...]。
        """
        payload = dict(content or {})
        payload["notice_kind"] = "assignment"
        mobile = (assignee_mobile or payload.get("assignee_mobile") or "").strip()
        at_mobiles = [mobile] if re.fullmatch(r"1[3-9]\d{9}", mobile) else []
        results: List[dict] = []
        if channel_types is not None and len(channel_types) == 0:
            return results
        configs = await NotificationConfig.filter(project_id=project_id, enabled=True).all()
        allowed = set(channel_types) if channel_types is not None else None

        async def _finish_channel(
            *,
            channel_type: str,
            status_flag: str,
            error_text: str = "",
            recipients: Optional[List[str]] = None,
            cfg_obj: Any = None,
        ) -> None:
            rec = recipients or []
            results.append(
                {
                    "channel": channel_type,
                    "status": status_flag,
                    "error": error_text or None,
                }
            )
            log_status = (
                "success"
                if status_flag == "success"
                else "skipped"
                if status_flag == "skipped"
                else "failed"
            )
            await NotificationService._log(
                project_id=project_id,
                channel_type=channel_type,
                notify_type="assignment",
                title=title,
                content_summary=NotificationService._sanitize_log_content(payload),
                recipients=NotificationService._log_recipients_for_channel(
                    channel_type, rec, cfg_obj
                ),
                status=log_status,
                error_msg=error_text or ("" if status_flag != "skipped" else "已跳过"),
                related_id=related_id,
                related_type=related_type,
            )

        for cfg in configs:
            if getattr(cfg, "tm_assignment_notify", True) is False:
                continue
            if allowed is not None and cfg.channel_type not in allowed:
                continue
            # 指派邮件统一走全局 SMTP；项目邮件渠道仅用于执行告警/自动推报告
            if cfg.channel_type == "email":
                continue
            status_flag = "failed"
            error_text = ""
            recipients: List[str] = []
            try:
                if cfg.channel_type == "dingtalk":
                    await NotificationService._send_dingtalk_alert(
                        cfg, title, payload, at_mobiles=at_mobiles
                    )
                elif cfg.channel_type == "wechat":
                    await NotificationService._send_wechat_alert(
                        cfg, title, payload, at_mobiles=at_mobiles
                    )
                elif cfg.channel_type == "feishu":
                    await NotificationService._send_feishu_alert(
                        cfg, title, payload, at_mobiles=at_mobiles
                    )
                else:
                    continue
                status_flag = "success"
            except Exception as e:
                error_text = str(e)
                logger.error(
                    "[NotificationService] 指派通知失败 (%s): %s",
                    cfg.channel_type,
                    e,
                )
            await _finish_channel(
                channel_type=cfg.channel_type,
                status_flag=status_flag,
                error_text=error_text,
                recipients=recipients,
                cfg_obj=cfg,
            )

        email_wanted = allowed is None or "email" in allowed

        async def _send_assignment_email_via_global_smtp() -> None:
            if not email_allowed:
                await _finish_channel(
                    channel_type="email",
                    status_flag="skipped",
                    error_text="个人偏好或免打扰已关闭邮件外发",
                )
                return
            email = (assignee_email or "").strip()
            if not email:
                await _finish_channel(
                    channel_type="email",
                    status_flag="skipped",
                    error_text="被指派人未配置邮箱",
                )
                return
            if not await SystemSmtpConfig.first():
                await _finish_channel(
                    channel_type="email",
                    status_flag="failed",
                    error_text="未配置全局 SMTP",
                )
                return
            status_flag = "failed"
            error_text = ""
            try:
                body = NotificationService._build_alert_body(payload, is_html=True)
                await NotificationService._send_email(to=[email], subject=title, body_html=body)
                status_flag = "success"
            except Exception as e:
                error_text = str(e)
                logger.error("[NotificationService] 指派邮件失败: %s", e)
            await _finish_channel(
                channel_type="email",
                status_flag=status_flag,
                error_text=error_text,
                recipients=[email],
            )

        if email_wanted:
            await _send_assignment_email_via_global_smtp()
        return results

    @staticmethod
    async def send_alert(
        project_id: int,
        title: str,
        content: dict,
        related_id: Optional[int] = None,
        related_type: str = "",
        alert_scope: str = "ui",
    ):
        """
        执行失败告警入口（按渠道配置的分项开关过滤）。
        alert_scope: api | ui | perf | app
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

        alert_field = NotificationService._alert_field_for_scope(alert_scope)
        for cfg in configs:
            # 与「自动推报告」分离：未开对应类型的失败告警则跳过
            if not getattr(cfg, alert_field, True):
                continue
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
                elif cfg.channel_type == "feishu":
                    await NotificationService._send_feishu_alert(cfg, title, content)
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
                    recipients=NotificationService._log_recipients_for_channel(
                        cfg.channel_type, recipients, cfg
                    ),
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
        *,
        auto_push_only: bool = False,
        config_ids: Optional[List[int]] = None,
    ):
        """发送 API 测试报告（邮件 HTML 附件 + 可选 IM 摘要）"""
        if record_type == "plan":
            record = await ApiPlanRunRecord.get_or_none(id=record_id)
            if not record:
                raise ValueError("执行记录不存在")
            plan = await record.plan
            from app.routers.http.utils import api_run_result_to_case_display

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
        total = record.total_cases or 0
        success = record.success_cases or 0
        failed = record.failed_cases or 0
        skipped = getattr(record, "skipped_cases", 0) or 0
        pass_rate = round(success / total * 100, 2) if total else 0
        duration_sec = record.duration
        try:
            # API duration 多为毫秒
            if duration_sec is not None and float(duration_sec) > 1000:
                duration_sec = float(duration_sec) / 1000.0
        except (TypeError, ValueError):
            pass
        report_info = {
            "title": "API 测试执行报告",
            "name_label": body_label,
            "name": report_name,
            "status": record.status,
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "error": 0,
            "pass_rate": pass_rate,
            "duration": duration_sec,
            "run_by": record.run_by,
            "env_name": getattr(record, "env_name", None) or report_record.get("env_name"),
            "note": "详细交互报告请查看附件 HTML（本地打开后可展开用例、查看断言与响应）。",
        }
        return await NotificationService._dispatch_report(
            project_id,
            subject=subject,
            report_info=report_info,
            attachment=(filename, html_content, "text/html"),
            recipients=recipients,
            config_ids=config_ids,
            auto_push_field="api_auto_push_report" if auto_push_only else None,
            related_id=record_id,
            related_type=related_type,
        )

    @staticmethod
    async def send_ui_report(
        plan_execution_id: int,
        recipients: Optional[List[str]] = None,
        *,
        auto_push_only: bool = False,
        config_ids: Optional[List[int]] = None,
    ):
        """发送 UI 测试报告（邮件 HTML 附件 + 可选 IM 摘要）"""
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

        # 邮件附件：内嵌失败步骤截图（避免 MinIO 内网裂图）；超体积自动降级无图；不用 all
        html_content, image_mode_used = build_email_html_report(
            record_data, "task", suite_records, case_records
        )
        filename = f"ui_report_{plan_execution_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        subject = f"[UI测试报告] {record_data['task_name']} - {record.status}"
        env_name = ""
        env = record_data.get("env") or {}
        if isinstance(env, str):
            try:
                env = json.loads(env)
            except Exception:
                env = {}
        if isinstance(env, dict):
            env_name = env.get("env_name") or env.get("name") or ""
        fail_n = int(record.fail or 0)
        error_n = int(record.error or 0)
        report_info = {
            "title": "Web UI 测试执行报告",
            "name_label": "计划名称",
            "name": record_data["task_name"],
            "status": record.status,
            "total": record.case_count or 0,
            "success": record.success or 0,
            "failed": fail_n,
            "error": error_n,
            "skipped": record.skip or 0,
            "pass_rate": record.pass_rate,
            "duration": record.duration,
            "run_by": record.username,
            "env_name": env_name,
            "note": email_report_attachment_note(image_mode_used),
        }
        return await NotificationService._dispatch_report(
            project_id,
            subject=subject,
            report_info=report_info,
            attachment=(filename, html_content, "text/html"),
            recipients=recipients,
            config_ids=config_ids,
            auto_push_field="ui_auto_push_report" if auto_push_only else None,
            related_id=plan_execution_id,
            related_type="ui_plan_execution",
        )

    @staticmethod
    async def send_perf_report(
        project_id: int,
        record_id: int,
        recipients: Optional[List[str]] = None,
        *,
        auto_push_only: bool = False,
        config_ids: Optional[List[int]] = None,
    ):
        """发送性能测试报告（邮件 HTML 附件 + 可选 IM 摘要）"""
        record = await PerfRecord.get_or_none(id=record_id)
        if not record:
            raise ValueError("执行记录不存在")
        if record.project_id != project_id:
            raise ValueError("记录与项目不匹配")

        scene = await record.scene
        scene_name = scene.name if scene else "未知场景"

        from app.routers.perf.records import _generate_perf_html_report

        html_content = _generate_perf_html_report(record, scene, editable=False)
        filename = f"perf_report_{record_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        subject = f"[性能测试报告] {scene_name} - {record.status}"
        report_info = {
            "title": "性能测试执行报告",
            "name_label": "场景名称",
            "name": scene_name,
            "status": record.status,
            "total": record.total_requests or 0,
            "success": max((record.total_requests or 0) - int((record.error_rate or 0) / 100 * (record.total_requests or 0)), 0),
            "failed": 0,
            "error": 0,
            "skipped": 0,
            "pass_rate": round(100 - float(record.error_rate or 0), 2),
            "duration": record.duration,
            "run_by": record.run_by or "-",
            "extra_rows": [
                ("QPS", round(record.qps or 0, 2)),
                ("平均 RT", f"{round(record.avg_response_time or 0, 2)} ms"),
                ("错误率", f"{round(record.error_rate or 0, 2)}%"),
                ("总请求", record.total_requests or 0),
            ],
            "note": "详细压测报告请查看附件 HTML（与平台导出内容一致，可离线打开）。",
        }
        return await NotificationService._dispatch_report(
            project_id,
            subject=subject,
            report_info=report_info,
            attachment=(filename, html_content, "text/html"),
            recipients=recipients,
            config_ids=config_ids,
            auto_push_field="perf_auto_push_report" if auto_push_only else None,
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
                auto_push_only=True,
            )
        except Exception as e:
            print(f"[AutoReport] Perf report auto push failed: {e}")

    @staticmethod
    async def send_app_plan_report(
        plan_execution_id: int,
        recipients: Optional[List[str]] = None,
        *,
        auto_push_only: bool = False,
        config_ids: Optional[List[int]] = None,
    ):
        """发送 App 计划执行报告（邮件 HTML 附件 + 可选 IM 摘要）"""
        from app.models.app import AppPlanExecution
        from app.routers.app.records import _build_report_context

        record_data, suite_records, case_records, filename, _img_options = await _build_report_context(
            plan_execution_id, "task", False, "none", False, None
        )
        project_id = None
        record = await AppPlanExecution.get_or_none(id=plan_execution_id, is_del=False).prefetch_related("project")
        if record:
            project = await record.project
            project_id = project.id if project else record.project_id

        html_content, image_mode_used = build_email_html_report(
            record_data, "task", suite_records, case_records
        )
        subject = f"[App测试报告] {record_data.get('task_name', '计划')} - {record_data.get('status', '')}"
        fail_n = int(record_data.get("fail", 0) or 0)
        error_n = int(record_data.get("error", 0) or 0)
        report_info = {
            "title": "App 测试执行报告",
            "name_label": "计划名称",
            "name": record_data.get("task_name", "计划"),
            "status": record_data.get("status", ""),
            "total": record_data.get("case_count", 0) or 0,
            "success": record_data.get("success", 0) or 0,
            "failed": fail_n,
            "error": error_n,
            "skipped": record_data.get("skip", 0) or 0,
            "pass_rate": record_data.get("pass_rate"),
            "duration": record_data.get("duration"),
            "run_by": record_data.get("username", ""),
            "note": email_report_attachment_note(image_mode_used),
        }
        return await NotificationService._dispatch_report(
            project_id,
            subject=subject,
            report_info=report_info,
            attachment=(filename, html_content, "text/html"),
            recipients=recipients,
            config_ids=config_ids,
            auto_push_field="app_auto_push_report" if auto_push_only else None,
            related_id=plan_execution_id,
            related_type="app_plan_execution",
        )

    @staticmethod
    async def send_app_suite_report(
        suite_execution_id: int,
        recipients: Optional[List[str]] = None,
        *,
        auto_push_only: bool = False,
        config_ids: Optional[List[int]] = None,
    ):
        """发送 App 套件执行报告（邮件 HTML 附件 + 可选 IM 摘要）"""
        from app.routers.app.records import _build_report_context
        from app.models.app import AppSuiteExecution

        record_data, suite_records, case_records, filename, _img_options = await _build_report_context(
            suite_execution_id, "suite", False, "none", False, None
        )
        suite_record = await AppSuiteExecution.get_or_none(id=suite_execution_id, is_del=False).prefetch_related("suite")
        project_id = None
        if suite_record:
            suite = await suite_record.suite
            project_id = suite.project_id if suite else None

        html_content, image_mode_used = build_email_html_report(
            record_data, "suite", suite_records, case_records
        )
        subject = f"[App测试报告] {record_data.get('suite_name', '套件')} - {record_data.get('status', '')}"
        fail_n = int(record_data.get("fail", 0) or 0)
        error_n = int(record_data.get("error", 0) or 0)
        report_info = {
            "title": "App 套件执行报告",
            "name_label": "套件名称",
            "name": record_data.get("suite_name", "套件"),
            "status": record_data.get("status", ""),
            "total": record_data.get("case_count", 0) or 0,
            "success": record_data.get("success", 0) or 0,
            "failed": fail_n,
            "error": error_n,
            "skipped": record_data.get("skip", 0) or 0,
            "pass_rate": record_data.get("pass_rate"),
            "duration": record_data.get("duration"),
            "run_by": record_data.get("username", ""),
            "note": email_report_attachment_note(image_mode_used),
        }
        return await NotificationService._dispatch_report(
            project_id,
            subject=subject,
            report_info=report_info,
            attachment=(filename, html_content, "text/html"),
            recipients=recipients,
            config_ids=config_ids,
            auto_push_field="app_auto_push_report" if auto_push_only else None,
            related_id=suite_execution_id,
            related_type="app_suite_execution",
        )

    @staticmethod
    def test_smtp_connection(
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool = True,
        sender: str = "",
        to: Optional[str] = None,
        timeout: int = 15,
    ) -> dict:
        """用表单中的 SMTP 参数探测连通性，并发送一封短测试邮件。

        不读写数据库，便于保存前验证。
        """
        host = (host or "").strip()
        username = (username or "").strip()
        password = password or ""
        to_addr = (to or "").strip() or username
        sender_name = (sender or "").strip() or "BrickCore"

        if not host:
            raise ValueError("请填写 SMTP 服务器")
        if not port:
            raise ValueError("请填写端口")
        if not username:
            raise ValueError("请填写发件账号")
        if not password:
            raise ValueError("请填写密码/授权码")
        if "@" not in to_addr:
            raise ValueError("测试收件人不是有效邮箱")

        msg = MIMEMultipart()
        msg["From"] = f"{Header(sender_name, 'utf-8').encode()} <{username}>"
        msg["To"] = to_addr
        msg["Subject"] = Header("BrickCore SMTP 连通性测试", "utf-8").encode()
        msg.attach(
            MIMEText(
                "<p>这是一封 SMTP 测试邮件。</p><p>若能收到，说明当前配置可以正常发信。</p>",
                "html",
                "utf-8",
            )
        )

        server = None
        try:
            if use_tls:
                server = smtplib.SMTP_SSL(host, int(port), timeout=timeout)
            else:
                server = smtplib.SMTP(host, int(port), timeout=timeout)
                server.starttls()
            server.login(username, password)
            server.sendmail(username, [to_addr], msg.as_string())
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass

        return {"ok": True, "to": to_addr, "host": host, "port": int(port)}

    @staticmethod
    def _send_email_sync(
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        sender: str,
        to: List[str],
        subject: str,
        body_html: str,
        attachments: Optional[List[tuple]] = None,
    ):
        """同步 SMTP 发送（供线程池调用，避免阻塞事件循环）。"""
        msg = MIMEMultipart()
        msg["From"] = f"{Header(sender, 'utf-8').encode()} <{username}>"
        msg["To"] = ", ".join(to)
        msg["Subject"] = Header(subject, "utf-8").encode()
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        if attachments:
            for filename, content, mime_type in attachments:
                raw = content.encode("utf-8") if isinstance(content, str) else content
                if mime_type == "text/html":
                    part = MIMEText(
                        content if isinstance(content, str) else content.decode("utf-8", errors="replace"),
                        "html",
                        "utf-8",
                    )
                    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                else:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(raw)
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                msg.attach(part)

        server = None
        try:
            timeout = 60 if attachments else 15
            if use_tls:
                server = smtplib.SMTP_SSL(host, port, timeout=timeout)
            else:
                server = smtplib.SMTP(host, port, timeout=timeout)
                server.starttls()
            server.login(username, password)
            refused = server.sendmail(username, to, msg.as_string())
            if refused:
                detail = "; ".join(f"{addr}: {err}" for addr, err in refused.items())
                raise RuntimeError(f"SMTP 拒收部分收件人：{detail}")
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass

    @staticmethod
    async def _send_email(to: List[str], subject: str, body_html: str, attachments: Optional[List[tuple]] = None):
        """底层邮件发送"""
        smtp = await SystemSmtpConfig.first()
        if not smtp:
            raise ValueError("未配置全局 SMTP")

        await asyncio.to_thread(
            NotificationService._send_email_sync,
            host=smtp.host,
            port=smtp.port,
            username=smtp.username,
            password=smtp.password,
            use_tls=smtp.use_tls,
            sender=smtp.sender,
            to=to,
            subject=subject,
            body_html=body_html,
            attachments=attachments,
        )

    @staticmethod
    async def _send_email_alert(cfg: NotificationConfig, title: str, content: dict):
        """发送邮件告警"""
        recipients = cfg.config.get("recipients", [])
        if not recipients:
            return

        body = NotificationService._build_alert_body(content, is_html=True)
        await NotificationService._send_email(to=recipients, subject=title, body_html=body)

    @staticmethod
    async def _send_dingtalk_alert(
        cfg: NotificationConfig,
        title: str,
        content: dict,
        *,
        at_mobiles: Optional[List[str]] = None,
    ):
        """发送钉钉告警；at_mobiles 非空时 @ 对应手机号。"""
        config = cfg.config or {}
        webhook = config.get("webhook_url")
        if not webhook:
            raise ValueError("未配置钉钉 Webhook")

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
        mobiles = [m for m in (at_mobiles or []) if m]
        if mobiles:
            # 钉钉 markdown @ 需在正文中出现 @手机号
            mention = " ".join(f"@{m}" for m in mobiles)
            text = f"{mention}\n{text}"
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text
            },
        }
        if mobiles:
            payload["at"] = {"atMobiles": mobiles, "isAtAll": False}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json=payload)
            resp.raise_for_status()
            result = resp.json()
            if result.get("errcode") != 0:
                raise RuntimeError(f"钉钉发送失败: {result}")

    @staticmethod
    async def _send_wechat_alert(
        cfg: NotificationConfig,
        title: str,
        content: dict,
        *,
        at_mobiles: Optional[List[str]] = None,
    ):
        """发送企业微信告警；有手机号时改用 text + mentioned_mobile_list 以支持 @。"""
        config = cfg.config or {}
        webhook = config.get("webhook_url")
        if not webhook:
            raise ValueError("未配置企微 Webhook")

        text = NotificationService._build_alert_body(content, is_html=False)
        mobiles = [m for m in (at_mobiles or []) if m]
        if mobiles:
            body = f"{title}\n{text}" if title else text
            payload = {
                "msgtype": "text",
                "text": {
                    "content": body,
                    "mentioned_mobile_list": mobiles,
                },
            }
        else:
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
    async def _send_feishu_alert(
        cfg: NotificationConfig,
        title: str,
        content: dict,
        *,
        at_mobiles: Optional[List[str]] = None,
    ):
        """发送飞书告警。自定义机器人无法按手机号真实 @，正文中写入 @手机号 提示。"""
        config = cfg.config or {}
        webhook = config.get("webhook_url")
        if not webhook:
            raise ValueError("未配置飞书 Webhook")

        text = NotificationService._build_alert_body(content, is_html=False)
        mobiles = [m for m in (at_mobiles or []) if m]
        if mobiles:
            mention = " ".join(f"@{m}" for m in mobiles)
            text = f"{mention}\n{text}"
        message = f"**{title}**\n{text}" if title else text
        payload = {
            "msg_type": "text",
            "content": {
                "text": message,
            },
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json=payload)
            resp.raise_for_status()
            result = resp.json()
            code = result.get("code", result.get("StatusCode", -1))
            if code not in (0, "0"):
                raise RuntimeError(f"飞书发送失败: {result}")

    @staticmethod
    def _build_alert_body(content: dict, is_html: bool = False) -> str:
        """组装告警/通知内容。"""
        if (content or {}).get("notice_kind") == "quality":
            return NotificationService._build_quality_notice_body(content, is_html=is_html)
        if (content or {}).get("notice_kind") == "assignment":
            return NotificationService._build_assignment_notice_body(content, is_html=is_html)
        t = content.get("execution_type", "")
        name = content.get("name", "")
        status = content.get("status", "")
        total = content.get("total", 0)
        success = content.get("success", 0)
        failed = content.get("failed", 0)
        pass_rate = content.get("pass_rate", 0)
        duration = content.get("duration", 0)
        run_by = content.get("run_by", "")
        link = NotificationService._ensure_absolute_link(content.get("link", ""))
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

    @staticmethod
    def _build_quality_notice_body(content: dict, is_html: bool = False) -> str:
        name = content.get("name", "")
        status = content.get("status", "")
        release_key = content.get("release_key", "")
        metrics = content.get("metrics") or {}
        waiver = content.get("waiver_reason") or ""
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        completion = metrics.get("completion_rate")
        pass_rate = metrics.get("pass_rate")
        blocker = metrics.get("blocker_open")
        critical = metrics.get("critical_open")
        if is_html:
            body = f"""
            <h3>版本质量门禁通知</h3>
            <p><b>版本：</b>{release_key} {name}</p>
            <p><b>结论：</b>{status}</p>
            <p><b>完成率：</b>{completion} &nbsp; <b>通过率：</b>{pass_rate}</p>
            <p><b>Blocker：</b>{blocker} &nbsp; <b>Critical：</b>{critical}</p>
            <p><b>时间：</b>{time_str}</p>
            """
            if waiver:
                body += f"<p><b>豁免原因：</b>{waiver}</p>"
            return body
        md = f"""### 版本质量门禁通知
**版本：** {release_key} {name}
**结论：** {status}
**完成率：** {completion}　**通过率：** {pass_rate}
**Blocker：** {blocker}　**Critical：** {critical}
**时间：** {time_str}
"""
        if waiver:
            md += f"**豁免原因：** {waiver}\n"
        return md

    @staticmethod
    def _escape_md_text(text: str) -> str:
        s = str(text or "")
        for ch in ("\\", "*", "_", "[", "]", "(", ")", "`", "#", ">", "|"):
            s = s.replace(ch, "\\" + ch)
        return s

    @staticmethod
    def _build_assignment_notice_body(content: dict, is_html: bool = False) -> str:
        event_label = content.get("event_label") or content.get("event_type") or "指派"
        name = content.get("name") or ""
        detail = content.get("detail") or ""
        project_name = content.get("project_name") or ""
        actor = content.get("actor") or ""
        link = NotificationService._ensure_absolute_link(content.get("link") or "")
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if is_html:
            esc = html_module.escape
            event_label = esc(str(event_label))
            name = esc(str(name))
            detail = esc(str(detail))
            project_name = esc(str(project_name))
            actor = esc(str(actor))
            link_esc = esc(str(link)) if link else ""
            body = f"""
            <h3>测试管理指派通知</h3>
            <p><b>类型：</b>{event_label}</p>
            <p><b>标题：</b>{name}</p>
            <p><b>说明：</b>{detail}</p>
            <p><b>项目：</b>{project_name} &nbsp; <b>操作人：</b>{actor}</p>
            <p><b>时间：</b>{time_str}</p>
            """
            if link:
                body += f'<p><a href="{link_esc}">打开详情</a></p>'
            return body
        esc = NotificationService._escape_md_text
        event_label = esc(str(event_label))
        name = esc(str(name))
        detail = esc(str(detail))
        project_name = esc(str(project_name))
        actor = esc(str(actor))
        md = f"""### 测试管理指派通知
**类型：** {event_label}
**标题：** {name}
**说明：** {detail}
**项目：** {project_name}　**操作人：** {actor}
**时间：** {time_str}
"""
        if link:
            md += f"\n[打开详情](<{link}>)"
        return md
