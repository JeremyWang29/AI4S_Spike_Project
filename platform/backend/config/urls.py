from django.urls import path
from modules.projects import views

urlpatterns = [
    path("api/v1/health", views.health),
    path("api/v1/session/login", views.session_login),
    path("api/v1/session/logout", views.session_logout),
    path("api/v1/projects", views.projects_collection),
    path("api/v1/projects/<uuid:project_id>/status", views.project_status),
    path("api/v1/projects/<uuid:project_id>/gold/evaluate", views.evaluate_gold),
    path("api/v1/projects/<uuid:project_id>/retrieval/compile", views.compile_retrieval),
    path("api/v1/projects/<uuid:project_id>/retrieval/manual-runs", views.record_manual_run),
    path("api/v1/projects/<uuid:project_id>/materials/import-summary", views.import_summary),
    path("api/v1/projects/<uuid:project_id>/evidence", views.add_evidence),
    path("api/v1/projects/<uuid:project_id>/navigation", views.navigation),
    path("api/v1/projects/<uuid:project_id>/candidates", views.create_candidate),
    path("api/v1/projects/<uuid:project_id>/decisions", views.create_decision),
    path("api/v1/projects/<uuid:project_id>/contributions/validate", views.validate_contribution),
    path("api/v1/projects/<uuid:project_id>/models/status", views.model_status),
    path("api/v1/projects/<uuid:project_id>/tasks/<uuid:task_id>", views.task_status),
]
