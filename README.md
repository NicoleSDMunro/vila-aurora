# Vila Aurora — Q13 | Matriz de Riscos e Gatilhos S&OE

Dashboard acadêmico em Streamlit para a Questão 13 do Bloco 4 (Grupo 02).

## Funcionalidades

- Matriz de sete riscos operacionais com probabilidade, impacto, KPI, gatilho, responsável e ação operacional;
- Mapa de calor e priorização de riscos;
- Cenários F1 (promoção +40% na semana 20) e F2 (lead time duplicado nas semanas 30–31);
- Upload opcional de planilhas Q11/Q12 e Dashboard;
- Exportação Excel da matriz.

## Executar

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Publicar no Streamlit Community Cloud

Acesse https://share.streamlit.io/, autentique-se com GitHub, escolha **Deploy app**, selecione o repositório `NicoleSDMunro/vila-aurora`, branch `main` e arquivo `app.py`. Confirme o deploy e use o endereço fornecido pelo Streamlit.

**Dados:** as planilhas originais não estão incluídas no repositório público; carregue-as apenas na interface do aplicativo. Limiares gerenciais propostos não são medições de campo.
