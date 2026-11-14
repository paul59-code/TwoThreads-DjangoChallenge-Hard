from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from .models import Fight, DraftBatch
from .services import dispatch_fights

@require_http_methods(['GET', 'POST'])
def simulate(request):
    if request.method == 'POST':
        try:
            count = dispatch_fights()
            messages.success(request, f'Queued {count} fight tasks.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect('simulate')
    fights = Fight.objects.select_related('blue_soldier', 'red_soldier').prefetch_related('events__attacker', 'events__defender').order_by('pk')
    return render(request, 'war/simulate.html', {'fights': fights, 'active': Fight.objects.filter(queued=True).exists(), 'batches': DraftBatch.objects.all()})
