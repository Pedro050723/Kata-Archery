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
    # As colunas que vão aparecer na lista principal
    list_display = ('id', 'obter_nome_aluno', 'telefone_avulso', 'data_aula', 'horario', 'status')
    
    # Filtros laterais para facilitar a busca no dia a dia
    list_filter = ('status', 'data_aula')
    
    # Barra de pesquisa (busca tanto pelo nome da conta quanto pelo nome digitado)
    search_fields = ('atleta__first_name', 'atleta__last_name', 'nome_avulso', 'telefone_avulso', 'id_transacao_mp')

    # Função inteligente para exibir o nome correto na coluna
    def obter_nome_aluno(self, obj):
        if obj.atleta:
            return f"{obj.atleta.first_name} {obj.atleta.last_name} (Logado)"
        return f"{obj.nome_avulso} (Avulso)"
    
    obter_nome_aluno.short_description = 'Nome do Aluno'