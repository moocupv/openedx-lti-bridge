from django.urls import path
from . import views

urlpatterns = [
    path("launch", views.launch, name="lti_bridge_launch"),
    path("continue", views.continue_launch, name="lti_bridge_continue"),
]
