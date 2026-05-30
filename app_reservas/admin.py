from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Atleta, Horario, Reserva

class AtletaAdmin(UserAdmin):
    # Adiciona a nossa seção "Informações do Plano" na tela de edição
    fieldsets = UserAdmin.fieldsets + (
        ('Informações do Plano', {'fields': ('tipo_plano', 'aulas_restantes')}),
    )
    # Mostra essas colunas na lista geral de usuários para facilitar sua vida
    list_display = ('username', 'email', 'first_name', 'last_name', 'tipo_plano', 'aulas_restantes')

# Registra o Atleta usando as novas regras
admin.site.register(Atleta, AtletaAdmin)

@admin.register(Horario)
class HorarioAdmin(admin.ModelAdmin):
    list_display = ('dia_semana', 'hora_inicio', 'hora_fim', 'vagas_totais', 'ativo')
    list_filter = ('dia_semana', 'ativo')

@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ('atleta', 'horario', 'data_aula', 'status', 'criado_em')
    list_filter = ('status', 'data_aula', 'horario__dia_semana')
    search_fields = ('atleta__first_name', 'atleta__last_name')