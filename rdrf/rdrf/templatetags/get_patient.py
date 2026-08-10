from django import template
from registry.patients.models import ParentGuardian, Patient

register = template.Library()


@register.simple_tag
def get_patient(patient_id):
    try:
        if not patient_id:
            return None
        patient = Patient.objects.get(pk=patient_id)
        return patient
    except Patient.DoesNotExist:
        return None


@register.simple_tag
def get_parent(user):
    if not user.is_authenticated or not user.is_parent:
        return None
    return ParentGuardian.objects.filter(user=user).first()
