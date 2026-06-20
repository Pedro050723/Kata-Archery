from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

class Atleta(AbstractUser):
    TIPO_PLANO_CHOICES = [
        ('AVULSO', 'Avulso'),
        ('MENSAL', 'Mensalista'),
    ]
    
    tipo_plano = models.CharField(
        max_length=10, 
        choices=TIPO_PLANO_CHOICES, 
        default='AVULSO'
    )
    aulas_restantes = models.IntegerField(default=0)
    telefone = models.CharField(max_length=15, blank=True, null=True)

    def __str__(self):
        # get_full_name() é uma função nativa que junta first_name e last_name.
        # Se for vazio, ele usa o username como plano B (or self.username)
        nome_exibicao = self.get_full_name() or self.username
        return f"{nome_exibicao} - {self.tipo_plano}"

class Horario(models.Model):
    DIAS_SEMANA = [
        ('DOM', 'Domingo'),
        ('SEG', 'Segunda-feira'),
        ('TER', 'Terça-feira'),
        ('QUA', 'Quarta-feira'),
        ('QUI', 'Quinta-feira'),
        ('SEX', 'Sexta-feira'),
        ('SAB', 'Sábado'),
    ]

    data_exata = models.DateField(
        null=True, 
        blank=True, 
        help_text="Preencha APENAS se for um evento de dia único. Deixe em branco para turmas que se repetem toda semana."
    )

    dia_semana = models.CharField(max_length=3, choices=DIAS_SEMANA)
    hora_inicio = models.TimeField()
    hora_fim = models.TimeField()
    vagas_totais = models.IntegerField(default=10) # A trava de 10 vagas
    ativo = models.BooleanField(default=True) # Permite desativar um horário sem apagar do banco

    class Meta:
        ordering = ['dia_semana', 'hora_inicio']
        # Evita criar dois horários idênticos no banco
        unique_together = ['dia_semana', 'hora_inicio', 'hora_fim']

    def __str__(self):
        return f"{self.get_dia_semana_display()} - {self.hora_inicio.strftime('%H:%M')} às {self.hora_fim.strftime('%H:%M')}"


class Reserva(models.Model):
    STATUS_PAGAMENTO = [
        ('PENDENTE', 'Aguardando Pix'),
        ('PAGO', 'Confirmado'),
        ('CANCELADO', 'Cancelado/Expirado'),
        ('COMPARECEU', 'Compareceu'),
        ('FALTOU', 'Faltou'),
    ]

    atleta = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True
    )
    horario = models.ForeignKey(Horario, on_delete=models.PROTECT, related_name='reservas_horario')
    data_aula = models.DateField() # Para saber qual terça-feira específica é a aula
    status = models.CharField(max_length=10, choices=STATUS_PAGAMENTO, default='PENDENTE')
    nome_avulso = models.CharField(max_length=100, blank=True, null=True)
    telefone_avulso = models.CharField(max_length=20, blank=True, null=True)
    
    # Rastreabilidade para o Webhook do Mercado Pago
    id_transacao_mp = models.CharField(max_length=255, blank=True, null=True) 
    
    # Para a rotina de cancelar após 15 min
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-data_aula', 'horario__hora_inicio']

    def __str__(self):
        # Se for um aluno logado, usa o nome dele. Se não, usa o nome do avulso.
        nome = self.atleta.first_name if self.atleta else self.nome_avulso
        
        # Opcional: formatação de data para ficar bonito no painel
        data_formatada = self.data_aula.strftime("%d/%m") if self.data_aula else "Sem data"
        
        return f"{nome} - {self.horario.get_dia_semana_display()} ({data_formatada})"