class ContractError(Exception):
    """Raised inside /api/v2/ handlers; converted to the standard error envelope."""

    def __init__(
        self,
        http_status: int,
        code: str,
        message: str,
        errors=None,
        retryable: bool = False,
        data=None,
    ):
        self.http_status = http_status
        self.code = code
        self.message = message
        self.errors = errors or {}
        self.retryable = retryable
        self.data = data
        super().__init__(message)
