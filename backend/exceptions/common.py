"""Common / shared exceptions."""

from fastapi import HTTPException, status


class NotFoundException(HTTPException):
    def __init__(self, entity: str, identifier: str | int) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity} '{identifier}' not found",
        )


class AlreadyExistsException(HTTPException):
    def __init__(self, entity: str, identifier: str | int) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{entity} '{identifier}' already exists",
        )


class ValidationException(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class ConfigurationException(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Configuration error: {detail}",
        )
