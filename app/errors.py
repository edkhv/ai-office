class DomainError(Exception):
    def __init__(self, code, status=400, message=None, retryable=False):
        self.code = code
        self.status = status
        self.message = message or code.replace("_", " ").capitalize()
        self.retryable = retryable
        super().__init__(code)
