"""S3 object storage. Tables store only keys and hashes; all access is via signed URLs.

Signed URLs are generated with a client bound to the *public* endpoint because SigV4 signs
the host: a URL signed for `http://s3:8333` (compose network) won't verify when the browser
fetches `http://localhost:8333`.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from kehora_common.settings import Settings, require

SIGNED_URL_TTL_SECONDS = 600  # PRD 10: 10-minute expiry


@dataclass(frozen=True)
class StoredObject:
    key: str
    sha256: str
    size: int


class Storage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        creds: dict[str, Any] = {"region_name": settings.s3_region}
        if settings.s3_access_key_id is not None:
            creds["aws_access_key_id"] = settings.s3_access_key_id.get_secret_value()
            creds["aws_secret_access_key"] = require(
                settings.s3_secret_access_key, "S3_SECRET_ACCESS_KEY"
            ).get_secret_value()
        cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        self._client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint_url, config=cfg, **creds
        )
        self._signer = boto3.client(
            "s3",
            endpoint_url=settings.s3_public_endpoint_url or settings.s3_endpoint_url,
            config=cfg,
            **creds,
        )

    def ensure_bucket(self) -> None:
        """Create the bucket if missing. Dev/test only; prod buckets come from Terraform."""
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self.bucket)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return StoredObject(key=key, sha256=digest, size=len(data))

    def get_bytes(self, key: str) -> bytes:
        body: bytes = self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return body

    def presign_get(self, key: str, ttl: int = SIGNED_URL_TTL_SECONDS) -> str:
        url: str = self._signer.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=ttl
        )
        return url

    def presign_put(self, key: str, content_type: str, ttl: int = SIGNED_URL_TTL_SECONDS) -> str:
        url: str = self._signer.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=ttl,
        )
        return url
