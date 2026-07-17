import logging

from app.worker.main import configure_logging


def test_worker_logging_exposes_app_info_and_quiets_httpx(monkeypatch):
    configured = {}
    real_get_logger = logging.getLogger

    class FakeLogger:
        def setLevel(self, level):
            configured["httpx_level"] = level

    monkeypatch.setattr(
        logging,
        "basicConfig",
        lambda **kwargs: configured.update(kwargs),
    )
    monkeypatch.setattr(
        logging,
        "getLogger",
        lambda name=None: (
            FakeLogger() if name == "httpx" else real_get_logger(name)
        ),
    )

    configure_logging()

    assert configured["level"] == logging.INFO
    assert configured["httpx_level"] == logging.WARNING
    assert "%(name)s" in configured["format"]
