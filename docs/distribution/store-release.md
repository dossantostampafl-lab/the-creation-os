# Empacotamento Apple App Store, Samsung Galaxy Store e Google Play

Nome: Creation OS. Bundle/applicationId: `com.thecreationos.app`. Versão nativa inicial1.0, build1. Android mínimo24, target36. iOS mínimo15, arm64. O desenvolvedor deve confirmar propriedade/disponibilidade desse identificador antes do primeiro envio; mudar depois quebra a identidade de atualizações.

## Builds reproduzíveis

Com Node22+, JDK21 e AndroidSDK36:

```sh
cd frontend
npm ci
CREATION_MOBILE_API_URL=https://148-116-109-255.sslip.io/api/v1 npm run mobile:android
```

Resultados: `android/app/build/outputs/apk/debug/app-debug.apk` e `android/app/build/outputs/bundle/release/app-release.aab`. APKdebug tem assinatura de desenvolvimento e serve a testes. AABrelease não possui assinatura de distribuição. Samsung aceita APKrelease assinado; o build também produz `app-release-unsigned.apk`, que deve receber sua assinatura privada. Nenhuma chave de assinatura deve entrar no repositório, no ZIP ou no frontend.

No macOS com Xcode compatível com o SDK exigido no momento do envio:

```sh
cd frontend
npm ci
npm run mobile:sync
npx cap open ios
```

Selecione o Team correto, mantenha BundleID e versões, escolha dispositivo genérico, Product→Archive e DistributeApp. AppStoreConnect exige conta ativa, certificados/provisionamento e assinatura. O workflow `Mobile packaging` compila Android, um app de simulador e um archive iOS para dispositivos sem assinatura; ele não publica em nenhuma loja.

O endereço de backend é validado como HTTPS no build; está embutido no pacote. Mudanças de domínio requerem rebuild. Configure CORS nativo no backend. Os modelos de voz e inference vivem no servidor e não são incluídos no app.

## Conteúdo para as fichas

- Nome: Creation OS.
- Descrição curta: Converse com Deus por voz e organize conhecimento, projetos e operações.
- Descrição: Creation OS reúne conversação por texto e voz, memória contextual por projeto, revisão de oportunidades de12 universos e um laboratório de treinamentoCyberRange controlado pelo proprietário. O sistema diferencia hipóteses de evidências e mantém ações sob a autorização do Creator. O aplicativo requer acesso a uma instalaçãoCreationOS configurada e conexão com seu servidor.
- Categoria sugerida: Produtividade. Classificação etária: responder aos questionários oficiais considerando conteúdo de AI e treinamento de segurança; não inventar uma classificação numérica.
- Política de privacidade: `<URLpública-da-instalação>/privacy.html`.
- Suporte/código: `https://github.com/dossantostampafl-lab/the-creation-os`.
- Acesso para revisão: conta de teste previamente criada em instalação isolada, com12universos sem credenciais reais; transmitir senha somente pelo campo privado da loja. O app não oferece cadastro público de contas.

## Privacidade e declaração de dados

Microfone: somente durante sessão de voz em primeiro plano. Áudio é enviado ao servidor configurado para reconhecimento localVosk; não é gravado como arquivo pela funcionalidade de voz. Transcrições, respostas e memória permanecem no banco do operador. Texto e contexto selecionado são enviados ao gatewayLLM configurado; o provedor recebe esse conteúdo. Não declarar “nenhum dado coletado” quando usar backend/gateway externo.

Declarar identificação de conta e conteúdo fornecido/transcrito como dados vinculados à funcionalidade do app; diagnósticos técnicos se o operador os conservar. Avaliar a classificação de áudio efêmero nas fichas atuais de cada loja. Não há SDKpublicitário, tracking ou venda de dados nesta implementação. O manifestPrivacyInfo do app declara UserID/UserContent; osSDKsCapacitor também incluem manifests. Conferir o relatório de privacidade gerado pelo Xcode antes do envio.

Revogação de memória não substitui exclusão física do banco/backups. Antes de distribuição pública, o operador deve fornecer canal privado de suporte, política de retenção/eliminação e tratamento de solicitações, com sua identidade legal e contato. Se passar a oferecer criação pública de contas, implementar exclusão dentro do aplicativo conforme regras das lojas.

## Critérios antes da publicação

Testar em Android/Samsung e iPhone/iPad reais: login/refresh, permissão negada, wakeword e cinco turnos, interrupção, áudio externo/Bluetooth, suspensão/retomada, tela bloqueada, rede lenta/offline, layouts, acessibilidade e exclusão/retensão de dados. Preparar capturas reais de cada tamanho de tela; não usar evidência de testesmockados como prova de microfone em hardware.

Confirmar identidade do publisher, contas Apple/Samsung/Google, assinatura, formulário de dados, classificação etária, URLs acessíveis e credenciais privadas de revisão. A versão de compilação não equivale à aceitação na loja. As lojas podem avaliar funcionalidade mínima/AI; é necessário enviar o aplicativo real e atender ao retorno do revisor.

Estado desta entrega: Android compilado e fontes iOS preparados; assinatura, testes em dispositivos e submissão dependem desses recursos externos. Não há IPAassinado, publicação ou promessa de aprovação.
