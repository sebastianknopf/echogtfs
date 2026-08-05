from __future__ import annotations

from datetime import UTC, datetime
import io
import json
import zipfile

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.database.models import (
    AppSetting,
    DataSource,
    DataSourceEnrichment,
    DataSourceMapping,
    User,
)
from echogtfs.services.scheduler import get_datasource_scheduler_service
from echogtfs.services.systemcopy.intf_systemcopy import SystemCopyInterface


class SystemCopyService(SystemCopyInterface):
    """Export and import selected system tables as JSON files in a ZIP archive."""

    FORMAT_VERSION = 1

    _ERR_INVALID_INPUT = "error.invalid_input"
    _ERR_SERVER_ERROR = "error.server_error"

    DOMAIN_SYSTEM_SETTINGS = "system_settings"
    DOMAIN_GTFS_SETTINGS = "gtfs_settings"
    DOMAIN_USERS = "users"
    DOMAIN_DATASOURCES = "datasources"

    FILE_SYSTEM_SETTINGS = "sys_app_settings.json"
    FILE_GTFS_SETTINGS = "gtfs_settings.json"
    FILE_USERS = "sys_users.json"
    FILE_DATASOURCES = "sys_data_sources.json"
    FILE_MAPPINGS = "sys_data_source_mappings.json"
    FILE_ENRICHMENTS = "sys_data_source_enrichments.json"

    _GTFS_KEYS = {
        AppSetting.KEY_GTFS_FEED_URL,
        AppSetting.KEY_GTFS_CRON,
        AppSetting.KEY_GTFS_IMPORT_STATUS,
        AppSetting.KEY_GTFS_IMPORT_TIME,
        AppSetting.KEY_GTFS_IMPORT_MESSAGE,
    }

    _SYSTEM_KEYS = (
        AppSetting.KEY_COLOR_PRIMARY,
        AppSetting.KEY_COLOR_SECONDARY,
        AppSetting.KEY_APP_TITLE,
        AppSetting.KEY_APP_LANGUAGE,
        AppSetting.KEY_GTFS_RT_SERVICE_ALERTS_PATH,
        AppSetting.KEY_GTFS_RT_TRIP_UPDATES_PATH,
        AppSetting.KEY_GTFS_RT_VEHICLE_POSITIONS_PATH,
        AppSetting.KEY_GTFS_RT_USERNAME,
        AppSetting.KEY_GTFS_RT_PASSWORD,
        AppSetting.KEY_CLEANUP_CRON,
        AppSetting.KEY_CLEANUP_EXPIRED_POLICY,
        AppSetting.KEY_CLEANUP_DELETE_AFTER_DAYS,
    )

    def __init__(self, repository: SystemRepositoryInterface | None = None):
        self._repository = repository

    async def export_zip(
        self,
        selection: dict[str, bool],
    ) -> bytes:
        if self._repository is None:
            raise ValueError(self._ERR_SERVER_ERROR)
        self._validate_selection(selection)

        payload_files: dict[str, list[dict[str, object]]] = {}
        selected_domains = self._normalized_selection(selection)

        app_settings = await self._repository.list_app_settings()
        users = await self._repository.list_users()
        data_sources = await self._repository.list_data_sources()
        mappings = await self._repository.list_all_data_source_mappings()
        enrichments = await self._repository.list_all_data_source_enrichments()

        if selected_domains[self.DOMAIN_SYSTEM_SETTINGS]:
            payload_files[self.FILE_SYSTEM_SETTINGS] = self._serialize_app_settings(app_settings, keys=set(self._SYSTEM_KEYS))

        if selected_domains[self.DOMAIN_GTFS_SETTINGS]:
            payload_files[self.FILE_GTFS_SETTINGS] = self._serialize_app_settings(app_settings, keys=self._GTFS_KEYS)

        if selected_domains[self.DOMAIN_USERS]:
            payload_files[self.FILE_USERS] = self._serialize_users(users)

        if selected_domains[self.DOMAIN_DATASOURCES]:
            payload_files[self.FILE_DATASOURCES] = self._serialize_data_sources(data_sources)
            payload_files[self.FILE_MAPPINGS] = self._serialize_data_source_mappings(mappings)
            payload_files[self.FILE_ENRICHMENTS] = self._serialize_data_source_enrichments(enrichments)

        manifest = {
            "format_version": self.FORMAT_VERSION,
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "selected_domains": selected_domains,
            "files": list(payload_files.keys()),
            "row_counts": {name: len(rows) for name, rows in payload_files.items()},
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
            for file_name, rows in payload_files.items():
                archive.writestr(file_name, json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8"))

        return buffer.getvalue()

    async def import_zip(
        self,
        archive_bytes: bytes,
    ) -> dict[str, object]:
        if self._repository is None:
            raise ValueError(self._ERR_SERVER_ERROR)
        manifest, files = self._read_archive(archive_bytes)

        summary: dict[str, object] = {
            "format_version": manifest.get("format_version", 0),
            "imported_at_utc": datetime.now(UTC).isoformat(),
            "domains": {
                self.DOMAIN_SYSTEM_SETTINGS: {"created": 0, "updated": 0, "remapped": 0},
                self.DOMAIN_GTFS_SETTINGS: {"created": 0, "updated": 0, "remapped": 0},
                self.DOMAIN_USERS: {"created": 0, "updated": 0, "remapped": 0},
                self.DOMAIN_DATASOURCES: {"created": 0, "updated": 0, "remapped": 0},
            },
        }
        datasource_imported = False

        async with self._repository.get_session() as db:
            if self.FILE_SYSTEM_SETTINGS in files:
                rows = files.get(self.FILE_SYSTEM_SETTINGS, [])
                created, updated = await self._import_app_settings(db, rows)
                summary["domains"][self.DOMAIN_SYSTEM_SETTINGS]["created"] = created
                summary["domains"][self.DOMAIN_SYSTEM_SETTINGS]["updated"] = updated

            if self.FILE_GTFS_SETTINGS in files:
                rows = files.get(self.FILE_GTFS_SETTINGS, [])
                created, updated = await self._import_app_settings(db, rows)
                summary["domains"][self.DOMAIN_GTFS_SETTINGS]["created"] = created
                summary["domains"][self.DOMAIN_GTFS_SETTINGS]["updated"] = updated

            if self.FILE_USERS in files:
                users = files.get(self.FILE_USERS, [])
                created, updated, remapped = await self._import_users(db, users)
                summary["domains"][self.DOMAIN_USERS]["created"] = created
                summary["domains"][self.DOMAIN_USERS]["updated"] = updated
                summary["domains"][self.DOMAIN_USERS]["remapped"] = remapped

            if self.FILE_DATASOURCES in files:
                source_rows = files.get(self.FILE_DATASOURCES, [])
                mapping_rows = files.get(self.FILE_MAPPINGS, [])
                enrichment_rows = files.get(self.FILE_ENRICHMENTS, [])
                created, updated, remapped = await self._import_data_sources(db, source_rows, mapping_rows, enrichment_rows)
                summary["domains"][self.DOMAIN_DATASOURCES]["created"] = created
                summary["domains"][self.DOMAIN_DATASOURCES]["updated"] = updated
                summary["domains"][self.DOMAIN_DATASOURCES]["remapped"] = remapped
                datasource_imported = True

            await db.commit()
            await self._sync_sequence_if_postgresql(db, "sys_users")
            await self._sync_sequence_if_postgresql(db, "sys_data_sources")

        if datasource_imported:
            await get_datasource_scheduler_service().schedule_all_data_sources()

        return summary

    @staticmethod
    def _normalized_selection(selection: dict[str, bool]) -> dict[str, bool]:
        return {
            SystemCopyService.DOMAIN_SYSTEM_SETTINGS: bool(selection.get(SystemCopyService.DOMAIN_SYSTEM_SETTINGS)),
            SystemCopyService.DOMAIN_GTFS_SETTINGS: bool(selection.get(SystemCopyService.DOMAIN_GTFS_SETTINGS)),
            SystemCopyService.DOMAIN_USERS: bool(selection.get(SystemCopyService.DOMAIN_USERS)),
            SystemCopyService.DOMAIN_DATASOURCES: bool(selection.get(SystemCopyService.DOMAIN_DATASOURCES)),
        }

    @staticmethod
    def _validate_selection(selection: dict[str, bool]) -> None:
        normalized = SystemCopyService._normalized_selection(selection)
        if not any(normalized.values()):
            raise ValueError(SystemCopyService._ERR_INVALID_INPUT)

    def _read_archive(self, archive_bytes: bytes) -> tuple[dict[str, object], dict[str, list[dict[str, object]]]]:
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes), mode="r") as archive:
                names = set(archive.namelist())
                if "manifest.json" not in names:
                    raise ValueError(SystemCopyService._ERR_INVALID_INPUT)

                manifest_raw = archive.read("manifest.json")
                manifest = json.loads(manifest_raw.decode("utf-8"))

                format_version = int(manifest.get("format_version", 0))
                if format_version != self.FORMAT_VERSION:
                    raise ValueError(SystemCopyService._ERR_INVALID_INPUT)

                files: dict[str, list[dict[str, object]]] = {}

                known_files = {
                    self.FILE_SYSTEM_SETTINGS,
                    self.FILE_GTFS_SETTINGS,
                    self.FILE_USERS,
                    self.FILE_DATASOURCES,
                    self.FILE_MAPPINGS,
                    self.FILE_ENRICHMENTS,
                }

                for file_name in names:
                    if file_name not in known_files:
                        continue
                    payload = json.loads(archive.read(file_name).decode("utf-8"))
                    if not isinstance(payload, list):
                        raise ValueError(SystemCopyService._ERR_INVALID_INPUT)
                    files[file_name] = payload

                # Datasource domain is only valid when parent table is present.
                if self.FILE_DATASOURCES not in files:
                    files.pop(self.FILE_MAPPINGS, None)
                    files.pop(self.FILE_ENRICHMENTS, None)

                return manifest, files
        except zipfile.BadZipFile as exc:
            raise ValueError(self._ERR_INVALID_INPUT) from exc
        except json.JSONDecodeError as exc:
            raise ValueError(self._ERR_INVALID_INPUT) from exc

    def _serialize_app_settings(self, rows: list[AppSetting], *, keys: set[str]) -> list[dict[str, object]]:
        return [
            {
                "key": row.key,
                "value": row.value,
            }
            for row in rows
            if row.key in keys
        ]

    def _serialize_users(self, users: list[User]) -> list[dict[str, object]]:
        return [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "hashed_password": user.hashed_password,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "is_technical_contact": user.is_technical_contact,
                "created_at": self._to_iso_datetime(user.created_at),
            }
            for user in users
        ]

    def _serialize_data_sources(self, sources: list[DataSource]) -> list[dict[str, object]]:
        return [
            {
                "id": source.id,
                "name": source.name,
                "type": source.type,
                "config": source.config,
                "cron": source.cron,
                "is_active": source.is_active,
                "invalid_reference_policy": self._to_enum_value(source.invalid_reference_policy),
                # Last execution timestamp is intentionally reset for system copy exports.
                "last_run_at": None,
                "created_at": self._to_iso_datetime(source.created_at),
                "updated_at": self._to_iso_datetime(source.updated_at),
            }
            for source in sources
        ]

    def _serialize_data_source_mappings(self, mappings: list[DataSourceMapping]) -> list[dict[str, object]]:
        return [
            {
                "id": mapping.id,
                "data_source_id": mapping.data_source_id,
                "entity_type": mapping.entity_type,
                "key": mapping.key,
                "value": mapping.value,
            }
            for mapping in mappings
        ]

    def _serialize_data_source_enrichments(self, enrichments: list[DataSourceEnrichment]) -> list[dict[str, object]]:
        return [
            {
                "id": enrichment.id,
                "data_source_id": enrichment.data_source_id,
                "enrichment_type": self._to_enum_value(enrichment.enrichment_type),
                "source_field": self._to_enum_value(enrichment.source_field),
                "key": enrichment.key,
                "value": enrichment.value,
                "sort_order": enrichment.sort_order,
            }
            for enrichment in enrichments
        ]

    async def _import_app_settings(self, db: AsyncSession, rows: list[dict[str, object]]) -> tuple[int, int]:
        created = 0
        updated = 0
        for row in rows:
            key = str(row.get("key", "")).strip()
            if not key:
                continue
            value = str(row.get("value", ""))
            setting = await db.get(AppSetting, key)
            if setting is None:
                db.add(AppSetting(key=key, value=value))
                created += 1
            else:
                setting.value = value
                updated += 1
        return created, updated

    async def _import_users(self, db: AsyncSession, rows: list[dict[str, object]]) -> tuple[int, int, int]:
        result = await db.execute(select(User))
        existing_users = list(result.scalars().all())

        by_username = {u.username: u for u in existing_users}
        by_id = {u.id: u for u in existing_users}
        used_ids = set(by_id.keys())
        used_emails = {u.email: u for u in existing_users}

        created = 0
        updated = 0
        remapped = 0

        for row in rows:
            username = str(row.get("username", "")).strip()
            if not username:
                continue

            existing = by_username.get(username)
            if existing is not None:
                email = str(row.get("email", existing.email)).strip()
                email_owner = used_emails.get(email)
                if email and email_owner is not None and email_owner.id != existing.id:
                    raise ValueError(f"Cannot update user '{username}': email '{email}' already exists")

                if email_owner is not None and email_owner.id == existing.id and email != existing.email:
                    used_emails.pop(existing.email, None)
                    used_emails[email] = existing

                existing.email = email
                existing.hashed_password = str(row.get("hashed_password", existing.hashed_password))
                existing.is_active = bool(row.get("is_active", existing.is_active))
                existing.is_superuser = bool(row.get("is_superuser", existing.is_superuser))
                existing.is_technical_contact = bool(row.get("is_technical_contact", existing.is_technical_contact))
                updated += 1
                continue

            imported_id = int(row.get("id", 0))
            target_id = imported_id
            if imported_id in used_ids:
                target_id = self._next_free_id(used_ids)
                remapped += 1

            email = str(row.get("email", "")).strip()
            if not email:
                raise ValueError(f"Cannot create user '{username}': missing email")
            email_owner = used_emails.get(email)
            if email_owner is not None:
                raise ValueError(f"Cannot create user '{username}': email '{email}' already exists")

            user = User(
                id=target_id,
                username=username,
                email=email,
                hashed_password=str(row.get("hashed_password", "")),
                is_active=bool(row.get("is_active", True)),
                is_superuser=bool(row.get("is_superuser", False)),
                is_technical_contact=bool(row.get("is_technical_contact", False)),
            )
            created_at = self._parse_datetime(row.get("created_at"))
            if created_at is not None:
                user.created_at = created_at

            db.add(user)
            by_username[user.username] = user
            by_id[user.id] = user
            used_ids.add(user.id)
            used_emails[user.email] = user
            created += 1

        return created, updated, remapped

    async def _import_data_sources(
        self,
        db: AsyncSession,
        source_rows: list[dict[str, object]],
        mapping_rows: list[dict[str, object]],
        enrichment_rows: list[dict[str, object]],
    ) -> tuple[int, int, int]:
        result = await db.execute(select(DataSource))
        existing_sources = list(result.scalars().all())

        by_name = {s.name: s for s in existing_sources}
        by_id = {s.id: s for s in existing_sources}
        used_ids = set(by_id.keys())

        source_id_map: dict[int, int] = {}
        created = 0
        updated = 0
        remapped = 0

        for row in source_rows:
            imported_id = int(row.get("id", 0))
            name = str(row.get("name", "")).strip()
            if not name:
                continue

            existing = by_name.get(name)
            if existing is not None:
                existing.type = str(row.get("type", existing.type))
                existing.config = str(row.get("config", existing.config))
                existing.cron = self._none_or_str(row.get("cron"))
                existing.is_active = bool(row.get("is_active", existing.is_active))
                existing.invalid_reference_policy = str(
                    row.get("invalid_reference_policy", self._to_enum_value(existing.invalid_reference_policy))
                )
                existing.last_run_at = self._parse_datetime(row.get("last_run_at"))
                source_id_map[imported_id] = existing.id
                updated += 1
                continue

            target_id = imported_id
            if target_id in used_ids:
                target_id = self._next_free_id(used_ids)
                remapped += 1

            source = DataSource(
                id=target_id,
                name=name,
                type=str(row.get("type", "")),
                config=str(row.get("config", "{}")),
                cron=self._none_or_str(row.get("cron")),
                is_active=bool(row.get("is_active", True)),
                invalid_reference_policy=str(row.get("invalid_reference_policy", "not_specified")),
                last_run_at=self._parse_datetime(row.get("last_run_at")),
            )

            created_at = self._parse_datetime(row.get("created_at"))
            if created_at is not None:
                source.created_at = created_at
            updated_at = self._parse_datetime(row.get("updated_at"))
            if updated_at is not None:
                source.updated_at = updated_at

            db.add(source)
            by_name[source.name] = source
            by_id[source.id] = source
            used_ids.add(source.id)
            source_id_map[imported_id] = source.id
            created += 1

        mapping_created, mapping_updated = await self._import_data_source_mappings(db, source_id_map, mapping_rows)
        enrichment_created, enrichment_updated = await self._import_data_source_enrichments(db, source_id_map, enrichment_rows)

        # Include mapping/enrichment changes in datasource domain update counts.
        updated += mapping_updated + enrichment_updated
        created += mapping_created + enrichment_created
        return created, updated, remapped

    async def _import_data_source_mappings(
        self,
        db: AsyncSession,
        source_id_map: dict[int, int],
        rows: list[dict[str, object]],
    ) -> tuple[int, int]:
        result = await db.execute(select(DataSourceMapping))
        existing_rows = list(result.scalars().all())
        existing_by_key = {
            (row.data_source_id, row.entity_type, row.key): row
            for row in existing_rows
        }

        created = 0
        updated = 0
        for row in rows:
            imported_source_id = int(row.get("data_source_id", 0))
            source_id = source_id_map.get(imported_source_id)
            if source_id is None:
                continue

            entity_type = str(row.get("entity_type", "")).strip()
            key = str(row.get("key", "")).strip()
            if not entity_type or not key:
                continue

            composite_key = (source_id, entity_type, key)
            existing = existing_by_key.get(composite_key)
            value = str(row.get("value", ""))

            if existing is None:
                item = DataSourceMapping(
                    data_source_id=source_id,
                    entity_type=entity_type,
                    key=key,
                    value=value,
                )
                db.add(item)
                existing_by_key[composite_key] = item
                created += 1
            else:
                existing.value = value
                updated += 1

        return created, updated

    async def _import_data_source_enrichments(
        self,
        db: AsyncSession,
        source_id_map: dict[int, int],
        rows: list[dict[str, object]],
    ) -> tuple[int, int]:
        result = await db.execute(select(DataSourceEnrichment))
        existing_rows = list(result.scalars().all())
        existing_by_key = {
            (row.data_source_id, row.enrichment_type, row.source_field, row.key, row.sort_order): row
            for row in existing_rows
        }

        created = 0
        updated = 0
        for row in rows:
            imported_source_id = int(row.get("data_source_id", 0))
            source_id = source_id_map.get(imported_source_id)
            if source_id is None:
                continue

            enrichment_type = str(row.get("enrichment_type", "")).strip()
            source_field = str(row.get("source_field", "")).strip()
            key = str(row.get("key", "")).strip()
            if not enrichment_type or not source_field or not key:
                continue

            sort_order = int(row.get("sort_order", 0))
            composite_key = (source_id, enrichment_type, source_field, key, sort_order)
            existing = existing_by_key.get(composite_key)
            value = str(row.get("value", ""))

            if existing is None:
                item = DataSourceEnrichment(
                    data_source_id=source_id,
                    enrichment_type=enrichment_type,
                    source_field=source_field,
                    key=key,
                    value=value,
                    sort_order=sort_order,
                )
                db.add(item)
                existing_by_key[composite_key] = item
                created += 1
            else:
                existing.value = value
                updated += 1

        return created, updated

    @staticmethod
    def _next_free_id(used_ids: set[int]) -> int:
        if not used_ids:
            return 1
        candidate = max(used_ids) + 1
        while candidate in used_ids:
            candidate += 1
        return candidate

    async def _sync_sequence_if_postgresql(self, db: AsyncSession, table_name: str) -> None:
        bind = db.get_bind()
        if bind is None or bind.dialect.name != "postgresql":
            return

        await db.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table_name}), 1), true)"
            )
        )

    @staticmethod
    def _to_iso_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    @staticmethod
    def _to_enum_value(value: object) -> str:
        if hasattr(value, "value"):
            return str(getattr(value, "value"))
        return str(value)

    @staticmethod
    def _none_or_str(value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None
