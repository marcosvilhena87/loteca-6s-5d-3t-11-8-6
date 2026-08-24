# Loteca 6S-5D-3T — Estratégia 11-8-6

Projeto para geração de **um único palpite final por concurso da Loteca**, usando histórico, probabilidades estimadas, calibração e otimização estrutural para maximizar prioritariamente:

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

Em caso de empate de probabilidades:

```text
1 > 2 > X
```

Quando o **FLAMENGO/RJ** participar, sua vitória deve obrigatoriamente estar entre as marcações.

Soft Constraints nunca podem relaxar Hard Constraints.

---

# Consistência estrutural

```text
6 secos  x 1 =  6 marcações
5 duplos x 2 = 10 marcações
3 triplos x 3 =  9 marcações
Total          = 25 marcações
```

A distribuição por rank também fecha exatamente:

```text
11 Top1
8 Top2
6 Top3
Total = 25
```

---

# Tipos de decisão

Para cada partida, o otimizador pode escolher:

```text
S1   = Top1
S2   = Top2
S3   = Top3
D12  = Top1 + Top2
D13  = Top1 + Top3
D23  = Top2 + Top3
T123 = Top1 + Top2 + Top3
```

Coberturas:

```text
CoberturaS1   = p(top1)
CoberturaS2   = p(top2)
CoberturaS3   = p(top3)
CoberturaD12  = p(top1) + p(top2)
CoberturaD13  = p(top1) + p(top3)
CoberturaD23  = p(top2) + p(top3) = 1 - p(top1)
CoberturaT123 = 1
```

A decisão final é global. Não selecionar secos, duplos ou triplos apenas pelo `risk_rank` ou por `1-p(top1)`.

---

# Estrutura dos duplos e triplos

```text
D12 + D13 + D23 = 5
T123 = 3
```

Os secos por rank são derivados de:

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

E obrigatoriamente:

```text
SecoTop1 + SecoTop2 + SecoTop3 = 6
```

---

# DoubleGain, RecoveryGain e TripleGain

Para D12 e D13:

```text
DoubleGain(D12) = p(top2)
DoubleGain(D13) = p(top3)
```

Para D23:

```text
RecoveryGain(D23)
= CoberturaD23 - p(top1)
= 1 - 2*p(top1)
```

Para T123 em comparação com S1:

```text
TripleGain(T123 vs S1)
= 1 - p(top1)
```

Como o triplo consome duas marcações adicionais em relação a S1:

```text
GainPerExtraMark(T123 vs S1)
= (1 - p(top1)) / 2
```

`GainPerExtraMark` é apenas diagnóstico. O objetivo continua sendo a maximização exata de `P(>=13)`.

---

# Soft Constraints

## Preferência contra vitórias de Palmeiras e Vasco

Quando **PALMEIRAS/SP** ou **VASCO DA GAMA/RJ** participarem, favorecer soluções que excluam suas vitórias, desde que isso não comprometa significativamente a qualidade global.

Ordem correta:

```text
1. encontrar o ótimo probabilístico dentro das Hard Constraints
2. definir uma faixa de soluções quase ótimas
3. dentro da faixa, favorecer exclusão de Palmeiras/Vasco
4. priorizar exclusão de ambas, quando possível
5. aplicar demais critérios de desempate
```

Tolerância inicial de pesquisa:

```text
perda relativa máxima em P(>=13) = 0,5%
```

Não adicionar bônus arbitrário diretamente a `P(>=13)`.

Auditoria futura desejada:

```text
melhor solução sem Soft Constraint
melhor solução anti-Vasco
melhor solução anti-Palmeiras
melhor solução anti-ambos
perda relativa de cada alternativa
```

---

# risk_rank

Ordenar os 14 jogos do maior risco relativo de falha do Top1 para o menor:

```text
risk_rank = 1..14
risk_rank = 1  -> maior risco
risk_rank = 14 -> menor risco
```

Auditar por rank:

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

Métricas candidatas:

```text
RiskRankPrecision@8
RiskRankRecall@8
RiskRankNDCG@8
RiskRankECE
Brier por risk_rank
```

`risk_rank` é um sinal de risco, não uma regra automática de alocação de marcações.

---

# Promoção probabilística vs promoção decisória

Uma calibração pode melhorar LogLoss/Brier sem demonstrar melhora de `13+`.

Separar conceitualmente:

```text
risk_rank_probability_promoted
risk_rank_decision_promoted
```

Critérios probabilísticos:

```text
LogLoss
Brier
ECE
calibração por rank
```

Critérios decisórios:

```text
13+
12+
Net13Gain
DecisionNetGain
DecisionWinRate
mean_hits
```

A melhora probabilística é evidência auxiliar; não prova melhora do bilhete final.

---

# Seleção dos triplos

Os três triplos devem ser escolhidos globalmente.

Não assumir:

```text
triplos = três menores p(top1)
```

nem:

```text
triplos = risk_rank 1, 2 e 3
```

A estrutura 11-8-6 cria compensações globais entre Top1, Top2 e Top3.

Para cada triplo registrar:

```text
Jogo
risk_rank
p(top1)
p(top2)
p(top3)
entropia
gap12
gap13
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

A distribuição exata de acertos é obtida por convolução dinâmica.

Objetivo:

```text
P(>=13) = P(13) + P(14)
```

Estado estrutural da programação dinâmica:

```text
(Top1, Top2, Top3, duplos, triplos)
```

Estado terminal:

```text
(11, 8, 6, 5, 3)
```

A quantidade de secos é derivada:

```text
secos = 14 - duplos - triplos = 6
```

---

# Distribuição exata de acertos

Reportar:

```text
P(14)
P(13)
P(>=13)
P(12)
P(>=12)
```

A probabilidade retornada pelo otimizador deve ser confirmada independentemente pela distribuição final.

```text
Auditoria DP vs otimizador -> diferença esperada próxima de zero
```

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
13+
12+
mean_hits
median_hits
Net13Gain
DecisionNetGain
DecisionWinRate
RecoveryRate
DoubleWasteRate
TripleRescueRate
TripleWasteRate
```

O ganho estimado pelo próprio modelo em `P(>=13)` não prova ganho real.

---

# Comparação 8S-6D-0T vs 6S-5D-3T

Executar comparação histórica direta usando os mesmos concursos e probabilidades:

```text
Champion antigo = 8S-6D-0T / 10-5-5
Challenger novo = 6S-5D-3T / 11-8-6
```

Métricas principais:

```text
14
13+
12+
mean_hits
Net13Gain
```

Objetivo da comparação:

```text
medir se as marcações extras e os três triplos
se convertem em ganho real de 13+ fora da amostra
```

---

# Backtest dos triplos

Para cada triplo histórico registrar:

```text
Top1_hit
Top1_fail
TripleRescue
TripleWaste
```

Definições:

```text
TripleRescue = Top1 falhou, mas Top2/Top3 acertou
TripleWaste  = Top1 acertou; as duas marcações extras não foram necessárias
```

Consolidar:

```text
TripleRescueRate
TripleWasteRate
13+ obtidos com resgate de triplo
12+ obtidos com resgate de triplo
```

---

# Backtest por composição estrutural

Registrar:

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
TripleRescue
TripleWaste
```

Consolidar por composição:

```text
D12 D13 D23 | concursos | 14 | 13+ | 12+ | mean_hits
```

Não promover composição fixa apenas porque aparece frequentemente no otimizador.

---

# StructuralCost da distribuição 11-8-6

Medir:

```text
P13plus_relaxado = melhor P(>=13) com 6S/5D/3T sem impor 11/8/6
P13plus_11_8_6   = melhor P(>=13) impondo 11/8/6
StructuralCost   = P13plus_relaxado - P13plus_11_8_6
```

`StructuralCost` é diagnóstico e nunca autoriza relaxar Hard Constraints do Champion implantado.

---

# Pesquisa de distribuições alternativas de rank

Testar distribuições compatíveis com 25 marcações, por exemplo:

```text
11-8-6
12-7-6
11-9-5
10-9-6
12-8-5
```

Somente promover uma nova distribuição após walk-forward robusto.

Comparar:

```text
13+
12+
mean_hits
Net13Gain
robustez temporal
```

Essa pesquisa deve ser tratada como Challenger estrutural separado.

---

# Robustez temporal

Comparar resultados em:

```text
últimos 50 concursos
últimos 100 concursos
últimos 200 concursos
histórico completo
```

Sinais instáveis devem sofrer shrinkage ou permanecer apenas como diagnóstico.

---

# Shrinkage adaptativo do risk_rank

Candidato de pesquisa:

```text
lift_final = 1 + confiança * (lift_observado - 1)
```

A confiança pode considerar:

```text
n
largura do IC95%
estabilidade temporal
consistência entre janelas
```

Ranks instáveis devem ser puxados mais fortemente para `1.0`.

---

# Modelos Challenger condicionais

## Challenger A — Top1 vai falhar?

Target:

```text
Top1_fail
```

Features candidatas:

```text
p(top1)
p(top2)
p(top3)
gap12
gap13
entropia
risk_rank
posição no concurso
janelas históricas
```

Aplicação inicial: sinal auxiliar para alocação estrutural, sem substituir as probabilidades 1/X/2.

## Challenger B — se Top1 falhar, Top2 ou Top3?

Estudar:

```text
P(top2_hit | top1_fail)
P(top3_hit | top1_fail)
```

Métricas:

```text
ConditionalAccuracy
ConditionalLogLoss
ConditionalBrier
Top2Recall_when_Top1Fails
Top3Recall_when_Top1Fails
```

Aplicação preferencial: orientar D12/D13/D23 e necessidade de T123.

---

# Auditoria estrutural 6S-5D-3T

A antiga auditoria simples de “6º vs 7º candidato a duplo” não é suficiente para a nova estrutura.

Substituir por duas fronteiras conceituais:

```text
TRIPLO <-> DUPLO
DUPLO  <-> SECO
```

Mas a auditoria principal deve ser global, reconstruindo sempre uma solução válida 6S/5D/3T e 11/8/6.

---

# Matriz completa de promoções e rebaixamentos

Para cada jogo testar, quando estruturalmente possível:

```text
S1/S2/S3
<-> D12/D13/D23
<-> T123
```

Cada alternativa deve:

```text
1. alterar a decisão candidata
2. reconstruir globalmente o restante do bilhete
3. manter 6S/5D/3T e 11/8/6
4. recalcular exatamente P(>=13)
5. recalcular P(>=12)
```

Telemetria:

```text
Jogo
DecisaoAtual
Alternativa
P13plus_original
P13plus_alternativo
DeltaP13plus
P12plus_original
P12plus_alternativo
DeltaP12plus
```

---

# Structural Importance

Para cada decisão do bilhete, medir o custo de sua melhor substituição válida:

```text
StructuralImportance_i
= P13plus_original - melhor_P13plus_sem_a_decisao_atual
```

Interpretação:

```text
valor alto  -> decisão estruturalmente importante
valor baixo -> decisão marginal / facilmente substituível
```

---

# structural_rank

Separar:

```text
risk_rank       = risco de falha do Top1
structural_rank = valor marginal da alocação de marcações
```

Um jogo pode ter alto risco e ainda assim não merecer triplo, porque outra decisão como D23 pode usar melhor o orçamento estrutural.

Comparar por jogo:

```text
risk_rank
structural_rank
DecisaoAtual
StructuralImportance
```

---

# Confidence Margin da decisão

Para cada jogo, comparar a decisão atual com sua melhor alternativa estrutural válida:

```text
ConfidenceMargin
= P13plus_atual - P13plus_melhor_alternativa
```

Isso permite distinguir:

```text
decisão robusta
vs
decisão marginal
```

---

# Degenerescência do ótimo

Contar quantas soluções válidas existem dentro de:

```text
0,10%
0,25%
0,50%
1,00%
```

de perda relativa em relação ao ótimo.

Interpretação:

```text
muitas soluções quase ótimas -> preferências soft são baratas
poucas soluções quase ótimas  -> estrutura ótima é rígida
```

---

# Bilhete alternativo de diversidade

Como diagnóstico, encontrar uma solução quase ótima com máxima distância de Hamming do Champion.

Objetivo:

```text
maximizar diversidade
sujeito a P13plus >= limite de quase ótimo
```

Não substitui o bilhete oficial. Serve para medir concentração e estabilidade do ótimo.

---

# Miss Type Analysis

Quando o bilhete errar um jogo, registrar:

```text
resultado real era Top1 / Top2 / Top3
decisão escolhida
seco / duplo / triplo
risk_rank
structural_rank
```

Objetivo: detectar padrões como:

```text
Top3 excessivamente perdido em secos
D23 resgatando muitos Top1_fail
triplos desperdiçados em favoritos fortes
```

---

# Bootstrap e incerteza de 13+

Como `13+` é raro, diferenças pequenas podem ser ruído.

Para Champion/Challenger estimar:

```text
IC95% da taxa de 13+
IC95% da diferença de taxas
bootstrap pareado por concurso
IC95% do Net13Gain
```

O bootstrap deve preservar o pareamento concurso a concurso.

Não promover técnica cujo ganho dependa de poucos concursos isolados.

---

# Champion / Challenger

```text
Champion   = método atualmente implantado
Challenger = nova regra, modelo ou estrutura candidata
```

Promover somente quando:

```text
1. todas as Hard Constraints forem satisfeitas
2. houver melhora real de 13+ em walk-forward
3. Net13Gain for positivo ou claramente não inferior sob incerteza
4. não houver regressão relevante em 12+
5. DecisionNetGain / DecisionWinRate forem compatíveis
6. houver robustez temporal
7. não houver evidência de sobreajuste
```

LogLoss, Brier, ECE, `mean_hits` e métricas condicionais são auxiliares.

---

# Telemetria mínima por jogo

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

Telemetria estrutural futura:

```text
structural_rank
StructuralImportance
ConfidenceMargin
melhor alternativa válida
DeltaP13plus
DeltaP12plus
```

---

# Estado atual

A migração principal para **6S-5D-3T / 11-8-6 está operacional**.

A execução atual confirma funcionamento de:

```text
6 secos / 5 duplos / 3 triplos
11 Top1 / 8 Top2 / 6 Top3
25 marcações
T123 no otimizador
programação dinâmica com estado 11/8/6 + 5D + 3T
validação independente das Hard Constraints
regra obrigatória do Flamengo
DoubleGain / RecoveryGain / TripleGain
GainPerExtraMark
matriz de substituições
calibração por temperatura
calibração e auditoria por risk_rank
Soft Constraints anti-Palmeiras/Vasco
convolução exata da distribuição de acertos
```

Na execução de referência, a auditoria independente confirmou diferença zero entre o objetivo do otimizador e a distribuição recalculada:

```text
Auditoria DP vs otimizador = 0.000e+00
```

A antiga seção “fronteira do 6º vs 7º candidato a duplo” deve ser considerada **legado do modelo 8S-6D-0T** e será substituída pela auditoria global Triplo/Duplo/Seco.

---

# Roadmap priorizado

## Prioridade 1 — auditoria estrutural nativa do 6S-5D-3T

```text
1. remover/substituir a velha fronteira 6º vs 7º duplo
2. implementar fronteiras Triplo<->Duplo e Duplo<->Seco
3. criar matriz completa de promoções/rebaixamentos
4. calcular StructuralImportance
5. calcular ConfidenceMargin
6. criar structural_rank
7. gerar explicação automática para decisões inesperadas
```

## Prioridade 2 — provar o ganho da nova estrutura

```text
1. walk-forward 8S-6D-0T vs 6S-5D-3T
2. TripleRescueRate / TripleWasteRate
3. bootstrap pareado para 13+
4. IC95% de Net13Gain
5. robustez em 50/100/200 concursos e histórico completo
```

## Prioridade 3 — validar a distribuição 11-8-6

```text
1. medir StructuralCost de 11-8-6
2. pesquisar distribuições alternativas de rank
3. comparar 11-8-6, 12-7-6, 11-9-5, 10-9-6, 12-8-5 etc.
4. promover apenas com ganho walk-forward robusto
```

## Prioridade 4 — evolução do risk_rank

```text
1. separar promoção probabilística da promoção decisória
2. shrinkage adaptativo por estabilidade/confiança
3. Challenger Top1_fail
4. Challenger Top2 vs Top3 condicionado à falha do Top1
5. analisar Miss Type por risk_rank
```

## Prioridade 5 — estabilidade e explicabilidade

```text
1. degenerescência do ótimo
2. bilhete alternativo de máxima diversidade
3. custo histórico das Soft Constraints
4. relatório por concurso Champion vs Challenger
5. explicação automática por jogo com DeltaP13plus
```

---

# Princípio geral

O projeto procura construir **um único bilhete de 14 jogos**, com exatamente **6 secos, 5 duplos, 3 triplos e distribuição 11-8-6**, cuja combinação de probabilidades, histórico e estrutura maximize:

```text
P(acertos >= 13)
```

Toda melhoria deve ser demonstrada fora da amostra, comparada contra um Champion e mantida sempre dentro das Hard Constraints.