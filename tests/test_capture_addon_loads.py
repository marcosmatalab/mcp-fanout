"""The capture addon must load the way mitmproxy actually loads it: by path, not as a module.

This is the test whose absence let the whole capture layer be dead on arrival. The addon used
relative imports, which work under `import mcpfanout.capture_addon` and fail under mitmproxy's
loader, and nothing in the suite loaded it either way. The failure mode is the dangerous kind:
mitmdump logs the load error and keeps proxying, so a run completes, writes no flows, and reads
as "no server egressed anything".

No mitmproxy dependency here. The loader below is a faithful copy of the mechanism in
mitmproxy/addons/script.py::load_script -- a synthetic dotted name under a package that does not
exist, plus the script's own directory on sys.path -- which is exactly what breaks relative
imports.
"""

import importlib.util
import os
import sys
from pathlib import Path

ADDON = Path(__file__).resolve().parent.parent / "src" / "mcpfanout" / "capture_addon.py"


def _load_as_mitmproxy_would(path: Path, run_dir: Path):
    """Load the addon exactly as mitmproxy does, with its run directory redirected.

    ``addons = [FanoutRecorder()]`` runs at import time and FanoutRecorder.__init__ mkdirs
    MCPFANOUT_RUNDIR, so loading this module has a filesystem side effect. Left unset it lands
    on runs/live inside the repository: a test that writes into the tree it is testing.
    """
    fullname = "__mitmproxy_script__." + path.stem
    saved_path = list(sys.path)
    saved_env = {k: os.environ.get(k) for k in ("MCPFANOUT_RUNDIR", "MCPFANOUT_CONTROL")}
    sys.path.insert(0, str(path.parent))
    os.environ["MCPFANOUT_RUNDIR"] = str(run_dir)
    os.environ["MCPFANOUT_CONTROL"] = str(run_dir / "control")
    try:
        spec = importlib.util.spec_from_file_location(fullname, str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = saved_path
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.modules.pop(fullname, None)


def test_addon_loads_by_path_under_a_synthetic_package(tmp_path):
    module = _load_as_mitmproxy_would(ADDON, tmp_path)
    assert hasattr(module, "addons"), "mitmproxy looks for a module-level `addons` list"
    assert module.addons, "empty addons list registers no hooks"


def test_addon_exposes_the_hooks_mitmproxy_calls(tmp_path):
    """A hook mitmproxy never finds is a hook that never runs, and the run still 'succeeds'."""
    recorder = _load_as_mitmproxy_would(ADDON, tmp_path).addons[0]
    for hook in ("request", "done"):
        assert callable(getattr(recorder, hook, None)), f"addon has no {hook}() hook"


def test_addon_source_uses_no_relative_imports():
    """Belt and braces: the loader test above catches this, but not the reason.

    Pinning the rule itself means the next person sees WHY an absolute import is required inside
    a package, instead of 'tidying' it back to a relative one and rediscovering this the hard way.
    """
    offenders = [line.strip() for line in ADDON.read_text().splitlines()
                 if line.startswith("from .") or line.startswith("import .")]
    assert not offenders, f"mitmproxy's by-path loader cannot resolve these: {offenders}"
