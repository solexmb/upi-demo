"""
Centralized configuration. Reads from environment variables so the same
code runs unchanged locally, in a Function App, or in any other runner -
only the App Settings / .env values change between environments.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Raised when a required setting is missing."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"Missing required setting: {name}. Set it as an environment "
            f"variable locally, or as a Function App Application Setting in Azure."
        )
    return value


def _parse_prefix_list(raw: str) -> list[str]:
    """Splits a comma-separated list of prefixes into a clean list, e.g.
    "daily/ExportA/,daily/ExportB/" -> ["daily/ExportA/", "daily/ExportB/"].
    A single value with no comma still works fine - it just becomes a
    one-item list. Empty/missing input returns [""] (scan the whole
    container), not an empty list."""
    if not raw:
        return [""]
    return [p.strip() for p in raw.split(",") if p.strip()] or [""]


@dataclass(frozen=True)
class Settings:
    dest_account_url: str
    dest_container: str
    vendor: str
    optional_sub_directories: str
    report_prefix: str
    focus_version: str
    source_account_url: str
    source_container: str
    source_prefixes: list[str]
    max_periods: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            dest_account_url=_require("FOCUS_DEST_ACCOUNT_URL"),
            dest_container=_require("FOCUS_DEST_CONTAINER"),
            # Defaults below match the values confirmed against the real,
            # working Cloudability credential - override via env vars if
            # your setup differs.
            vendor=os.environ.get("FOCUS_VENDOR", "Microsoft Azure"),
            optional_sub_directories=os.environ.get("FOCUS_SUB_DIRECTORIES", ""),
            report_prefix=os.environ.get("FOCUS_REPORT_PREFIX", "reports"),
            focus_version=os.environ.get("FOCUS_SPEC_VERSION", "1.0"),
            # Source = where Azure's Cost Management Export lands. Only
            # actually needed by the unattended pipeline (pipeline.py) that
            # fetches the latest export automatically - left optional here
            # (not _require'd) so the interactive cli.py, which takes a file
            # path directly instead, doesn't break when these aren't set.
            source_account_url=os.environ.get("SOURCE_ACCOUNT_URL", ""),
            source_container=os.environ.get("SOURCE_CONTAINER", ""),
            # Comma-separated list of folders to search for the latest
            # export - e.g. "daily/PRD-TestProdExport/". If another export
            # folder gets added later, just add it here
            # ("daily/ExportA/,daily/ExportB/") - no code change needed.
            source_prefixes=_parse_prefix_list(os.environ.get("SOURCE_PREFIX", "")),
            # How many of the most recent billing periods to (re)process each run.
            # 2 = current + previous month, so last month gets its final upload.
            max_periods=int(os.environ.get("FOCUS_MAX_PERIODS", "2")),
        )

    def require_source(self) -> None:
        """Validates that source settings are present. Call this explicitly
        in code paths that actually need to fetch from the source container
        (the unattended pipeline) - not in paths that already have the file
        (the interactive CLI)."""
        missing = [
            name for name, value in [
                ("SOURCE_ACCOUNT_URL", self.source_account_url),
                ("SOURCE_CONTAINER", self.source_container),
            ] if not value
        ]
        if missing:
            raise ConfigError(
                f"Missing required setting(s) for the automated pipeline: "
                f"{', '.join(missing)}"
            )
