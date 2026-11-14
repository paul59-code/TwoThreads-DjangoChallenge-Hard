from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

def initial_health():
    return settings.WAR_INITIAL_HEALTH

class Person(models.Model):
    external_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=250)
    age = models.PositiveIntegerField()
    key = models.TextField(blank=True, null=True)
    rank = models.CharField(max_length=100, null=True, blank=True)
    health = models.BigIntegerField(default=initial_health)
    attributes = models.JSONField(default=dict, blank=True)
    def __str__(self):
        return f'{self.name} (#{self.external_id})'

class DraftBatch(models.Model):
    source = models.TextField(unique=True)
    payload = models.JSONField(null=True)
    status = models.CharField(max_length=20, default='PENDING', db_index=True)
    download_task_id = models.CharField(max_length=100, blank=True)
    draft_task_id = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

class Fight(models.Model):
    external_id = models.CharField(max_length=250, unique=True)
    blue_soldier = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='fights_first')
    red_soldier = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='fights_second')
    status = models.CharField(max_length=20, default='PENDING', db_index=True)
    queued = models.BooleanField(default=False)
    task_id = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)
    initial_health = models.JSONField(default=dict)
    final_health = models.JSONField(default=dict)
    result = models.TextField(blank=True)
    source_data = models.JSONField(default=dict)
    class Meta:
        constraints = [models.CheckConstraint(condition=~models.Q(blue_soldier=models.F('red_soldier')), name='different_fight_participants')]

class FightEvent(models.Model):
    fight = models.ForeignKey(Fight, on_delete=models.CASCADE, related_name='events')
    attacker = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='attacks')
    defender = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='defences')
    damage = models.PositiveBigIntegerField()
    event_index = models.PositiveIntegerField()
    processed = models.BooleanField(default=False)
    health_before = models.BigIntegerField(null=True)
    health_after = models.BigIntegerField(null=True)
    source_data = models.JSONField(default=dict)
    class Meta:
        ordering = ['event_index']
        constraints = [models.UniqueConstraint(fields=['fight', 'event_index'], name='unique_fight_event')]
    def clean(self):
        if {self.attacker_id, self.defender_id} != {self.fight.blue_soldier_id, self.fight.red_soldier_id}:
            raise ValidationError('Attacker and defender must be the two distinct fight participants.')

