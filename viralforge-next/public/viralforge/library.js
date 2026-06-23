// ViralForge — biblioteca de hooks e estruturas de thread.
// Atalhos de partida. {tema} é placeholder — troque ao usar.

export const HOOKS = [
  // Contrário
  { pattern: "Contrário", text: "Todo mundo está errado sobre {tema}." },
  { pattern: "Contrário", text: "Pare de fazer {tema} do jeito que te ensinaram." },
  { pattern: "Contrário", text: "A maioria trata {tema} como commodity. É aí que perde dinheiro." },
  { pattern: "Contrário", text: "Opinião impopular: {tema} está te segurando, não te ajudando." },
  { pattern: "Contrário", text: "Esqueça tudo que te disseram sobre {tema}." },
  { pattern: "Contrário", text: "{tema} é a coisa mais incompreendida do seu nicho." },
  // Numérico / específico
  { pattern: "Numérico", text: "Testei {tema} por 30 dias. 3 coisas mudaram tudo." },
  { pattern: "Numérico", text: "1.000 horas em {tema} resumidas em 5 frases:" },
  { pattern: "Numérico", text: "90% das pessoas erram {tema} no primeiro passo." },
  { pattern: "Numérico", text: "Levei 6 meses pra entender {tema}. Você leva 6 minutos:" },
  { pattern: "Numérico", text: "7 verdades sobre {tema} que ninguém te conta:" },
  { pattern: "Numérico", text: "R$0 gastos, {tema} resolvido. O passo a passo:" },
  // Curiosidade / loop
  { pattern: "Curiosidade", text: "Existe um jeito de {tema} que quase ninguém usa." },
  { pattern: "Curiosidade", text: "Descobri por acidente como {tema} realmente funciona." },
  { pattern: "Curiosidade", text: "O que ninguém te fala sobre {tema}:" },
  { pattern: "Curiosidade", text: "Tem um detalhe em {tema} que muda o jogo. Aqui está:" },
  { pattern: "Curiosidade", text: "Plot twist sobre {tema} que vai te irritar:" },
  { pattern: "Curiosidade", text: "A razão real por trás de {tema} não é o que você pensa." },
  // Stakes
  { pattern: "Stakes", text: "Se você ainda faz {tema} assim, está perdendo dinheiro." },
  { pattern: "Stakes", text: "Todo dia sem {tema} é um concorrente te ultrapassando." },
  { pattern: "Stakes", text: "Antes que seja tarde: conserte {tema} hoje." },
  { pattern: "Stakes", text: "{tema} mal feito custa mais caro do que você imagina." },
  { pattern: "Stakes", text: "O erro em {tema} que silenciosamente mata seu crescimento:" },
  { pattern: "Stakes", text: "Você não tem problema de talento. Tem problema de {tema}." },
  // Autoridade / build in public
  { pattern: "Autoridade", text: "Construindo {tema} em público — dia 1:" },
  { pattern: "Autoridade", text: "Como eu transformo {tema} em autoridade no automático:" },
  { pattern: "Autoridade", text: "Meu sistema de {tema}, sem enrolação:" },
  { pattern: "Autoridade", text: "O que aprendi fazendo {tema} de verdade (não na teoria):" },
  { pattern: "Autoridade", text: "{tema}: o que funcionou, o que falhou e o que eu refaria." },
  { pattern: "Autoridade", text: "Ninguém pediu, mas aqui está meu framework de {tema}." },
];

export const THREAD_TEMPLATES = [
  { name: "Sistema passo a passo", text: "Como eu {resultado} com {tema}, do zero.\nO sistema completo (e o que ninguém conta): 🧵\n\n1/ \n2/ \n3/ \n\nNo fim: o atalho que economiza meses." },
  { name: "Mitos x realidade", text: "5 mitos sobre {tema} que te custam dinheiro: 🧵\n\nMito 1: \nRealidade: \n\nMito 2: \nRealidade: " },
  { name: "Antes / depois", text: "Há 1 ano eu {situação ruim}.\nHoje {situação boa}.\nA diferença foi {tema}. O passo a passo: 🧵" },
  { name: "Erros pra evitar", text: "Os 5 erros que cometi com {tema} pra você não repetir: 🧵\n\n1/ \n2/ " },
  { name: "Ferramentas/hacks", text: "5 ferramentas de {tema} que parecem trapaça: 🧵\n\n1/ \n2/ " },
  { name: "Estudo de caso", text: "Peguei {input} e transformei em {output} usando {tema}.\nReplicável, passo a passo: 🧵" },
  { name: "Contrarian profundo", text: "Todo mundo faz {tema} assim.\nEu faço o oposto — e funciona melhor.\nPor quê: 🧵" },
  { name: "Checklist", text: "O checklist de {tema} que rodo antes de {ação}: 🧵\n\n☐ \n☐ \n☐ " },
  { name: "Lições", text: "5 lições de {tempo} fazendo {tema}: 🧵\n\n1/ \n2/ " },
  { name: "Framework", text: "Meu framework de {tema} em 4 passos.\nRoube à vontade: 🧵\n\n1/ \n2/ \n3/ \n4/ " },
];
