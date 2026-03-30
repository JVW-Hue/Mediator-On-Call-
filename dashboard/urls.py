from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.AdminDashboardView.as_view(), name="admin_home"),
    path("disputes/", views.DisputeListView.as_view(), name="dispute_list"),
    path("dispute/<int:pk>/", views.DisputeDetailView.as_view(), name="dispute_detail"),
    path("dispute/<int:pk>/delete/", views.delete_dispute, name="delete_dispute"),
    path("dispute/<int:pk>/download/", views.download_case_file, name="download_case_file"),
    path("dispute/<int:pk>/assign-mediator/", views.assign_mediator_to_dispute, name="assign_mediator_to_dispute"),
    path("dispute/<int:pk>/screen/", views.screen_dispute_page, name="screen_dispute_page"),
    path("dispute/<int:pk>/assign/", views.assign_mediator_page, name="assign_mediator_page"),
    path("screen/", views.screen_dispute, name="screen_dispute"),
    path("assign/", views.assign_mediator_post, name="assign_mediator"),
    path("referred-cases/", views.referred_cases_view, name="referred_cases"),
    path("mediatable-cases/", views.mediatable_cases_view, name="mediatable_cases"),
    path("mediators/", views.mediators_list, name="mediators_list"),
    path("mediator/", views.mediator_dashboard, name="mediator_home"),
    path("mediator/sessions/", views.mediator_sessions, name="mediator_sessions"),
    path("mediator/accept/<int:dispute_id>/", views.mediator_accept_case, name="mediator_accept_case"),
    path("mediator/session/<int:pk>/outcome/", views.submit_mediation_outcome, name="submit_mediation_outcome"),
    path("calendar/note/", views.save_calendar_note, name="save_calendar_note"),
]
