"""Deterministic content hashing utilities."""

from __future__ import annotations

import hashlib
import json

from .experiment import ExperimentManifest


def content_hash(manifest: ExperimentManifest) -> str:
    canonical = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
