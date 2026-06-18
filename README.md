<p align="center"><a href="https://github.com/danielcarro/sabermail-releases" target="_blank"><img src="https://github.com/ideacatlab/simple-mailship/blob/main/.github/images/logo.png?raw=true" width="350" alt="SaberMail"></a></p>

<h1 align="center">SaberMail</h1>
<p align="center"><strong>Gestão Profissional de Campanhas de Email Marketing</strong></p>

<p align="center">
  <a href="https://github.com/danielcarro/sabermail-releases/releases/latest">
    <img src="https://img.shields.io/github/v/release/danielcarro/sabermail-releases?label=versão&color=0d6efd" alt="Versão">
  </a>
  <img src="https://img.shields.io/badge/plataforma-Windows%2010%2F11-blue" alt="Windows">
  <img src="https://img.shields.io/github/downloads/danielcarro/sabermail-releases/total?color=success" alt="Downloads">
</p>

---

## 📥 Download

Baixe o instalador mais recente na página de [Releases](https://github.com/danielcarro/sabermail-releases/releases/latest).

| Arquivo | Descrição |
|---------|-----------|
| `SaberMail_Installer_v1.0.0.exe` | Instalador completo (recomendado) |

**Requisitos:** Windows 10/11, conexão com internet, conta Gmail com Senha de App.

---

## ✨ Funcionalidades

- **Envio em massa** com template HTML personalizado
- **Intervalo aleatório** entre 2-5s para evitar bloqueio
- **Limite diário** configurável (padrão: 500 emails/dia)
- **Checkpoint automático** — retoma de onde parou em caso de falha
- **Pausar / Retomar / Cancelar** campanha a qualquer momento
- **Monitoramento de bounce** via IMAP (identifica automaticamente devoluções)
- **Interface gráfica** com 6 abas:
  - 📊 Dashboard
  - 🚀 Campanha
  - 📋 Listas
  - ⚙️ Config SMTP
  - 📋 Relatórios
  - 📬 Bounce
- **Logs detalhados** em JSON + SQLite por campanha
- **CSV limpo** gerado automaticamente removendo bouncing

---

## 📖 Guia Rápido

### 1. Instalação

Execute o instalador e siga as instruções na tela. O aplicativo será instalado em `C:\Program Files\SaberMail\`.

### 2. Configure o Gmail

O SaberMail exige uma **Senha de App** do Gmail:

1. Acesse [Segurança da Conta Google](https://myaccount.google.com/security)
2. Ative a **Verificação em duas etapas** (2FA)
3. Vá em **Senhas de app**
4. Selecione: App = "Email", Dispositivo = "Windows Computador"
5. Clique em **Gerar**
6. Copie a senha de 16 caracteres (ex: `abcd efgh ijkl mnop`)

### 3. Abra o SaberMail

Na primeira execução, você verá a tela de boas-vindas. Vá até a aba **⚙️ Config SMTP** e preencha:

| Campo | Valor |
|-------|-------|
| Servidor SMTP | `smtp.gmail.com` |
| Porta | `587` |
| Usar SSL? | Desligado |
| Usuário | `seuemail@gmail.com` |
| Senha | Sua Senha de App de 16 dígitos |

Os dados são salvos automaticamente e persistidos entre execuções.

### 4. Prepare seu template HTML

Edite o arquivo `{AppData}\SaberMail\templates\rhsudeste.html` (ou acessível pelo botão "Abrir pasta de templates" na interface).

**Placeholders disponíveis no template:**

| Placeholder | Descrição |
|------------|-----------|
| `{{NOME_EMPRESA}}` ou `{{nome_empresa}}` | Nome da empresa |
| `{{CNPJ}}` ou `{{cnpj}}` | CNPJ |
| `{{CIDADE}}` ou `{{cidade}}` | Cidade |
| `{{TELEFONE}}` ou `{{telefone}}` | Telefone |
| `{{APTA}}` ou `{{apta}}` | Status (Sim/Não) |
| `{{EMAIL}}` ou `{{email}}` | Email de destino |

Os placeholders funcionam com maiúsculas e minúsculas.

### 5. Prepare sua lista de leads (CSV)

Coloque seus arquivos CSV na pasta `{AppData}\SaberMail\listas\` (acessível pela interface).

Formato esperado do CSV:

```csv
CNPJ,Razao Social,Fundacao,Cidade,Apta,Telefone,Email
00.000.000/0001-00,EMPRESA EXEMPLO LTDA,1990-01-01,SAO PAULO,Sim,(11) 99999-9999,contato@empresa.com
```

As colunas do CSV viram placeholders no template automaticamente.

### 6. Envie sua campanha

1. Abra a aba **🚀 Campanha**
2. Selecione o arquivo CSV
3. Configure o assunto e template
4. Ative o monitoramento de bounce (IMAP) se desejar
5. Clique em **Iniciar Envio**
6. Acompanhe o progresso em tempo real

---

## 🎮 Controle da Campanha

Durante o envio, você pode:

| Ação | Como fazer |
|------|------------|
| ⏸️ Pausar | Clique em **Pausar** na interface |
| ▶️ Retomar | Clique em **Continuar** |
| ✋ Cancelar | Clique em **Cancelar** |
| 📊 Ver status | O dashboard atualiza automático |

O checkpoint é salvo a cada 50 emails. Se o programa fechar, a campanha pode ser retomada de onde parou.

---

## 📊 Relatórios

Cada campanha gera:

- **Log JSON** em `{AppData}\SaberMail\logs\campanha_*.json`
- **Registro no SQLite** (acessível pela aba 📋 Relatórios)
- **CSV limpo** com bounced removidos: `clean_<csv>.csv`

---

## 🔧 Configuração Avançada

### Portas SMTP

| Conexão | Porta | SMTP_USE_SSL |
|---------|-------|-------------|
| SSL (recomendado) | 465 | `true` |
| STARTTLS | 587 | `false` |
| Sem criptografia | 25 | `false` |

### IMAP para Bounce

Configuração opcional para detecção automática de devoluções:

| Campo | Padrão |
|-------|--------|
| Servidor IMAP | `imap.gmail.com` |
| Porta IMAP | `993` |
| Usar SSL | Ligado |

Usa as mesmas credenciais do SMTP.

---

## ❓ FAQ

**Preciso de Python para usar?**
Não. O instalador já inclui tudo que você precisa. É só baixar e executar.

**Quantos emails posso enviar por dia?**
Contas gratuitas do Gmail: 500 emails/dia. Google Workspace: 2.000 emails/dia.

**O que acontece se perder a internet?**
O checkpoint salva o progresso a cada 50 emails. Ao religar, a campanha retoma automaticamente.

**O programa é seguro?**
Suas credenciais ficam armazenadas localmente no SQLite do próprio aplicativo. Nada é enviado para servidores externos.

---

## 📝 Licença

MIT

---

<p align="center"><em>SaberMail — Gestão de Campanhas de Email Marketing</em></p>
