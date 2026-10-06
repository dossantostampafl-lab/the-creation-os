# Verificação de instruções do chat

O prompt compartilhado pelo chat de texto e pela voz impunha prosa e proibia listas e outros formatos, mesmo quando solicitados. Isso conflitava com pedidos de saída literal. O smoke em produção recebeu `Voz local está ativa.` para `Responda apenas: voz local ativa`.

A correção mantém prosa curta como padrão, mas respeita formato, idioma e texto literal pedidos no turno atual. Mantém as regras de contexto, evidências e autorização; não insere respostas prontas nem reescreve a saída do modelo.

Na comparação sintética com o FreeLLM configurado, o prompt anterior passou em 11/12 casos e o corrigido em 12/12 (Actions run 37410532039). São amostras, não garantia determinística. Uma primeira comparação encontrou também uma expectativa ambígua de marcadores na lista; o pedido foi esclarecido antes desta comparação.

Após instalar o backend atualizado, execute **Deploy → check-chat-instructions**, com `ref=main`. O teste usa o prompt importado da API em execução e o FreeLLM primário, sem fallback: texto literal, pontuação, JSON, lista, aritmética e contexto, duas vezes cada. Cada chamada tem limite de 20 segundos. Qualquer erro ou resposta incompatível resulta em status de falha. O relatório registra apenas caso, resultado e duração, sem respostas ou conversas reais.

Esse diagnóstico verifica geração e instruções. Execute também o smoke da atualização e **Deploy → browser-gauntlet** para verificar autenticação, persistência, interface e voz sintética. A voz sintética não comprova a captura pelo microfone físico do usuário.
