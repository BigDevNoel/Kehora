# ADR-0002: SeaweedFS instead of MinIO for local S3

- Status: accepted
- Date: 2026-10-30

## Context

The Phase 0 brief asks for MinIO in docker-compose as the local S3. MinIO no longer publishes a
public container image: `minio/minio` is gone from Docker Hub and `quay.io/minio/minio` has no
public manifest. Production uses Amazon S3 (CLAUDE.md), so the local server only has to speak the
S3 API well enough for boto3, including presigned PUT and GET URLs.

## Decision

Use SeaweedFS (`chrislusf/seaweedfs:4.51`, Apache-2.0) in single-container mode
(`weed server -s3`) as the local S3 endpoint. All application code talks to it only through
boto3 with `S3_ENDPOINT_URL`, so switching back to MinIO or to real S3 is a config change.

## Consequences

- No vendor-specific code; `S3_ENDPOINT_URL` unset means real AWS S3.
- SeaweedFS S3 credentials come from a small JSON config generated from `.env` at container start.
- Revisit if SeaweedFS's presigned URL behaviour diverges from AWS in a way our tests catch.
