"""Typed CLI errors with distinct exit codes (spec §8).

0 success · 1 validation · 2 auth · 3 approval denied/blocked ·
4 upstream API error · 5 unexpected.
"""


class CliError(Exception):
    exit_code = 5

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class ValidationError(CliError):
    exit_code = 1


class AuthError(CliError):
    exit_code = 2


class ApprovalDeniedError(CliError):
    exit_code = 3


class ApprovalBlockedError(CliError):
    exit_code = 3


class UpstreamError(CliError):
    exit_code = 4

    def __init__(self, message, code=None):
        super().__init__(message)
        self.message = message
        self.code = code