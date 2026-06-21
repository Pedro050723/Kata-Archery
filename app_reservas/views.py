import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import logout
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from datetime import datetime, timedelta, date
from django.utils import timezone
import mercadopago
from .models import Horario, Reserva

def lista_horarios(request):
    horarios = Horario.objects.filter(ativo=True)
    mapa_dias = {'DOM': 6, 'SEG': 0, 'TER': 1, 'QUA': 2, 'QUI': 3, 'SEX': 4, 'SAB': 5}
    agora = timezone.localtime(timezone.now())
    hoje = agora.date()
    
    # Vamos criar uma nova lista apenas com as turmas que ainda não passaram
    horarios_disponiveis = []
    
    for horario in horarios:
        # SE FOR UM EVENTO ÚNICO (Tem data_exata)
        if horario.data_exata:
            # Verifica se o evento já passou (Data antiga OU Data de hoje mas horário já passou)
            if hoje > horario.data_exata or (hoje == horario.data_exata and agora.time() > horario.hora_inicio):
                continue # Pula este horário, ele não vai para a tela
                
            horario.proxima_data = horario.data_exata
            
        # SE FOR UMA TURMA SEMANAL COMUM (Não tem data_exata)
        else:
            dia_alvo = mapa_dias[horario.dia_semana]
            dias_faltando = (dia_alvo - hoje.weekday() + 7) % 7
            if dias_faltando == 0 and agora.time() > horario.hora_inicio:
                dias_faltando = 7
            horario.proxima_data = hoje + timedelta(days=dias_faltando)
            
        horarios_disponiveis.append(horario)
    
    contexto = {
        'horarios': horarios_disponiveis # Passa a lista filtrada para o HTML
    }
    return render(request, 'app_reservas/lista_horarios.html', contexto)

def detalhes_reserva(request, horario_id):
    horario = get_object_or_404(Horario, id=horario_id)
    agora = timezone.localtime(timezone.now())
    hoje = agora.date()
    
    # --- 1. CÁLCULO DA DATA DA AULA ---
    if horario.data_exata:
        data_proxima_aula = horario.data_exata
        if hoje > data_proxima_aula or (hoje == data_proxima_aula and agora.time() > horario.hora_inicio):
            messages.error(request, 'Este evento já foi encerrado.')
            return redirect('lista_horarios')
    else:
        mapa_dias = {'DOM': 6, 'SEG': 0, 'TER': 1, 'QUA': 2, 'QUI': 3, 'SEX': 4, 'SAB': 5}
        dia_alvo = mapa_dias[horario.dia_semana]
        dias_faltando = (dia_alvo - hoje.weekday() + 7) % 7
        if dias_faltando == 0 and agora.time() > horario.hora_inicio:
            dias_faltando = 7
        data_proxima_aula = hoje + timedelta(days=dias_faltando)

    # --- 2. VERIFICAÇÃO DE VAGAS (Bloqueia o espaço no banco) ---
    vagas_ocupadas = Reserva.objects.filter(
        horario=horario, 
        data_aula=data_proxima_aula, 
        status__in=['PAGO', 'PENDENTE']
    ).count()
    vagas_restantes = horario.vagas_totais - vagas_ocupadas

    # CORREÇÃO BUG 2: Lista pública mostra APENAS quem já pagou
    reservas_confirmadas_tela = Reserva.objects.filter(
        horario=horario,
        data_aula=data_proxima_aula,
        status='PAGO'
    )

    # --- 3. FLUXO DE RESERVA (MÉTODO POST) ---
    if request.method == 'POST':
        if vagas_restantes <= 0:
            messages.error(request, 'Desculpe, esta turma já está lotada.')
            return redirect('detalhes_reserva', horario_id=horario.id)

        # 3.1 Identificação do Usuário
        if request.user.is_authenticated:
            nome_comprador = request.user.first_name
            email_comprador = request.user.email if request.user.email else f"{request.user.username}@kataarchery.com"
            
            # Mensalista com saldo aprova na hora
            if request.user.tipo_plano == 'MENSAL' and getattr(request.user, 'aulas_restantes', 0) > 0:
                Reserva.objects.create(
                    atleta=request.user, horario=horario, data_aula=data_proxima_aula, status='PAGO'
                )
                request.user.aulas_restantes -= 1
                request.user.save()
                messages.success(request, f'Reserva confirmada! Restam: {request.user.aulas_restantes} aulas.')
                return redirect('lista_horarios')
                
        else:
            nome_comprador = request.POST.get('nome_avulso', 'Visitante')
            telefone_comprador = request.POST.get('telefone_avulso', '')
            
            if not nome_comprador or not telefone_comprador:
                messages.error(request, 'Por favor, preencha seu Nome e WhatsApp.')
                return redirect('detalhes_reserva', horario_id=horario.id)
                
            telefone_limpo = ''.join(filter(str.isdigit, telefone_comprador))
            email_comprador = f"avulso.{telefone_limpo}@kataarchery.com"

        # CORREÇÃO BUG 1: Evitar duplicação por F5 (Reaproveita se já existir Pendente)
        # 3.2 Cria a Reserva como PENDENTE no Banco de Dados (Evitando Duplicação)
        if request.user.is_authenticated:
            reserva = Reserva.objects.filter(
                atleta=request.user, horario=horario, data_aula=data_proxima_aula, status='PENDENTE'
            ).first()
            
            if not reserva:
                # CORREÇÃO: Se o primeiro nome estiver em branco, usa o username como garantia
                nome_gravar = request.user.first_name if request.user.first_name else request.user.username
                
                reserva = Reserva.objects.create(
                    atleta=request.user,
                    nome_avulso=nome_gravar, # <-- Agora gravamos o seu nome real aqui também!
                    horario=horario,
                    data_aula=data_proxima_aula,
                    status='PENDENTE'
                )
        else:
            reserva = Reserva.objects.filter(
                nome_avulso=nome_comprador, telefone_avulso=telefone_comprador, horario=horario, data_aula=data_proxima_aula, status='PENDENTE'
            ).first()
            
            if not reserva:
                reserva = Reserva.objects.create(
                    nome_avulso=nome_comprador,
                    telefone_avulso=telefone_comprador,
                    horario=horario,
                    data_aula=data_proxima_aula,
                    status='PENDENTE'
                )

        # 3.3 Dados do Mercado Pago
        payment_data = {
            "transaction_amount": 20.00,
            "description": f"Reserva Kata Archery - {horario.get_dia_semana_display()}",
            "payment_method_id": "pix",
            "payer": {
                "email": email_comprador,
                "first_name": nome_comprador,
            },
            "external_reference": str(reserva.id),
            "notification_url": "https://www.clubekataarchery.com.br/webhook/pix/"
        }

        try:
            sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
            payment_response = sdk.payment().create(payment_data)
            payment = payment_response["response"]
            
            if payment_response["status"] == 201:
                qr_code_base64 = payment['point_of_interaction']['transaction_data']['qr_code_base64']
                qr_code_copia_cola = payment['point_of_interaction']['transaction_data']['qr_code']
                
                contexto_pagamento = {
                    'horario': horario,
                    'data_proxima_aula': data_proxima_aula,
                    'qr_code_base64': qr_code_base64,
                    'qr_code_copia_cola': qr_code_copia_cola,
                    'reserva_id': reserva.id
                }
                return render(request, 'app_reservas/pagamento_pix.html', contexto_pagamento)
            else:
                print(f"\n--- ERRO MERCADO PAGO ---\n{payment}")
                reserva.delete()
                messages.error(request, 'Erro ao gerar o pagamento. Verifique com o clube.')
                return redirect('detalhes_reserva', horario_id=horario.id)
                
        except Exception as e:
            print(f"Erro na API: {e}")
            reserva.delete()
            messages.error(request, 'Erro interno. Tente novamente.')
            return redirect('detalhes_reserva', horario_id=horario.id)

    # --- 4. EXIBIÇÃO DA TELA (MÉTODO GET) ---
    contexto = {
        'horario': horario,
        'data_proxima_aula': data_proxima_aula,
        'vagas_restantes': vagas_restantes,
        'vagas_totais': horario.vagas_totais,
        'reservas': reservas_confirmadas_tela, # Exibe apenas os confirmados de fato
    }
    return render(request, 'app_reservas/detalhes_reserva.html', contexto)
@csrf_exempt
def mercadopago_webhook(request):
    if request.method == 'POST':
        try:
            # O Mercado Pago envia os dados no corpo (body) da requisição
            data = json.loads(request.body)
            
            # Verifica se o aviso é sobre um pagamento (pode vir como 'type' ou 'action')
            if data.get('type') == 'payment' or data.get('action') == 'payment.created':
                payment_id = data.get('data', {}).get('id')
                
                if payment_id:
                    # Regra de Segurança: Nunca confie cegamente no aviso. 
                    # Pergunte ativamente ao Mercado Pago o status real desse ID.
                    sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
                    payment_info = sdk.payment().get(payment_id)
                    
                    if payment_info["status"] == 200: # A API respondeu com sucesso
                        pagamento = payment_info["response"]
                        status_pagamento = pagamento.get("status")
                        
                        # Pegamos o ID da nossa reserva que enviamos na hora de gerar o Pix
                        reserva_id = pagamento.get("external_reference")
                        
                        if reserva_id and status_pagamento == 'approved':
                            # Busca a nossa reserva pendente no banco usando o ID dela
                            reserva = Reserva.objects.filter(id=reserva_id, status='PENDENTE').first()
                            
                            if reserva:
                                reserva.status = 'PAGO'
                                reserva.save()
                                # A partir daqui, o nome do aluno é garantido na lista de presença
                        
        except Exception as e:
            # Em produção, fica salvo no server.log em caso de erro
            print(f"Erro no processamento do webhook: {e}")
            
        # O Mercado Pago exige que seu servidor responda "200 OK" rápido, 
        # senão ele acha que deu erro e fica reenviando a mensagem.
        return JsonResponse({'status': 'ok'}, status=200)

    # Se alguém tentar acessar a URL pelo navegador (GET), bloqueia.
    return JsonResponse({'error': 'Método não permitido'}, status=405)

@staff_member_required(login_url='/admin/login')
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

def sair_conta(request):
    logout(request)
    messages.info(request, "Você saiu da sua conta com segurança. Até a próxima!")
    return redirect('lista_horarios')