from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models import Base

config = context.config
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

target_metadata = Base.metadata


def render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Render string enums without their implicit CHECK (the table-level CHECK is rendered explicitly)."""
    import sqlalchemy as sa

    if type_ == "type" and isinstance(obj, sa.Enum) and not obj.native_enum:
        values = ", ".join(repr(v) for v in obj.enums)
        return f"sa.Enum({values}, name={obj.name!r}, native_enum=False, create_constraint=False, length={obj.length})"
    return False


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, compare_type=True, render_item=render_item)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True,
                          render_item=render_item)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
