from django.db import models


class Person(models.Model):
    """Persoană înregistrată / soldat. `id` este cel primit de la API (nu auto-generat)."""

    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=200)
    age = models.IntegerField()
    health = models.IntegerField(default=100)  # scade pe măsură ce se rejoacă luptele
    rank = models.CharField(max_length=50, null=True, blank=True, db_index=True)  # Private/Sergeant/..., setat de drafting
    key = models.CharField(max_length=100, null=True, blank=True)  # indiciu pentru pasul următor (apare la Hellstorm Fireburn)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} (#{self.id})"


class Fight(models.Model):
    PENDING, RUNNING, DONE = "pending", "running", "done"
    STATUSES = [(PENDING, "pending"), (RUNNING, "running"), (DONE, "done")]

    # id-ul din API dacă există, altfel se generează la încărcare
    id = models.IntegerField(primary_key=True)
    soldier_a = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="fights_as_a")
    soldier_b = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="fights_as_b")
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING, db_index=True)

    class Meta:
        ordering = ["id"]


class FightEvent(models.Model):
    fight = models.ForeignKey(Fight, on_delete=models.CASCADE, related_name="events")
    order = models.PositiveIntegerField()  # poziția în luptă; păstrează ordinea evenimentelor
    attacker = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="attacks")
    defender = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="defenses")
    damage = models.IntegerField()
    # Completate la simulare:
    applied = models.BooleanField(default=False)
    defender_health_after = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["fight_id", "order"]
        constraints = [
            models.UniqueConstraint(fields=["fight", "order"], name="uniq_event_order_per_fight"),
        ]
