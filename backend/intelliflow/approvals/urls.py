from rest_framework.routers import SimpleRouter

from intelliflow.approvals.views import ApprovalViewSet
from intelliflow.core.api.viewsets import WORKSPACE_PREFIX

router = SimpleRouter(trailing_slash=False)
router.register(f"{WORKSPACE_PREFIX}/approvals", ApprovalViewSet, basename="approval")

urlpatterns = router.urls
