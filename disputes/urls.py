from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "disputes"

urlpatterns = [
    path("", RedirectView.as_view(url="/apply/", permanent=False), name="home"),
    path("apply/", views.apply_view, name="apply"),
    path("success/", views.success_view, name="application_success"),
    path("respond/<uuid:token>/", views.respond_view, name="respond"),
    path("view-defence/<uuid:token>/", views.view_defence, name="view_defence"),
    path("outcome/<uuid:token>/", views.view_outcome, name="view_outcome"),
    path("confirm/<uuid:token>/", views.applicant_confirm_view, name="applicant_confirm"),
]
