from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("disputes", "0013_calendarnote_deleted_at_calendarnote_is_deleted"),
    ]

    operations = [
        migrations.AddField(
            model_name="mediationsession",
            name="host_link",
            field=models.URLField(
                blank=True, help_text="Mediator's host link for the meeting"
            ),
        ),
        migrations.AlterField(
            model_name="mediationsession",
            name="zoom_link",
            field=models.URLField(blank=True),
        ),
    ]
