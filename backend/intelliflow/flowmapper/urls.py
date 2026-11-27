from rest_framework.routers import SimpleRouter

from intelliflow.core.api.viewsets import WORKSPACE_PREFIX as WS
from intelliflow.flowmapper.views import InterviewViewSet, ProcessMapViewSet

router = SimpleRouter(trailing_slash=False)
router.register(f"{WS}/interviews", InterviewViewSet, basename="interview")
router.register(f"{WS}/process-maps", ProcessMapViewSet, basename="process-map")

urlpatterns = router.urls
