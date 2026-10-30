import docker
import pytest

from kehora_engines.base import EngineError, SandboxJob, SandboxLimits, SandboxResult
from kehora_engines.cad import CadEngine, CadInput
from kehora_engines.echo import IMAGE, EchoEngine, EchoInput, EchoOutput
from kehora_engines_runner.hosted import E2BSandbox
from kehora_engines_runner.local_docker import LocalDockerSandbox
from kehora_engines_runner.runner import run_engine
from kehora_engines_runner.sandbox import SandboxPolicyError
from kehora_schemas import CheckStatus


@pytest.fixture(scope="module")
def sandbox() -> LocalDockerSandbox:
    return LocalDockerSandbox(egress_proxy="http://egress:8888", egress_allowlist={"pypi.org"})


def _job(script: str, **kw: object) -> SandboxJob:
    return SandboxJob(image=IMAGE, command=["sh", "-c", script], **kw)


# --- pure engine logic (no Docker) ------------------------------------------------------
def test_echo_verify_passes_and_fails() -> None:
    engine, inp = EchoEngine(), EchoInput(message="hi")
    assert engine.verify(inp, EchoOutput(text="hi", sha256="x"))[0].status == CheckStatus.pass_
    assert engine.verify(inp, EchoOutput(text="ho", sha256="x"))[0].status == CheckStatus.fail


def test_echo_parse_rejects_failed_run() -> None:
    result = SandboxResult(exit_code=1, stdout="", stderr="boom", outputs={})
    with pytest.raises(EngineError, match="exit 1"):
        EchoEngine().parse(EchoInput(message="hi"), result)


def test_later_phase_engines_are_interface_stubs() -> None:
    with pytest.raises(NotImplementedError, match="phase 1"):
        CadEngine().build_job(CadInput())


async def test_policy_rejects_secrets_and_unlisted_hosts(sandbox: LocalDockerSandbox) -> None:
    with pytest.raises(SandboxPolicyError, match="secret"):
        await sandbox.run(_job("true", env={"ANTHROPIC_API_KEY": "x"}))
    with pytest.raises(SandboxPolicyError, match="allowlist"):
        await sandbox.run(_job("true", network_allowlist=["evil.example"]))


async def test_e2b_stub_fails_loudly() -> None:
    with pytest.raises(NotImplementedError):
        await E2BSandbox(None).run(_job("true"))


# --- real Docker ----------------------------------------------------------------------
@pytest.mark.docker
async def test_echo_round_trip_in_sandbox(sandbox: LocalDockerSandbox) -> None:
    run = await run_engine(sandbox, EchoEngine(), EchoInput(message="hello kehora"))
    assert run.output.text == "hello kehora"
    assert run.checks[0].status == CheckStatus.pass_
    assert run.result.exit_code == 0 and "done" in run.result.stdout


@pytest.mark.docker
async def test_runs_as_nobody_with_read_only_rootfs_and_no_network(
    sandbox: LocalDockerSandbox,
) -> None:
    script = (
        "id -u > /work/out/uid; "
        "(touch /etc/x 2>/dev/null && echo writable || echo readonly) > /work/out/rootfs; "
        "(wget -q -T 3 -O /dev/null http://1.1.1.1 && echo online || echo offline) > /work/out/net"
    )
    result = await sandbox.run(_job(script))
    assert result.outputs["uid"].strip() == b"65534"
    assert result.outputs["rootfs"].strip() == b"readonly"
    assert result.outputs["net"].strip() == b"offline"


@pytest.mark.docker
async def test_timeout_kills_job(sandbox: LocalDockerSandbox) -> None:
    result = await sandbox.run(_job("sleep 30", limits=SandboxLimits(timeout_s=2)))
    assert result.timed_out and result.exit_code == 137
    assert result.duration_ms < 15_000


@pytest.mark.docker
async def test_memory_limit_is_enforced(sandbox: LocalDockerSandbox) -> None:
    # Allocate ~200 MB in a 64 MB sandbox: the kernel OOM-kills the process.
    script = "head -c 200000000 /dev/zero | tail > /dev/null"
    result = await sandbox.run(_job(script, limits=SandboxLimits(memory_mb=64, timeout_s=30)))
    assert result.exit_code != 0


@pytest.mark.docker
async def test_sandbox_resources_are_removed(sandbox: LocalDockerSandbox) -> None:
    await sandbox.run(_job("true"))
    client = docker.from_env()
    assert client.containers.list(all=True, filters={"label": "kehora.sandbox"}) == []
    assert client.volumes.list(filters={"label": "kehora.sandbox"}) == []


@pytest.mark.docker
async def test_egress_proxy_allows_listed_hosts_and_filters_others(
    sandbox: LocalDockerSandbox,
) -> None:
    # The job sits on the internal sandbox network; the proxy is its only route out.
    script = (
        "wget -q -T 10 -O /dev/null http://pypi.org/simple/ 2> /work/out/allowed; "
        "wget -q -T 10 -O /dev/null http://example.com/ 2> /work/out/denied; "
        "wget -q -T 5 -O /dev/null -Y off http://1.1.1.1/ 2> /work/out/direct; true"
    )
    result = await sandbox.run(_job(script, network_allowlist=["pypi.org"]))
    # tinyproxy answers "403 Filtered" for hosts outside its allowlist; pypi answering at all
    # (even with its own "SSL is required") proves the request got through.
    assert b"Filtered" not in result.outputs["allowed"]
    assert b"pypi" in result.outputs["allowed"].lower() or b"SSL" in result.outputs["allowed"]
    assert b"403 Filtered" in result.outputs["denied"]
    assert result.outputs["direct"]  # direct connection fails: no route out of the network
