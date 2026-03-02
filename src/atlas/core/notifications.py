"""Notification service with pluggable channel backends."""

from __future__ import annotations

import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx

from atlas.core.config import NotificationsConfig, get_settings
from atlas.core.logging import get_logger
from atlas.core.secrets import get_secret

logger = get_logger(__name__)


@dataclass
class Alert:
    """A notification alert to be dispatched."""

    subject: str
    body: str
    severity: str = "warning"  # "info", "warning", "error"
    run_id: Optional[int] = None
    run_date: Optional[date] = None
    metadata: dict = field(default_factory=dict)


class NotificationChannel(ABC):
    """Base class for notification channel backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def send(self, alert: Alert) -> bool:
        """Send an alert. Returns True on success."""
        pass


class EmailChannel(NotificationChannel):
    """SMTP email notification channel."""

    @property
    def name(self) -> str:
        return "email"

    def __init__(self) -> None:
        settings = get_settings()
        cfg = settings.notifications.channels.email
        self._host = cfg.smtp_host
        self._port = cfg.smtp_port
        self._use_tls = cfg.smtp_use_tls
        self._sender = get_secret(cfg.sender_secret, default="atlas-noreply@localhost")
        recipients_raw = get_secret(cfg.recipients_secret, default="")
        self._recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    def send(self, alert: Alert) -> bool:
        if not self._recipients:
            logger.warning("Email channel has no recipients configured, skipping")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[ATLAS] {alert.subject}"
        msg["From"] = self._sender
        msg["To"] = ", ".join(self._recipients)
        msg.attach(MIMEText(alert.body, "plain"))

        try:
            if self._use_tls:
                with smtplib.SMTP(self._host, self._port, timeout=30) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.sendmail(self._sender, self._recipients, msg.as_string())
            else:
                with smtplib.SMTP(self._host, self._port, timeout=30) as server:
                    server.sendmail(self._sender, self._recipients, msg.as_string())
            logger.info("Email alert sent", recipients=len(self._recipients), subject=alert.subject)
            return True
        except Exception as e:
            logger.error("Failed to send email alert", error=str(e))
            return False


class SlackChannel(NotificationChannel):
    """Slack webhook notification channel."""

    @property
    def name(self) -> str:
        return "slack"

    def __init__(self) -> None:
        settings = get_settings()
        cfg = settings.notifications.channels.slack
        self._webhook_url = get_secret(cfg.webhook_url_secret)
        self._channel = cfg.channel
        self._username = cfg.username

    def send(self, alert: Alert) -> bool:
        if not self._webhook_url:
            logger.warning("Slack webhook URL not configured, skipping")
            return False

        severity_emoji = {"info": "\u2139\ufe0f", "warning": "\u26a0\ufe0f", "error": "\U0001f6a8"}.get(
            alert.severity, "\u2139\ufe0f"
        )

        payload = {
            "channel": self._channel,
            "username": self._username,
            "text": f"{severity_emoji} *{alert.subject}*\n{alert.body}",
        }

        try:
            resp = httpx.post(self._webhook_url, json=payload, timeout=15)
            resp.raise_for_status()
            logger.info("Slack alert sent", channel=self._channel, subject=alert.subject)
            return True
        except Exception as e:
            logger.error("Failed to send Slack alert", error=str(e))
            return False


class LogChannel(NotificationChannel):
    """Fallback channel that writes alerts to the structured log."""

    @property
    def name(self) -> str:
        return "log"

    def send(self, alert: Alert) -> bool:
        log_fn = {"error": logger.error, "warning": logger.warning}.get(alert.severity, logger.info)
        log_fn(
            f"ALERT: {alert.subject}",
            body=alert.body,
            severity=alert.severity,
            run_id=alert.run_id,
        )
        return True


class NotificationService:
    """
    Dispatches alerts through configured channels.

    Always logs the alert.  Additionally routes through email / slack
    channels when they are enabled in configuration.
    """

    def __init__(self, config: Optional[NotificationsConfig] = None) -> None:
        self._config = config or get_settings().notifications
        self._channels: list[NotificationChannel] = [LogChannel()]

        if self._config.channels.email.enabled:
            try:
                self._channels.append(EmailChannel())
            except Exception as e:
                logger.warning("Could not initialise email channel", error=str(e))

        if self._config.channels.slack.enabled:
            try:
                self._channels.append(SlackChannel())
            except Exception as e:
                logger.warning("Could not initialise Slack channel", error=str(e))

        logger.debug(
            "NotificationService initialised",
            channels=[c.name for c in self._channels],
        )

    def notify(self, alert: Alert) -> list[str]:
        """
        Send *alert* through every configured channel.

        Returns list of channel names that successfully delivered.
        """
        successes: list[str] = []
        for channel in self._channels:
            try:
                if channel.send(alert):
                    successes.append(channel.name)
            except Exception as e:
                logger.error(f"Channel {channel.name} raised", error=str(e))
        return successes

    # ------------------------------------------------------------------
    # Convenience helpers called directly from the orchestrator
    # ------------------------------------------------------------------

    def notify_run_result(
        self,
        status: str,
        run_id: int,
        run_date: date,
        records_inserted: int,
        records_updated: int,
        errors: list[str],
        duration_seconds: float,
    ) -> None:
        """Send alert for a pipeline run based on status and config flags."""
        should_alert = False
        if status == "failed" and self._config.on_failure:
            should_alert = True
        elif status == "partial" and self._config.on_partial_success:
            should_alert = True

        if not should_alert:
            return

        severity = "error" if status == "failed" else "warning"
        error_block = "\n".join(f"  - {e}" for e in errors) if errors else "  (none)"

        body = (
            f"Run ID:   {run_id}\n"
            f"Date:     {run_date}\n"
            f"Status:   {status}\n"
            f"Duration: {duration_seconds:.1f}s\n"
            f"Inserted: {records_inserted}  |  Updated: {records_updated}\n"
            f"Errors:\n{error_block}"
        )

        self.notify(Alert(
            subject=f"Pipeline {status.upper()} for {run_date}",
            body=body,
            severity=severity,
            run_id=run_id,
            run_date=run_date,
        ))

    def notify_anomaly(
        self,
        run_id: int,
        run_date: date,
        current_records: int,
        average_records: float,
        threshold_pct: float,
    ) -> None:
        """Send alert when record volume drops below the rolling-average threshold."""
        if not self._config.on_anomaly:
            return

        pct = (current_records / average_records * 100) if average_records > 0 else 0
        body = (
            f"Run ID:            {run_id}\n"
            f"Date:              {run_date}\n"
            f"Records this run:  {current_records}\n"
            f"Rolling average:   {average_records:.0f}\n"
            f"Ratio:             {pct:.1f}% (threshold {threshold_pct * 100:.0f}%)\n"
        )

        self.notify(Alert(
            subject=f"Data volume anomaly for {run_date}",
            body=body,
            severity="warning",
            run_id=run_id,
            run_date=run_date,
        ))


def check_volume_anomaly(
    current_records: int,
    recent_counts: list[int],
    threshold_pct: float = 0.80,
) -> bool:
    """
    Return True if *current_records* is below *threshold_pct* of the
    average of *recent_counts*.
    """
    if not recent_counts:
        return False
    avg = sum(recent_counts) / len(recent_counts)
    if avg == 0:
        return False
    return current_records < avg * threshold_pct
