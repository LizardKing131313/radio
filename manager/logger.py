"""Настройка структурного логирования через structlog.

Что делает:
- пишет JSON в stderr и файл
- берет уровень из LOG_LEVEL
- добавляет run_id из RUN_ID, параметра или автогенерации
- приводит structlog и stdlib logging к одному формату
- прокидывает контекст через contextvars

export LOG_LEVEL=INFO
export RUN_ID=localdev-123
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import structlog
from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    get_contextvars,
    merge_contextvars,
)
from structlog.processors import JSONRenderer
from structlog.stdlib import ProcessorFormatter
from structlog.typing import FilteringBoundLogger, Processor


def _common_processors() -> list[Processor]:
    # Общая цепочка processor-ов для structlog и stdlib formatter.
    return [
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.dict_tracebacks,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]


def configure_logging(run_id: str | None = None) -> str:
    # Функция идемпотентно пересобирает root logger, поэтому ее безопасно
    # вызывать в каждой контейнерной команде.
    level: int = _parse_log_level(os.getenv("LOG_LEVEL"))
    time_stamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    formatter = ProcessorFormatter(
        processor=JSONRenderer(ensure_ascii=False),
        foreign_pre_chain=[
            merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            time_stamper,
        ],
    )

    stderr_handler = logging.StreamHandler(stream=sys.stderr)
    stderr_handler.setFormatter(formatter)

    log_path = os.getenv("LOG_FILE", "logs/manager.log")
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(stderr_handler)
    root.addHandler(file_handler)
    root.setLevel(level)

    structlog.configure(
        processors=_common_processors(),
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    effective_run_id: str = run_id or os.getenv("RUN_ID") or _generate_run_id()
    bind_contextvars(run_id=effective_run_id)
    return effective_run_id


def get_logger(name: str) -> FilteringBoundLogger:
    """Получить structlog logger с именем компонента."""
    return structlog.get_logger(name)


def set_run_id(new_run_id: str | None = None) -> str:
    """
    Установить или заменить текущий run_id в contextvars.

    Возвращает фактический run_id.
    """
    rid: str = new_run_id or _generate_run_id()
    bind_contextvars(run_id=rid)
    return rid


def get_run_id() -> str | None:
    """Прочитать текущий run_id из contextvars."""
    ctx: dict[str, Any] = dict(get_contextvars())
    rid = ctx.get("run_id")
    return str(rid) if rid is not None else None


def bind_context(**kwargs: str | int | float | bool) -> None:
    """
    Добавить произвольные поля в logging context.

    Пример: bind_context(request_id="abc123", user="alice")
    """
    bind_contextvars(**kwargs)


def reset_log_context() -> None:
    """Очистить contextvars, которые использует structlog."""
    clear_contextvars()


def _parse_log_level(value: str | None) -> int:
    # Неизвестный непустой LOG_LEVEL трактуем как DEBUG, чтобы проблему было
    # проще увидеть в логах.
    if not value:
        return logging.INFO
    normalized = value.strip().upper()
    mapping: dict[str, int] = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET,
    }
    return mapping.get(normalized, logging.DEBUG)


def _generate_run_id() -> str:
    return uuid.uuid4().hex[:12]
