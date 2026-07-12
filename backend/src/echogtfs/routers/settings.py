from fastapi import APIRouter

from echogtfs.enum.system import ExpiredAlertPolicy
from echogtfs.services.database import get_repository
from echogtfs.services.database.models import AppSetting
from echogtfs.schemas import AppSettings, PublicAppSettings
from echogtfs.security import CurrentSuperuser, hash_password
from echogtfs.services.cleanup import schedule_cleanup_from_settings

try:
    from echogtfs._version import version as __version__
except ImportError:
    __version__ = "0.0.0+unknown"

router = APIRouter()

DEFAULTS = AppSettings(
    color_primary="#008c99",
    color_secondary="#99cc04",
    app_title="echogtfs",
    app_language="de",
    gtfs_rt_path="realtime/service-alerts.pbf",
    gtfs_rt_username="",
    gtfs_rt_password="",
    cleanup_cron="*/10 * * * *",
    cleanup_expired_policy=ExpiredAlertPolicy.DEACTIVATE,
    cleanup_delete_after_days=-1,
)


async def _load() -> AppSettings:
    repository = get_repository()
    rows = await repository.get_all_app_settings()
    
    # Initialize defaults in database if not present
    if AppSetting.KEY_GTFS_RT_PATH not in rows:
        await repository.set_app_setting(AppSetting.KEY_GTFS_RT_PATH, DEFAULTS.gtfs_rt_path)
        rows[AppSetting.KEY_GTFS_RT_PATH] = DEFAULTS.gtfs_rt_path
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
        gtfs_rt_path     = rows.get(AppSetting.KEY_GTFS_RT_PATH, DEFAULTS.gtfs_rt_path),
        gtfs_rt_username = rows.get(AppSetting.KEY_GTFS_RT_USERNAME, DEFAULTS.gtfs_rt_username),
        gtfs_rt_password = rows.get(AppSetting.KEY_GTFS_RT_PASSWORD, DEFAULTS.gtfs_rt_password),
        cleanup_cron     = rows.get(AppSetting.KEY_CLEANUP_CRON, DEFAULTS.cleanup_cron),
        cleanup_expired_policy = ExpiredAlertPolicy(
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
    repository = get_repository()

    await repository.set_app_setting(AppSetting.KEY_COLOR_PRIMARY, payload.color_primary)
    await repository.set_app_setting(AppSetting.KEY_COLOR_SECONDARY, payload.color_secondary)
    await repository.set_app_setting(AppSetting.KEY_APP_TITLE, payload.app_title)
    await repository.set_app_setting(AppSetting.KEY_APP_LANGUAGE, payload.app_language)
    await repository.set_app_setting(AppSetting.KEY_GTFS_RT_PATH, payload.gtfs_rt_path)
    
    # Cleanup settings
    await repository.set_app_setting(AppSetting.KEY_CLEANUP_CRON, payload.cleanup_cron)
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
                await repository.set_app_setting(AppSetting.KEY_GTFS_RT_PASSWORD, hash_password(payload.gtfs_rt_password))
            else:
                # Empty string with username present → keep existing password unchanged
                pass
        # else: None means keep existing password
    
    # Re-schedule cleanup job with new settings
    await schedule_cleanup_from_settings()
    
    # Return current settings (reload to get actual stored password status)
    return await _load()
