"""Warm ``examples/pyst_cache.json`` from the live PyST vocabulary service.

Run by hand, once, whenever the examples need a broader concept the cache
does not already have. This needs network access to reach
``https://vocab.sentier.dev``. A token is optional -- the service answers
public concepts without one -- but if one is available it should be set as
``PYST_AUTH_TOKEN`` in the environment. Never write the token to a file, and
never pass it as an argument, since either would put it where `git status`
can see it:

    uv run python dev/warm_pyst_cache.py
    # or, with a token available:
    PYST_AUTH_TOKEN=<your token> uv run python dev/warm_pyst_cache.py

No extra install is needed: ``trailrunner.resolution.pyst`` talks to PyST
with the standard library alone (see that module's docstring for why: the
``pyst-client`` package on PyPI cannot actually be imported).

The cache this writes is not an optimisation: it is committed beside the
examples so a run reproduces on a plane, in a lecture hall, or in two years'
time without needing the network or the token again. See
``trailrunner/resolution/pyst.py`` for the taxonomy that reads it back.

**Watch the "no such concept" block this prints.** An IRI the vocabulary
does not have answers ``[]`` from the relationships endpoint exactly as a
real top concept with no parents does, so a warming run that looks entirely
successful can mean the product dimension will relax nothing, ever, for
those IRIs -- and several of the IRIs this project's own models use are
invented rather than vocabulary concepts. Nothing is cached for them (an
invented IRI must not end up in a committed cache file looking like a
concept), and they are printed at the end, loudly, because that is the one
moment someone is looking.
"""

from trailrunner.resolution import PystLabels, PystTaxonomy, default_client

# The real BONSAI vocabulary concepts the shipped models now use --
# trailrunner/models/dac.py's CO2_CAPTURED/HEAT/ELECTRICITY and
# trailrunner/models/electricity.py's ELECTRICITY/NATURAL_GAS. See
# .superpowers/sdd/2026-09-22-phase-4-surfaces-and-showcase/step-0-report.md
# for how each was found and verified against the live service.
IRIS = [
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_2811_21",  # co2-captured: "Carbon dioxide"
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_9",  # heat: "heat from main producers of heat"
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_17100",  # electricity: "electricity"
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_12020",  # natural-gas: "Natural gas, liquefied or in the gaseous state"
    # The cement showcase -- trailrunner/models/cement.py's CEMENT, LIMESTONE
    # and STEAM. fi_1730_6 is the specific technology the plant asks for and
    # fi_1730 is the generic concept one skos:broader step above it; the
    # relaxation beat in examples/showcase.ipynb walks exactly that edge, so
    # this entry is what lets the beat resolve with no network.
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_37440",  # cement: "Portland cement, aluminous cement, slag cement and similar hydraulic cements, except in the form of clinkers"
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_15200",  # limestone: "Gypsum; anhydrite; limestone flux; limestone and other calcareous stone, of a kind used for the manufacture of lime or cement"
    "https://vocab.sentier.dev/products/bonsai/2025.1/BONSAI2025.1/fi_1730_6",  # steam: "heat from electric boilers"
]


def main() -> None:
    taxonomy = PystTaxonomy("examples/pyst_cache.json", client=default_client())
    reached: set[str] = set()
    for iri in IRIS:
        parents = taxonomy.broader(iri)
        print(iri, "->", parents)
        reached.add(iri)
        reached.update(parents)
    taxonomy.save()

    # The other half of what a concept carries. The examples print a
    # traversal, and a traversal keyed on IRIs reads as `fi_2811_21` unless
    # something supplies the vocabulary's own name for that concept. Warmed
    # for the parents too, since a generalised demand is answered at one.
    labels = PystLabels("examples/pyst_labels.json", client=default_client())
    print()
    for iri in sorted(reached):
        print(f"{iri} -> {labels.label(iri)!r}")
    labels.save()

    unknown = sorted(taxonomy.unknown_iris)
    if unknown:
        print()
        print("!" * 72)
        print("!! THE VOCABULARY HAS NO SUCH CONCEPT (404 from /api/v1/concepts/):")
        for iri in unknown:
            print(f"!!   {iri}")
        print("!!")
        print("!! These are not concepts, so they have no skos:broader and the")
        print("!! product dimension can never relax them, whatever max_steps says.")
        print("!! Nothing was cached for them. Either fix the IRI to one the")
        print("!! vocabulary actually has, or accept that generalisation does not")
        print("!! apply to this product and say so where the model declares it.")
        print("!" * 72)


if __name__ == "__main__":
    main()
