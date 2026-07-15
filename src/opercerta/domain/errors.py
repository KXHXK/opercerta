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
