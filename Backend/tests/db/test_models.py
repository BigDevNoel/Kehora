import uuid

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from kehora_db.models import (
    AgentRun,
    AuditLog,
    CreditLedgerEntry,
    Organization,
    Project,
    ProjectVersion,
    RunEventRow,
    User,
)

pytestmark = pytest.mark.db


async def _seed(session: AsyncSession) -> tuple[User, Organization, Project, AgentRun]:
    user = User(clerk_id=f"user_{uuid.uuid4().hex}", email="maker@example.com")
    org = Organization(name="Personal", type="personal")
    session.add_all([user, org])
    await session.flush()
    project = Project(org_id=org.id, owner_id=user.id, title="Phone stand")
    session.add(project)
    await session.flush()
    run = AgentRun(
        project_id=project.id, org_id=org.id, created_by_id=user.id, trigger_prompt="a stand"
    )
    session.add(run)
    await session.flush()
    return user, org, project, run


async def test_ids_are_uuid_v7_and_timestamps_utc(session: AsyncSession) -> None:
    user, _, project, run = await _seed(session)
    for row in (user, project, run):
        assert row.id.version == 7
    await session.refresh(run)
    assert run.created_at.utcoffset() is not None
    assert run.status == "queued"
    assert run.cost_minor == 0 and run.cost_currency == "USD"


async def test_check_constraint_rejects_unknown_enum_value(session: AsyncSession) -> None:
    session.add(User(clerk_id="user_bad", role="superuser"))
    with pytest.raises(IntegrityError, match="ck_users_role"):
        await session.flush()


async def test_run_event_seq_unique_per_run(session: AsyncSession) -> None:
    *_, run = await _seed(session)
    session.add(RunEventRow(run_id=run.id, seq=1, type="run_started"))
    await session.flush()
    session.add(RunEventRow(run_id=run.id, seq=1, type="node_started"))
    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.parametrize("model", [RunEventRow, CreditLedgerEntry, AuditLog])
async def test_append_only_tables_reject_update_and_delete(
    session: AsyncSession, model: type[RunEventRow | CreditLedgerEntry | AuditLog]
) -> None:
    _, org, _, run = await _seed(session)
    row: RunEventRow | CreditLedgerEntry | AuditLog
    if model is RunEventRow:
        row = RunEventRow(run_id=run.id, seq=1, type="run_started")
    elif model is CreditLedgerEntry:
        row = CreditLedgerEntry(org_id=org.id, delta=10, reason="grant", balance_after=10)
    else:
        row = AuditLog(action="user.role_changed", target="user:x")
    session.add(row)
    await session.flush()

    table = model.__tablename__
    for stmt in (f"UPDATE {table} SET updated_at = now()", f"DELETE FROM {table}"):  # noqa: S608
        with pytest.raises(DBAPIError, match="append-only"):
            async with session.begin_nested():
                await session.execute(text(stmt))


async def test_project_versions_are_immutable(session: AsyncSession) -> None:
    _, _, project, _ = await _seed(session)
    version = ProjectVersion(project_id=project.id, number=1, spec={"title": "v1"})
    session.add(version)
    await session.flush()
    with pytest.raises(DBAPIError, match="immutable"):
        await session.execute(
            update(ProjectVersion).where(ProjectVersion.id == version.id).values(number=2)
        )
