from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = "disputes"

urlpatterns = [
    path("", RedirectView.as_view(url="/apply/", permanent=False), name="home"),
    path("apply/", views.apply_view, name="apply"),
    path("apply/upload-photo/", views.upload_photo_ajax, name="upload_photo"),
    path("apply/remove-photo/", views.remove_photo_ajax, name="remove_photo"),
    path("apply/get-photos/", views.get_photos_ajax, name="get_photos"),
    path("success/<int:dispute_id>/", views.success_view, name="application_success"),
    path("success/", views.success_view, name="application_success"),
    path("respond/<uuid:token>/", views.respond_view, name="respond"),
    path("view-defence/<uuid:token>/", views.view_defence, name="view_defence"),
    path("outcome/<uuid:token>/", views.view_outcome, name="view_outcome"),
    path("confirm/<uuid:token>/", views.applicant_confirm_view, name="applicant_confirm"),
    path("final-confirm/<uuid:token>/", views.applicant_final_confirm_view, name="applicant_final_confirm"),
    path("setup-admin/", views.setup_admin_view, name="setup_admin"),
]
