from django.db import migrations, models

def add_rank(apps, schema_editor):
    person = apps.get_model('war', 'Person')
    columns = {c.name for c in schema_editor.connection.introspection.get_table_description(schema_editor.connection.cursor(), person._meta.db_table)}
    # Also supports the initial local bootstrap schema, which already had rank.
    if 'rank' not in columns:
        field = models.JSONField(blank=True, null=True)
        field.set_attributes_from_name('rank')
        schema_editor.add_field(person, field)

def remove_rank(apps, schema_editor):
    person = apps.get_model('war', 'Person')
    field = models.JSONField(blank=True, null=True)
    field.set_attributes_from_name('rank')
    schema_editor.remove_field(person, field)

class Migration(migrations.Migration):
    dependencies = [('war', '0001_initial')]
    operations = [migrations.SeparateDatabaseAndState(
        database_operations=[migrations.RunPython(add_rank, remove_rank)],
        state_operations=[migrations.AddField(model_name='person', name='rank', field=models.JSONField(blank=True, null=True))],
    )]
