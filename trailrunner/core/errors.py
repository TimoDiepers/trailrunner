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


class MissingUnit(TrailrunnerError):
    """A parameter column asked for a unit has none declared in its datapackage.

    Raised where the unit is read rather than carried onward as ``None``: an
    Exchange's unit is a ``str``, and a silent ``None`` surfaces much later as
    a validation error blaming the model for what is really missing metadata.
    """


class DuplicateFactor(TrailrunnerError):
    """A method file states two characterization factors for one key.

    ``(flow_iri, flow_unit, location, time)`` identifies a factor. Two rows
    sharing one key is a data error in exactly the way two models producing
    one product is: there is no rule that picks between them, so silently
    keeping whichever came last would put an unexplained number in the score.
    """


class MissingColumns(TrailrunnerError):
    """A parquet file does not have the columns its reader needs.

    Named in the same style as ``MissingUnit``, and for the same reason: a
    bare ``KeyError('flow_iri')`` names neither the file nor the layout that
    was expected, which leaves the reader guessing at both.
    """
