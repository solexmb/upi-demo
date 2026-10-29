"""
Azure Blob Storage I/O. Authentication goes through auth.get_credential(),
which explicitly detects and logs whether it's using AKS Workload Identity
(GitLab Runner pods) or falling back to local `az login` - see auth.py for
why that's handled explicitly rather than left to a silent SDK chain.
"""

from __future__ import annotations

import json
import logging

from azure.storage.blob import BlobServiceClient

from .auth import get_credential

logger = logging.getLogger(__name__)


def download_blob(account_url: str, container: str, blob_name: str) -> bytes:
    """Fetches a single blob's bytes. Used for local/manual testing against
    the real source container - the Function App gets its bytes directly
    from the blob trigger instead."""
    credential = get_credential()
    service_client = BlobServiceClient(account_url=account_url, credential=credential)
    blob_client = service_client.get_container_client(container).get_blob_client(blob_name)
    data = blob_client.download_blob().readall()
    logger.info("Downloaded %s/%s (%d bytes)", container, blob_name, len(data))
    return data


def get_latest_blob_name(
    account_url: str,
    container: str,
    prefixes: str | list[str] = "",
    suffixes: tuple[str, ...] = (".csv", ".csv.gz"),
) -> str:
    """Finds the most-recently-modified blob whose name ends in one of
    `suffixes`, searched across one or more `prefixes` (folders). Used by
    the unattended daily pipeline (GitLab CI, etc.) to find the newest
    Cost Management Export file automatically, since there's no blob
    trigger to hand it a specific file by name.

    `prefixes` can be a single string (back-compat) or a list - e.g.
    ["daily/ExportA/", "daily/ExportB/"] - in which case every folder is
    searched and the single newest file across ALL of them wins. This
    means adding a new export folder later is a config change (update the
    list), never a code change."""
    if isinstance(prefixes, str):
        prefixes = [prefixes]

    credential = get_credential()
    service_client = BlobServiceClient(account_url=account_url, credential=credential)
    container_client = service_client.get_container_client(container)

    candidates = []
    for prefix in prefixes:
        matches = [
            blob for blob in container_client.list_blobs(name_starts_with=prefix)
            if blob.name.lower().endswith(suffixes)
        ]
        logger.info("Prefix %r: %d matching blob(s)", prefix, len(matches))
        candidates.extend(matches)

    if not candidates:
        raise FileNotFoundError(
            f"No blobs matching {suffixes} found under any of {prefixes!r} "
            f"in container {container!r}"
        )

    latest = max(candidates, key=lambda b: b.last_modified)
    logger.info(
        "Found %d matching blob(s) across %d prefix(es); latest is %s (modified %s)",
        len(candidates), len(prefixes), latest.name, latest.last_modified,
    )
    return latest.name


def get_latest_blob_per_prefix(
    account_url: str,
    container: str,
    prefixes: list[str],
    suffixes: tuple[str, ...] = (".csv", ".csv.gz"),
) -> list[str]:
    """Latest matching blob from EACH prefix (one per subscription export).
    Unlike get_latest_blob_name, nothing is dropped: every prefix must yield
    a file, or the whole run fails - uploading a partial set as the full
    month-to-date would silently leave a subscription out of Cloudability."""
    credential = get_credential()
    service_client = BlobServiceClient(account_url=account_url, credential=credential)
    container_client = service_client.get_container_client(container)

    chosen = []
    for prefix in prefixes:
        matches = [
            b for b in container_client.list_blobs(name_starts_with=prefix)
            if b.name.lower().endswith(suffixes)
        ]
        if not matches:
            raise FileNotFoundError(f"No export file found under prefix {prefix!r}")

        # An export run is one folder (.../<period>/<run-guid>/) and Azure may
        # split it into several part files (part_0_0001.csv.gz, part_1_0001...).
        # Find the newest run, then take EVERY part in that same folder.
        latest = max(matches, key=lambda b: b.last_modified)
        run_folder = latest.name.rsplit("/", 1)[0] + "/"
        parts = sorted(b.name for b in matches if b.name.startswith(run_folder))
        logger.info(
            "Prefix %r -> run folder %s, %d part file(s): %s",
            prefix, run_folder, len(parts), parts,
        )
        chosen.extend(parts)
    return chosen


def upload_outputs(
    account_url: str,
    container: str,
    parquet_bytes: bytes,
    manifest: dict,
    paths: dict,
) -> None:
    """Uploads the Parquet data file and the manifest.json to the
    destination container, at the paths computed by build_manifest()."""
    credential = get_credential()
    service_client = BlobServiceClient(account_url=account_url, credential=credential)
    container_client = service_client.get_container_client(container)

    parquet_path = f"{paths['base_path']}/{paths['parquet_filename']}"
    manifest_path = f"{paths['base_path']}/{paths['manifest_filename']}"

    container_client.upload_blob(name=parquet_path, data=parquet_bytes, overwrite=True)
    container_client.upload_blob(
        name=manifest_path,
        data=json.dumps(manifest, indent=2),
        overwrite=True,
    )
    logger.info("Uploaded data file: %s/%s", container, parquet_path)
    logger.info("Uploaded manifest: %s/%s", container, manifest_path)
