import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from datetime import datetime, timedelta, date
from django.utils import timezone
import mercadopago
from .models import Horario, Reserva

def lista_horarios(request):
    # 1. Busca todos os horários ativos
    horarios = Horario.objects.filter(ativo=True)
    
    # 2. Mapa completo com os 7 dias da semana
    mapa_dias = {
        'DOM': 6, 
        'SEG': 0, 
        'TER': 1, 
        'QUA': 2, 
        'QUI': 3, 
        'SEX': 4, 
        'SAB': 5
    }
    
    agora = timezone.localtime(timezone.now())
    hoje = agora.date()
    
    # 3. Passa por cada horário calculando a sua próxima data real
    for horario in horarios:
        dia_alvo = mapa_dias[horario.dia_semana]
        dias_faltando = (dia_alvo - hoje.weekday() + 7) % 7
        
        # Se a aula for hoje, mas o horário já passou, agenda para a semana que vem
        if dias_faltando == 0 and agora.time() > horario.hora_inicio:
            dias_faltando = 7
            
        # Cria um atributo temporário na memória chamado 'proxima_data'
        horario.proxima_data = hoje + timedelta(days=dias_faltando)
    
    # 4. Envia os dados atualizados para o HTML
    contexto = {
        'horarios': horarios
    }
    return render(request, 'app_reservas/lista_horarios.html', contexto)

def detalhes_reserva(request, horario_id):
    horario = get_object_or_404(Horario, id=horario_id)
    
    # --- Cálculo da Data ---
    mapa_dias = {'DOM': 6, 'SEG': 0, 'TER': 1, 'QUA': 2, 'QUI': 3, 'SEX': 4, 'SAB': 5}
    agora = timezone.localtime(timezone.now())
    hoje = agora.date()
    dia_alvo = mapa_dias[horario.dia_semana]
    dias_faltando = (dia_alvo - hoje.weekday() + 7) % 7
    if dias_faltando == 0 and agora.time() > horario.hora_inicio:
        dias_faltando = 7
    data_proxima_aula = hoje + timedelta(days=dias_faltando)

    # --- NOVA BUSCA: Recolha as reservas ativas para esta turma ---
    reservas_turma = Reserva.objects.filter(
        horario=horario, data_aula=data_proxima_aula
    ).exclude(status='CANCELADO')

    # --- Lógica do Botão Confirmar (POST) ---
    if request.method == 'POST':
        # Conta o total usando a nossa busca já existente
        vagas_ocupadas = reservas_turma.count()

        if vagas_ocupadas >= horario.vagas_totais:
            messages.error(request, 'Desculpe, a última vaga foi preenchida.')
            return redirect('lista_horarios')
        
        atleta_logado = None
        nome_comprador = ""
        telefone_comprador = ""

        if request.user.is_authenticated:
            atleta_logado = request.user
            nome_comprador = request.user.first_name
            
            if request.user.tipo_plano == 'MENSAL' and getattr(request.user, 'aulas_restantes', 0) > 0:
                Reserva.objects.create(
                    atleta=request.user,
                    horario=horario,
                    data_aula=data_proxima_aula,
                    status='PAGO'
                )
                request.user.aulas_restantes -= 1
                request.user.save()
                messages.success(request, f'Reserva confirmada! Você usou 1 aula do seu pacote. Restam: {request.user.aulas_restantes}.')
                return redirect('lista_horarios')
                
        else:
            nome_comprador = request.POST.get('nome_avulso', 'Visitante')
            telefone_comprador = request.POST.get('telefone_avulso', '')
            
            if not nome_comprador or not telefone_comprador:
                messages.error(request, 'Por favor, preencha seu Nome e WhatsApp.')
                return redirect('detalhes_reserva', horario_id=horario.id)

        # Guarda a reserva inicial como PENDENTE
        nova_reserva = Reserva.objects.create(
            atleta=atleta_logado,
            nome_avulso=nome_comprador if not atleta_logado else "",
            telefone_avulso=telefone_comprador if not atleta_logado else "",
            horario=horario,
            data_aula=data_proxima_aula,
            status='PENDENTE'
        )

        sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)

        payment_data = {
            "transaction_amount": 20.00,
            "description": f"Reserva Kata Archery - {horario.get_dia_semana_display()}",
            "payment_method_id": "pix",
            "payer": {
                "email": "test@testuser.com", 
                "first_name": nome_comprador,
            }
        }

        result = sdk.payment().create(payment_data)
        payment = result["response"]

        if "id" not in payment:
            nova_reserva.delete()
            messages.error(request, 'Erro ao gerar o pagamento. Verifique com o clube.')
            return redirect('lista_horarios')

        nova_reserva.id_transacao_mp = str(payment["id"])
        nova_reserva.save()

        pix_copia_cola = payment['point_of_interaction']['transaction_data']['qr_code']
        qr_code_img = payment['point_of_interaction']['transaction_data']['qr_code_base64']

        contexto_pix = {
            'reserva': nova_reserva,
            'pix_copia_cola': pix_copia_cola,
            'qr_code_img': qr_code_img
        }
        return render(request, 'app_reservas/checkout_pix.html', contexto_pix)

    # --- Lógica de Exibir a Tela (GET) ---
    contexto = {
        'horario': horario,
        'data_aula': data_proxima_aula,
        'reservas_turma': reservas_turma  # <-- Enviando a lista de alunos para a página
    }
    return render(request, 'app_reservas/detalhes_reserva.html', contexto)

@csrf_exempt
def mercadopago_webhook(request):
    if request.method == 'POST':
        try:
            # O Mercado Pago envia os dados no corpo (body) da requisição
            data = json.loads(request.body)
            
            # Verifica se o aviso é sobre um "pagamento"
            if data.get('type') == 'payment':
                payment_id = data.get('data', {}).get('id')
                
                # Regra de Segurança: Nunca confie cegamente no aviso. 
                # Pergunte ativamente ao Mercado Pago o status real desse ID.
                sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
                payment_info = sdk.payment().get(payment_id)
                
                if payment_info["status"] == 200: # A API respondeu com sucesso
                    status_pagamento = payment_info["response"]["status"]
                    
                    # Busca a nossa reserva no banco usando o ID da transação
                    reserva = Reserva.objects.filter(id_transacao_mp=str(payment_id)).first()
                    
                    if reserva and status_pagamento == 'approved':
                        reserva.status = 'PAGO'
                        reserva.save()
                        # A partir daqui, o nome do aluno é garantido na lista de presença
                        
        except Exception as e:
            # Em produção, o ideal é salvar esse erro em um arquivo de log
            print(f"Erro no processamento do webhook: {e}")
            
        # O Mercado Pago exige que seu servidor responda "200 OK" rápido, 
        # senão ele acha que deu erro e fica reenviando a mensagem.
        return JsonResponse({'status': 'ok'}, status=200)

    # Se alguém tentar acessar a URL pelo navegador (GET), bloqueia.
    return JsonResponse({'error': 'Método não permitido'}, status=405)

@staff_member_required(login_url='login')
def painel_instrutor(request):
    hoje = date.today()
    
    # Busca apenas reservas de hoje para frente que estejam pagas
    reservas_confirmadas = Reserva.objects.filter(
        data_aula__gte=hoje,
        status='PAGO'
    ).order_by('data_aula', 'horario__hora_inicio')

    contexto = {
        'reservas': reservas_confirmadas,
        'hoje': hoje
    }
    return render(request, 'app_reservas/painel_instrutor.html', contexto)

@staff_member_required(login_url='login')
def atualizar_presenca(request, reserva_id, acao):
    reserva = get_object_or_404(Reserva, id=reserva_id)
    
    # Apenas como segurança, garantimos que é um POST
    if request.method == 'POST':
        if acao == 'compareceu':
            reserva.status = 'COMPARECEU'
            messages.success(request, f'✅ Presença de {reserva.atleta.first_name} confirmada!')
        elif acao == 'faltou':
            reserva.status = 'FALTOU'
            messages.warning(request, f'❌ Falta de {reserva.atleta.first_name} registrada.')
            
        reserva.save()
        
    return redirect('painel_instrutor')