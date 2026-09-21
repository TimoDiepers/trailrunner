"""Exception hierarchy.

Unresolvable *data* becomes a recorded leaf in the Log. Unresolvable
*contracts* raise one of these.
"""


class TrailrunnerError(Exception):
    """Base class for every error trailrunner raises."""


class NoProducer(TrailrunnerError):
    """No registered model produces the requested flow."""


class AmbiguousProducer(TrailrunnerError):
    """More than one registered model produces the requested flow."""


class ValidationError(TrailrunnerError):
    """A model returned a Result that breaks the Model contract."""


class ParameterNotFound(TrailrunnerError):
    """No parameter row could be resolved for the requested location and time."""


class MissingUnit(TrailrunnerError):
    """A parameter column asked for a unit has none declared in its datapackage.

    Raised where the unit is read rather than carried onward as ``None``: an
    Exchange's unit is a ``str``, and a silent ``None`` surfaces much later as
    a validation error blaming the model for what is really missing metadata.
    """
