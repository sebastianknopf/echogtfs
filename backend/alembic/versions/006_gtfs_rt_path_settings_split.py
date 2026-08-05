"""Rename GTFS-RT service alerts path setting and add feed-specific path settings.

Revision ID: 006_gtfs_rt_path_settings_split
Revises: 005_realtime_tables
Create Date: 2026-07-21 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "006_gtfs_rt_path_settings_split"
down_revision: Union[str, None] = "005_realtime_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


app_settings = sa.table(
    "sys_app_settings",
    sa.column("key", sa.String(length=64)),
    sa.column("value", sa.String(length=2048)),
)


def upgrade() -> None:
    bind = op.get_bind()

    old_key = "gtfs_rt_path"
    service_alerts_key = "gtfs_rt_service_alerts_path"
    trip_updates_key = "gtfs_rt_trip_updates_path"
    vehicle_positions_key = "gtfs_rt_vehicle_positions_path"

    service_alerts_value = bind.execute(
        sa.select(app_settings.c.value).where(app_settings.c.key == old_key)
    ).scalar_one_or_none()

    if service_alerts_value is None:
        service_alerts_value = bind.execute(
            sa.select(app_settings.c.value).where(app_settings.c.key == service_alerts_key)
        ).scalar_one_or_none()

    if service_alerts_value is None:
        service_alerts_value = "realtime/service-alerts.pbf"

    old_key_exists = bind.execute(
        sa.select(app_settings.c.key).where(app_settings.c.key == old_key)
    ).scalar_one_or_none()
    service_alerts_key_exists = bind.execute(
        sa.select(app_settings.c.key).where(app_settings.c.key == service_alerts_key)
    ).scalar_one_or_none()

    if old_key_exists is not None and service_alerts_key_exists is None:
        bind.execute(
            sa.update(app_settings)
            .where(app_settings.c.key == old_key)
            .values(key=service_alerts_key)
        )
    elif service_alerts_key_exists is None:
        bind.execute(
            sa.insert(app_settings).values(key=service_alerts_key, value=service_alerts_value)
        )

    if old_key_exists is not None:
        bind.execute(sa.delete(app_settings).where(app_settings.c.key == old_key))

    trip_updates_exists = bind.execute(
        sa.select(app_settings.c.key).where(app_settings.c.key == trip_updates_key)
    ).scalar_one_or_none()
    if trip_updates_exists is None:
        bind.execute(
            sa.insert(app_settings).values(
                key=trip_updates_key,
                value="realtime/trip-updates.pbf",
            )
        )

    vehicle_positions_exists = bind.execute(
        sa.select(app_settings.c.key).where(app_settings.c.key == vehicle_positions_key)
    ).scalar_one_or_none()
    if vehicle_positions_exists is None:
        bind.execute(
            sa.insert(app_settings).values(
                key=vehicle_positions_key,
                value="realtime/vehicle-positions.pbf",
            )
        )


def downgrade() -> None:
    bind = op.get_bind()

    old_key = "gtfs_rt_path"
    service_alerts_key = "gtfs_rt_service_alerts_path"
    trip_updates_key = "gtfs_rt_trip_updates_path"
    vehicle_positions_key = "gtfs_rt_vehicle_positions_path"

    service_alerts_value = bind.execute(
        sa.select(app_settings.c.value).where(app_settings.c.key == service_alerts_key)
    ).scalar_one_or_none()

    if service_alerts_value is None:
        service_alerts_value = "realtime/service-alerts.pbf"

    old_key_exists = bind.execute(
        sa.select(app_settings.c.key).where(app_settings.c.key == old_key)
    ).scalar_one_or_none()
    service_alerts_key_exists = bind.execute(
        sa.select(app_settings.c.key).where(app_settings.c.key == service_alerts_key)
    ).scalar_one_or_none()

    if service_alerts_key_exists is not None and old_key_exists is None:
        bind.execute(
            sa.update(app_settings)
            .where(app_settings.c.key == service_alerts_key)
            .values(key=old_key)
        )
    elif old_key_exists is None:
        bind.execute(
            sa.insert(app_settings).values(key=old_key, value=service_alerts_value)
        )

    if service_alerts_key_exists is not None:
        bind.execute(sa.delete(app_settings).where(app_settings.c.key == service_alerts_key))

    bind.execute(sa.delete(app_settings).where(app_settings.c.key == trip_updates_key))
    bind.execute(sa.delete(app_settings).where(app_settings.c.key == vehicle_positions_key))
