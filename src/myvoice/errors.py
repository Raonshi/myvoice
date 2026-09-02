from __future__ import annotations


class MyVoiceError(Exception):
    exit_code = 50


class ConfigurationError(MyVoiceError):
    exit_code = 2


class InputValidationError(MyVoiceError):
    exit_code = 10


class VoiceProfileError(MyVoiceError):
    exit_code = 11


class TTSError(MyVoiceError):
    exit_code = 20


class DeviceMemoryError(TTSError):
    exit_code = 21


class AudioToolError(MyVoiceError):
    exit_code = 30


class JobStateError(MyVoiceError):
    exit_code = 40
