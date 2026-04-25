"""Authentication / authorization exceptions."""

from fastapi import HTTPException, status


class NotAuthenticatedException(HTTPException):
    def __init__(self, detail: str = "Not authenticated") -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class InsufficientScopesException(HTTPException):
    def __init__(self, missing: list[str] | None = None) -> None:
        detail = "Insufficient permissions"
        if missing:
            detail = f"Missing scopes: {', '.join(missing)}"
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class InvalidCredentialsException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )


class UserDisabledException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
