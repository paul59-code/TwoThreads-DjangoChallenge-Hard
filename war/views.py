from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .models import Fight, FightEvent, Person
from .services import reset_all, simulate_pending


@require_http_methods(["GET", "POST"])
def simulate(request):
    """GET: rejoacă luptele nerejucate (în paralel) și afișează rezultatele.
    POST cu `reset`: readuce totul la început și redirecționează înapoi."""
    if request.method == "POST":
        if "reset" in request.POST:
            reset_all()
        return redirect("simulate")

    simulated_now = simulate_pending()

    fights = []
    queryset = Fight.objects.select_related("soldier_a", "soldier_b").prefetch_related(
        "events__attacker", "events__defender"
    )
    for fight in queryset:
        events = list(fight.events.all())
        dealt = {fight.soldier_a_id: 0, fight.soldier_b_id: 0}
        for event in events:
            dealt[event.attacker_id] = dealt.get(event.attacker_id, 0) + event.damage
        a, b = fight.soldier_a, fight.soldier_b
        if dealt[a.id] == dealt[b.id]:
            winner = None
        else:
            winner = a if dealt[a.id] > dealt[b.id] else b
        fights.append(
            {"fight": fight, "events": events, "dealt_a": dealt[a.id], "dealt_b": dealt[b.id], "winner": winner}
        )

    context = {
        "fights": fights,
        "simulated_now": simulated_now,
        "soldiers": Person.objects.all(),
        "keyed": Person.objects.exclude(key__isnull=True).exclude(key=""),
        "totals": {
            "people": Person.objects.count(),
            "fights": Fight.objects.count(),
            "events": FightEvent.objects.count(),
            "damage": FightEvent.objects.filter(applied=True).aggregate(s=Sum("damage"))["s"] or 0,
        },
    }
    return render(request, "war/simulate.html", context)
