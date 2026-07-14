class InvalidRecoveryFacts(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)
