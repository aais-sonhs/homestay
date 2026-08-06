class PasswordResetError(Exception):
    def __init__(self, code, message, *, status=400, extra=None):
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra or {}
        super().__init__(message)
