import uvicorn

from echogtfs.common.config import settings


def main() -> None:
    # Keep standard Uvicorn INFO logs by default; enable full debug output when DEBUG=true.
    uvicorn_log_level = "debug" if settings.debug else "info"

    uvicorn.run(
        "echogtfs.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=uvicorn_log_level,
        access_log=True,
    )


if __name__ == "__main__":
    main()
