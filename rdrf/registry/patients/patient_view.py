from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic.base import View
from rdrf.models.definition.models import Registry


class PatientView(View):
    def get(self, request, registry_code):
        registry = get_object_or_404(Registry, code=registry_code)
        user = request.user
        qs = (
            user.patients_in_care if request.user.is_carer else user.user_object
        )
        patients = list(qs.filter(rdrf_registry=registry))
        if not patients:
            raise Http404(
                _("No patient found for this user in this registry")
            )
        if len(patients) == 1:
            return redirect(
                reverse("patient_edit", args=[registry_code, patients[0].id])
            )
        # Multiple patients in care (e.g. a carer for several participants):
        # send them to the patient listing to choose, consistent with the
        # carer default landing page.
        return redirect(reverse("patientslisting"))
