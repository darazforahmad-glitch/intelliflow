from django.urls import path

from intelliflow.dashboard.views import DashboardView, WeeklyReportView, stream_events

urlpatterns = [
    path("workspaces/<uuid:workspace_id>/dashboard", DashboardView.as_view()),
    path("workspaces/<uuid:workspace_id>/reports/weekly.csv", WeeklyReportView.as_view()),
    path("workspaces/<uuid:workspace_id>/events", stream_events),
]
