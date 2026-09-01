from unittest.mock import Mock

from django.test import TestCase

from rdrf.forms.consent_forms import CustomConsentFormGenerator
from rdrf.models.definition.models import (
    ConsentQuestion,
    ConsentSection,
    Registry,
)


class ConsentFormTests(TestCase):
    def setUp(self):
        self.registry = Registry.objects.create(code="consenttst")
        self.section = ConsentSection.objects.create(
            code="ConsentSection",
            registry=self.registry,
            section_label="Consent section",
            validation_rule="requiredconsent",
        )
        self.required_question = ConsentQuestion.objects.create(
            code="requiredconsent",
            position=1,
            section=self.section,
            question_label="I confirm the required consent.",
        )
        self.optional_question = ConsentQuestion.objects.create(
            code="optionalconsent",
            position=2,
            section=self.section,
            question_label="I confirm an optional consent.",
        )
        self.viewing_user = Mock(is_clinician=False)

    def test_single_question_validation_rule_is_a_field_error(self):
        form = CustomConsentFormGenerator(
            self.registry, viewing_user=self.viewing_user
        ).create_form({self.optional_question.field_key: "on"})

        self.assertFalse(form.is_valid())
        self.assertFalse(form.fields[self.required_question.field_key].required)
        self.assertEqual(
            form.errors[self.required_question.field_key],
            ["Please confirm this consent before saving."],
        )
        self.assertNotIn("Consent Section", form.errors.as_text())