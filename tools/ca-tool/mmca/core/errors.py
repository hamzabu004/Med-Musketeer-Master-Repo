class MMCAError(Exception):
    """Expected, user-displayable provisioning failure."""


class SafetyError(MMCAError):
    """An operation failed a safety or identity check."""
