from collections.abc import Iterator

from echogtfs.services.database import RepositoryInterface
from echogtfs.services.mapping.mapping_service_error import MappingServiceError


class MappingExportService:
    """Exports data source mappings in CSV format."""

    async def export_csv_stream(
        self,
        repository: RepositoryInterface,
        source_id: int,
        entity_type: str,
    ) -> Iterator[bytes]:
        """Return a byte stream of semicolon-separated CSV rows for one source/entity type."""
        source = await repository.get_data_source_by_id(source_id)
        
        if source is None:
            raise MappingServiceError(status_code=404, detail="Data source not found")

        mappings = await repository.list_data_source_mappings(source_id, entity_type)

        def _stream_rows() -> Iterator[bytes]:
            for mapping in mappings:
                key = mapping.key.replace(";", ",")
                value = mapping.value.replace(";", ",")
                yield f"{key};{value}\n".encode("utf-8")

        return _stream_rows()
