# Gerador de Memorial Descritivo

POC web para gerar memorial descritivo a partir de geometria desenhada ou importada.

## Rodar localmente no Windows

```bat
cd C:\Projetos\gerador-memorial-descritivo\gerador-memorial-descritivo\backend
.venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
python app.py
```

Acesse:

```text
http://localhost:5000
```

## Entradas disponíveis nesta versão

- Desenho no mapa
- CSV
- GeoJSON
- Shapefile ZIP

## CSV esperado

```csv
vertice,x,y,ordem
V1,354215.432,7403125.876,1
V2,354245.918,7403130.221,2
V3,354248.115,7403102.774,3
V4,354217.006,7403098.312,4
```

## Ajustes da versão atualizada

- Correção do desenho no mapa: o cálculo continua em SIRGAS 2000 / UTM 23S, mas o mapa usa coordenadas WGS84.
- Upload de Shapefile ZIP.
- Botão Limpar / reiniciar.
- Validação de pelo menos uma face como Logradouro Público.
- Campo complementar obrigatório quando o tipo for Outro.
- Tratamento melhor de erro quando o backend devolve HTML em vez de JSON.
