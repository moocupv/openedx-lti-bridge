import json

from django.http import HttpResponse, HttpResponseBadRequest
from django.middleware.csrf import get_token
from django.shortcuts import redirect
from django.utils.html import escape
from django.views.decorators.http import require_http_methods

SESSION_TARGET_KEY = "lti_bridge_target"
SESSION_PAYLOAD_KEY = "lti_bridge_payload"

# Puedes mantenerlo en settings como ya haces
DEFAULT_LOGIN_URL = "/auth/login/lti/"


def _autosubmit_post_html(action_url: str, fields: dict, title: str = "Redirecting...") -> str:
    """
    Returns a minimal HTML page with an auto-submitting POST form.
    """
    inputs = []
    for k, v in (fields or {}).items():
        # LTI params are strings; if not, serialize to string
        if v is None:
            v = ""
        elif not isinstance(v, str):
            v = json.dumps(v)
        inputs.append(
            f'<input type="hidden" name="{escape(str(k))}" value="{escape(v)}"/>'
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


@require_http_methods(["GET", "POST"])
def launch(request):
    """
    Entry point called by your tool/consumer:
    - Receives target (where to finally POST) and payload (LTI params)
    - Stores them in session
    - Sends user through Open edX LTI login endpoint via auto-submitting POST
    """
    target = request.POST.get("target") or request.GET.get("target")
    payload_raw = request.POST.get("payload") or request.GET.get("payload")

    if not target or not payload_raw:
        return HttpResponseBadRequest("Missing 'target' or 'payload'.")

    try:
        payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
        if not isinstance(payload, dict):
            return HttpResponseBadRequest("'payload' must be a JSON object.")
    except Exception:
        return HttpResponseBadRequest("Invalid JSON in 'payload'.")

    # Store for after authentication
    request.session[SESSION_TARGET_KEY] = target
    request.session[SESSION_PAYLOAD_KEY] = payload

    # Ensure session is saved before redirecting into auth
    request.session.modified = True

    # POST into the LTI login endpoint (no next= supported)
    login_url = getattr(request, "site", None)  # not used; keep simple
    login_url = DEFAULT_LOGIN_URL

    # If /auth/login/lti/ is CSRF-exempt (usual), you don't need csrftoken.
    # If it isn't, you'd need to include csrfmiddlewaretoken. Generally it is exempt.
    html = _autosubmit_post_html(login_url, fields={}, title="Signing you in...")
    return HttpResponse(html)


@require_http_methods(["GET"])
def continue_launch(request):
    """
    After social-auth finishes, our pipeline redirects here.
    We then POST the original LTI payload to the original target.
    """
    target = request.session.pop(SESSION_TARGET_KEY, None)
    payload = request.session.pop(SESSION_PAYLOAD_KEY, None)

    if not target or not payload:
        # Nothing to continue: go somewhere safe (or return 400)
        return redirect("/")

    html = _autosubmit_post_html(target, payload, title="Continuing...")
    return HttpResponse(html)
