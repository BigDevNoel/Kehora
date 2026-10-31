# syntax=docker/dockerfile:1
# CAD engine sandbox image (ADR-0010). Context: ./Backend/infra/docker/engines/cad
# Runs build123d scripts with no network as `nobody` on a read-only rootfs (ADR-0008).
FROM python:3.12-slim-trixie

# OCCT needs a few X/GL client libraries even in the no-VTK build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

# The wheels are large (OCP alone is ~67 MB): keep finished downloads in a BuildKit cache so a
# timed-out build resumes instead of starting over.
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --retries 10 --require-hashes -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && python -c "import build123d, trimesh"

# Read-only rootfs: keep caches and HOME on the writable /tmp mount.
ENV HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp
WORKDIR /work
