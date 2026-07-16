from uuid import UUID


class InvalidRecoveryFacts(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OperationNotFound(LookupError):
    code = "operation_not_found"

    def __init__(self, operation_id: UUID) -> None:
        self.operation_id = operation_id
        super().__init__(self.code)


class ApprovalAlreadyDecided(RuntimeError):
    code = "approval_already_decided"

    def __init__(self, operation_id: UUID) -> None:
        self.operation_id = operation_id
        super().__init__(self.code)


class IdempotencyConflict(RuntimeError):
    code = "idempotency_conflict"

    def __init__(self, operation_id: UUID, idempotency_key: str) -> None:
        self.operation_id = operation_id
        self.idempotency_key = idempotency_key
        super().__init__(self.code)


class WriteNotAuthorized(RuntimeError):
    code = "write_not_authorized"

    def __init__(self, operation_id: UUID, status: str) -> None:
        self.operation_id = operation_id
        self.status = status
        super().__init__(self.code)
