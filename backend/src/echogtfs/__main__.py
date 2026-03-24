import uvicorn

from echogtfs.config import settings


def main() -> None:
    uvicorn.run(
        "echogtfs.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
