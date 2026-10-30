from alembic import context
from sqlalchemy import create_engine, pool

from kehora_common.settings import get_settings
from kehora_db import models  # noqa: F401  (registers tables on Base.metadata)
from kehora_db.base import Base

target_metadata = Base.metadata


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    # Ignore tables we don't own (PostGIS tiger/topology, spatial_ref_sys, langgraph).
    return not (type_ == "table" and reflected and compare_to is None)


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # The `langgraph` schema belongs to the LangGraph checkpointer (ADR-0005); only `public`
    # is managed here, which is Alembic's default when include_schemas is False.
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
