"""Provider errors raised by core-owned integrations.

Adapters never leak upstream bodies, credentials, or signed media URLs.
"""


class IntegrationError(RuntimeError):
    """Base class for provider failures surfaced to the outbox worker."""


class ASRTranscriptionError(IntegrationError):
    pass


class AIFeedbackError(IntegrationError):
    def __init__(self, message: str, *, reason: str = "feedback_error"):
        super().__init__(message)
        self.reason = reason


class AudioStorageError(IntegrationError):
    pass
