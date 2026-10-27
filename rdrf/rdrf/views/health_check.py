import logging

from django.db import InterfaceError, OperationalError, connections
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from rdrf.models.definition.models import Registry

logger = logging.getLogger(__name__)


@never_cache
@require_safe
def liveness_check(request):
    return JsonResponse({"success": True})


@never_cache
@require_safe
def readiness_check(request):
    for alias in ("default", "clinical"):
        try:
            with connections[alias].cursor() as cursor:
                cursor.execute("SELECT 1")
        except (OperationalError, InterfaceError):
            connections[alias].close()
            logger.warning("Database readiness check failed: alias=%s", alias)
            return JsonResponse({"success": False}, status=503)
    logger.info("Database readiness check succeeded")
    return JsonResponse({"success": True})


def health_check(request):
    return JsonResponse(
        {
            "success": True,
            "hosted_registries_count": Registry.objects.count(),
        }
    )
