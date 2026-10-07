class ProviderError(RuntimeError):
    """An external data provider could not be reached or returned unusable data.

    `source` names the provider in user-facing messages, e.g. "Frankfurter exchange-rate service".
    """

    def __init__(self, message: str, source: str = "data provider"):
        super().__init__(message)
        self.source = source
