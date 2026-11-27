from rest_framework.routers import SimpleRouter

from intelliflow.flowmapper.views import InterviewViewSet, ProcessMapViewSet

from intelliflow.core.api.viewsets import WORKSPACE_PREFIX as WS

router = SimpleRouter(trailing_slash=False)
router.register(f"{WS}/interviews", InterviewViewSet, basename="interview")
router.register(f"{WS}/process-maps", ProcessMapViewSet, basename="process-map")

urlpatterns = router.urls
