"""Launch Hermes for one Finder user profile, executed by Hermes' own interpreter.

Kept alone in this directory on purpose: the script's folder lands on ``sys.path[0]``,
so no sibling module may shadow a Hermes import (``acp``, ``tools`` ...).

Hermes profiles read the data root's ``auth.json`` as a read-only fallback. On a
multi-user server that would hand the operator's own subscriptions to every user, so the
fallback is switched off before the CLI starts.
"""

import os
import runpy
import sys

for var in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
    os.environ.pop(var, None)

agent_dir = os.environ.get("FINDER_HERMES_AGENT_DIR", "")
if agent_dir:
    sys.path.insert(0, agent_dir)
sys._hermes_pin_default_home = True  # type: ignore[attr-defined]

try:
    import hermes_bootstrap  # noqa: F401  (git installs: environment wiring)
except ImportError:
    pass

import hermes_cli.auth as _auth  # noqa: E402

_auth._global_auth_file_path = lambda: None
_auth._load_global_auth_store = lambda: {}

# Same rule for the Claude subscription grant kept beside the data root.
try:
    import agent.anthropic_credentials as _anthropic

    _anthropic._root_hermes_oauth_file = lambda: None
except Exception:
    pass

# Sign-in pages are opened by the user in THEIR browser, never on the server.
import webbrowser  # noqa: E402

webbrowser.open = lambda *args, **kwargs: False

if sys.argv[1:2] == ["--finder-default-model"]:
    # Helper for the Finder backend: Hermes' default model id for a provider.
    from hermes_cli.models import get_default_model_for_provider

    print(get_default_model_for_provider(sys.argv[2]) or "")
    sys.exit(0)

sys.argv = ["hermes", *sys.argv[1:]]
runpy.run_module("hermes_cli.main", run_name="__main__", alter_sys=True)
