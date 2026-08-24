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

Distribuição por rank:

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

A decisão é global. Não selecionar secos, duplos ou triplos apenas por `risk_rank`, entropia ou `1-p(top1)`.

---

# Estrutura dos duplos e triplos

```text
D12 + D13 + D23 = 5
T123 = 3
```

Secos por rank:

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

Como o triplo consome duas marcações adicionais:

```text
GainPerExtraMark(T123 vs S1)
= (1 - p(top1)) / 2
```

`GainPerExtraMark` é apenas diagnóstico. O objetivo permanece a maximização exata de `P(>=13)`.

---

# Soft Constraints

## Preferência contra vitórias de Palmeiras e Vasco

Quando **PALMEIRAS/SP** ou **VASCO DA GAMA/RJ** participarem, favorecer soluções que excluam suas vitórias, desde que isso não comprometa significativamente a qualidade global.

Ordem:

```text
1. encontrar o ótimo probabilístico dentro das Hard Constraints
2. definir uma faixa de soluções quase ótimas
3. favorecer exclusão de Palmeiras/Vasco dentro dessa faixa
4. priorizar exclusão de ambas, quando possível
5. aplicar os demais critérios de desempate
```

Tolerância inicial de pesquisa:

```text
perda relativa máxima em P(>=13) = 0,5%
```

Não adicionar bônus arbitrário diretamente a `P(>=13)`.

Auditoria desejada:

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

Métricas:

```text
RiskRankPrecision@8
RiskRankRecall@8
RiskRankNDCG@8
RiskRankECE
Brier por risk_rank
```

`risk_rank` mede risco de falha do Top1; não mede diretamente o valor de gastar marcações naquele jogo.

---

# Promoção probabilística vs promoção decisória

Uma calibração pode melhorar LogLoss/Brier sem melhorar `13+`.

Separar explicitamente no código:

```text
risk_rank_probability_promoted
risk_rank_ticket_promoted
```

Critérios probabilísticos:

```text
LogLoss
Brier
ECE
calibração
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

A melhora probabilística é evidência auxiliar e não prova melhora do bilhete final.

O ajuste probabilístico pode permanecer promovido mesmo quando `risk_rank_ticket_promoted = False`, caso ainda não exista ganho decisório fora da amostra.

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
StructuralMargin
RelativeStructuralMargin
structural_rank
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

Secos:

```text
14 - 5 duplos - 3 triplos = 6
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

Após a otimização:

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

# Auditoria estrutural nativa 6S-5D-3T

A auditoria deve considerar explicitamente as fronteiras:

```text
TRIPLO <-> DUPLO
DUPLO  <-> SECO
```

A auditoria principal é global: qualquer promoção ou rebaixamento deve reconstruir uma solução válida 6S/5D/3T e 11/8/6.

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
4. recalcular P(14)
5. recalcular P(>=13)
6. recalcular P(>=12)
```

Persistir a matriz completa em CSV:

```text
Concurso
JogoOriginal
DecisaoOriginal
JogoSubstituto
DecisaoAlternativa
P14_original
P14_alternativo
DeltaP14
P13plus_original
P13plus_alternativo
DeltaP13plus
P12plus_original
P12plus_alternativo
DeltaP12plus
```

O console pode mostrar apenas as melhores alternativas por decisão; o CSV deve manter todas as alternativas válidas.

---

# StructuralMargin

```text
StructuralMargin_i
= P13plus_original - melhor_P13plus_alternativo_valido
```

Interpretação:

```text
valor alto  -> decisão estruturalmente rígida/importante
valor baixo -> decisão marginal/facilmente substituível
```

Não chamar essa métrica de confiança estatística. Ela mede custo no espaço de soluções.

## Classificação qualitativa inicial

```text
StructuralMargin < 0,075 pp       -> MARGINAL
0,075 a < 0,20 pp                 -> MODERADA
0,20  a < 0,40 pp                 -> FORTE
>= 0,40 pp                         -> MUITO FORTE
```

As faixas são diagnósticas e devem ser validadas historicamente.

### Calibração futura das classes

Comparar os cortes fixos com classes derivadas dos quantis históricos de `StructuralMargin`:

```text
P25
P50
P75
P90
```

Somente substituir os cortes atuais se os limites empíricos mostrarem maior estabilidade e utilidade fora da amostra.

---

# structural_rank

```text
risk_rank       = risco de falha do Top1
structural_rank = ordenação por StructuralMargin
```

Um jogo pode ter alto risco e ainda assim não merecer triplo, porque D23 ou outra alocação pode usar melhor o orçamento estrutural.

Telemetria:

```text
risk_rank
structural_rank
DecisaoAtual
StructuralMargin
RelativeStructuralMargin
classe estrutural
melhor alternativa válida
```

---

# SecondBestMargin e AlternativeGap

Além da melhor alternativa, registrar a segunda melhor alternativa estrutural válida:

```text
BestAlternativeMargin
SecondBestMargin
AlternativeGap = SecondBestMargin - StructuralMargin
```

Interpretação:

```text
AlternativeGap pequeno -> várias alternativas estruturalmente semelhantes
AlternativeGap grande  -> quase empate concentrado em uma alternativa específica
```

Essa distinção permite separar:

```text
marginalidade difusa
vs
marginalidade pareada
```

---

# RelativeStructuralMargin

Além da margem absoluta, registrar:

```text
RelativeStructuralMargin
= StructuralMargin / P13plus_original
```

Objetivo: medir o custo da troca em relação ao próprio nível de `P(>=13)` do bilhete.

Reportar preferencialmente como percentual relativo e manter a margem absoluta em pontos percentuais.

---

# Degenerescência do ótimo

Contar quantas soluções válidas existem dentro de perdas relativas de:

```text
0,05%
0,10%
0,25%
0,50%
1,00%
```

Registrar:

```text
faixa
n_solucoes_na_faixa
melhor_P13plus
pior_P13plus
amplitude_P13plus
maior_distancia_Hamming
```

Interpretação:

```text
muitas soluções quase ótimas -> região plana; Soft Constraints são baratas
poucas soluções quase ótimas  -> ótimo rígido; alterações custam mais
```

---

# Bilhete alternativo de diversidade

Como diagnóstico, encontrar uma solução quase ótima com máxima distância de Hamming do Champion.

```text
maximizar diversidade
sujeito a P13plus >= limite de quase ótimo
```

Não substitui o bilhete oficial. Serve para medir concentração do ótimo e diversidade disponível dentro da faixa quase ótima.

---

# TicketRigidityIndex

Criar uma métrica global de rigidez do bilhete apenas para diagnóstico.

Versão inicial simples:

```text
TicketRigidityIndex
= média dos StructuralMargins dos 14 jogos
```

Também registrar:

```text
mediana
mínimo
máximo
desvio-padrão
n_MARGINAL
n_MODERADA
n_FORTE
n_MUITO_FORTE
```

Interpretação:

```text
rigidez alta  -> poucas decisões facilmente substituíveis
rigidez baixa -> muitos quase empates estruturais
```

Não usar `TicketRigidityIndex` como objetivo até existir validação histórica.

---

# Validação histórica do StructuralMargin

Registrar em todos os concursos walk-forward:

```text
Concurso
Jogo
Decisao
risk_rank
structural_rank
StructuralMargin
RelativeStructuralMargin
SecondBestMargin
AlternativeGap
ClasseEstrutural
ResultadoReal
HitsFinal
```

Pesquisar:

```text
1. decisões de margem alta mudam menos entre Champion e Challenger?
2. margem alta está associada a maior estabilidade temporal?
3. decisões marginais concentram alterações de bilhete?
4. decisões marginais concentram ganhos/perdas dos Challengers?
5. classes estruturais mantêm significado entre janelas temporais?
```

`StructuralMargin` é inicialmente uma métrica de explicabilidade. Só poderá virar sinal de decisão após evidência fora da amostra.

---

# Relação risk_rank x structural_rank

Analisar:

```text
alto risco / alta importância estrutural
alto risco / baixa importância estrutural
baixo risco / alta importância estrutural
baixo risco / baixa importância estrutural
```

Gerar também um resumo automático de divergências extremas:

```text
maior risco com baixa importância estrutural
menor risco com alta importância estrutural
maior diferença absoluta entre risk_rank e structural_rank
```

Objetivo: mostrar por que “jogo difícil” não significa automaticamente “triplo”.

---

# Métricas específicas dos triplos

Registrar historicamente:

```text
TripleRescue
TripleWaste
TripleCritical
TripleMargin
```

Definições:

```text
TripleRescue
= Top1 falhou, mas Top2/Top3 coberto pelo triplo acertou

TripleWaste
= Top1 acertou; as duas marcações extras não foram necessárias naquele jogo

TripleCritical
= sem aquele triplo, o bilhete cairia de 13+ para menos de 13

TripleMargin
= custo em P13plus de rebaixar aquele triplo para a melhor estrutura alternativa válida
```

Consolidar:

```text
TripleRescueRate
TripleWasteRate
TripleCriticalRate
média/mediana de TripleMargin
13+ obtidos com resgate crítico de triplo
```

---

# Challengers de seleção de triplos

Comparar o DP global com heurísticas simples:

```text
A = triplos escolhidos pelo DP
B = três menores p(top1)
C = três maiores entropias
D = três maiores 1-p(top1)
E = seleção aleatória válida repetida em múltiplas amostras
```

Comparar:

```text
13+
12+
mean_hits
Net13Gain
TripleCriticalRate
```

Objetivo: medir quanto do valor vem da existência dos três triplos e quanto vem da localização ótima escolhida pelo DP.

---

# Métricas específicas de D23

Registrar:

```text
RecoverySuccess
RecoveryCritical
Top1AbandonmentLoss
NetRecoveryGain
```

Definições:

```text
RecoverySuccess
= Top1 falhou e Top2/Top3 coberto por D23 acertou

Top1AbandonmentLoss
= Top1 acertou, mas foi excluído pelo D23

RecoveryCritical
= a escolha D23 foi necessária para manter o bilhete em 13+
```

Consolidar:

```text
RecoverySuccessRate
RecoveryCriticalRate
Top1AbandonmentLossRate
NetRecoveryGain
```

Objetivo: medir quando o caráter agressivo de D23 gera ganho líquido real.

---

# Zona marginal como espaço de pesquisa

Medir historicamente:

```text
% das mudanças Champion/Challenger na zona marginal
% dos ganhos de hits originados na zona marginal
% das perdas originadas na zona marginal
% das mudanças de faixa 13+ originadas na zona marginal
```

Se a maior parte das mudanças úteis ocorrer nas decisões marginais, testar Challengers restritos a essa região.

---

# Proteção experimental do núcleo estrutural

Challenger de pesquisa:

```text
fixar decisões MUITO FORTE/FORTE
permitir mudanças apenas nas MODERADAS/MARGINAIS
```

Comparar contra o otimizador totalmente livre.

Objetivo: verificar se `StructuralMargin` permite reduzir o espaço de busca sem regressão de `13+`.

Essa proteção nunca deve ser promovida sem validação walk-forward.

---

# Backtest walk-forward

Comparar no mínimo:

```text
A = probabilidades brutas
B = + temperatura
C = + temperatura + risk_rank probabilístico
D = + alteração decisória de risk_rank, quando candidata
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
RecoverySuccessRate
RecoveryCriticalRate
Top1AbandonmentLossRate
TripleRescueRate
TripleWasteRate
TripleCriticalRate
TicketRigidityIndex
```

O ganho estimado pelo próprio modelo em `P(>=13)` não prova ganho real.

---

# StructuralCost da distribuição 11-8-6

```text
P13plus_relaxado = melhor P(>=13) com 6S/5D/3T sem impor 11/8/6
P13plus_11_8_6   = melhor P(>=13) impondo 11/8/6
StructuralCost   = P13plus_relaxado - P13plus_11_8_6
```

`StructuralCost` é diagnóstico e nunca autoriza relaxar as Hard Constraints do Champion implantado.

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

Comparar:

```text
13+
12+
mean_hits
Net13Gain
robustez temporal
StructuralCost
```

Tratar cada distribuição como Challenger estrutural separado.

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

Aplicação inicial: sinal auxiliar para alocação estrutural, sem substituir probabilidades 1/X/2.

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

# Miss Type Analysis

Quando o bilhete errar um jogo, registrar:

```text
resultado real = Top1 / Top2 / Top3
decisão escolhida
seco / duplo / triplo
risk_rank
structural_rank
StructuralMargin
RelativeStructuralMargin
classe estrutural
```

Objetivo: detectar padrões como:

```text
Top3 excessivamente perdido em secos
D23 resgatando muitos Top1_fail
triplos desperdiçados em favoritos fortes
decisões marginais concentrando erros
```

---

# Bootstrap e incerteza de 13+

Como `13+` é raro, diferenças pequenas podem ser ruído.

Para Champion/Challenger:

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
Challenger = nova regra, modelo ou estrutura candidata dentro do projeto 6S-5D-3T / 11-8-6
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

LogLoss, Brier, ECE, `mean_hits`, `StructuralMargin` e métricas condicionais são evidências auxiliares.

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
structural_rank
StructuralMargin
RelativeStructuralMargin
classe estrutural
melhor alternativa válida
SecondBestMargin
AlternativeGap
```

---

# Resumo estrutural do bilhete

## Núcleo estrutural

```text
Rank estrutural | Jogo | Decisão | StructuralMargin | RelativeStructuralMargin | Classe
```

## Zona marginal

```text
Jogo | Decisão | Melhor alternativa | StructuralMargin | AlternativeGap | DeltaP12plus
```

## Perfil de rigidez

```text
MUITO FORTE: n
FORTE:       n
MODERADA:    n
MARGINAL:    n

StructuralMargin média
StructuralMargin mediana
StructuralMargin mínima
StructuralMargin máxima
TicketRigidityIndex
```

---

# Divergências risco x estrutura

Imprimir os casos mais informativos:

```text
maior risco com menor importância estrutural
menor risco com maior importância estrutural
maior |risk_rank - structural_rank|
```

Essa seção deve explicar por que a alocação global pode divergir de uma ordenação simples por risco.

---

# Explicação automática por jogo

Gerar justificativa auditável usando somente métricas calculadas.

Exemplo:

```text
Jogo X recebeu D23 porque possui alto risco de falha do Top1,
a cobertura Top2+Top3 é competitiva e a melhor reconstrução
estrutural alternativa reduz P13plus em Y pp.
```

A explicação nunca deve substituir ou alterar o cálculo global.

---

# Estado atual

A estrutura **6S-5D-3T / 11-8-6 está operacional**.

A execução de referência confirma:

```text
6 secos / 5 duplos / 3 triplos
11 Top1 / 8 Top2 / 6 Top3
25 marcações
T123 no otimizador
programação dinâmica 11/8/6 + 5D + 3T
validação independente das Hard Constraints
regra obrigatória do Flamengo
DoubleGain / RecoveryGain / TripleGain
GainPerExtraMark
matriz de substituições estruturais
structural_rank
StructuralMargin classificado e SecondBestMargin
persistência da matriz completa em output/predictions_substitutions.csv
resumos de núcleo estrutural e zona marginal
calibração por temperatura
calibração e auditoria por risk_rank
Soft Constraints anti-Palmeiras/Vasco
convolução exata da distribuição de acertos
```

Na execução de referência:

```text
P(14)   = 0.57582317%
P(13)   = 3.88596809%
P(>=13) = 4.46179126%
P(12)   = 11.75782819%
P(>=12) = 16.21961945%
Auditoria DP vs otimizador = 0.000e+00
```

A calibração de `risk_rank` apresentou melhora probabilística e leve melhora decisória média, mas ainda sem ganho observado de `13+` na amostra de validação da execução de referência. Portanto, a distinção entre promoção probabilística e promoção decisória permanece prioritária.

---

# Roadmap priorizado

## Prioridade 1 — completar a auditoria estrutural

```text
1. [x] StructuralMargin
2. [x] classificação MARGINAL / MODERADA / FORTE / MUITO FORTE
3. [x] persistência da matriz completa em CSV
4. [x] BestAlternativeMargin e SecondBestMargin
5. [x] núcleo estrutural e zona marginal
6. [ ] AlternativeGap
7. [ ] RelativeStructuralMargin
8. [ ] DeltaP14 na matriz de substituições
9. [ ] perfil de rigidez / TicketRigidityIndex
10. [ ] divergências risk_rank x structural_rank
```

## Prioridade 2 — validar StructuralMargin fora da amostra

```text
1. salvar StructuralMargin em todo walk-forward
2. salvar RelativeStructuralMargin, SecondBestMargin e AlternativeGap
3. testar estabilidade temporal do structural_rank
4. verificar se decisões marginais concentram mudanças de Champion/Challenger
5. verificar se margem alta prediz estabilidade estrutural
6. validar ou recalibrar as classes por quantis históricos
```

## Prioridade 3 — medir o valor real de triplos e D23

```text
1. TripleRescueRate
2. TripleWasteRate
3. TripleCriticalRate
4. TripleMargin
5. RecoverySuccessRate
6. RecoveryCriticalRate
7. Top1AbandonmentLossRate
8. NetRecoveryGain
9. comparar DP vs heurísticas simples e seleção aleatória válida de triplos
```

## Prioridade 4 — medir rigidez global do ótimo

```text
1. degenerescência em 0,05 / 0,10 / 0,25 / 0,50 / 1,00%
2. bilhete quase ótimo de máxima distância de Hamming
3. custo histórico das Soft Constraints
4. medir regiões locais de quase empate
5. testar proteção experimental do núcleo estrutural
```

## Prioridade 5 — validar estrutura e distribuição

```text
1. bootstrap pareado para 13+ entre Champion e Challengers internos
2. IC95% de Net13Gain
3. robustez em 50/100/200 concursos e histórico completo
4. StructuralCost da distribuição 11-8-6
5. pesquisa de distribuições alternativas
6. validação walk-forward das mudanças estruturais candidatas
```

## Prioridade 6 — evolução do risk_rank

```text
1. separar risk_rank_probability_promoted de risk_rank_ticket_promoted no código
2. shrinkage adaptativo
3. Challenger Top1_fail
4. Challenger Top2 vs Top3 condicionado a Top1_fail
5. Miss Type Analysis por risk_rank e structural_rank
```

---

# Princípio geral

O projeto procura construir **um único bilhete de 14 jogos**, com exatamente **6 secos, 5 duplos, 3 triplos e distribuição 11-8-6**, cuja combinação de probabilidades, histórico e estrutura maximize:

```text
P(acertos >= 13)
```

Toda melhoria deve ser demonstrada fora da amostra, comparada contra um Champion interno do próprio projeto e mantida sempre dentro das Hard Constraints.
