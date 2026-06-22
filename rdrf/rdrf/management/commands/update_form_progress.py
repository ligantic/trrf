import sys

from django.core.management.base import BaseCommand
from registry.patients.models import Patient

from rdrf.forms.progress.form_progress import FormProgress
from rdrf.helpers.registry_features import RegistryFeatures
from rdrf.models.definition.models import Registry


class Command(BaseCommand):
    help = "Recalculates form progress for all patients"

    def add_arguments(self, parser):
        parser.add_argument("registry_code")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be recalculated without writing any progress records.",
        )
        parser.add_argument(
            "--patient-id",
            dest="patient_ids",
            action="append",
            type=int,
            default=None,
            help="Limit to the given patient id. May be repeated to target several patients.",
        )

    def handle(self, registry_code, **options):
        self.registry_model = None
        try:
            self.registry_model = Registry.objects.get(code=registry_code)
        except Registry.DoesNotExist:
            self.stderr.write(
                "Error: Unknown registry code: %s" % registry_code
            )
            sys.exit(1)
            return

        if self.registry_model is not None:
            self._update_progress(
                dry_run=options["dry_run"],
                patient_ids=options["patient_ids"],
            )
            if options["dry_run"]:
                self.stdout.write("Dry run complete (no changes written)")
            else:
                self.stdout.write("Progress recalculated OK")

    def _update_progress(self, dry_run=False, patient_ids=None):
        form_progress = FormProgress(self.registry_model)

        uses_contexts = self.registry_model.has_feature(
            RegistryFeatures.CONTEXTS
        )

        patient_qs = Patient.objects.filter(
            rdrf_registry__in=[self.registry_model]
        )
        if patient_ids:
            patient_qs = patient_qs.filter(pk__in=patient_ids)

        patients_processed = 0
        contexts_processed = 0

        for patient_model in patient_qs:
            if not uses_contexts:
                default_context = patient_model.default_context(
                    self.registry_model
                )
                if not dry_run:
                    form_progress.save_for_patient(
                        patient_model, default_context
                    )
                patients_processed += 1
                contexts_processed += 1
                self.stdout.write(
                    "%sRecalculated progress for Patient %s"
                    % ("[dry-run] " if dry_run else "", patient_model.pk)
                )
            else:
                contexts = [
                    context_model
                    for context_model in patient_model.context_models
                    if context_model.registry_id == self.registry_model.id
                ]
                if not contexts:
                    self.stdout.write(
                        "No contexts for Patient %s, skipping"
                        % patient_model.pk
                    )
                    continue
                for context_model in contexts:
                    if not dry_run:
                        form_progress.save_for_patient(
                            patient_model, context_model
                        )
                patients_processed += 1
                contexts_processed += len(contexts)
                self.stdout.write(
                    "%sRecalculated progress for Patient %s (%d contexts)"
                    % (
                        "[dry-run] " if dry_run else "",
                        patient_model.pk,
                        len(contexts),
                    )
                )

        self.stdout.write(
            "%s%d patient(s), %d context(s) %s"
            % (
                "[dry-run] " if dry_run else "",
                patients_processed,
                contexts_processed,
                "would be recalculated" if dry_run else "recalculated",
            )
        )
