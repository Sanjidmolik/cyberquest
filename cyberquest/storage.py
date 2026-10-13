"""
Phase 1 — Steps 2 to 5: private Cloudflare R2 storage for uploaded and generated files.

Enabled only when MEDIA_STORAGE=r2 (see cyberquest/settings.py). Local
development keeps FileSystemStorage under MEDIA_ROOT.

Privacy rules are fixed here rather than read from the environment:
  * objects are written without an ACL, so the bucket's own (private) policy applies;
  * existing names are never overwritten, so a stored certificate PDF cannot
    be replaced by a later save that happens to reuse its name;
  * url() only ever returns a short-lived signed URL. The application itself
    never links to it: pages stream files through permission-checked views
    (cyberquest.media_access.serve_stored_file).
"""

from boto3.s3.transfer import TransferConfig
from botocore.config import Config
from storages.backends.s3 import S3Storage


class PrivateR2Storage(S3Storage):
    def __init__(self, **settings):
        settings.update(
            default_acl=None,
            querystring_auth=True,
            file_overwrite=False,
            custom_domain=None,
            gzip=False,
        )
        settings.setdefault("region_name", "auto")
        settings.setdefault("signature_version", "s3v4")
        settings.setdefault("querystring_expire", 300)
        # Gunicorn sync workers: no background transfer threads.
        settings.setdefault("transfer_config", TransferConfig(use_threads=False))
        settings.setdefault(
            "client_config",
            Config(
                # Only send/verify checksums when an operation requires them,
                # which keeps uploads compatible with R2's S3 API.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
            ),
        )
        super().__init__(**settings)
