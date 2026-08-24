# Loteca 6S-5D-3T — Estratégia 11-8-6

Projeto para geração de **um único palpite final por concurso da Loteca**, usando histórico, probabilidades estimadas e informações do próximo concurso para maximizar prioritariamente:

```text
P(acertos >= 13)
```

Toda técnica deve respeitar integralmente as Hard Constraints. Probabilidades, histórico, calibração, heurísticas, meta-modelos e Soft Constraints só podem atuar dentro do espaço de soluções válidas.

---

# Hard Constraints

```text
14 jogos
6 secos
5 duplos
3 triplos
11 Top1
8 Top2
6 Top3
25 marcações
```

Em caso de empate de probabilidades, usar:

```text
1 > 2 > X
```

Quando o **FLAMENGO/RJ** participar, sua vitória deve obrigatoriamente estar entre as marcações.

Soft Constraints nunca podem relaxar Hard Constraints.

---

# Consistência estrutural

A estrutura possui exatamente:

```text
6 secos  x 1 marcação =  6
5 duplos x 2 marcações = 10
3 triplos x 3 marcações = 9
Total                  = 25 marcações
```

A distribuição por rank também deve fechar exatamente:

```text
11 Top1
8 Top2
6 Top3
Total = 25 marcações
```

Nenhuma solução parcial ou final pode violar esses totais.

---

# Tipos de decisão por jogo

Para cada partida, considerar sete possibilidades estruturais:

```text
S1   = Top1
S2   = Top2
S3   = Top3
D12  = Top1 + Top2
D13  = Top1 + Top3
D23  = Top2 + Top3
T123 = Top1 + Top2 + Top3
```

O triplo possui cobertura total:

```text
CoberturaT123 = 1.0
```

A decisão final é global: não escolher secos, duplos ou triplos isoladamente apenas por ranking de risco.

---

# Estrutura dos duplos e triplos

Definir:

```text
D12 = quantidade de duplos Top1+Top2
D13 = quantidade de duplos Top1+Top3
D23 = quantidade de duplos Top2+Top3
T123 = quantidade de triplos
```

Com:

```text
D12 + D13 + D23 = 5
T123 = 3
```

Os secos por rank são determinados pelos totais globais:

```text
SecoTop1 = 11 - D12 - D13 - T123
SecoTop2 =  8 - D12 - D23 - T123
SecoTop3 =  6 - D13 - D23 - T123
```

Como `T123 = 3`:

```text
SecoTop1 = 8 - D12 - D13
SecoTop2 = 5 - D12 - D23
SecoTop3 = 3 - D13 - D23
```

Além disso:

```text
SecoTop1 + SecoTop2 + SecoTop3 = 6
```

Toda composição candidata deve satisfazer simultaneamente essas identidades.

---

# Cobertura das decisões

```text
CoberturaS1   = p(top1)
CoberturaS2   = p(top2)
CoberturaS3   = p(top3)
CoberturaD12  = p(top1) + p(top2)
CoberturaD13  = p(top1) + p(top3)
CoberturaD23  = p(top2) + p(top3) = 1 - p(top1)
CoberturaT123 = 1
```

Como:

```text
p(top1) >= p(top2) >= p(top3)
```

isoladamente:

```text
CoberturaD12 >= CoberturaD13 >= CoberturaD23
```

Isso não significa que D12 deva ser sempre preferido. A solução precisa fechar exatamente 11/8/6, 6S/5D/3T e maximizar o objetivo global.

---

# DoubleGain, RecoveryGain e TripleGain

D12 e D13 preservam Top1 e acrescentam uma segunda marcação:

```text
DoubleGain(D12) = p(top2)
DoubleGain(D13) = p(top3)
```

D23 abandona Top1 e troca por Top2+Top3:

```text
RecoveryGain(D23)
= CoberturaD23 - p(top1)
= 1 - 2*p(top1)
```

O triplo cobre os três resultados. Em comparação com um seco Top1:

```text
TripleGain(T123 vs S1)
= 1 - p(top1)
```

Como o triplo consome duas marcações adicionais em relação a um seco, registrar também para auditoria:

```text
GainPerExtraMark(T123 vs S1)
= (1 - p(top1)) / 2
```

Essa métrica é apenas diagnóstica. O objetivo principal continua sendo a maximização exata de `P(>=13)`.

---

# Soft Constraints — preferências de solução

As Soft Constraints atuam somente depois de garantida a validade estrutural do bilhete e nunca podem violar as Hard Constraints.

## Preferência contra vitórias de Palmeiras e Vasco

Quando **PALMEIRAS/SP** ou **VASCO DA GAMA/RJ** participarem do concurso, favorecer soluções que **excluam a vitória dessas equipes**, priorizando empate ou derrota, desde que isso não comprometa significativamente a qualidade global da aposta.

A regra deve ser tratada como preferência, e não como proibição absoluta:

```text
1. encontrar a melhor P(>=13) possível dentro das Hard Constraints
2. definir uma faixa de soluções quase ótimas
3. dentro dessa faixa, favorecer a exclusão das vitórias de Palmeiras e Vasco
4. priorizar soluções que excluam a vitória de ambas as equipes
5. somente depois aplicar os demais critérios de desempate estrutural
```

A comparação deve usar uma tolerância explícita e auditável em relação ao ótimo global. Uma referência inicial para pesquisa é limitar a perda relativa de `P(>=13)` a **0,5%**, sujeita a validação em backtest walk-forward.

Exemplo:

```text
P13plus_otimo = 0,04000
P13plus_candidato = 0,03985
perda_relativa = 0,375%
```

Nesse caso, o candidato permanece dentro de uma tolerância de 0,5% e pode ser preferido se excluir uma ou ambas as vitórias indesejadas.

Pontuação conceitual da preferência:

```text
2 = exclui vitória de PALMEIRAS/SP e VASCO DA GAMA/RJ
1 = exclui vitória de uma das duas equipes
0 = não exclui nenhuma
```

Não adicionar bônus arbitrário diretamente a `P(>=13)`.

A ordem correta é:

```text
ótimo probabilístico
-> faixa aceitável de quase ótimos
-> preferência anti-Palmeiras/Vasco
-> demais critérios de desempate
```

---

# risk_rank

Ordenar as 14 partidas do maior risco relativo de falha do Top1 para o menor:

```text
risk_rank = 1..14
risk_rank=1  -> maior risco
risk_rank=14 -> menor risco
```

A calibração por `risk_rank` deve usar somente concursos anteriores, ser validada cronologicamente e só ser promovida quando houver ganho fora da amostra.

Auditar:

```text
n
pTop1_medio_previsto
Top1_hit_observado
Top1_fail_observado
IC95%
CalibrationError
RiskRankStability
HistoricalConfidence
lift_shrunk
```

Métricas relevantes:

```text
RiskRankPrecision@8
RiskRankRecall@8
RiskRankNDCG@8
RiskRankECE
Brier por risk_rank
```

`risk_rank` é um sinal de risco e não uma regra automática para definir os 5 duplos ou 3 triplos.

---

# Seleção dos triplos

Os três triplos devem ser escolhidos globalmente pelo otimizador.

Não assumir automaticamente:

```text
triplos = três menores p(top1)
```

ou:

```text
triplos = risk_rank 1, 2 e 3
```

A restrição 11-8-6 cria compensações entre Top1, Top2 e Top3. Portanto, a melhor localização dos triplos pode depender da composição simultânea de secos e duplos.

Para cada triplo selecionado, registrar:

```text
Jogo
risk_rank
p(top1)
p(top2)
p(top3)
entropia
gap12
gap13
cobertura anterior alternativa
TripleGain
GainPerExtraMark
DeltaP13plus de substituição
```

---

# Otimização direta

Para cada jogo:

```text
seco:   c_i = p(resultado selecionado)
duplo:  c_i = p(resultado A) + p(resultado B)
triplo: c_i = 1
```

Obter a distribuição exata de acertos por convolução dinâmica e otimizar diretamente:

```text
P(>=13) = P(13) + P(14)
```

O estado estrutural da programação dinâmica deve controlar:

```text
Top1 selecionados
Top2 selecionados
Top3 selecionados
número de duplos
número de triplos
```

Estado terminal esperado:

```text
(Top1, Top2, Top3, duplos, triplos)
= (11, 8, 6, 5, 3)
```

A quantidade de secos é derivada:

```text
secos = 14 - duplos - triplos = 6
```

A solução final deve satisfazer:

```text
6 secos
5 duplos
3 triplos
11 Top1
8 Top2
6 Top3
25 marcações
regra obrigatória do Flamengo
```

---

# Distribuição exata de acertos

Para cada jogo, usar a probabilidade coberta pela decisão escolhida.

A distribuição de 0 a 14 acertos deve ser calculada por convolução dinâmica, evitando ruído de Monte Carlo.

Reportar:

```text
P(14)
P(13)
P(>=13)
P(12)
P(>=12)
```

A probabilidade reportada pelo otimizador deve ser confirmada por cálculo independente da distribuição final.

---

# Backtest walk-forward

Comparar no mínimo:

```text
A = probabilidades brutas
B = + temperatura
C = + temperatura + risk_rank
```

Relatório mínimo:

```text
Concursos
LogLoss
Brier
14
>=13
>=12
mean_hits
median_hits
Net13Gain
DecisionNetGain
DecisionWinRate
RecoveryRate
DoubleWasteRate
TripleUsefulnessRate
```

O ganho estimado de `P(>=13)` pelo próprio modelo não prova ganho real.

---

# Backtest por composição estrutural

Registrar por concurso:

```text
D12
D13
D23
T123
SecoTop1
SecoTop2
SecoTop3
hits
14
13+
12+
P13_estimado
DoubleWaste
RecoverySuccess
TripleUseful
```

Consolidar por composição:

```text
D12 D13 D23 T123 | concursos | 14 | 13+ | 12+ | mean_hits
```

Também reportar:

```text
Net13Gain
DecisionNetGain
RecoveryRate
DoubleWasteRate
TripleUsefulnessRate
```

Não promover uma composição fixa apenas porque ela aparece com frequência no otimizador.

---

# Robustez temporal das composições

Comparar:

```text
últimos 50 concursos
últimos 100 concursos
últimos 200 concursos
histórico completo
```

Sinais instáveis devem sofrer shrinkage ou permanecer apenas como diagnóstico.

---

# Ablation estrutural

Comparar pelo menos:

```text
A = otimizador livre 6S-5D-3T / 11-8-6
B = triplos nos três maiores riscos + duplos otimizados
C = composição D12/D13/D23 aprendida historicamente
D = estrutura dinâmica por risk_rank + gaps + entropia
```

Critério principal:

```text
>=13
Net13Gain
```

Critérios auxiliares:

```text
>=12
mean_hits
DecisionNetGain
DecisionWinRate
```

---

# StructuralCost

Medir apenas para auditoria:

```text
P13plus_relaxado = melhor P(>=13) com 6 secos, 5 duplos e 3 triplos sem impor 11/8/6
P13plus_11_8_6  = melhor P(>=13) respeitando 11/8/6
StructuralCost  = P13plus_relaxado - P13plus_11_8_6
```

`StructuralCost` nunca autoriza relaxar Hard Constraints.

---

# Auditoria estrutural dos duplos e triplos

Não limitar a auditoria à fronteira simples por `1-p(top1)`.

Usar como auditoria principal:

```text
Jogo
risk_rank
p(top1)
p(top2)
p(top3)
Tipo
Cobertura
DoubleGain / RecoveryGain / TripleGain
GainPerExtraMark
DeltaP13plus de substituição
```

A fronteira por `risk_rank` pode permanecer como diagnóstico secundário.

---

# Matriz de substituições globais

Para cada decisão não-seca selecionada:

1. remover temporariamente a decisão;
2. testar outra localização e/ou outro tipo estrutural;
3. reconstruir uma solução global válida 11/8/6 e 6S/5D/3T;
4. recalcular exatamente `P(>=13)`;
5. medir:

```text
DeltaP13plus = P13plus_alternativo - P13plus_original
```

Telemetria sugerida:

```text
JogoOriginal
JogoSubstituto
TipoOriginal
TipoSubstituto
P13plus_original
P13plus_alternativo
DeltaP13plus
```

A troca deve preservar todas as Hard Constraints.

---

# Explicação de decisões inesperadas

Quando um jogo de alto risco permanecer seco enquanto outro de risco menor receber duplo ou triplo, emitir diagnóstico estrutural.

Exemplo:

```text
Jogo A permaneceu seco porque promovê-lo a triplo exigiria
compensações na distribuição 11/8/6 que reduziriam P(>=13) em X.
```

Sempre que possível, quantificar com `DeltaP13plus`.

---

# Pesquisa condicional Top1_fail -> Top2 / Top3

Estudar:

```text
P(top2_hit | top1_fail)
P(top3_hit | top1_fail)
```

Treinar um Challenger somente nos jogos históricos com:

```text
top1_hit = 0
```

Target sugerido:

```text
Top2 -> 1
Top3 -> 0
```

Features candidatas:

```text
risk_rank
gap12
gap13
gap23
entropia
p(top1)
p(top2)
p(top3)
posição no concurso
janelas históricas
```

Métricas:

```text
ConditionalAccuracy
ConditionalLogLoss
ConditionalBrier
Top2Recall_when_Top1Fails
Top3Recall_when_Top1Fails
```

A aplicação inicial preferencial é orientar D12/D13/D23 e a necessidade de T123, sem substituir probabilidades base sem validação.

---

# IC e bootstrap para 13+

Como `>=13` é raro, diferenças pequenas podem ser ruído.

Para Champion/Challenger, estimar:

```text
IC95% da taxa de 13+
IC95% da diferença de taxas
bootstrap pareado por concurso
IC95% do Net13Gain ou equivalente
```

O bootstrap deve preservar o pareamento Champion/Challenger por concurso.

Não promover técnica cujo ganho em 13+ seja estatisticamente frágil ou dependa de poucos concursos isolados.

---

# Champion/Challenger estrutural

```text
Champion = otimizador estrutural implantado
Challenger = nova regra/modelo/composição candidata
```

Uma mudança só deve ser promovida quando:

```text
1. todas as Hard Constraints forem satisfeitas
2. houver melhora real de >=13 em walk-forward
3. Net13Gain for positivo ou claramente não inferior sob incerteza
4. não houver regressão relevante em >=12
5. DecisionNetGain / DecisionWinRate forem compatíveis
6. houver robustez temporal
7. não houver evidência de sobreajuste
```

Log-loss, Brier, ECE, `mean_hits`, métricas condicionais e métricas de uso dos triplos são evidências auxiliares.

---

# Validação independente

Após a otimização, validar novamente:

```text
jogos = 14
secos = 6
duplos = 5
triplos = 3
Top1 = 11
Top2 = 8
Top3 = 6
marcações = 25
Flamengo = regra satisfeita, quando aplicável
```

Nunca corrigir silenciosamente um bilhete inválido.

---

# Telemetria mínima

Para cada jogo:

```text
Jogo
Mandante x Visitante
p(1)
p(X)
p(2)
top1 / top2 / top3
p(top1) / p(top2) / p(top3)
gap12
gap13
entropia
risk_rank
pTop1_base
pTop1_ajustado
delta_pTop1
ranking_mudou
CoberturaD12
CoberturaD13
CoberturaD23
CoberturaT123
seco / duplo / triplo
palpite
ranks selecionados
probabilidade coberta
DoubleGain / RecoveryGain / TripleGain
GainPerExtraMark
```

Resumo:

```text
Secos: 6/6
Duplos: 5/5
Triplos: 3/3
Top1: 11/11
Top2: 8/8
Top3: 6/6
Marcações: 25/25
Composição D12/D13/D23
Triplos: 3
Flamengo: regra satisfeita
```

Decomposição:

```text
P(14)
P(13)
P(>=13)
P(12)
P(>=12)
```

---

# Estado atual de implementação

Este repositório está sendo migrado da estrutura anterior **8S-6D-0T / 10-5-5** para a nova estrutura **6S-5D-3T / 11-8-6**.

O README define a especificação-alvo do projeto. Durante a migração, código, testes e telemetria devem ser atualizados para obedecer integralmente às Hard Constraints descritas neste documento.

Prioridades de implementação:

```text
1. adicionar T123 às opções do otimizador
2. alterar o estado da DP para controlar duplos e triplos
3. trocar o estado terminal para 11/8/6 + 5 duplos + 3 triplos
4. atualizar validate_ticket()
5. atualizar telemetria e auditorias estruturais
6. adaptar testes
7. executar backtest walk-forward Champion/Challenger
```

---

# Princípio geral

O projeto procura construir **um único bilhete de 14 jogos**, com exatamente **6 secos, 5 duplos, 3 triplos e distribuição 11-8-6**, cuja combinação de probabilidades, histórico e estrutura maximize:

```text
P(acertos >= 13)
```

Toda melhoria deve ser demonstrada fora da amostra e sempre dentro das Hard Constraints.