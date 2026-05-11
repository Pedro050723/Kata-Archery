from django.contrib.auth.models import AbstractUser
from django.db import models

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
        return f"{self.first_name} {self.last_name} - {self.tipo_plano}"