"""
Application exception hierarchy for the WTech Landing Page.

All domain errors inherit from ``AppError``, which carries a machine-readable
``error_code``, an HTTP status code and a human-readable ``message``.  The API
layer maps these exceptions to the standardised ``ErrorResponse`` JSON schema.

Requirements: 9.5, 13.1
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all application-level errors.

    Attributes:
        error_code: Machine-readable identifier used in the ``ErrorResponse``
            JSON body (e.g. ``"PROMPT_TOO_SHORT"``).
        http_status: HTTP status code that the API layer should return.
        message: Human-readable description of the error.
    """

    error_code: str = "APP_ERROR"
    http_status: int = 500

    def __init__(self, message: str | None = None) -> None:
        self.message: str = message or self.__class__.__doc__ or self.error_code
        super().__init__(self.message)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"{self.__class__.__name__}("
            f"error_code={self.error_code!r}, "
            f"http_status={self.http_status}, "
            f"message={self.message!r})"
        )


# ---------------------------------------------------------------------------
# Input validation errors (4xx)
# ---------------------------------------------------------------------------


class PromptTooShortError(AppError):
    """O prompt deve ter no mÃ­nimo 10 caracteres."""

    error_code = "PROMPT_TOO_SHORT"
    http_status = 400


class PromptTooLongError(AppError):
    """O prompt deve ter no mÃ¡ximo 2000 caracteres."""

    error_code = "PROMPT_TOO_LONG"
    http_status = 400


class MalformedInputError(AppError):
    """A entrada fornecida estÃ¡ malformada ou incompleta."""

    error_code = "MALFORMED_INPUT"
    http_status = 422


class NicheConfidenceLowError(AppError):
    """NÃ£o foi possÃ­vel identificar o nicho com confianÃ§a suficiente apÃ³s 3 tentativas."""

    error_code = "NICHE_CONFIDENCE_LOW"
    http_status = 422


# ---------------------------------------------------------------------------
# Generation / processing errors (5xx)
# ---------------------------------------------------------------------------


class GenerationFailedError(AppError):
    """A geraÃ§Ã£o do conteÃºdo falhou apÃ³s o nÃºmero mÃ¡ximo de tentativas."""

    error_code = "GENERATION_FAILED"
    http_status = 500


class JSONSchemaValidationError(AppError):
    """O JSON gerado nÃ£o Ã© vÃ¡lido de acordo com o schema oficial de landing pages."""

    error_code = "JSON_SCHEMA_VALIDATION_ERROR"
    http_status = 500


class RenderError(AppError):
    """Ocorreu um erro durante a renderizaÃ§Ã£o HTML/CSS no sandbox isolado."""

    error_code = "RENDER_ERROR"
    http_status = 500


# ---------------------------------------------------------------------------
# Publication / infrastructure errors (5xx / 503 / 504)
# ---------------------------------------------------------------------------


class SSLProvisioningError(AppError):
    """Falha ao provisionar o certificado SSL/TLS para o subdomÃ­nio."""

    error_code = "SSL_PROVISIONING_ERROR"
    http_status = 503


class CDNIntegrationError(AppError):
    """Falha ao integrar com o CDN Cloudflare."""

    error_code = "CDN_INTEGRATION_ERROR"
    http_status = 503


class PublicationTimeoutError(AppError):
    """O processo de publicaÃ§Ã£o excedeu o tempo limite de 5 minutos."""

    error_code = "PUBLICATION_TIMEOUT"
    http_status = 504


# ---------------------------------------------------------------------------
# Security / authentication errors (4xx)
# ---------------------------------------------------------------------------


class InvalidJWTError(AppError):
    """Token JWT ausente, expirado ou com assinatura invÃ¡lida."""

    error_code = "INVALID_JWT"
    http_status = 401


class CSRFValidationError(AppError):
    """Token CSRF ausente ou invÃ¡lido."""

    error_code = "CSRF_VALIDATION_ERROR"
    http_status = 403


class RateLimitExceededError(AppError):
    """Limite de requisiÃ§Ãµes excedido. Tente novamente mais tarde."""

    error_code = "RATE_LIMIT_EXCEEDED"
    http_status = 429

