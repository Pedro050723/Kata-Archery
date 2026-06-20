from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_horarios, name='lista_horarios'),
    path('reserva/<int:horario_id>/', views.detalhes_reserva, name='detalhes_reserva'),
    path('webhook/pix/', views.mercadopago_webhook, name='webhook_pix'),
    path('painel-instrutor/', views.painel_instrutor, name='painel_instrutor'),
    path('presenca/<int:reserva_id>/<str:acao>/', views.atualizar_presenca, name='atualizar_presenca'),
    path('sair/', views.sair_conta, name='sair_conta'),
]