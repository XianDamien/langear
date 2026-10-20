"""Provider errors raised by core-owned integrations.

Adapters never leak upstream bodies, credentials, or signed media URLs.
"""


class IntegrationError(RuntimeError):
    """Base class for provider failures surfaced to the outbox worker."""


class ASRTranscriptionError(IntegrationError):
    pass


class AIFeedbackError(IntegrationError):
    pass


class AudioStorageError(IntegrationError):
    pass
