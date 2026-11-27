from django.urls import path
from rest_framework.routers import SimpleRouter

from intelliflow.automations.catalog import (
    BlockCatalogView,
    ConnectorCatalogView,
    TemplateCatalogView,
)

from intelliflow.automations.views import AutomationViewSet
from intelliflow.core.api.viewsets import WORKSPACE_PREFIX

router = SimpleRouter(trailing_slash=False)
router.register(f"{WORKSPACE_PREFIX}/automations", AutomationViewSet, basename="automation")

urlpatterns = [
    path("templates", TemplateCatalogView.as_view()),
    path("blocks", BlockCatalogView.as_view()),
    path("connectors", ConnectorCatalogView.as_view()),
    *router.urls,
]
