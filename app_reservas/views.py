import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from datetime import datetime, timedelta
import mercadopago
from .models import Horario, Reserva

def lista_horarios(request):
    # Busca todos os horários marcados como 'ativo=True'
    horarios = Horario.objects.filter(ativo=True)
    
    # Prepara os dados para enviar ao HTML
    contexto = {
        'horarios': horarios
    }
    return render(request, 'app_reservas/lista_horarios.html', contexto)

@login_required
def detalhes_reserva(request, horario_id):
    horario = get_object_or_404(Horario, id=horario_id)
    
    # --- Cálculo da Data (Mantém igual) ---
    mapa_dias = {'SEG': 0, 'TER': 1, 'QUI': 3, 'SAB': 5}
    dia_alvo = mapa_dias[horario.dia_semana]
    agora = datetime.now()
    hoje = agora.date()
    dias_faltando = (dia_alvo - hoje.weekday() + 7) % 7
    if dias_faltando == 0 and agora.time() > horario.hora_inicio:
        dias_faltando = 7
    data_proxima_aula = hoje + timedelta(days=dias_faltando)

    # --- Lógica do Botão Confirmar (POST) ---
    if request.method == 'POST':
        vagas_ocupadas = Reserva.objects.filter(
            horario=horario, data_aula=data_proxima_aula
        ).exclude(status='CANCELADO').count()

        if vagas_ocupadas >= horario.vagas_totais:
            messages.error(request, 'Desculpe, a última vaga foi preenchida.')
            return redirect('lista_horarios')
        
        # --- NOVA LÓGICA: Mensalista ---
        # Verifica se é plano mensal e se tem saldo de aulas
        if request.user.tipo_plano == 'MENSAL' and request.user.aulas_restantes > 0:
            
            # Cria a reserva já confirmada
            nova_reserva = Reserva.objects.create(
                atleta=request.user,
                horario=horario,
                data_aula=data_proxima_aula,
                status='PAGO' # O status 'PAGO' garante o nome na lista
            )
            
            # Desconta 1 aula do pacote do aluno e salva no banco
            request.user.aulas_restantes -= 1
            request.user.save()

            messages.success(request, f'Reserva confirmada! Você usou 1 aula do seu pacote. Restam: {request.user.aulas_restantes}.')
            return redirect('lista_horarios')

        # 1. Salva a reserva inicial como PENDENTE
        nova_reserva = Reserva.objects.create(
            atleta=request.user,
            horario=horario,
            data_aula=data_proxima_aula,
            status='PENDENTE'
        )

        # 2. Configura o SDK do Mercado Pago
        sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)

        # 3. Prepara os dados do Pix
        # Nota: O Mercado Pago exige um e-mail. Se o usuário não tiver, passamos um fictício.
        email_aluno = request.user.email if request.user.email else "aluno@kataarchery.com"
        
        payment_data = {
            "transaction_amount": 20.00,
            "description": f"Reserva Kata Archery - {horario.get_dia_semana_display()}",
            "payment_method_id": "pix",
            "payer": {
                "email": email_aluno,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
            }
        }

        # 4. Faz a requisição para gerar o Pix
        result = sdk.payment().create(payment_data)
        payment = result["response"]

        # Se houver erro na API (ex: chave errada), cancela a reserva e avisa
        if "id" not in payment:
            nova_reserva.delete()
            messages.error(request, 'Erro ao gerar o pagamento. Verifique com o clube.')
            return redirect('lista_horarios')

        # 5. Salva o ID da transação no banco (Essencial para o Webhook depois!)
        nova_reserva.id_transacao_mp = str(payment["id"])
        nova_reserva.save()

        # 6. Extrai o "Copia e Cola" e o QR Code em Base64
        pix_copia_cola = payment['point_of_interaction']['transaction_data']['qr_code']
        qr_code_img = payment['point_of_interaction']['transaction_data']['qr_code_base64']

        # 7. Redireciona para a tela mostrando o Pix
        contexto_pix = {
            'reserva': nova_reserva,
            'pix_copia_cola': pix_copia_cola,
            'qr_code_img': qr_code_img
        }
        return render(request, 'app_reservas/checkout_pix.html', contexto_pix)

    # --- Lógica de Exibir a Tela (GET) ---
    contexto = {
        'horario': horario,
        'data_aula': data_proxima_aula
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