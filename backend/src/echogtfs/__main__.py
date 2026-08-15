from copy import deepcopy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from echogtfs.common.config import settings


def _build_logging_config() -> dict:
    logging_config = deepcopy(LOGGING_CONFIG)
    timestamp_format = "%Y-%m-%d %H:%M:%S"

    logging_config["formatters"]["default"].update(
        fmt="%(levelprefix)s %(asctime)s %(message)s",
        datefmt=timestamp_format,
    )
    logging_config["formatters"]["access"].update(
        fmt='%(levelprefix)s %(asctime)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        datefmt=timestamp_format,
    )

    return logging_config


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
        log_config=_build_logging_config(),
    )


if __name__ == "__main__":
    main()
