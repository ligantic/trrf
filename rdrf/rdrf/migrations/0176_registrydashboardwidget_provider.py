from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rdrf", "0175_proinstrument_proinstrumentadministration_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="registrydashboardwidget",
            name="provider",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AlterField(
            model_name="registrydashboardwidget",
            name="widget_type",
            field=models.CharField(
                choices=[
                    ("demographics", "Demographics"),
                    ("clinical_data", "Clinical Data"),
                    ("registry_plugin", "Registry plugin"),
                    ("consents", "Consent"),
                    ("module_progress", "Module Progress"),
                ],
                max_length=50,
            ),
        ),
        migrations.AlterUniqueTogether(
            name="registrydashboardwidget",
            unique_together={
                ("registry_dashboard", "widget_type", "provider")
            },
        ),
    ]
