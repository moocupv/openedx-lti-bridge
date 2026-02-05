from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

import requests
from requests.utils import cookiejar_from_dict

SESSION_TARGET_KEY = "lti_bridge_target"
SESSION_PAYLOAD_KEY = "lti_bridge_payload"


def _is_safe_target(target: str) -> bool:
    """
    Allowlist:
    - must be absolute path under /lti_provider
    - reject scheme/host, protocol-relative, and path traversal
    """
    if not target or not isinstance(target, str):
        return False

    if not (target == "/lti_provider" or target.startswith("/lti_provider/")):
        return False

    if "://" in target:
        return False
    if target.startswith("//"):
        return False
    if ".." in target:
        return False

    return True


def _html_autopost(action: str, params: dict) -> str:
    def esc(s: str) -> str:
        return (
            str(s)
            .replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    inputs = "\n".join(
        f'<input type="hidden" name="{esc(k)}" value="{esc(v)}"/>'
        for k, v in (params or {}).items()
    )
    return f"""<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Redirecting…</title></head>
  <body>
    <form id="f" method="post" action="{esc(action)}">
      {inputs}
    </form>
    <script>document.getElementById("f").submit();</script>
  </body>
</html>
"""


def _lti_login_url() -> str:
    # Keep using the LTI login endpoint to trigger provisioning/linking.
    return getattr(settings, "LTI_BRIDGE_LOGIN_URL", "/auth/login/lti/")


@csrf_exempt
def launch(request):
    """
    POST /lti/bridge/launch?target=/lti_provider/...

    Stores POST payload + target in session, then performs the LTI login
    server-side (to trigger user provisioning/linking) and finally redirects
    the browser to /lti/bridge/continue, copying back any auth cookies created
    by the LTI login.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    target = request.GET.get("target", "")
    if not _is_safe_target(target):
        return HttpResponseBadRequest("Invalid target")

    payload = dict(request.POST.items())

    # Persist launch state for the continuation step
    request.session[SESSION_TARGET_KEY] = target
    request.session[SESSION_PAYLOAD_KEY] = payload
    request.session.modified = True

    # Call the LTI login endpoint on this same host.
    # We intentionally do NOT rely on `next` since /auth/login/lti/ ignores it.
    login_url = request.build_absolute_uri(_lti_login_url())

    s = requests.Session()

    # Forward browser cookies (affinity, existing session, etc.)
    if request.COOKIES:
        s.cookies.update(cookiejar_from_dict(request.COOKIES))

    try:
        r = s.post(
            login_url,
            data=payload,
            allow_redirects=False,
            timeout=getattr(settings, "LTI_BRIDGE_LOGIN_TIMEOUT", 10),
        )
    except requests.RequestException as e:
        return HttpResponseBadRequest(f"LTI login request failed: {e}")

    if r.status_code not in (302, 303):
        return HttpResponseBadRequest(f"Unexpected response from LTI login: {r.status_code}")

    # Now redirect the browser into our continuation step...
    resp = redirect(reverse("lti_bridge_continue"))

    # ...and copy cookies set/updated by the LTI login back to the browser
    # (at minimum, sessionid; also App Gateway affinity cookies if present).
    for c in s.cookies:
        if not c.name:
            continue

        # Best-effort HttpOnly extraction; default True for safety.
        httponly = True
        if hasattr(c, "rest") and isinstance(c.rest, dict):
            httponly = c.rest.get("HttpOnly", True)

        # For LTI-in-iframe deployments, Secure + SameSite=None is typical.
        samesite = "None" if c.secure else "Lax"

        resp.set_cookie(
            key=c.name,
            value=c.value,
            domain=c.domain or None,
            path=c.path or "/",
            secure=bool(c.secure),
            httponly=httponly,
            samesite=samesite,
        )

    return resp


def continue_launch(request):
    """
    GET /lti/bridge/continue

    After auth, replays the stored POST to the target under /lti_provider/...
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        login_url = getattr(settings, "LOGIN_URL", "/login")
        return redirect(f"{login_url}?next={reverse('lti_bridge_continue')}")

    target = request.session.get(SESSION_TARGET_KEY)
    payload = request.session.get(SESSION_PAYLOAD_KEY)

    if not target or not payload:
        return HttpResponseBadRequest("No pending LTI launch")

    if not _is_safe_target(target):
        return HttpResponseBadRequest("Invalid target in session")

    # One-shot: clear stored launch state
    request.session.pop(SESSION_TARGET_KEY, None)
    request.session.pop(SESSION_PAYLOAD_KEY, None)
    request.session.modified = True

    return HttpResponse(_html_autopost(target, payload))
