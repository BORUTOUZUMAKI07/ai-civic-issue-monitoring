import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    """Resolve the migration URL lazily.

    Importing :mod:`src.core.config` at module scope meant that merely loading
    ``env.py`` required every required environment variable to be present.
    A missing ``SECRET_KEY`` then surfaced as a pydantic validation error that
    looked like a broken migration rather than missing configuration, and it
    fired even for ``alembic --help``. Deferring the import to the point of use
    keeps ``env.py`` importable everywhere and confines the failure to commands
    that actually need a database.
    """
    from src.core.config import settings

    return settings.ASYNC_DATABASE_URI


def _target_metadata():
    from src.models import Base

    return Base.metadata


def _escape_percent(url: str) -> str:
    """Escape ``%`` for ``ConfigParser`` interpolation.

    ``Config.set_main_option`` stores the value and ``get_main_option``
    interpolates it on the way out, where ``%`` is the escape character. Any
    percent-encoded byte in the connection string (a ``%`` in a password, a
    percent-encoded query value) therefore made every alembic command die with
    ``Invalid interpolation syntax`` before it ever reached the database.
    Doubling them is exactly the escaping ConfigParser expects.
    """
    return url.replace("%", "%%")


def run_migrations_offline() -> None:
    config.set_main_option("sqlalchemy.url", _escape_percent(_database_url()))
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=_target_metadata(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=_target_metadata())
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Build the engine from the URL directly instead of reading it back out of
    # the config file. `async_engine_from_config` pulls the section through
    # `ConfigParser.items()`, whose raw/interpolated behaviour differs between
    # alembic versions — the one place an escaped `%` could come back doubled.
    # The online path never needs the stored value, so it never has to ask.
    connectable = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
