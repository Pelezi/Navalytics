# GAS - Game Analyst System

## 📋 Descrição do Projeto

Este é um **sistema completo de análise de partidas de Batalha Naval** que captura dados em tempo real de um dispositivo físico (Arduino/ESP via porta serial) e apresenta estatísticas detalhadas através de uma interface web moderna.

### O que o sistema faz:

1. **Captura telemetria de partidas** via porta serial (Arduino/ESP)
2. **Armazena dados estruturados** em banco SQLite
3. **Apresenta dashboards interativos** com:
   - 📊 **Dashboard**: Métricas globais, heatmaps, análises estratégicas
   - 🟢 **Partida Atual**: Acompanhamento em tempo real com tabuleiros visuais
   - 🗂 **Histórico**: Arquivo completo de todas as partidas
   - 🏆 **Ranking**: Pódio animado com top 10 jogadores

### Principais funcionalidades:

✅ Event feed ao vivo durante partidas  
✅ Visualização de tabuleiros em tempo real com acertos/erros  
✅ Heatmap progressivo de taxa de acerto por posição  
✅ Análise de primeiro/último navio afundado  
✅ Estatísticas de turnos, precisão, tempo médio  
✅ Sistema de ranking com pódio visual  


## 🚀 Como Executar

### **1. Requisitos**

- **Python 3.8+**
- Porta serial disponível (USB conectada ao Arduino/ESP)
- Sistema operacional: Windows, Linux ou macOS

### **2. Instalação**

```bash
# Clone ou baixe o projeto
git clone https://github.com/pelezi/navalytics.git
cd navalytics/

# Crie um ambiente virtual (recomendado)
python -m venv .venv

# Ative o ambiente virtual
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Instale as dependências
pip install -r requirements.txt
```

### **3. Capturar Dados da Serial** (Terminal 1)

```bash
# Executa o ingestor que lê a porta serial e salva no banco
python ingest_serial.py

# O script escuta a porta serial 115200 por padrão
```

**Importante**: Deixe este terminal rodando continuamente para capturar as partidas.

### **5. Abrir a Interface Web** (Terminal 2)

```bash
# Em outro terminal (com o ambiente virtual ativado):
streamlit run app.py

# A interface abrirá automaticamente em:
# http://localhost:8501
```


## 📁 Estrutura do Projeto

```
navalytics/
├── app.py                  # Aplicação Streamlit principal
├── core.py                 # Funções e queries utilizadas nas páginas do app
├── ingest_serial.py        # Captura dados da porta serial e salva no banco
├── telemetry_parser.py     # Parser de eventos do protocolo
├── schema.sql              # Estrutura do banco de dados
├── requirements.txt        # Dependências Python
├── battleship.db           # Banco SQLite (criado automaticamente)
└── tabs/                   # Módulos das diferentes páginas
    ├── dashboard.py        # Métricas globais e análises
    ├── current_game.py     # Partida ao vivo
    ├── games.py            # Histórico de partidas
    └── ranking.py          # Ranking de jogadores
```


## 🎮 Protocolo de Telemetria

O sistema espera receber via serial eventos no formato CSV:

- **PN**: Nova partida → `PN,NomeJogador1,NomeJogador2`
- **GS**: Início do jogo → `GS,timestamp_ms`
- **PS**: Posicionamento de navio → `PS,jogador,x,y,tamanho,horizontal,timestamp`
- **SH**: Disparo → `SH,atacante,defensor,x,y,acertou,afundou,restantes,timestamp`
- **GE**: Fim da partida → `GE,vencedor,duracao_ms,NomeJogador1,tiros_jogador1,acertos_jogador1,afundados_jogador1,pontuacao_jogador1,NomeJogador2,tiros_jogador2,acertos_jogador2,afundados_jogador2,pontuacao_jogador2`

## 🎯 Próximos Passos

Após executar, você poderá:
1. Iniciar partidas no dispositivo físico
2. Acompanhar em tempo real na aba "🟢 Partida Atual"
3. Analisar estatísticas no "📊 Dashboard"
4. Consultar histórico em "🗂 Histórico"
5. Ver rankings em "🏆 Ranking"

**Dica**: O repositório tem dados de 3 partidas reais para você explorar!