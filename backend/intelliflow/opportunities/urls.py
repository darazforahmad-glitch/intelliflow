from rest_framework.routers import SimpleRouter

from intelliflow.opportunities.views import OpportunityViewSet
from intelliflow.core.api.viewsets import WORKSPACE_PREFIX

router = SimpleRouter(trailing_slash=False)
router.register(f"{WORKSPACE_PREFIX}/opportunities", OpportunityViewSet, basename="opportunitie")

urlpatterns = router.urls
