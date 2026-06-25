import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import csv
import json
from pathlib import Path
import re
from datetime import datetime, date
import os
import signal
import sys
from dotenv import load_dotenv
import random

def _ssl_ctx():
    path = Path(__file__).resolve().parent / "ssl" / "gmail-ca-bundle.pem"
    ctx = ssl.create_default_context(cafile=str(path))
    ctx.verify_flags = ssl.VERIFY_X509_PARTIAL_CHAIN
    return ctx

def reconectar_smtp(max_tentativas=6):
    """Tenta reconectar ao servidor SMTP até max_tentativas vezes.
    Retorna o novo servidor ou lança ConnectionError se todas falharem."""
    ultimo_erro = None
    for tentativa in range(1, max_tentativas + 1):
        try:
            print(f"🔄 Tentativa {tentativa}/{max_tentativas} de reconexão SMTP...")
            time.sleep(5)
            if SMTP_PORT == 465:
                sv = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30, context=_ssl_ctx())
            else:
                sv = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
                sv.starttls(context=_ssl_ctx())
            sv.login(SMTP_USER, SMTP_PASS)
            print("✅ Reconectado com sucesso!")
            return sv
        except Exception as e:
            ultimo_erro = e
            print(f"   ❌ Tentativa {tentativa} falhou: {e}")
    raise ConnectionError(
        f"Não foi possível reconectar ao servidor SMTP após {max_tentativas} tentativas. "
        f"Último erro: {ultimo_erro}"
    )

def _eh_erro_conexao(erro):
    """Verifica se o erro está relacionado a perda de conexão SMTP."""
    if isinstance(erro, smtplib.SMTPServerDisconnected):
        return True
    texto = str(erro).lower()
    palavras = ["conexão com servidor perdida", "conexão perdida", "connection lost",
                "connection refused", "timed out", "timeout", "connection reset",
                "broken pipe", "server disconnected", "disconnect",
                "the server is not responding", "socket"]
    return any(p in texto for p in palavras)

# ============================================================
# CARREGA CONFIGURAÇÕES DO .ENV
# ============================================================
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print("✅ Arquivo .env carregado com sucesso!")
else:
    print(f"⚠️  Arquivo .env não encontrado em: {env_path}")
    print("   Por favor, crie o arquivo .env com suas configurações SMTP")
    sys.exit(1)

# Configurações do .env
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
SMTP_USER = os.getenv("SMTP_USERNAME", "")
SMTP_PASS = os.getenv("SMTP_PASSWORD", "")
FROM_NAME = os.getenv("FROM_NAME", "NewLeads - Prospecção Inteligente")
ASSUNTO = os.getenv("SUBJECT", "Leads segmentados NewLeads - Prospecção Inteligente")
TEMPLATE_PATH = os.getenv("TEMPLATE_PATH", "./templates/rhsudeste.html")
REPLY_TO = os.getenv("REPLY_TO", "")

# Configurações de envio
DELAY_MIN_SEGUNDOS = 2
DELAY_MAX_SEGUNDOS = 5
EMAILS_POR_DIA = 500
EMAILS_POR_LOTE = 50

# ============================================================
# CONFIGURAÇÕES DE PASTAS
# ============================================================
PASTA_RAIZ = Path(__file__).parent
PASTA_TEMPLATES = PASTA_RAIZ / "templates"
PASTA_LISTAS = PASTA_RAIZ / "listas"
PASTA_LOGS = PASTA_RAIZ / "logs"
PASTA_CHECKPOINTS = PASTA_RAIZ / "checkpoints"

# Arquivos de controle
ARQUIVO_CHECKPOINT = PASTA_CHECKPOINTS / "campanha_atual.json"
ARQUIVO_CANCELAMENTO = PASTA_CHECKPOINTS / "cancelar.txt"
ARQUIVO_PAUSA = PASTA_CHECKPOINTS / "pausar.txt"

# ============================================================
# CRIA PASTAS
# ============================================================
def criar_pastas():
    """Cria todas as pastas necessárias"""
    for pasta in [PASTA_TEMPLATES, PASTA_LISTAS, PASTA_LOGS, PASTA_CHECKPOINTS]:
        if not pasta.exists():
            pasta.mkdir(parents=True)
            print(f"📁 Pasta criada: {pasta}")
    print()

# ============================================================
# FUNÇÕES DE CONTROLE
# ============================================================
def verificar_pausa():
    """Verifica se a campanha foi pausada"""
    if ARQUIVO_PAUSA.exists():
        try:
            with open(ARQUIVO_PAUSA, "r", encoding="utf-8") as f:
                conteudo = f.read().strip()
                return conteudo.lower() == "sim"
        except:
            return False
    return False

def verificar_cancelamento():
    """Verifica se a campanha foi cancelada"""
    if ARQUIVO_CANCELAMENTO.exists():
        try:
            with open(ARQUIVO_CANCELAMENTO, "r", encoding="utf-8") as f:
                conteudo = f.read().strip()
                return conteudo.lower() == "sim"
        except:
            return False
    return False

def tratar_sinal(signum, frame):
    """Trata sinal de interrupção (Ctrl+C)"""
    print("\n\n⚠️  Interrupção detectada! Salvando checkpoint antes de sair...")
    sys.exit(0)

# ============================================================
# FUNÇÕES DE LOG E CHECKPOINT
# ============================================================
def criar_log_campanha():
    """Cria arquivo de log para a campanha atual"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = PASTA_LOGS / f"campanha_{timestamp}.json"
    return log_path

def salvar_checkpoint(indice, total, enviados, falhas, log_path, status="em_andamento"):
    """Salva checkpoint da campanha"""
    checkpoint = {
        "data_campanha": datetime.now().isoformat(),
        "ultimo_indice": indice,
        "total_contatos": total,
        "enviados_com_sucesso": enviados,
        "falhas": falhas if isinstance(falhas, list) else [],
        "log_path": str(log_path) if log_path else None,
        "status": status,
        "assunto": ASSUNTO,
        "remetente": SMTP_USER
    }
    
    try:
        with open(ARQUIVO_CHECKPOINT, "w", encoding="utf-8") as f:
            json.dump(checkpoint, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️  Erro ao salvar checkpoint: {e}")
    
    return checkpoint

def carregar_checkpoint():
    """Carrega checkpoint salvo se existir e for válido"""
    if not ARQUIVO_CHECKPOINT.exists():
        return None
    
    # Verifica se o arquivo não está vazio
    try:
        if ARQUIVO_CHECKPOINT.stat().st_size == 0:
            print(f"⚠️  Arquivo checkpoint vazio. Removendo...")
            ARQUIVO_CHECKPOINT.unlink()
            return None
    except:
        return None
    
    try:
        with open(ARQUIVO_CHECKPOINT, "r", encoding="utf-8") as f:
            checkpoint = json.load(f)
        
        # Verifica se o checkpoint tem os campos necessários
        if not checkpoint or "ultimo_indice" not in checkpoint:
            print(f"⚠️  Checkpoint inválido. Removendo...")
            ARQUIVO_CHECKPOINT.unlink()
            return None
        
        # Verifica se é da mesma data
        try:
            data_checkpoint = datetime.fromisoformat(checkpoint["data_campanha"]).date()
            if data_checkpoint == date.today():
                return checkpoint
            else:
                print(f"\n⚠️  Checkpoint de {data_checkpoint} é de outro dia.")
                print("   Iniciando nova campanha para hoje.")
                ARQUIVO_CHECKPOINT.unlink()
                return None
        except:
            return checkpoint
            
    except json.JSONDecodeError:
        print(f"⚠️  Arquivo checkpoint corrompido. Removendo...")
        ARQUIVO_CHECKPOINT.unlink()
        return None
    except Exception as e:
        print(f"⚠️  Erro ao ler checkpoint: {e}. Removendo...")
        try:
            ARQUIVO_CHECKPOINT.unlink()
        except:
            pass
        return None

def registrar_envio(log_path, email, empresa, status, erro=None):
    """Registra resultado do envio no log"""
    # Carrega log existente
    log_data = None
    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                log_data = json.load(f)
        except:
            log_data = None
    
    if not log_data:
        log_data = {
            "data_inicio": datetime.now().isoformat(),
            "total_emails": 0,
            "sucessos": 0,
            "falhas": 0,
            "envios": []
        }
    
    # Adiciona novo registro
    registro = {
        "timestamp": datetime.now().isoformat(),
        "email": email,
        "empresa": empresa[:100],
        "status": status,
        "erro": erro if erro else None
    }
    
    log_data["envios"].append(registro)
    log_data["total_emails"] = len(log_data["envios"])
    log_data["sucessos"] = sum(1 for e in log_data["envios"] if e["status"] == "sucesso")
    log_data["falhas"] = sum(1 for e in log_data["envios"] if e["status"] == "falha")
    
    # Salva log
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️  Erro ao salvar log: {e}")
    
    return log_data

def verificar_limite_diario():
    """Verifica se já atingiu o limite diário de emails"""
    hoje = date.today()
    total_enviados_hoje = 0
    
    # Soma todos os logs de hoje
    if PASTA_LOGS.exists():
        for log_file in PASTA_LOGS.glob("campanha_*.json"):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    log_data = json.load(f)
                    data_log = datetime.fromisoformat(log_data["data_inicio"]).date()
                    if data_log == hoje:
                        total_enviados_hoje += log_data.get("sucessos", 0)
            except:
                pass
    
    restantes = EMAILS_POR_DIA - total_enviados_hoje
    return total_enviados_hoje, max(restantes, 0)

# ============================================================
# VALIDAÇÃO DAS CONFIGURAÇÕES
# ============================================================
def validar_configuracoes():
    """Valida se as configurações do .env estão corretas"""
    erros = []
    
    if not SMTP_USER or SMTP_USER == "seuemail@gmail.com":
        erros.append("❌ SMTP_USERNAME não configurado no arquivo .env")
    
    if not SMTP_PASS or SMTP_PASS == "sua_senha_de_app_16_digitos":
        erros.append("❌ SMTP_PASSWORD não configurado no arquivo .env")
    
    if SMTP_USER and "@" not in SMTP_USER:
        erros.append("❌ SMTP_USERNAME deve ser um e-mail válido")
    
    if erros:
        print("\n" + "=" * 60)
        print("⚠️  ERROS NA CONFIGURAÇÃO DO .ENV")
        print("=" * 60)
        for erro in erros:
            print(erro)
        print("\n📌 Configure corretamente o arquivo .env antes de continuar!")
        print(f"   Arquivo: {Path(__file__).parent / '.env'}")
        return False
    
    return True

# ============================================================
# FUNÇÕES DE TEMPLATE E EMAIL
# ============================================================
def ler_template_html():
    """Lê o arquivo HTML do template"""
    template_relativo = TEMPLATE_PATH.lstrip("./")
    template_path = PASTA_RAIZ / template_relativo
    
    if not template_path.exists():
        template_path = PASTA_TEMPLATES / Path(template_relativo).name
    
    if not template_path.exists():
        print(f"❌ Arquivo template não encontrado!")
        print(f"   Procurado em: {template_path}")
        print(f"   Verifique o TEMPLATE_PATH no arquivo .env")
        return None
    
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"❌ Erro ao ler template: {e}")
        return None

def personalizar_html(html_base, contato):
    """Substitui placeholders no HTML pelos dados do contato"""
    html_personalizado = html_base
    
    # Pega primeiro nome da empresa para saudação
    nome_empresa = contato.get("nome_empresa", "")
    nome_curto = nome_empresa.split()[0] if nome_empresa else "Cliente"
    
    substituicoes = {
        "{{NOME_EMPRESA}}": nome_empresa,
        "{{EMPRESA}}": nome_empresa,
        "{{CIDADE}}": contato.get("cidade", ""),
        "{{CNPJ}}": contato.get("cnpj", ""),
        "{{TELEFONE}}": contato.get("telefone", ""),
        "{{APTA}}": contato.get("apta", ""),
        "{{EMAIL}}": contato.get("email", ""),
        "{{nome}}": nome_curto,
        "{{NOME}}": nome_curto,
    }
    
    for placeholder, valor in substituicoes.items():
        if valor:
            html_personalizado = html_personalizado.replace(placeholder, valor)
    
    return html_personalizado

def ler_contatos_csv(arquivo_csv):
    """Lê a lista de contatos do CSV"""
    csv_path = PASTA_LISTAS / arquivo_csv
    contatos = []
    
    if not csv_path.exists():
        print(f"❌ Arquivo CSV não encontrado: {csv_path}")
        return None
    
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            # Detecta o delimitador
            primeira_linha = f.readline()
            f.seek(0)
            delimitador = ';' if ';' in primeira_linha else ','
            
            reader = csv.DictReader(f, delimiter=delimitador)
            
            # Verifica as colunas disponíveis
            colunas = reader.fieldnames
            print(f"📊 Colunas encontradas: {', '.join(colunas)}")
            
            # Mapeia colunas (suporta diferentes nomes)
            coluna_email = None
            coluna_empresa = None
            coluna_cidade = None
            coluna_cnpj = None
            coluna_telefone = None
            coluna_apta = None
            
            for col in colunas:
                col_lower = col.lower().strip()
                if 'email' in col_lower:
                    coluna_email = col
                elif 'razao' in col_lower or 'empresa' in col_lower or 'nome' in col_lower:
                    coluna_empresa = col
                elif 'cidade' in col_lower:
                    coluna_cidade = col
                elif 'cnpj' in col_lower:
                    coluna_cnpj = col
                elif 'telefone' in col_lower or 'fone' in col_lower:
                    coluna_telefone = col
                elif 'apta' in col_lower:
                    coluna_apta = col
            
            if not coluna_email:
                print(f"❌ Coluna de email não encontrada no CSV!")
                print(f"   Colunas disponíveis: {colunas}")
                return None
            
            for row in reader:
                email = row.get(coluna_email, "").strip().lower()
                
                # Filtra emails inválidos
                if not email or '@' not in email or '.' not in email:
                    continue
                
                # Limpa telefone
                telefone = row.get(coluna_telefone, "").strip() if coluna_telefone else ""
                if '|' in telefone:
                    telefone = telefone.split('|')[0].strip()
                
                contato = {
                    "email": email,
                    "nome_empresa": row.get(coluna_empresa, "").strip() if coluna_empresa else "",
                    "cnpj": row.get(coluna_cnpj, "").strip() if coluna_cnpj else "",
                    "cidade": row.get(coluna_cidade, "").strip() if coluna_cidade else "",
                    "apta": row.get(coluna_apta, "").strip() if coluna_apta else "",
                    "telefone": telefone
                }
                contatos.append(contato)
        
        return contatos
        
    except Exception as e:
        print(f"❌ Erro ao ler CSV: {e}")
        return None

def enviar_email(servidor, destinatario, contato, html_base):
    """Envia um email individual"""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = ASSUNTO
        msg["From"] = f"{FROM_NAME} <{SMTP_USER}>"
        msg["To"] = destinatario
        
        if REPLY_TO:
            msg["Reply-To"] = REPLY_TO
        
        # Personaliza o HTML com os dados do contato
        html_personalizado = personalizar_html(html_base, contato)
        
        parte_html = MIMEText(html_personalizado, "html", "utf-8")
        msg.attach(parte_html)
        
        servidor.sendmail(SMTP_USER, destinatario, msg.as_string())
        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, "Erro de autenticação - Verifique usuário/senha"
    except smtplib.SMTPRecipientsRefused:
        return False, "Destinatário recusado pelo servidor"
    except smtplib.SMTPServerDisconnected:
        return False, "Conexão com servidor perdida"
    except Exception as e:
        return False, str(e)

# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================
def main():
    print("=" * 70)
    print("🚀 NEWLEADS - DISPARADOR DE EMAILS (COM RECUPERAÇÃO)")
    print("=" * 70)
    
    # Configura tratamento de sinais
    signal.signal(signal.SIGINT, tratar_sinal)
    
    # Valida configurações do .env
    if not validar_configuracoes():
        return
    
    # Mostra configurações carregadas
    print(f"\n⚙️  CONFIGURAÇÕES CARREGADAS:")
    print(f"   SMTP_HOST: {SMTP_HOST}:{SMTP_PORT}")
    print(f"   SMTP_USER: {SMTP_USER}")
    print(f"   FROM_NAME: {FROM_NAME}")
    print(f"   ASSUNTO: {ASSUNTO[:50]}..." if len(ASSUNTO) > 50 else f"   ASSUNTO: {ASSUNTO}")
    print(f"   TEMPLATE_PATH: {TEMPLATE_PATH}")
    
    # Cria pastas
    criar_pastas()
    
    # Verifica template
    print("\n📄 Verificando template HTML...")
    html_template = ler_template_html()
    if not html_template:
        return
    
    print(f"✅ Template carregado com sucesso!")
    
    # Verifica limite diário
    enviados_hoje, restantes_hoje = verificar_limite_diario()
    print(f"\n📊 LIMITE DIÁRIO: {EMAILS_POR_DIA} emails")
    print(f"   Enviados hoje: {enviados_hoje}")
    print(f"   Disponível hoje: {restantes_hoje}")
    
    if restantes_hoje <= 0:
        print("\n❌ Limite diário atingido! Tente novamente amanhã.")
        return
    
    # Pergunta qual CSV usar
    csv_files = list(PASTA_LISTAS.glob("*.csv"))
    if not csv_files:
        print(f"\n❌ Nenhum arquivo CSV encontrado em: {PASTA_LISTAS}")
        print("   Coloque seu arquivo CSV na pasta 'listas'")
        return
    
    print("\n📋 Arquivos CSV disponíveis:")
    for i, file in enumerate(csv_files, 1):
        size_kb = file.stat().st_size / 1024
        print(f"   {i}. {file.name} ({size_kb:.1f} KB)")
    
    try:
        escolha = input(f"\nSelecione o arquivo (1-{len(csv_files)}): ").strip()
        idx = int(escolha) - 1
        if idx < 0 or idx >= len(csv_files):
            print("❌ Seleção inválida!")
            return
        arquivo_csv = csv_files[idx].name
    except ValueError:
        print("❌ Digite um número válido!")
        return
    
    # Carrega contatos
    print(f"\n📂 Carregando contatos de: {arquivo_csv}")
    contatos = ler_contatos_csv(arquivo_csv)
    if not contatos:
        print("❌ Nenhum contato válido encontrado no CSV!")
        return
    
    print(f"✅ {len(contatos)} contatos válidos encontrados")
    
    # Mostra primeiros contatos como exemplo
    print("\n📊 Primeiros contatos da lista:")
    for i, contato in enumerate(contatos[:5], 1):
        nome = contato['nome_empresa'][:35] if contato['nome_empresa'] else "Sem nome"
        print(f"   {i}. {nome} - {contato['email']}")
    if len(contatos) > 5:
        print(f"   ... e mais {len(contatos) - 5} contatos")
    
    # Limita pelo limite diário
    if len(contatos) > restantes_hoje:
        print(f"\n⚠️  Limitando para {restantes_hoje} emails (limite diário)")
        print(f"   Os primeiros {restantes_hoje} serão enviados hoje.")
        contatos = contatos[:restantes_hoje]
    
    # Verifica checkpoint
    checkpoint = carregar_checkpoint()
    start_index = 0
    log_path = None
    enviados = 0
    falhas = []
    
    if checkpoint and checkpoint.get("ultimo_indice", 0) < len(contatos):
        print(f"\n🔄 Recuperando campanha anterior...")
        print(f"   Último índice processado: {checkpoint['ultimo_indice']}")
        print(f"   Emails enviados com sucesso: {checkpoint.get('enviados_com_sucesso', 0)}")
        
        start_index = checkpoint["ultimo_indice"]
        enviados = checkpoint.get("enviados_com_sucesso", 0)
        falhas = checkpoint.get("falhas", [])
        log_path = Path(checkpoint["log_path"]) if checkpoint.get("log_path") else None
        
        resposta = input(f"\nDeseja continuar de onde parou? (s/N): ").lower()
        if resposta != 's':
            start_index = 0
            enviados = 0
            falhas = []
            log_path = None
            if ARQUIVO_CHECKPOINT.exists():
                ARQUIVO_CHECKPOINT.unlink()
            print("Iniciando nova campanha...")
    
    # Cria novo log se necessário
    if not log_path:
        log_path = criar_log_campanha()
        print(f"\n📝 Log da campanha: {log_path.name}")
    
    # Confirmação final
    total_envio = len(contatos) - start_index
    print("\n" + "=" * 70)
    print(f"📊 RESUMO DA CAMPANHA")
    print("=" * 70)
    print(f"📋 Arquivo: {arquivo_csv}")
    print(f"📧 Total a enviar: {total_envio}")
    print(f"⏱️  Intervalo: {DELAY_MIN_SEGUNDOS}-{DELAY_MAX_SEGUNDOS} segundos")
    print(f"📦 Checkpoint a cada: {EMAILS_POR_LOTE} emails")
    print(f"🎯 Limite diário: {EMAILS_POR_DIA} emails")
    print(f"\n📌 COMANDOS DURANTE O ENVIO:")
    print("   Ctrl+C = Salva checkpoint e sai")
    print("   Use 'python controles.py' em outro terminal para pausar/cancelar")
    
    resposta = input(f"\n⚠️  Deseja iniciar o envio para {total_envio} empresa(s)? (s/N): ").lower()
    if resposta != 's':
        print("❌ Envio cancelado.")
        return
    
    # Conexão SMTP
    server = None
    try:
        print("\n🔌 Conectando ao servidor SMTP...")
        print(f"   Servidor: {SMTP_HOST}:{SMTP_PORT}")
        
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30, context=_ssl_ctx())
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            server.starttls(context=_ssl_ctx())
        
        server.login(SMTP_USER, SMTP_PASS)
        print("✅ Conexão estabelecida com sucesso!")
        
        total = len(contatos)
        
        for i in range(start_index, total):
            # Verifica cancelamento
            if verificar_cancelamento():
                print("\n🛑 Cancelamento solicitado. Salvando checkpoint...")
                salvar_checkpoint(i, total, enviados, falhas, log_path, "cancelada")
                break
            
            # Verifica pausa
            while verificar_pausa():
                print("\n⏸️  Campanha pausada. Aguardando continuação...")
                time.sleep(5)
            
            contato = contatos[i]
            email = contato["email"]
            empresa = contato["nome_empresa"][:45] if contato["nome_empresa"] else "Sem nome"
            cidade = contato.get("cidade", "N/A")
            
            print(f"\n📤 [{i+1}/{total}] {empresa}")
            print(f"   📧 {email}")
            print(f"   📍 {cidade}")
            
            # Tenta enviar com reconexão automática em caso de falha de conexão
            enviado = False
            erro_final = None
            max_tentativas_envio = 3  # 1 tentativa inicial + até 2 reconexões

            for tentativa_envio in range(max_tentativas_envio):
                sucesso, erro = enviar_email(server, email, contato, html_template)

                if sucesso:
                    enviado = True
                    break

                erro_final = erro

                if _eh_erro_conexao(erro):
                    if tentativa_envio < max_tentativas_envio - 1:
                        print(f"   ⚠️ Conexão perdida. Tentando reconectar...")
                        try:
                            server.close()
                        except Exception:
                            pass
                        try:
                            server = reconectar_smtp()
                            print(f"   🔁 Reenviando email...")
                            continue
                        except ConnectionError as e:
                            erro_final = str(e)
                            print(f"   ❌ {erro_final}")
                            break
                else:
                    break

            if enviado:
                print(f"   ✅ Enviado com sucesso!")
                enviados += 1
                registrar_envio(log_path, email, empresa, "sucesso")
            else:
                print(f"   ❌ Falha: {erro_final}")
                falhas.append({"email": email, "empresa": empresa, "erro": erro_final})
                registrar_envio(log_path, email, empresa, "falha", erro_final)
                # Se for erro de conexão irrecuperável, para a campanha
                if _eh_erro_conexao(erro_final):
                    salvar_checkpoint(i + 1, total, enviados, falhas, log_path, "interrompida")
                    print(f"\n❌ Campanha interrompida devido a falha de conexão SMTP.")
                    break
            
            # Delay aleatório entre 2-5 segundos
            if i < total - 1 and not _eh_erro_conexao(erro_final):  # Não espera após o último
                delay = random.uniform(DELAY_MIN_SEGUNDOS, DELAY_MAX_SEGUNDOS)
                print(f"   ⏳ Aguardando {delay:.1f} segundos...")
                time.sleep(delay)
            
            # Checkpoint a cada lote
            if (i + 1) % EMAILS_POR_LOTE == 0:
                salvar_checkpoint(i + 1, total, enviados, falhas, log_path)
                print(f"\n💾 Checkpoint salvo: {i+1}/{total} emails processados")
        
        # Salva checkpoint final
        if not verificar_cancelamento():
            salvar_checkpoint(total, total, enviados, falhas, log_path, "concluida")
        
        # Resumo final
        print("\n" + "=" * 70)
        print("📊 RELATÓRIO FINAL")
        print("=" * 70)
        print(f"✅ Emails enviados com sucesso: {enviados}")
        print(f"❌ Falhas: {len(falhas)}")
        print(f"📧 Total processado: {total}")
        print(f"\n📁 Log salvo em: {log_path}")
        print(f"💾 Checkpoint em: {ARQUIVO_CHECKPOINT}")
        
        if falhas:
            print(f"\n🔴 {len(falhas)} falhas ocorreram.")
            print("   Verifique o arquivo de log para detalhes.")
        
    except smtplib.SMTPAuthenticationError:
        print("\n❌ ERRO DE AUTENTICAÇÃO SMTP!")
        print("   Verifique seu usuário e senha no arquivo .env")
        print("   Lembre-se: Use uma Senha de App do Google, não sua senha normal")
        
    except smtplib.SMTPServerDisconnected:
        print("\n❌ CONEXÃO COM O SERVIDOR PERDIDA!")
        print("   Verifique sua conexão com a internet")
        print("   O checkpoint foi salvo, execute novamente para continuar")
        if 'i' in locals():
            salvar_checkpoint(i + 1, total, enviados, falhas, log_path, "interrompida")
        
    except Exception as e:
        print(f"\n❌ ERRO CRÍTICO: {e}")
        print("   Salvando checkpoint antes de encerrar...")
        if 'i' in locals():
            salvar_checkpoint(i + 1, total, enviados, falhas, log_path, "interrompida")
        
    finally:
        if server:
            try:
                server.quit()
            except:
                pass
            print("\n🔌 Conexão SMTP encerrada.")

# ============================================================
# PONTO DE ENTRADA
# ============================================================
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Programa interrompido pelo usuário.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")
        sys.exit(1)