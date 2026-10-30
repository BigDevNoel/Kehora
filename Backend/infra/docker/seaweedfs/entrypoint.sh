#!/bin/sh
# Local S3 (ADR-0002). Writes the S3 identity config from env, then starts SeaweedFS.
set -eu

: "${S3_ACCESS_KEY_ID:?S3_ACCESS_KEY_ID is required}"
: "${S3_SECRET_ACCESS_KEY:?S3_SECRET_ACCESS_KEY is required}"

cat > /tmp/s3.json <<EOF
{
  "identities": [
    {
      "name": "kehora",
      "credentials": [
        { "accessKey": "${S3_ACCESS_KEY_ID}", "secretKey": "${S3_SECRET_ACCESS_KEY}" }
      ],
      "actions": ["Admin", "Read", "Write", "List", "Tagging"]
    }
  ]
}
EOF

exec weed server -dir=/data -s3 -s3.port=8333 -s3.config=/tmp/s3.json -master.volumeSizeLimitMB=256 -volume.max=0
