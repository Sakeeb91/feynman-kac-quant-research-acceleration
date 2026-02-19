from __future__ import annotations

import structlog

from fk_quant_research_accel.logging import configure_logging


def setup_function() -> None:
    structlog.reset_defaults()


def test_configure_logging_initializes_logger() -> None:
    configure_logging("INFO")
    logger = structlog.get_logger()
    logger.info("hello")


def test_debug_messages_visible_at_debug_level(capfd) -> None:
    configure_logging("DEBUG")
    logger = structlog.get_logger()
    logger.debug("test_debug")

    captured = capfd.readouterr()
    assert "test_debug" in captured.err


def test_info_messages_filtered_at_error_level(capfd) -> None:
    configure_logging("ERROR")
    logger = structlog.get_logger()
    logger.info("should_not_appear")

    captured = capfd.readouterr()
    assert "should_not_appear" not in captured.err


def test_bound_logger_preserves_context(capfd) -> None:
    configure_logging("INFO")
    logger = structlog.get_logger().bind(run_id="abc")
    logger.info("with_context")

    captured = capfd.readouterr()
    assert "with_context" in captured.err
    assert "run_id" in captured.err
    assert "abc" in captured.err
