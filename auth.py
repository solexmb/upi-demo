"""
Resolves the Azure credential to use, and - unlike calling
DefaultAzureCredential() directly and hoping - logs which auth method it
actually picked. This matters because DefaultAzureCredential tries several
methods in a silent chain; when auth fails, the real cause is often "it
tried the wrong one and swallowed the real error," which is hard to debug
from a generic failure message alone.

In this project's environments, this resolves to:
- AKS (Workload Identity, e.g. a GitLab Runner pod with the
  azure.workload.identity/use: "true" label): the kubelet/webhook injects
  AZURE_CLIENT_ID, AZURE_TENANT_ID, and AZURE_FEDERATED_TOKEN_FILE
  automatically. We detect these and use WorkloadIdentityCredential
  explicitly, rather than letting DefaultAzureCredential guess.
- Local development: falls back to DefaultAzureCredential, which picks up
  your `az login` session (AzureCliCredential) or similar.
"""

from __future__ import annotations

import logging
import os

from azure.identity import DefaultAzureCredential, WorkloadIdentityCredential

logger = logging.getLogger(__name__)

_WORKLOAD_IDENTITY_ENV_VARS = ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_FEDERATED_TOKEN_FILE")


def get_credential():
    """Returns the Azure credential to use, logging which path was taken.
    Call this once per process and reuse the result - don't call it per
    request."""
    present = {name: os.environ.get(name) for name in _WORKLOAD_IDENTITY_ENV_VARS}
    missing = [name for name, value in present.items() if not value]

    if not missing:
        token_file = present["AZURE_FEDERATED_TOKEN_FILE"]
        if not os.path.isfile(token_file):
            # The env vars are set but the token file isn't actually there -
            # this is the single most common workload-identity misconfig
            # (e.g. the pod label is missing, so AKS's webhook never mounted
            # it). Fail loudly here instead of letting a generic auth error
            # surface three layers down inside the Azure SDK.
            raise RuntimeError(
                f"AZURE_FEDERATED_TOKEN_FILE is set to {token_file!r} but that "
                f"file doesn't exist. This usually means the pod is missing "
                f"the 'azure.workload.identity/use: \"true\"' label, or isn't "
                f"running under the expected ServiceAccount - check that "
                f"before assuming this is a code problem."
            )
        logger.info(
            "Using WorkloadIdentityCredential (AZURE_CLIENT_ID=%s) - "
            "workload identity environment detected.",
            present["AZURE_CLIENT_ID"],
        )
        return WorkloadIdentityCredential(
            tenant_id=present["AZURE_TENANT_ID"],
            client_id=present["AZURE_CLIENT_ID"],
            token_file_path=token_file,
        )

    logger.info(
        "Workload identity env vars not fully present (missing: %s) - "
        "falling back to DefaultAzureCredential (expected for local "
        "development, e.g. an `az login` session).",
        ", ".join(missing),
    )
    return DefaultAzureCredential()
