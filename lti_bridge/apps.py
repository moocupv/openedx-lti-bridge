from django.apps import AppConfig

class LtiBridgeConfig(AppConfig):
    name = "lti_bridge"

    def ready(self):
        from django.conf import settings

        step = "lti_bridge.pipeline.redirect_to_lti_target"
        anchor = "common.djangoapps.third_party_auth.pipeline.ensure_redirect_url_is_safe"

        pipeline = list(getattr(settings, "SOCIAL_AUTH_PIPELINE", []))
        if step not in pipeline:
            if anchor in pipeline:
                pipeline.insert(pipeline.index(anchor), step)
            else:
                pipeline.append(step)

        settings.SOCIAL_AUTH_PIPELINE = pipeline
