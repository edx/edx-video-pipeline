"""
Module containing all the Enumerations used in the API.
"""


class TranscriptionProviderErrorType:
    """
    Transcription provider's errors enumeration.
    """
    INVALID_CREDENTIALS = 1
    INVALID_PROVIDER = 2
    MISSING_REQUIRED_ATTRIBUTES = 3
