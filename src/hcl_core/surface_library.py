"""Named surface catalog for hcl_radiance geometry import.

All entries are flagged illustrative=True — they are starting-point values,
not measured data for your specific build materials.
"""

import os

_NOTES = ("Illustrative reflectance/transmittance — a starting value, "
          "not measured data for your build.")

# Catalog: {name: {type, refl|tvis, family, illustrative}}
_CATALOG = {
    "painted_gypsum": {
        "type": "plastic",
        "refl": 0.70,
        "family": "wall",
        "illustrative": True,
    },
    "white_ceiling": {
        "type": "plastic",
        "refl": 0.80,
        "family": "ceiling",
        "illustrative": True,
    },
    "oak_floor": {
        "type": "plastic",
        "refl": 0.25,
        "family": "floor",
        "illustrative": True,
    },
    "concrete": {
        "type": "plastic",
        "refl": 0.30,
        "family": "floor",
        "illustrative": True,
    },
    "clear_float_6mm": {
        "type": "glass",
        "tvis": 0.78,
        "family": "glazing",
        "illustrative": True,
    },
    "low_e_double": {
        "type": "glass",
        "tvis": 0.62,
        "family": "glazing",
        "illustrative": True,
    },
    "grass_ground": {
        "type": "ground",
        "refl": 0.20,
        "family": "ground",
        "illustrative": True,
    },
    "asphalt_ground": {
        "type": "ground",
        "refl": 0.10,
        "family": "ground",
        "illustrative": True,
    },
}

_NAMES = list(_CATALOG)


def list_surfaces() -> list:
    """Names of all entries in the built-in surface catalog."""
    return list(_NAMES)


def surface_lookup(name: str) -> dict:
    """Return a copy of the catalog entry for *name*.

    Raises KeyError on unknown names.
    """
    try:
        return dict(_CATALOG[name])
    except KeyError:
        raise KeyError(f"unknown surface {name!r}; known: {_NAMES}")


def surface_meta(name: str) -> dict:
    """Return {"family", "illustrative", "measured", "notes", "source"} for *name*.

    measured == True ONLY when the entry carries a `source` citation AND a readable `spd` file.
    The shipped catalog is illustrative-only; measured entries are introduced via real data.
    Raises KeyError on unknown names.
    """
    entry = surface_lookup(name)               # raises KeyError if unknown
    source = entry.get("source")
    spd_path = entry.get("spd")
    measured = bool(source) and bool(spd_path) and os.path.exists(spd_path)
    return {
        "family": entry["family"],
        "illustrative": not measured,
        "measured": measured,
        "notes": _NOTES,
        "source": source,
    }
