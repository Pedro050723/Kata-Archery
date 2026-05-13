from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Atleta, Horario, Reserva

# Registra o seu usuário customizado no admin
admin.site.register(Atleta, UserAdmin)

@admin.register(Horario)
class HorarioAdmin(admin.ModelAdmin):
    list_display = ('dia_semana', 'hora_inicio', 'hora_fim', 'vagas_totais', 'ativo')
    list_filter = ('dia_semana', 'ativo')

@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('atleta', 'horario', 'data_aula', 'status', 'criado_em')
    list_filter = ('status', 'data_aula', 'horario__dia_semana')
    search_fields = ('atleta__first_name', 'atleta__last_name')