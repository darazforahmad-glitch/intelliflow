from rest_framework.routers import SimpleRouter

from intelliflow.runs.views import RunViewSet
from intelliflow.core.api.viewsets import WORKSPACE_PREFIX

router = SimpleRouter(trailing_slash=False)
router.register(f"{WORKSPACE_PREFIX}/runs", RunViewSet, basename="run")

urlpatterns = router.urls
