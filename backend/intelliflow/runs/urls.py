from rest_framework.routers import SimpleRouter

from intelliflow.core.api.viewsets import WORKSPACE_PREFIX
from intelliflow.runs.views import RunViewSet

router = SimpleRouter(trailing_slash=False)
router.register(f"{WORKSPACE_PREFIX}/runs", RunViewSet, basename="run")

urlpatterns = router.urls
