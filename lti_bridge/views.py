from urllib.parse import unquote

from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.utils.html import escape
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

SESSION_TARGET_KEY = "lti_bridge_target"
SESSION_PAYLOAD_KEY = "lti_bridge_payload"

LTI_LOGIN_URL = getattr(settings, "LTI_BRIDGE_LOGIN_URL", "/auth/login/lti/")

def _is_safe_internal_path(path: str) -> bool:
    """
    Accept only internal absolute paths like '/foo/bar'.
    Reject scheme/host ('http://'), protocol-relative ('//evil.com'), etc.
    """
    if not path or not isinstance(path, str):
        return False
    if not path.startswith("/"):
        return False
    if path.startswith("//"):
        return False
    if "://" in path:
        return False
    if "\x00" in path:
        return False
    return True

def _autosubmit_post_html(action_url: str, fields: dict, title: str = "Redirecting...") -> str:
    inputs = []
    for k, v in (fields or {}).items():
        if v is None:
            v = ""
        inputs.append(
            f'<input type="hidden" name="{escape(str(k))}" value="{escape(str(v))}"/>'
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
</head>
<body>
  <noscript>
    <p>This step requires JavaScript to submit a POST request.</p>
  </noscript>
  <form id="lti-bridge-form" method="post" action="{escape(action_url)}">
    {''.join(inputs)}
  </form>
  <script>
    document.getElementById("lti-bridge-form").submit();
  </script>
</body>
</html>
"""

@csrf_exempt
@require_http_methods(["GET", "POST"])
def launch(request):
    """
    Called by the external tool/consumer.

    - target is provided as an internal path, e.g. /lti_provider/courses/...
      (can come in querystring like ?target=%2F... or as POST field)
    - LTI 1.1 launch params MUST come by POST (oauth_* etc.)
    """
    # 1) Extract target from GET or POST
    target = request.POST.get("target") or request.GET.get("target") or ""
    # If target is percent-encoded (like in your example), unquote is fine
    target = unquote(target)

    if not _is_safe_internal_path(target):
        return HttpResponseBadRequest("Invalid target: must be an internal path starting with '/'.")

    # 2) LTI payload must be POSTed (signed)
    if request.method != "POST":
        return HttpResponseBadRequest("LTI launch must be POST. Send LTI params in POST, target can be in querystring.")

    payload = request.POST.dict()
    payload.pop("target", None)  # keep target out of LTI payload

    # Minimal LTI 1.1 sanity check
    if "oauth_consumer_key" not in payload or "oauth_signature" not in payload:
        return HttpResponseBadRequest("Missing LTI OAuth fields (oauth_consumer_key/oauth_signature).")

    # 3) Store for after authentication
    request.session[SESSION_TARGET_KEY] = target
    request.session[SESSION_PAYLOAD_KEY] = payload
    request.session.modified = True

    # 4) POST into Open edX LTI login endpoint with the same signed payload
    html = _autosubmit_post_html(LTI_LOGIN_URL, payload, title="Signing you in…")
    return HttpResponse(html)


@require_http_methods(["GET"])
def continue_launch(request):
    """
    After authentication, redirect internally to the stored target.
    """
    target = request.session.pop(SESSION_TARGET_KEY, None)
    request.session.pop(SESSION_PAYLOAD_KEY, None)  # no longer needed after login

    if not _is_safe_internal_path(target or ""):
        return redirect("/")

    return redirect(target)
