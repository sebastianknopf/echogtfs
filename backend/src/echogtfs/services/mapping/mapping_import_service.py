from io import BytesIO
from typing import BinaryIO

from echogtfs.services.database import RepositoryInterface
from echogtfs.services.mapping.mapping_service_error import MappingServiceError


class MappingImportService:
    """Imports data source mappings from CSV."""

    def __init__(self, max_size_bytes: int = 10 * 1024 * 1024):
        self._max_size_bytes = max_size_bytes

    async def import_csv_stream(
        self,
        repository: RepositoryInterface,
        source_id: int,
        entity_type: str,
        stream: BinaryIO,
        filename: str | None,
    ) -> int:
        """Import mappings from a CSV byte stream and return inserted row count."""
        source = await repository.get_data_source_by_id(source_id)

        if source is None:
            raise MappingServiceError(status_code=404, detail="Data source not found")

        if not filename or not filename.lower().endswith(".csv"):
            raise MappingServiceError(
                status_code=400,
                detail="Invalid file extension. Only .csv files are allowed.",
            )

        content = self._read_content_with_limit(stream)

        try:
            csv_text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MappingServiceError(
                status_code=400,
                detail="Invalid file encoding. Only UTF-8 encoded files are allowed.",
            ) from exc

        new_mappings = self._parse_mappings(csv_text)

        await repository.replace_data_source_mappings_for_entity_type(
            source_id,
            entity_type,
            new_mappings,
        )

        return len(new_mappings)

    def _read_content_with_limit(self, stream: BinaryIO) -> bytes:
        """Read stream content while enforcing maximum file size."""
        raw = self._to_seekable_stream(stream)
        raw.seek(0)
        content = raw.read(self._max_size_bytes + 1)

        if len(content) > self._max_size_bytes:
            raise MappingServiceError(
                status_code=413,
                detail="File too large. Maximum size is 10 MB.",
            )
        
        return content

    @staticmethod
    def _to_seekable_stream(stream: BinaryIO) -> BinaryIO:
        """Ensure stream is seekable for deterministic reads."""
        if stream.seekable():
            return stream
        
        return BytesIO(stream.read())

    @staticmethod
    def _parse_mappings(csv_text: str) -> list[dict[str, str]]:
        """Parse and validate semicolon-separated mapping rows."""
        lines = csv_text.strip().split("\n")
        if not lines:
            raise MappingServiceError(status_code=400, detail="CSV file is empty")

        mappings: list[dict[str, str]] = []
        for line_num, line in enumerate(lines, start=1):
            row = line.strip()
            if not row:
                continue

            parts = row.split(";")
            if len(parts) != 2:
                raise MappingServiceError(
                    status_code=400,
                    detail=f"Invalid CSV format at line {line_num}. Expected format: key;value",
                )

            key = parts[0].strip()
            value = parts[1].strip()

            if not key or not value:
                raise MappingServiceError(
                    status_code=400,
                    detail=f"Empty key or value at line {line_num}",
                )

            if len(key) > 128:
                raise MappingServiceError(
                    status_code=400,
                    detail=f"Key too long at line {line_num} (max 128 characters)",
                )

            if len(value) > 512:
                raise MappingServiceError(
                    status_code=400,
                    detail=f"Value too long at line {line_num} (max 512 characters)",
                )

            mappings.append({"key": key, "value": value})

        if not mappings:
            raise MappingServiceError(status_code=400, detail="No valid mappings found in CSV")

        return mappings
