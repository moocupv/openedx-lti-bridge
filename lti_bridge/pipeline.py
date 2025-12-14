from django.shortcuts import redirect

SESSION_TARGET_KEY = "lti_bridge_target"

def redirect_to_lti_target(strategy, backend, *args, **kwargs):
    request = getattr(strategy, "request", None)
    if not request:
        return
    if request.session.get(SESSION_TARGET_KEY):
        return redirect("/lti/bridge/continue")
