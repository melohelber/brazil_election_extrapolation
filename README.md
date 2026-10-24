# Apuração presidencial 2026

Projeto para coletar o resultado presidencial do segundo turno no TSE e gerar,
em uma única execução, o snapshot bruto e o resultado projetado das 27 UFs,
do exterior e do Brasil.

O mesmo domínio atende dois modos: a CLI original e uma interface web responsiva
com frontend estático e backend Python em Vercel Functions.

## Interface web

Para abrir o fluxo completo localmente usando dados mockados:

```bash
make dev
```

Acesse `http://127.0.0.1:8000/?mock=1`, clique em **Atualizar apuração**,
confira o status das 27 UFs e do exterior e confirme a geração da análise.

Para usar o TSE real no servidor local:

```bash
make dev-real
```

No Vercel, `public/` é servido pela CDN e `api/snapshot.py` executa a coleta e a
projeção. O navegador mantém o snapshot entre a confirmação e o cálculo; os
JSONs podem ser baixados pelos botões da interface.

Depois que o repositório estiver conectado ao Vercel, uma atualização passa
pelos testes e é publicada com um único comando:

```bash
make deploy
```

## Execução

Na raiz do projeto:

```bash
python3 main.py
```

O programa coleta todas as localidades, mostra `OK` ou `ERRO` para cada uma e
pergunta `Gerar o JSON de resultado? [Y/N]:`. Com `Y`, os dois arquivos são
gravados em `var/snapshots/` com o mesmo identificador de data e hora:

```text
coleta_YYYYMMDD_HHMMSS.json
resultado_YYYYMMDD_HHMMSS.json
```

Os logs ficam em `var/logs/execucao_YYYYMMDD_HHMMSS.log`. Se uma localidade
falhar, o snapshot incompleto é preservado com os erros e o resultado parcial
não é gerado.

Para uma execução automatizada, sem a pergunta interativa:

```bash
python3 main.py --yes
```

## Simulação local

Para visualizar o fluxo completo sem acessar o TSE:

```bash
python3 main.py --mock
```

O modo mock mostra no terminal os votos simulados de cada UF e do exterior,
exibe o resumo `OK` e faz a mesma pergunta `Y/N` do fluxo real. Os resultados
ficam isolados em `var/mock_snapshots/`, com os nomes
`coleta_mock_YYYYMMDD_HHMMSS.json` e
`resultado_mock_YYYYMMDD_HHMMSS.json`.

O cenário padrão está em `data/mocks/cenario_padrao.json`. Para testar outro
arquivo no mesmo formato:

```bash
python3 main.py --mock --arquivo-mock /caminho/para/cenario.json
```

O modo mock é identificado explicitamente no terminal, nos logs e no JSON de
coleta. Nenhuma requisição de rede é feita nesse modo.

## Base do primeiro turno

A base usada na projeção fica em `data/primeiro_turno/`:

- `comparecimento.json`: comparecimento por UF e exterior, incluindo votos
  válidos, brancos e nulos;
- `candidatos/`: resultados nominais de Brasil, 27 UFs e exterior.

Para atualizar toda essa base diretamente no TSE:

```bash
python3 main.py atualizar-primeiro-turno
```

A atualização baixa e valida todas as localidades antes de substituir os
arquivos locais.

## Estrutura

```text
.
├── main.py                         # entrada direta pelo terminal
├── pyproject.toml                  # pacote e comando instalável
├── src/apuracao_presidente/
│   ├── application/                 # casos de uso
│   ├── domain/                      # projeção e regras eleitorais
│   └── infrastructure/              # TSE, JSON e logging
├── data/
│   ├── primeiro_turno/              # base oficial de referência
│   ├── mocks/                       # cenários locais de simulação
│   └── exemplos/                    # entradas e resultado de exemplo
├── tests/                           # testes automatizados
└── var/
    ├── logs/                        # logs gerados
    ├── mock_snapshots/              # resultados gerados com --mock
    └── snapshots/                   # coleta e resultado por execução
```

## Testes

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
