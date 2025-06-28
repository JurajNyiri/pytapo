class TemporarySuspension(Exception):
    def __init__(self, message, value):
        super().__init__(message)
        self.value = value
