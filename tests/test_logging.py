from __future__ import annotations

import structlog

from fk_quant_research_accel.logging import configure_logging


def setup_function() -> None:
    structlog.reset_defaults()


def test_configure_logging_initializes_logger() -> None:
    configure_logging("INFO")
    logger = structlog.get_logger()
    logger.info("hello")
