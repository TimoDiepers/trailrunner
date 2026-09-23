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


class MissingProperty(TrailrunnerError):
    """A co-product lacks the property the run's allocation rule partitions on.

    Raised rather than defaulted: a partition over an assumed price is a
    fabricated value judgement, and it would be invisible in the result.
    """


class UnsupportedAttribution(TrailrunnerError):
    """A model cannot honour the run's attribution setting.

    A model may legitimately limit how far a user setting reaches. Saying so is
    the whole point — a model that silently ignored the setting would produce a
    number answering a different question than the one asked.
    """


class DuplicateBackgroundEntry(TrailrunnerError):
    """A background pack states two datasets for one product, unit and location.

    ``(product_iri, product_unit, location)`` is what
    ``BackgroundPack.lookup`` searches on, so two datasets sharing one key is
    a data error in exactly the way two models producing one product is (see
    ``AmbiguousModelMatch``) and two characterization factors for one flow is
    (see ``DuplicateFactor``): there is no rule that picks between them, so
    silently keeping whichever came last would put an unexplained number in
    the inventory -- and, worse here, label it with the wrong dataset name in
    the very resolution a reader checks a borrowed number against.
    """
