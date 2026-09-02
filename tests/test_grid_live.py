import asyncio
import pytest
from hcl_radiance.discover import radiance_status

pytestmark = pytest.mark.skipif(not radiance_status()["available"],
                                reason="Radiance not installed")

def test_run_grid_emit_path_offline(tmp_path):
    # Always-runnable: emit path returns commands regardless of Radiance.
    import hcl_mcp.server as srv
    out = asyncio.run(srv.run_grid(scene_sets=[["m.rad", "sky.rad", "g.rad"]],
                                   points=[[0, 0, 1.2, 0, 0, 1]], channel_type=0,
                                   work_dir=str(tmp_path), run=False))
    assert out["ran"] is False and any("rtrace" in c for c in out["commands"])
