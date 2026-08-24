# Loteca 8S-6D-0T — Estratégia 10-5-5

Projeto para geração de **um único palpite final por concurso da Loteca**, usando o histórico e as informações do próximo concurso para maximizar prioritariamente:

```text
P(acertos >= 13)
```

Toda técnica deve respeitar integralmente as Hard Constraints. Probabilidades, histórico, calibração, heurísticas, meta-modelos e Soft Constraints só podem atuar dentro do espaço de soluções válidas.

---

# Hard Constraints

```text
14 jogos
8 secos
6 duplos
0 triplos
10 Top1
5 Top2
5 Top3
20 marcações
```

Em caso de empate de probabilidades, usar:

```text
1 > 2 > X
```

Quando o **FLAMENGO/RJ** participar, sua vitória deve obrigatoriamente estar entre as marcações.

Soft Constraints nunca podem relaxar Hard Constraints.

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

Não adicionar bônus arbitrário diretamente a `P(>=13)`. A ordem correta é:

```text
ótimo probabilístico
-> faixa aceitável de quase ótimos
-> preferência anti-Palmeiras/Vasco
-> demais critérios de desempate
```

A tolerância deve ser validada historicamente. Se o ganho da preferência pessoal exigir perda probabilística acima do limite definido, prevalece a solução de maior qualidade global.

---

# Estrutura 10-5-5

Definir:

```text
D12 = Top1+Top2
D13 = Top1+Top3
D23 = Top2+Top3
D12 + D13 + D23 = 6
```

Os secos por rank são:

```text
SecoTop1 = 10 - D12 - D13
SecoTop2 = 5  - D12 - D23
SecoTop3 = 5  - D13 - D23
```

Uma baseline estrutural válida é:

```text
8 secos Top1
4 D23
1 D12
1 D13
```

Ela produz exatamente 10 Top1, 5 Top2 e 5 Top3. Essa composição é apenas referência de pesquisa, não regra obrigatória.

---

# Cobertura dos duplos

```text
CoberturaD12 = p(top1) + p(top2)
CoberturaD13 = p(top1) + p(top3)
CoberturaD23 = p(top2) + p(top3) = 1 - p(top1)
```

Como `p(top1) >= p(top2) >= p(top3)`, isoladamente:

```text
CoberturaD12 >= CoberturaD13 >= CoberturaD23
```

A escolha final, porém, é global e deve fechar exatamente 10/5/5.

---

# DoubleGain e RecoveryGain

D12 e D13 preservam Top1 e acrescentam uma segunda marcação:

```text
DoubleGain(D12) = p(top2)
DoubleGain(D13) = p(top3)
```

D23 é diferente: ele abandona Top1 e troca por Top2+Top3. Portanto:

```text
RecoveryGain(D23)
= CoberturaD23 - p(top1)
= 1 - 2*p(top1)
```

Não tratar D23 como `DoubleGain`.

Telemetria por jogo:

```text
p(top1)
p(top2)
p(top3)
CoberturaD12
CoberturaD13
CoberturaD23
tipo escolhido
DoubleGain, se D12/D13
RecoveryGain, se D23
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
RiskRankPrecision@6
RiskRankRecall@6
RiskRankNDCG@6
RiskRankECE
Brier por risk_rank
```

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
```

O ganho estimado de `P(>=13)` pelo próprio modelo não prova ganho real.

---

# Backtest por composição D12/D13/D23

Registrar por concurso:

```text
D12
D13
D23
hits
14
13+
12+
P13_estimado
DoubleWaste
RecoverySuccess
```

Consolidar por composição:

```text
D12 D13 D23 | concursos | 14 | 13+ | 12+ | mean_hits
```

Também reportar:

```text
Net13Gain
DecisionNetGain
RecoveryRate
DoubleWasteRate
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

Comparar:

```text
A = otimizador livre atual
B = composição fixa 4 D23 + 1 D12 + 1 D13
C = composição aprendida historicamente
D = composição dinâmica por risk_rank + gaps + entropia
```

Critério principal:

```text
>=13
Net13Gain
```

---

# StructuralCost

Medir apenas para auditoria:

```text
P13plus_relaxado = melhor P(>=13) com 8 secos e 6 duplos sem impor 10/5/5
P13plus_10_5_5  = melhor P(>=13) respeitando 10/5/5
StructuralCost  = P13plus_relaxado - P13plus_10_5_5
```

`StructuralCost` nunca autoriza relaxar Hard Constraints.

---

# Auditoria estrutural dos 6 duplos

A análise baseada exclusivamente na fronteira 6º/7º por `1-p(top1)` é insuficiente quando existem D12 e D13.

Usar como auditoria principal:

```text
Jogo
risk_rank
p(top1)
p(top2)
p(top3)
Tipo
Cobertura
DoubleGain ou RecoveryGain
DeltaP13plus de substituição
```

A fronteira por `risk_rank` pode permanecer como diagnóstico secundário.

---

# Matriz de substituições globais

Para cada duplo selecionado:

1. remover temporariamente a decisão;
2. testar outro jogo/tipo de duplo;
3. reconstruir solução global válida 10/5/5;
4. recalcular exatamente `P(>=13)`;
5. medir:

```text
DeltaP13plus = P13plus_alternativo - P13plus_original
```

Telemetria:

```text
DuploOriginal
JogoSubstituto
TipoOriginal
TipoSubstituto
P13plus_original
P13plus_alternativo
DeltaP13plus
```

---

# Explicação de secos inesperados

Quando um jogo de `risk_rank` baixo permanecer seco enquanto outro de rank posterior receber duplo, emitir diagnóstico estrutural.

Exemplo:

```text
Jogo A permaneceu seco porque promovê-lo a duplo exigiria
compensação estrutural que reduziria P(>=13) em X.
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

A aplicação inicial preferencial é orientar D12/D13/D23, sem substituir probabilidades base sem validação.

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

Log-loss, Brier, ECE, `mean_hits` e métricas condicionais são evidências auxiliares.

---

# Otimização direta

Para cada jogo:

```text
seco:  c_i = p(resultado selecionado)
duplo: c_i = p(resultado A) + p(resultado B)
```

Obter a distribuição exata de acertos por convolução dinâmica e otimizar diretamente:

```text
P(>=13) = P(13) + P(14)
```

A solução final deve satisfazer:

```text
8 secos
6 duplos
0 triplos
10 Top1
5 Top2
5 Top3
20 marcações
regra obrigatória do Flamengo
```

---

# Validação independente

Após a otimização, validar novamente:

```text
jogos = 14
secos = 8
duplos = 6
triplos = 0
Top1 = 10
Top2 = 5
Top3 = 5
marcações = 20
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
seco / duplo
palpite
ranks selecionados
probabilidade coberta
DoubleGain ou RecoveryGain
```

Resumo:

```text
Secos: 8/8
Duplos: 6/6
Triplos: 0/0
Top1: 10/10
Top2: 5/5
Top3: 5/5
Marcações: 20/20
Composição D12/D13/D23
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

# Princípio geral

O projeto procura construir **um único bilhete de 14 jogos**, com exatamente **8 secos, 6 duplos, 0 triplos e distribuição 10-5-5**, cuja combinação de probabilidades, histórico e estrutura maximize:

```text
P(acertos >= 13)
```

Toda melhoria deve ser demonstrada fora da amostra e sempre dentro das Hard Constraints.