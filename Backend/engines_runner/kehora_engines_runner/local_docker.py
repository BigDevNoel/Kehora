"""Local Docker sandbox for development (ADR-0008). Not for production: the worker needs the
Docker socket, which is root-equivalent on the host. Production uses a hosted provider.

Per job:
1. A scratch volume is filled with /work/in/* by a short-lived helper container.
2. The job container runs as nobody with a read-only rootfs, all capabilities dropped,
   no-new-privileges, CPU/memory/pids limits, the volume at /work and a small /tmp tmpfs.
   Network: none, or (if the job lists hosts) the internal sandbox network whose only way out
   is the allowlisting egress proxy.
3. After exit (or timeout -> kill), /work/out is copied back; containers and volume are removed.
"""

import asyncio
import io
import tarfile
import time
import uuid
from typing import Any

import docker
from docker.errors import DockerException, ImageNotFound, NotFound

from kehora_engines.base import SandboxJob, SandboxResult
from kehora_engines_runner.sandbox import SandboxError, check_allowlist, check_no_secrets

NOBODY = 65534
MAX_LOG_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 256 * 1024 * 1024


def _input_tar(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for d in ("in", "out"):
            info = tarfile.TarInfo(d)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755 if d == "in" else 0o777
            info.uid = info.gid = NOBODY
            tar.addfile(info)
        for name, data in files.items():
            if "/" in name or name.startswith("."):
                raise SandboxError(f"input file names must be flat: {name!r}")
            info = tarfile.TarInfo(f"in/{name}")
            info.size = len(data)
            info.mode = 0o444
            info.uid = info.gid = NOBODY
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _tail(log: bytes) -> str:
    return log[-MAX_LOG_BYTES:].decode(errors="replace")


def _read_outputs(stream: Any) -> dict[str, bytes]:
    raw = b"".join(stream)
    if len(raw) > MAX_OUTPUT_BYTES:
        raise SandboxError("sandbox output exceeds size limit")
    outputs: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            name = member.name.split("/", 1)[1] if "/" in member.name else member.name
            extracted = tar.extractfile(member)
            if extracted is not None:
                outputs[name] = extracted.read()
    return outputs


class LocalDockerSandbox:
    name = "local_docker"

    def __init__(
        self,
        *,
        sandbox_network: str = "kehora-sandbox",
        egress_proxy: str | None = None,
        egress_allowlist: set[str] | None = None,
        client: docker.DockerClient | None = None,
    ) -> None:
        self._client = client
        self._network = sandbox_network
        self._proxy = egress_proxy
        self._allowlist = egress_allowlist or set()

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    async def run(self, job: SandboxJob) -> SandboxResult:
        check_no_secrets(job)
        if job.network_allowlist:
            if not self._proxy:
                raise SandboxError("job needs network but no egress proxy is configured")
            check_allowlist(job, self._allowlist)
        return await asyncio.to_thread(self._run_sync, job)

    def _ensure_image(self, image: str) -> None:
        try:
            self.client.images.get(image)
        except ImageNotFound:
            self.client.images.pull(image)

    def _run_sync(self, job: SandboxJob) -> SandboxResult:
        tag = f"kehora-sbx-{uuid.uuid4().hex[:12]}"
        volume = None
        helper = None
        container = None
        try:
            self._ensure_image(job.image)
            volume = self.client.volumes.create(name=tag, labels={"kehora.sandbox": "1"})
            helper = self.client.containers.create(
                job.image,
                command=["true"],
                volumes={tag: {"bind": "/work", "mode": "rw"}},
                network_mode="none",
                labels={"kehora.sandbox": "1"},
            )
            helper.put_archive("/work", _input_tar(job.files))

            env = dict(job.env)
            network: dict[str, Any] = {"network_mode": "none"}
            if job.network_allowlist:
                network = {"network": self._network}
                proxy = self._proxy or ""
                for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                    env[var] = proxy

            container = self.client.containers.create(
                job.image,
                command=job.command,
                name=tag,
                working_dir="/work",
                environment=env,
                user=f"{NOBODY}:{NOBODY}",
                read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},  # noqa: S108
                volumes={tag: {"bind": "/work", "mode": "rw"}},
                nano_cpus=int(job.limits.cpus * 1e9),
                mem_limit=f"{job.limits.memory_mb}m",
                memswap_limit=f"{job.limits.memory_mb}m",
                pids_limit=job.limits.pids,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                labels={"kehora.sandbox": "1"},
                **network,
            )
            started = time.monotonic()
            container.start()
            timed_out = False
            try:
                status = container.wait(timeout=job.limits.timeout_s)
                exit_code = int(status.get("StatusCode", -1))
            except Exception:  # requests ReadTimeout / ConnectionError on timeout
                timed_out = True
                container.kill()
                exit_code = 137
            duration_ms = int((time.monotonic() - started) * 1000)

            stdout = _tail(container.logs(stdout=True, stderr=False))
            stderr = _tail(container.logs(stdout=False, stderr=True))
            outputs: dict[str, bytes] = {}
            try:
                stream, _ = container.get_archive("/work/out")
                outputs = _read_outputs(stream)
            except NotFound:
                pass
            return SandboxResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                outputs=outputs,
                timed_out=timed_out,
                duration_ms=duration_ms,
            )
        except DockerException as exc:
            raise SandboxError(f"docker sandbox failed: {exc}") from exc
        finally:
            for c in (container, helper):
                if c is not None:
                    try:
                        c.remove(force=True)
                    except DockerException:
                        pass
            if volume is not None:
                try:
                    volume.remove(force=True)
                except DockerException:
                    pass
