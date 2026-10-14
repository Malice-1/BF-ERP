class PurchaseRequestError(Exception):
    """A purchase action cannot be completed."""


class PurchaseRequestConflict(PurchaseRequestError):
    """The caller must reload the request before editing it."""
