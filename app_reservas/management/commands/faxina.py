from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from app_reservas.models import Reserva

class Command(BaseCommand):
    help = 'Cancela reservas não pagas após 15 minutos'

    def handle(self, *args, **kwargs):
        # 1. Calcula qual era a hora exata de 15 minutos atrás
        limite_de_tempo = timezone.now() - timedelta(minutes=15)
        
        # 2. Busca no banco de dados quem está PENDENTE e foi criado ANTES desse limite
        reservas_vencidas = Reserva.objects.filter(
            status='PENDENTE', 
            criado_em__lt=limite_de_tempo
        )
        
        quantidade = reservas_vencidas.count()
        
        # 3. Altera o status de cada uma para CANCELADO para liberar a vaga
        for reserva in reservas_vencidas:
            reserva.status = 'CANCELADO'
            reserva.save()
            
        # 4. Imprime uma mensagem no terminal
        self.stdout.write(self.style.SUCCESS(f'Faxina concluída! {quantidade} reservas canceladas.'))