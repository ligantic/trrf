import logging
import threading
import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.generic.base import View

from rdrf.security.mixins import SuperuserRequiredMixin

logger = logging.getLogger(__name__)

# Cache timeout for job status: 1 hour
_JOB_CACHE_TIMEOUT = 3600


def _run_import(job_id, registry_yaml):
    cache.set(f"import_job_{job_id}", {"status": "running"}, _JOB_CACHE_TIMEOUT)
    try:
        from rdrf.services.io.defs.importer import Importer

        importer = Importer()
        importer.load_yaml_from_string(registry_yaml)
        with transaction.atomic():
            importer.create_registry()
        cache.set(f"import_job_{job_id}", {"status": "success"}, _JOB_CACHE_TIMEOUT)
    except Exception as ex:
        logger.error("Import failed: %s" % ex, exc_info=ex)
        cache.set(
            f"import_job_{job_id}",
            {"status": "fail", "error_message": str(ex)},
            _JOB_CACHE_TIMEOUT,
        )


class ImportRegistryView(SuperuserRequiredMixin, View):
    def get(self, request):
        state = request.GET.get("state", "ready")
        user = get_user_model().objects.get(username=request.user)
        error_message = request.GET.get("error_message", None)

        context = {
            "user_obj": user,
            "state": state,
            "error_message": error_message,
        }

        return render(request, "rdrf_cdes/import_registry.html", context)

    def post(self, request, *args, **kwargs):
        registry_yaml = request.POST.get("registry_yaml", "")

        if request.FILES:
            registry_yaml = request.FILES["registry_yaml_file"].read()

        job_id = str(uuid.uuid4())
        t = threading.Thread(target=_run_import, args=(job_id, registry_yaml), daemon=True)
        t.start()

        return JsonResponse({"job_id": job_id})


class ImportRegistryStatusView(SuperuserRequiredMixin, View):
    def get(self, request, job_id):
        status = cache.get(f"import_job_{job_id}")
        if status is None:
            return JsonResponse({"status": "not_found"}, status=404)
        return JsonResponse(status)
