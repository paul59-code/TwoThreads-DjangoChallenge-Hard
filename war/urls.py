from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="simulate", permanent=False)),
    path("simulate", views.simulate, name="simulate"),
    path("simulate/", views.simulate),
]
