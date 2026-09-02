"""Site location from an EPW, in the DAYSIM/.wea convention.

The parser itself now lives in `hcl_core.epw_location`: the spectral pipeline needs the
same parse with no engine installed, and `hcl_core`'s solar-geometry functions already
speak this convention, so keeping it here made `hcl_core` import upward into the Daysim
adapter. This module re-exports it unchanged, so the `.wea`/`.hea` writers next door (and
the `hcl_daysim.epw.parse_epw_location` import path used by the analysis scripts) keep
working exactly as before.
"""

from hcl_core.epw_location import parse_epw_location

__all__ = ["parse_epw_location"]
