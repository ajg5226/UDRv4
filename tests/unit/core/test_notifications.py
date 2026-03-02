"""Tests for atlas.core.notifications."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from atlas.core.notifications import (
    Alert,
    LogChannel,
    NotificationService,
    check_volume_anomaly,
)


class TestAlert:
    def test_defaults(self):
        a = Alert(subject="test", body="body")
        assert a.severity == "warning"
        assert a.run_id is None
        assert a.metadata == {}


class TestLogChannel:
    def test_always_succeeds(self):
        ch = LogChannel()
        assert ch.name == "log"
        assert ch.send(Alert(subject="x", body="y")) is True


class TestCheckVolumeAnomaly:
    def test_no_recent_counts(self):
        assert check_volume_anomaly(10, []) is False

    def test_above_threshold(self):
        assert check_volume_anomaly(100, [100, 110, 90]) is False

    def test_below_threshold(self):
        assert check_volume_anomaly(50, [100, 100, 100], threshold_pct=0.80) is True

    def test_exactly_at_threshold(self):
        assert check_volume_anomaly(80, [100, 100, 100], threshold_pct=0.80) is False

    def test_zero_average(self):
        assert check_volume_anomaly(0, [0, 0, 0]) is False

    def test_custom_threshold(self):
        assert check_volume_anomaly(60, [100, 100, 100], threshold_pct=0.50) is False
        assert check_volume_anomaly(40, [100, 100, 100], threshold_pct=0.50) is True


class TestNotificationService:
    def test_log_channel_always_present(self):
        svc = NotificationService()
        channel_names = [c.name for c in svc._channels]
        assert "log" in channel_names

    def test_notify_returns_successes(self):
        svc = NotificationService()
        result = svc.notify(Alert(subject="test", body="body"))
        assert "log" in result

    def test_notify_run_result_failure(self):
        svc = NotificationService()
        svc.notify = MagicMock(return_value=["log"])
        svc.notify_run_result(
            status="failed",
            run_id=1,
            run_date=date(2026, 2, 24),
            records_inserted=0,
            records_updated=0,
            errors=["provider timeout"],
            duration_seconds=30.0,
        )
        svc.notify.assert_called_once()
        alert = svc.notify.call_args[0][0]
        assert "FAILED" in alert.subject
        assert alert.severity == "error"
        assert "provider timeout" in alert.body

    def test_notify_run_result_partial(self):
        svc = NotificationService()
        svc.notify = MagicMock(return_value=["log"])
        svc.notify_run_result(
            status="partial",
            run_id=2,
            run_date=date(2026, 2, 24),
            records_inserted=35,
            records_updated=0,
            errors=["some warning"],
            duration_seconds=10.0,
        )
        svc.notify.assert_called_once()
        alert = svc.notify.call_args[0][0]
        assert "PARTIAL" in alert.subject
        assert alert.severity == "warning"

    def test_notify_run_result_success_skipped(self):
        svc = NotificationService()
        svc.notify = MagicMock()
        svc.notify_run_result(
            status="success",
            run_id=3,
            run_date=date(2026, 2, 24),
            records_inserted=100,
            records_updated=5,
            errors=[],
            duration_seconds=8.0,
        )
        svc.notify.assert_not_called()

    def test_notify_anomaly_sends_alert(self):
        svc = NotificationService()
        svc.notify = MagicMock(return_value=["log"])
        svc.notify_anomaly(
            run_id=1,
            run_date=date(2026, 2, 24),
            current_records=20,
            average_records=100.0,
            threshold_pct=0.80,
        )
        svc.notify.assert_called_once()
        alert = svc.notify.call_args[0][0]
        assert "anomaly" in alert.subject.lower()

    def test_notify_anomaly_respects_config_flag(self):
        from atlas.core.config import NotificationsConfig
        cfg = NotificationsConfig(on_anomaly=False)
        svc = NotificationService(config=cfg)
        svc.notify = MagicMock()
        svc.notify_anomaly(
            run_id=1,
            run_date=date(2026, 2, 24),
            current_records=20,
            average_records=100.0,
            threshold_pct=0.80,
        )
        svc.notify.assert_not_called()


class TestEmailChannel:
    def test_no_recipients_returns_false(self, monkeypatch):
        monkeypatch.delenv("ATLAS_ALERT_EMAILS", raising=False)
        monkeypatch.delenv("ATLAS_ALERT_SENDER", raising=False)
        from atlas.core.notifications import EmailChannel
        ch = EmailChannel()
        assert ch.send(Alert(subject="test", body="body")) is False


class TestSlackChannel:
    def test_no_webhook_returns_false(self, monkeypatch):
        monkeypatch.delenv("ATLAS_SLACK_WEBHOOK", raising=False)
        from atlas.core.notifications import SlackChannel
        ch = SlackChannel()
        assert ch.send(Alert(subject="test", body="body")) is False
