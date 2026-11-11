from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("report", "0005_reportdesign_exclude_working_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportdesign",
            name="custom_filters",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
