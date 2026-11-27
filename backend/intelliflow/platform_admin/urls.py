from rest_framework.routers import SimpleRouter

from intelliflow.platform_admin.views import AdminViewSet

router = SimpleRouter(trailing_slash=False)
router.register("admin", AdminViewSet, basename="platform-admin")

urlpatterns = router.urls
