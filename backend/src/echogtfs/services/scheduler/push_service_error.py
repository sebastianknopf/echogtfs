class PushServiceError(Exception):
    """Domain error for the push API's datasource execution flow."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)

        self.status_code = status_code
        self.detail = detail
