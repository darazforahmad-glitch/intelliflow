from rest_framework.routers import SimpleRouter

from intelliflow.accounts.views import AuthViewSet

router = SimpleRouter(trailing_slash=False)
router.register("auth", AuthViewSet, basename="auth")

urlpatterns = router.urls
