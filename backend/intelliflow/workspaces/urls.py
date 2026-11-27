from rest_framework.routers import SimpleRouter

from intelliflow.workspaces.views import InvitationViewSet, WorkspaceViewSet

router = SimpleRouter(trailing_slash=False)
router.register("workspaces", WorkspaceViewSet, basename="workspace")
router.register("invitations", InvitationViewSet, basename="invitation")

urlpatterns = router.urls
