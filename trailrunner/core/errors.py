"""Exception hierarchy.

Unresolvable *data* becomes a recorded leaf in the Log. Unresolvable
*contracts* raise one of these.
"""


class TrailrunnerError(Exception):
    """Base class for every error trailrunner raises."""


class NoModelFound(TrailrunnerError):
    """No registered model produces the requested flow."""


class AmbiguousModelMatch(TrailrunnerError):
    """More than one registered model produces the requested flow."""


class ValidationError(TrailrunnerError):
    """A model returned a Result that breaks the Model contract."""


class ParameterNotFound(TrailrunnerError):
    """No parameter row could be resolved for the requested location and time."""
