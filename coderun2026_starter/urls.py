from django.urls import path
from war.views import simulate
urlpatterns = [path('simulate', simulate, name='simulate')]
