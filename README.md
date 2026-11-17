# Vila Aurora — Torre de Controle S&OE (3VA · Grupo 02)

Aplicativo **Streamlit** com painéis analíticos para o **Bloco 4 (Q13–Q15)**. Atualizado a partir do arquivo `app_vila_aurora (1).py` fornecido pelo grupo.

## Funcionalidades

- **Painel S&OE** com KPIs, alertas e semáforos operacionais.
- **Q13 — Matriz de riscos:** probabilidade × impacto, gatilhos quantitativos e responsáveis, com comparação de políticas Atual e S&OE.
- **Previsão e política:** backtesting de modelos, erro WAPE, estoques de segurança e perfil de famílias.
- **Simulação:** cenários de ruptura, descarte e logística; promoção de F1 na semana 20 (+40%) e atraso de F2 nas semanas 30–31.
- **Q14 — Automatizar × Humano:** decisões automatizáveis e decisões que exigem aprovação humana.
- **Q15 — Roadmap 90 dias:** ações, investimento e ROI em cenários.

## Como executar localmente

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Dados necessários

O aplicativo **precisa da planilha do Bloco 4** para calcular e exibir os painéis: `ENG4550_3VA_G02_BLOCO4_Dashboard_IA_Roadmap_2026.2_v01.xlsx`, contendo as abas `M_Dashboard_Input` e `N_ROI_Roadmap`.

Para utilizar, envie o arquivo `.xlsx` pela **barra lateral**. Localmente, também é possível colocá-lo na mesma pasta de `app.py`. O código não publica a planilha no repositório público.

> Importante: se não houver planilha carregada, o Streamlit mostrará uma mensagem pedindo o upload. Isso é esperado e evita expor os dados do grupo.

## Deploy no Streamlit Community Cloud

1. Acesse https://share.streamlit.io/ e autentique-se com GitHub.
2. Selecione **New app** e o repositório `NicoleSDMunro/vila-aurora`.
3. Escolha a branch `main` e o arquivo principal `app.py`.
4. Faça o deploy. As dependências serão instaladas a partir de `requirements.txt`.
5. Abra o app e faça o upload da planilha pelo painel lateral.

## Observações metodológicas

As premissas de lead time, validade e capacidade de viagem usadas no modelo são declaradas no código e **devem ser validadas pelo grupo**. Resultados das simulações não são fatos observados. A análise é acadêmica e depende das entradas e dos parâmetros selecionados.

## Segurança

Não suba planilhas privadas, senhas ou `secrets.toml` ao repositório público. O `.gitignore` exclui o arquivo local de segredos.
