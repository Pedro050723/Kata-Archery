from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from datetime import datetime, timedelta
from .models import Horario, Reserva

def lista_horarios(request):
    # Busca todos os horários marcados como 'ativo=True'
    horarios = Horario.objects.filter(ativo=True)
    
    # Prepara os dados para enviar ao HTML
    contexto = {
        'horarios': horarios
    }
    return render(request, 'app_reservas/lista_horarios.html', contexto)

@login_required(login_url='/admin/login/') # Se não estiver logado, manda pro painel admin por enquanto
def detalhes_reserva(request, horario_id):
    horario = get_object_or_404(Horario, id=horario_id)
    
    # --- Cálculo da Data (Mantido igual) ---
    mapa_dias = {'SEG': 0, 'TER': 1, 'QUI': 3, 'SAB': 5}
    dia_alvo = mapa_dias[horario.dia_semana]
    agora = datetime.now()
    hoje = agora.date()
    dias_faltando = (dia_alvo - hoje.weekday() + 7) % 7
    
    if dias_faltando == 0 and agora.time() > horario.hora_inicio:
        dias_faltando = 7
        
    data_proxima_aula = hoje + timedelta(days=dias_faltando)

    # --- Lógica de Salvar a Reserva (O clique do botão) ---
    if request.method == 'POST':
        # 1. Conta quantas reservas já existem para este dia e horário (ignorando canceladas)
        vagas_ocupadas = Reserva.objects.filter(
            horario=horario, 
            data_aula=data_proxima_aula
        ).exclude(status='CANCELADO').count()

        # 2. Trava de capacidade: Impede de salvar se já tiver 10 pessoas
        if vagas_ocupadas >= horario.vagas_totais:
            messages.error(request, 'Desculpe, a última vaga foi preenchida neste exato momento.')
            return redirect('lista_horarios')

        # 3. Cria a reserva no banco de dados
        nova_reserva = Reserva.objects.create(
            atleta=request.user,
            horario=horario,
            data_aula=data_proxima_aula,
            status='PENDENTE'
        )

        # 4. Avisa o usuário e redireciona (futuramente, vai para a tela do Pix)
        messages.success(request, 'Reserva iniciada! Pagamento pendente.')
        return redirect('lista_horarios')

    # --- Lógica de Exibir a Tela (GET) ---
    contexto = {
        'horario': horario,
        'data_aula': data_proxima_aula
    }
    return render(request, 'app_reservas/detalhes_reserva.html', contexto)