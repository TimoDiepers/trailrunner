"""Location fallback: CH -> RER -> GLO."""


class LocationHierarchy:
    """A child-to-parent map used to widen a parameter lookup.

    ``chain`` always ends at ``root``, so every lookup has a last resort.
    """

    def __init__(self, parents: dict[str, str] | None = None, root: str = "GLO") -> None:
        self._parents = dict(parents or {})
        self._root = root

    @property
    def root(self) -> str:
        """The last resort every chain ends at. Read-only: changing it mid-run
        would silently change which fallback rows match."""
        return self._root

    def chain(self, location: str | None) -> list[str | None]:
        """Ordered candidates, most specific first.

        ``None`` means "no location was requested", which callers read as
        "ignore the location column entirely".
        """
        if location is None:
            return [None]
        chain: list[str | None] = []
        current: str | None = location
        while current is not None and current not in chain:
            chain.append(current)
            current = self._parents.get(current)
        if self._root not in chain:
            chain.append(self._root)
        return chain
