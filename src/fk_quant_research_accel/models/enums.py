"""Enums shared across model and CLI layers."""

from __future__ import annotations

from enum import Enum


class ScenarioStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"
    ASIAN_CALL = "asian_call"
    BARRIER_UP_AND_OUT = "barrier_up_and_out"


class ScoringStrategy(str, Enum):
    LOSS_BASED = "loss_based"
    CONVERGENCE_RATE = "convergence_rate"
    PARETO_MULTI_OBJECTIVE = "pareto_multi_objective"
