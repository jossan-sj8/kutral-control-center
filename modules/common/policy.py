"""Control centre policies that do not depend on the infrastructure.

Today there is only one: deciding whether mail should go out. It lives here and not in
the domain because the decision is the same for creations, modifications, deletions and
reactivations, and because `ask` cannot be resolved from the domain: the domain does not
ask, the wizard asks.
"""

from __future__ import annotations

from typing import Any, Optional


def should_send_mail(environment: Any, explicit: Optional[bool] = None) -> bool:
    """Decide whether mail goes out, from the flag or from the configuration.

    `explicit` comes from the command line (`--enviar-correo` / `--no-enviar-correo`)
    and overrides everything. If it was not given, `cluster.send_mail` decides:

        always  -> yes
        never   -> no
        ask     -> no by default: the wizard is the one that asks and calls back with
                   explicit=True. The domain never sits waiting for input.

    Returning False in the `ask` case is deliberate: it is better not to send one mail
    too many than to send it without anyone having confirmed it.
    """
    if explicit is not None:
        return bool(explicit)
    policy = str((environment.config.get("cluster", {}) or {}).get("send_mail", "ask")).lower()
    return policy == "always"


def needs_confirmation(environment: Any, explicit: Optional[bool] = None) -> bool:
    """True when the question about mail is still pending for the operator."""
    if explicit is not None:
        return False
    policy = str((environment.config.get("cluster", {}) or {}).get("send_mail", "ask")).lower()
    return policy == "ask"
