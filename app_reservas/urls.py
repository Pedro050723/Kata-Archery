from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_horarios, name='lista_horarios'),
    path('reserva/<int:horario_id>/', views.detalhes_reserva, name='detalhes_reserva'),
]