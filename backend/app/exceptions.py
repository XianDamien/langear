"""Custom exceptions and error handling."""

from typing import Any

from fastapi import HTTPException, status


class LanGearException(Exception):
    """Base exception for LanGear application."""

    def __init__(self, code: str, message: str, status_code: int = 500):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class InvalidRatingError(LanGearException):
    """Raised when an invalid rating is provided."""

    def __init__(self):
        super().__init__(
            code="INVALID_RATING",
            message="Rating must be one of: again, hard, good, easy",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class AudioUploadError(LanGearException):
    """Raised when audio upload to OSS fails."""

    def __init__(self, details: str = ""):
        super().__init__(
            code="AUDIO_UPLOAD_FAILED",
            message=f"Failed to upload audio to OSS: {details}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ASRTranscriptionError(LanGearException):
    """Raised when ASR transcription fails."""

    def __init__(self, details: str = ""):
        super().__init__(
            code="ASR_TRANSCRIPTION_FAILED",
            message=f"Failed to transcribe audio: {details}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class AIFeedbackError(LanGearException):
    """Raised when AI feedback generation fails."""

    def __init__(self, details: str = ""):
        super().__init__(
            code="AI_FEEDBACK_FAILED",
            message=f"Failed to generate AI feedback: {details}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class SRSUpdateError(LanGearException):
    """Raised when FSRS update fails."""

    def __init__(self, details: str = ""):
        super().__init__(
            code="SRS_UPDATE_FAILED",
            message=f"Failed to update SRS state: {details}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class DBWriteError(LanGearException):
    """Raised when database write fails."""

    def __init__(self, details: str = ""):
        super().__init__(
            code="DB_WRITE_FAILED",
            message=f"Failed to write to database: {details}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class LessonNotCompletedError(LanGearException):
    """Raised when trying to get summary for incomplete lesson."""

    def __init__(self):
        super().__init__(
            code="LESSON_NOT_COMPLETED",
            message="Cannot generate summary for incomplete lesson",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class SummaryGenerationError(LanGearException):
    """Raised when lesson summary generation fails."""

    def __init__(self, details: str = ""):
        super().__init__(
            code="SUMMARY_GENERATION_FAILED",
            message=f"Failed to generate lesson summary: {details}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class InvalidSettingsError(LanGearException):
    """Raised when invalid settings are provided."""

    def __init__(self, details: str = ""):
        super().__init__(
            code="INVALID_SETTINGS",
            message=f"Invalid settings: {details}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
