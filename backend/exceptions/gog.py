"""GOG-specific exceptions."""

from fastapi import HTTPException, status


class GogNotAuthenticatedException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GOG account not authenticated. Please log in via Settings.",
        )


class GogTokenExpiredException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="GOG token expired and refresh failed.",
        )


class GogGameNotFoundException(HTTPException):
    def __init__(self, gog_id: int) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"GOG game {gog_id} not found",
        )


class GogDownloadException(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"GOG download error: {detail}",
        )
