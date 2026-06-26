class BudgetInsufficientError(Exception):
    pass

class BudgetValidationError(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("Validation budgétaire impossible.")
