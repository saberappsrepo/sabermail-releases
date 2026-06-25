; Inno Setup Script — SaberMail
; Gera um instalador Windows com todas as dependências e estrutura de pastas.

#define MyAppName "SaberMail"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Saber Apps - Desenvolvedor"
#define MyAppURL "https://saberapps.com.br"
#define MyAppExeName "SaberMail.exe"

[Setup]
AppId={{B8A3C4D5-E6F7-89AB-CDEF-0123456789AB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=SaberMail_Installer_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64os
DisableProgramGroupPage=yes
SetupIconFile=frontend\icon.ico
UninstallDisplayIcon={app}\SaberMail.exe

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na &Área de Trabalho"; GroupDescription: "Ícones adicionais:"

[Files]
; App principal + DLLs (--onedir)
Source: "dist\SaberMail\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\SaberMail\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Dados padrão (backend/)
Source: "backend\*"; DestDir: "{app}\backend"; Flags: ignoreversion recursesubdirs createallsubdirs

; .env padrão (se não existir, o app copia do backend\.env.example na primeira execução)
Source: "backend\.env.example"; DestDir: "{app}"; DestName: ".env.example"; Flags: ignoreversion

; Ícone do aplicativo
Source: "frontend\icon.ico"; DestDir: "{app}\frontend"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Executa o app após instalação (opcional)
Filename: "{app}\{#MyAppExeName}"; Description: "Executar {#MyAppName}"; Flags: nowait postinstall skipifsilent; WorkingDir: "{app}"

[UninstallRun]
; Limpa dados do usuário em AppData (opcional)
Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{userappdata}\SaberMail"""; Flags: runhidden

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Garante que .env existe na pasta do app
    if not FileExists(ExpandConstant('{app}\.env')) then
      if FileExists(ExpandConstant('{app}\.env.example')) then
        FileCopy(ExpandConstant('{app}\.env.example'),
                 ExpandConstant('{app}\.env'), False);
  end;
end;
