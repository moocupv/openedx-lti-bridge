from django.shortcuts import redirect

SESSION_TARGET_KEY = "lti_bridge_target"
SESSION_PAYLOAD_KEY = "lti_bridge_payload"

def redirect_to_lti_target(strategy, backend, *args, **kwargs):
    """
    If we're in an LTI bridge flow (target+payload stored in session),
    short-circuit the social-auth redirect and go to the bridge continue endpoint.
    """
    request = getattr(strategy, "request", None)
    if not request:
        return None

    if request.session.get(SESSION_TARGET_KEY) and request.session.get(SESSION_PAYLOAD_KEY):
        return redirect("/lti/bridge/continue")

    return None
