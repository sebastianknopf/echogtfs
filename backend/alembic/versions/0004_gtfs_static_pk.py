"""Use gtfs_id as primary key for static GTFS tables.

Revision ID: 0004_gtfs_static_pk
Revises: 0003_gtfs_trips_stop_times
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0004_gtfs_static_pk"
down_revision: Union[str, None] = "0003_gtfs_trips_stop_times"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_gtfs_foreign_keys() -> None:
    op.execute("ALTER TABLE gtfs_trips DROP CONSTRAINT IF EXISTS gtfs_trips_route_id_fkey")
    op.execute("ALTER TABLE gtfs_trips DROP CONSTRAINT IF EXISTS gtfs_trips_start_stop_id_fkey")
    op.execute("ALTER TABLE gtfs_trips DROP CONSTRAINT IF EXISTS gtfs_trips_end_stop_id_fkey")
    op.execute("ALTER TABLE gtfs_stop_times DROP CONSTRAINT IF EXISTS gtfs_stop_times_stop_id_fkey")


def _restore_gtfs_foreign_keys() -> None:
    op.execute(
        "ALTER TABLE gtfs_trips ADD CONSTRAINT gtfs_trips_route_id_fkey "
        "FOREIGN KEY (route_id) REFERENCES gtfs_routes (gtfs_id)"
    )
    op.execute(
        "ALTER TABLE gtfs_trips ADD CONSTRAINT gtfs_trips_start_stop_id_fkey "
        "FOREIGN KEY (start_stop_id) REFERENCES gtfs_stops (gtfs_id)"
    )
    op.execute(
        "ALTER TABLE gtfs_trips ADD CONSTRAINT gtfs_trips_end_stop_id_fkey "
        "FOREIGN KEY (end_stop_id) REFERENCES gtfs_stops (gtfs_id)"
    )
    op.execute(
        "ALTER TABLE gtfs_stop_times ADD CONSTRAINT gtfs_stop_times_stop_id_fkey "
        "FOREIGN KEY (stop_id) REFERENCES gtfs_stops (gtfs_id)"
    )


def upgrade() -> None:
    _drop_gtfs_foreign_keys()

    op.execute("ALTER TABLE gtfs_agencies DROP CONSTRAINT IF EXISTS gtfs_agencies_pkey")
    op.execute("ALTER TABLE gtfs_agencies ADD CONSTRAINT gtfs_agencies_pkey PRIMARY KEY (gtfs_id)")
    op.execute("ALTER TABLE gtfs_agencies DROP CONSTRAINT IF EXISTS gtfs_agencies_gtfs_id_key")
    op.execute("ALTER TABLE gtfs_agencies DROP COLUMN IF EXISTS id")

    op.execute("ALTER TABLE gtfs_stops DROP CONSTRAINT IF EXISTS gtfs_stops_pkey")
    op.execute("ALTER TABLE gtfs_stops ADD CONSTRAINT gtfs_stops_pkey PRIMARY KEY (gtfs_id)")
    op.execute("ALTER TABLE gtfs_stops DROP CONSTRAINT IF EXISTS gtfs_stops_gtfs_id_key")
    op.execute("ALTER TABLE gtfs_stops DROP COLUMN IF EXISTS id")

    op.execute("ALTER TABLE gtfs_routes DROP CONSTRAINT IF EXISTS gtfs_routes_pkey")
    op.execute("ALTER TABLE gtfs_routes ADD CONSTRAINT gtfs_routes_pkey PRIMARY KEY (gtfs_id)")
    op.execute("ALTER TABLE gtfs_routes DROP CONSTRAINT IF EXISTS gtfs_routes_gtfs_id_key")
    op.execute("ALTER TABLE gtfs_routes DROP COLUMN IF EXISTS id")

    _restore_gtfs_foreign_keys()


def downgrade() -> None:
    _drop_gtfs_foreign_keys()

    op.execute("ALTER TABLE gtfs_agencies ADD COLUMN IF NOT EXISTS id SERIAL")
    op.execute("ALTER TABLE gtfs_agencies DROP CONSTRAINT IF EXISTS gtfs_agencies_pkey")
    op.execute("ALTER TABLE gtfs_agencies ADD CONSTRAINT gtfs_agencies_pkey PRIMARY KEY (id)")
    op.execute("ALTER TABLE gtfs_agencies ADD CONSTRAINT gtfs_agencies_gtfs_id_key UNIQUE (gtfs_id)")

    op.execute("ALTER TABLE gtfs_stops ADD COLUMN IF NOT EXISTS id SERIAL")
    op.execute("ALTER TABLE gtfs_stops DROP CONSTRAINT IF EXISTS gtfs_stops_pkey")
    op.execute("ALTER TABLE gtfs_stops ADD CONSTRAINT gtfs_stops_pkey PRIMARY KEY (id)")
    op.execute("ALTER TABLE gtfs_stops ADD CONSTRAINT gtfs_stops_gtfs_id_key UNIQUE (gtfs_id)")

    op.execute("ALTER TABLE gtfs_routes ADD COLUMN IF NOT EXISTS id SERIAL")
    op.execute("ALTER TABLE gtfs_routes DROP CONSTRAINT IF EXISTS gtfs_routes_pkey")
    op.execute("ALTER TABLE gtfs_routes ADD CONSTRAINT gtfs_routes_pkey PRIMARY KEY (id)")
    op.execute("ALTER TABLE gtfs_routes ADD CONSTRAINT gtfs_routes_gtfs_id_key UNIQUE (gtfs_id)")

    _restore_gtfs_foreign_keys()
