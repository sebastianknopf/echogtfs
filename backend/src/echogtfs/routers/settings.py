from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, HTTPException, status

from echogtfs.enum.system import ExpiredRealtimeObjectPolicy
from echogtfs.services.database import get_realtime_repository, get_system_repository
from echogtfs.services.database.models import AppSetting
from echogtfs.services.security import get_security_service
from echogtfs.validation.schemas import AppSettings, PublicAppSettings
from echogtfs.common.security import CurrentSuperuser
from echogtfs.services.cleanup import CleanupService

try:
    from echogtfs._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"

router = APIRouter()


def _validate_minute_cron_expression(cron_expr: str) -> str:
    normalized = cron_expr.strip()
    if not normalized:
        return normalized

    if len(normalized.split()) != 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cron expression must be minute-based (5 fields)",
        )

    try:
        CronTrigger.from_crontab(normalized)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cron expression",
        ) from exc

    return normalized

DEFAULTS = AppSettings(
    color_primary="#008c99",
    color_secondary="#99cc04",
    app_title="echogtfs",
    app_language="de",
    gtfs_rt_service_alerts_path="realtime/service-alerts.pbf",
    gtfs_rt_trip_updates_path="realtime/trip-updates.pbf",
    gtfs_rt_vehicle_positions_path="realtime/vehicle-positions.pbf",
    gtfs_rt_username="",
    gtfs_rt_password="",
    cleanup_cron="*/10 * * * *",
    cleanup_expired_policy=ExpiredRealtimeObjectPolicy.DEACTIVATE,
    cleanup_delete_after_days=-1,
)


async def _load() -> AppSettings:
    repository = get_system_repository()
    rows = await repository.get_all_app_settings()
    
    # Initialize defaults in database if not present
    if AppSetting.KEY_GTFS_RT_SERVICE_ALERTS_PATH not in rows:
        await repository.set_app_setting(
            AppSetting.KEY_GTFS_RT_SERVICE_ALERTS_PATH,
            DEFAULTS.gtfs_rt_service_alerts_path,
        )
        rows[AppSetting.KEY_GTFS_RT_SERVICE_ALERTS_PATH] = DEFAULTS.gtfs_rt_service_alerts_path
    if AppSetting.KEY_GTFS_RT_TRIP_UPDATES_PATH not in rows:
        await repository.set_app_setting(
            AppSetting.KEY_GTFS_RT_TRIP_UPDATES_PATH,
            DEFAULTS.gtfs_rt_trip_updates_path,
        )
        rows[AppSetting.KEY_GTFS_RT_TRIP_UPDATES_PATH] = DEFAULTS.gtfs_rt_trip_updates_path
    if AppSetting.KEY_GTFS_RT_VEHICLE_POSITIONS_PATH not in rows:
        await repository.set_app_setting(
            AppSetting.KEY_GTFS_RT_VEHICLE_POSITIONS_PATH,
            DEFAULTS.gtfs_rt_vehicle_positions_path,
        )
        rows[AppSetting.KEY_GTFS_RT_VEHICLE_POSITIONS_PATH] = DEFAULTS.gtfs_rt_vehicle_positions_path
    if AppSetting.KEY_GTFS_RT_USERNAME not in rows:
        await repository.set_app_setting(AppSetting.KEY_GTFS_RT_USERNAME, DEFAULTS.gtfs_rt_username)
        rows[AppSetting.KEY_GTFS_RT_USERNAME] = DEFAULTS.gtfs_rt_username
    if AppSetting.KEY_GTFS_RT_PASSWORD not in rows:
        await repository.set_app_setting(AppSetting.KEY_GTFS_RT_PASSWORD, DEFAULTS.gtfs_rt_password)
        rows[AppSetting.KEY_GTFS_RT_PASSWORD] = DEFAULTS.gtfs_rt_password
    if AppSetting.KEY_CLEANUP_CRON not in rows:
        await repository.set_app_setting(AppSetting.KEY_CLEANUP_CRON, DEFAULTS.cleanup_cron)
        rows[AppSetting.KEY_CLEANUP_CRON] = DEFAULTS.cleanup_cron
    if AppSetting.KEY_CLEANUP_EXPIRED_POLICY not in rows:
        await repository.set_app_setting(AppSetting.KEY_CLEANUP_EXPIRED_POLICY, DEFAULTS.cleanup_expired_policy.value)
        rows[AppSetting.KEY_CLEANUP_EXPIRED_POLICY] = DEFAULTS.cleanup_expired_policy.value
    if AppSetting.KEY_CLEANUP_DELETE_AFTER_DAYS not in rows:
        await repository.set_app_setting(AppSetting.KEY_CLEANUP_DELETE_AFTER_DAYS, str(DEFAULTS.cleanup_delete_after_days))
        rows[AppSetting.KEY_CLEANUP_DELETE_AFTER_DAYS] = str(DEFAULTS.cleanup_delete_after_days)
    
    return AppSettings(
        color_primary    = rows.get(AppSetting.KEY_COLOR_PRIMARY, DEFAULTS.color_primary),
        color_secondary  = rows.get(AppSetting.KEY_COLOR_SECONDARY, DEFAULTS.color_secondary),
        app_title        = rows.get(AppSetting.KEY_APP_TITLE, DEFAULTS.app_title),
        app_language     = rows.get(AppSetting.KEY_APP_LANGUAGE, DEFAULTS.app_language),
        gtfs_rt_service_alerts_path = rows.get(
            AppSetting.KEY_GTFS_RT_SERVICE_ALERTS_PATH,
            DEFAULTS.gtfs_rt_service_alerts_path,
        ),
        gtfs_rt_trip_updates_path = rows.get(
            AppSetting.KEY_GTFS_RT_TRIP_UPDATES_PATH,
            DEFAULTS.gtfs_rt_trip_updates_path,
        ),
        gtfs_rt_vehicle_positions_path = rows.get(
            AppSetting.KEY_GTFS_RT_VEHICLE_POSITIONS_PATH,
            DEFAULTS.gtfs_rt_vehicle_positions_path,
        ),
        gtfs_rt_username = rows.get(AppSetting.KEY_GTFS_RT_USERNAME, DEFAULTS.gtfs_rt_username),
        gtfs_rt_password = rows.get(AppSetting.KEY_GTFS_RT_PASSWORD, DEFAULTS.gtfs_rt_password),
        cleanup_cron     = rows.get(AppSetting.KEY_CLEANUP_CRON, DEFAULTS.cleanup_cron),
        cleanup_expired_policy = ExpiredRealtimeObjectPolicy(
            rows.get(AppSetting.KEY_CLEANUP_EXPIRED_POLICY, DEFAULTS.cleanup_expired_policy.value)
        ),
        cleanup_delete_after_days = int(
            rows.get(AppSetting.KEY_CLEANUP_DELETE_AFTER_DAYS, str(DEFAULTS.cleanup_delete_after_days))
        ),
    )

@router.get("/app", response_model=PublicAppSettings)
async def get_public_app_settings() -> PublicAppSettings:
    """Public: returns theme and language settings (no authentication required)."""
    settings = await _load()
    return PublicAppSettings(
        color_primary=settings.color_primary,
        color_secondary=settings.color_secondary,
        app_title=settings.app_title,
        app_language=settings.app_language,
        app_version=__version__,
    )


@router.get("/", response_model=AppSettings)
async def get_settings(_: CurrentSuperuser) -> AppSettings:
    """Admin only: returns all app settings including GTFS-RT configuration."""
    return await _load()


@router.put("/", response_model=AppSettings)
async def update_settings(
    payload: AppSettings, _: CurrentSuperuser
) -> AppSettings:
    """Admin only: persists app settings."""
    repository = get_system_repository()
    cleanup_cron = _validate_minute_cron_expression(payload.cleanup_cron)

    await repository.set_app_setting(AppSetting.KEY_COLOR_PRIMARY, payload.color_primary)
    await repository.set_app_setting(AppSetting.KEY_COLOR_SECONDARY, payload.color_secondary)
    await repository.set_app_setting(AppSetting.KEY_APP_TITLE, payload.app_title)
    await repository.set_app_setting(AppSetting.KEY_APP_LANGUAGE, payload.app_language)
    await repository.set_app_setting(
        AppSetting.KEY_GTFS_RT_SERVICE_ALERTS_PATH,
        payload.gtfs_rt_service_alerts_path,
    )
    await repository.set_app_setting(
        AppSetting.KEY_GTFS_RT_TRIP_UPDATES_PATH,
        payload.gtfs_rt_trip_updates_path,
    )
    await repository.set_app_setting(
        AppSetting.KEY_GTFS_RT_VEHICLE_POSITIONS_PATH,
        payload.gtfs_rt_vehicle_positions_path,
    )
    
    # Cleanup settings
    await repository.set_app_setting(AppSetting.KEY_CLEANUP_CRON, cleanup_cron)
    await repository.set_app_setting(AppSetting.KEY_CLEANUP_EXPIRED_POLICY, payload.cleanup_expired_policy.value)
    await repository.set_app_setting(AppSetting.KEY_CLEANUP_DELETE_AFTER_DAYS, str(payload.cleanup_delete_after_days))
    
    # Basic Auth handling: Only clear both username and password if BOTH are empty/None
    # Otherwise, update individually
    username_is_empty = not payload.gtfs_rt_username
    password_is_empty = payload.gtfs_rt_password == "" or payload.gtfs_rt_password is None
    
    if username_is_empty and password_is_empty:
        # Both empty/None → disable Basic Auth completely
        await repository.set_app_setting(AppSetting.KEY_GTFS_RT_USERNAME, "")
        await repository.set_app_setting(AppSetting.KEY_GTFS_RT_PASSWORD, "")
    else:
        # Update username
        await repository.set_app_setting(AppSetting.KEY_GTFS_RT_USERNAME, payload.gtfs_rt_username)
        
        # Update password only if explicitly provided (not None)
        if payload.gtfs_rt_password is not None:
            if payload.gtfs_rt_password:
                # Hash and store new password
                await repository.set_app_setting(
                    AppSetting.KEY_GTFS_RT_PASSWORD,
                    get_security_service().hash_password(payload.gtfs_rt_password),
                )
            else:
                # Empty string with username present → keep existing password unchanged
                pass
        # else: None means keep existing password
    
    # Re-schedule cleanup job with new settings
    await CleanupService(repository, get_realtime_repository()).schedule_from_settings()
    
    # Return current settings (reload to get actual stored password status)
    return await _load()
