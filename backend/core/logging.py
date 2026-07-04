import logging
import sys

import structlog

from core.config import get_settings
from utils.pii import redact_pii


def _pii_processor(
    _logger: object, _name: str, event_dict: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = redact_pii(value)
    return event_dict


def configure_logging() -> None:
    settings = get_settings()
    level = logging.DEBUG if settings.app_debug else logging.INFO
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")
    for noisy_logger in ("httpx", "httpcore", "hpack", "http11"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _pii_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
            if settings.app_env != "local"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.app_debug else logging.INFO
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
