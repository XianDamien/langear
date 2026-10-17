class DomainError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message = status, code, message
        self.details = details or {}


def missing():
    raise DomainError(404, "NOT_FOUND", "Resource not found.")
