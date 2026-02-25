"""Problem specification protocol and defaults."""

from __future__ import annotations

from pydantic import BaseModel


class ProblemParams(BaseModel):
    """Base model for problem-specific parameters."""

