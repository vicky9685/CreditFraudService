# CreditFraudService

Enterprise-grade Credit Card Fraud Detection Service powered by open-source AI:
**RAG + ChromaDB + Qwen3/Ollama + LangChain + Google ADK + MCP + Enterprise Governance**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CreditFraudService                          │
│                                                                     │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────────────┐  │
│  │  FastAPI     │   │  MCP Server  │   │   ADK Agent            │  │
│  │  REST API    │   │  (stdio/SSE) │   │  (Qwen3 + 7 tools)    │  │
│  └──────┬───────┘   └──────┬───────┘   └──────────┬─────────────┘  │
│         │                  │                       │                │
│         └──────────────────┴───────────────────────┘                │
│                              │                                      │
│              ┌───────────────┼───────────────┐                      │
│              │               │               │                      │
│     ┌────────▼──────┐ ┌─────▼──────┐ ┌──────▼───────┐             │
│     │  RAG Pipeline │ │   Tools    │ │  Governance  │             │
│     │               │ │            │ │              │             │
│     │ LangChain     │ │ risk_score │ │ Audit Logger │             │
│     │ ChromaDB      │ │ fraud_anal │ │ Policy Engine│             │
│     │ Sentence-BERT │ │ tx_store   │ │ Prometheus   │             │
│     └───────┬───────┘ └─────┬──────┘ └──────────────┘             │
│             │               │                                      │
│     ┌───────▼───────────────▼──────┐                               │
│     │         Ollama / Qwen3       │                               │
│     │   (primary LLM backend)      │                               │
│     │   HuggingFace fallback       │                               │
│     └──────────────────────────────┘                               │
└─────────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Vector DB | **ChromaDB** (open-source) | Persistent embedding store for fraud KB |
| Embeddings | **sentence-transformers/all-MiniLM-L6-v2** | Local CPU embeddings, no API key |
| LLM | **Ollama + Qwen3** | Local inference, zero cost |
| LLM Fallback | **Qwen2.5-0.5B via HuggingFace** | Works without Ollama |
| RAG | **LangChain + ChromaDB** | Retrieval-augmented fraud analysis |
| Agent | **Google ADK** (LlmAgent) | Tool-calling fraud detection agent |
| MCP | **FastMCP** (Anthropic SDK) | Exposes tools via Model Context Protocol |
| API | **FastAPI** | REST API with OpenAPI docs |
| Governance | **Structlog + Prometheus** | Audit trails, metrics, policy enforcement |
| Data | **Synthetic Generator** | 500+ realistic fraud/legit transactions |

## Quick Start

### Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt

# (Recommended) Install Ollama for best LLM quality
# https://ollama.com/
ollama pull qwen3        # or: ollama pull qwen3:1.7b  (smaller)
```

### Option A — Run API Server

```bash
cp .env.example .env
python main.py
# → http://localhost:8000/docs
```

### Option B — Run Demo (no server)

```bash
python main.py --demo
```

### Option C — Run MCP Server

```bash
python main.py --mcp
# Communicates via stdio (connect from Claude Desktop or any MCP client)
```

### Option D — Index knowledge base only

```bash
python main.py --index
```

---

## API Endpoints

### Fraud Detection (`/api/v1/fraud/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/fraud/score` | Compute risk score for a transaction |
| POST | `/fraud/analyze` | Full feature + pattern analysis |
| GET | `/fraud/transaction/{id}` | Analyze stored transaction by ID |
| GET | `/fraud/transactions` | Search/filter transactions |
| GET | `/fraud/velocity/{card_last4}` | Card velocity metrics |
| GET | `/fraud/statistics` | Aggregated fraud stats |
| POST | `/fraud/investigate/{id}` | Full orchestration pipeline |

### RAG Knowledge Base (`/api/v1/rag/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/rag/query` | Natural language query with LLM |
| GET | `/rag/retrieve` | Semantic search (no LLM) |
| POST | `/rag/analyze-transaction/{id}` | RAG-augmented transaction analysis |
| POST | `/rag/index` | Re-index knowledge base |
| GET | `/rag/stats` | ChromaDB collection stats |

### ADK Agent (`/api/v1/agent/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/agent/chat` | Chat with fraud detection agent |
| GET | `/agent/status` | Agent status and available tools |

### Governance (`/api/v1/governance/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/governance/audit/events` | Recent audit events |
| GET | `/governance/audit/stats` | Audit statistics |
| GET | `/governance/metrics/summary` | Model performance metrics + drift |
| GET | `/governance/metrics/prometheus` | Prometheus scrape endpoint |
| GET | `/governance/policy/summary` | Active policies |
| POST | `/governance/feedback` | Submit prediction feedback |

---

## Knowledge Base

Four curated markdown documents indexed into ChromaDB:

| File | Coverage |
|------|---------|
| `fraud_patterns.md` | 8 fraud types (CNP, ATO, velocity, skimming...) |
| `compliance_rules.md` | PCI-DSS, BSA/AML, GDPR Art.22, SOX |
| `investigation_guide.md` | Step-by-step procedures, SAR filing checklist |
| `risk_indicators.md` | Feature weights, composite scoring formula |

---

## RAG Pipeline

```
User Query
    │
    ▼
EmbeddingService (sentence-transformers/all-MiniLM-L6-v2)
    │ embed query
    ▼
ChromaDB.query(top_k=5, cosine similarity)
    │ retrieve relevant chunks
    ▼
Augmented Prompt = [KB Context] + [Transaction Data] + [Query]
    │
    ▼
Ollama/Qwen3 → structured fraud analysis answer
```

---

## ADK Agent Tools

The Google ADK agent has access to 7 tools:

| Tool | Description |
|------|-------------|
| `tool_analyze_transaction` | Full analysis by transaction ID |
| `tool_score_risk` | Risk score from transaction JSON |
| `tool_detect_pattern` | Classify fraud pattern type |
| `tool_card_velocity` | Rolling velocity metrics |
| `tool_search_transactions` | Filter transaction store |
| `tool_fraud_statistics` | Aggregated stats |
| `tool_query_knowledge_base` | RAG knowledge base query |

---

## MCP Tools

The FastMCP server exposes 7 tools consumable by any MCP client:

```
analyze_transaction(transaction_id)
score_transaction_risk(transaction_json)
detect_fraud_patterns(transaction_json)
check_card_velocity(card_last4, window_hours)
search_fraud_transactions(filters...)
get_fraud_stats(hours)
query_fraud_knowledge(question, source_filter)
run_full_investigation(transaction_id)
```

### Claude Desktop Integration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fraud-detection": {
      "command": "python",
      "args": ["/path/to/CreditFraudService/main.py", "--mcp"]
    }
  }
}
```

---

## Enterprise AI Governance

### Audit Trail
- Every fraud decision logged to `./logs/audit.jsonl` (JSON Lines)
- PII masking before persistence (card numbers, emails, IPs)
- Tamper-evident integrity hash per event
- Sequential event IDs for gap detection

### Policy Enforcement (7 active policies)
1. `AUTO_BLOCK_THRESHOLD` — score ≥ 0.95 → immediate block
2. `HUMAN_REVIEW_REQUIRED` — score 0.70–0.95 → 4h SLA
3. `AML_STRUCTURING_ALERT` — amount $9,000–$9,999 → SAR filing
4. `CTR_REQUIRED` — amount ≥ $10,000 → Currency Transaction Report
5. `HIGH_RISK_COUNTRY` — IP in NG/RO/UA/BR → enhanced monitoring
6. `VELOCITY_LIMIT_EXCEEDED` — >10 tx/hr → velocity block
7. `GDPR_EXPLAINABILITY_MISSING` — automated decision without top factors

### Model Monitoring (Prometheus)
- `fraud_predictions_total` (counter, by risk_level/action)
- `fraud_prediction_latency_seconds` (histogram, p50/p95)
- `fraud_risk_score` (histogram, distribution)
- `fraud_detection_rate` (gauge, rolling)
- `policy_violations_total` (counter, by policy/severity)
- `rag_avg_similarity_score` (gauge)

### Drift Detection
Automated alert when metrics deviate >5% from baseline:
- Mean risk score drift
- Fraud rate drift
- Latency p95 drift

---

## Compliance Coverage

| Standard | Requirements Met |
|---------|----------------|
| **PCI-DSS** | Req 10.2/10.3 audit trails, PAN masking, access control |
| **BSA/AML** | CTR >$10k, SAR for structuring, velocity checks |
| **GDPR** | Art.22 automated decision logging, explainability, data minimisation |
| **SOX** | Immutable audit trail, model versioning, quarterly review support |

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=html

# Individual suites
pytest tests/test_data_generator.py -v
pytest tests/test_risk_scoring.py -v
pytest tests/test_governance.py -v
pytest tests/test_fraud_analysis.py -v
```

---

## Configuration

Copy `.env.example` to `.env` and configure:

```env
# LLM — Ollama/Qwen3
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:latest

# Risk thresholds
RISK_THRESHOLD_HIGH=0.80
AUTO_BLOCK_THRESHOLD=0.95

# Governance
PII_MASKING_ENABLED=true
REQUIRE_EXPLAINABILITY=true
MAX_REQUESTS_PER_MINUTE=60
```

---

## Project Structure

```
CreditFraudService/
├── main.py                    # Entry point (API / demo / MCP / index)
├── requirements.txt
├── config/
│   ├── settings.py            # Pydantic settings (reads .env)
│   └── policies.yaml          # Governance policy definitions
├── data/
│   ├── generator.py           # Synthetic fraud data generator
│   └── knowledge_base/        # 4 markdown knowledge docs
├── vectorstore/
│   └── chroma_store.py        # ChromaDB wrapper
├── rag/
│   ├── embeddings.py          # sentence-transformers service
│   ├── retriever.py           # ChromaDB retriever + indexer
│   └── pipeline.py            # Full RAG pipeline
├── llm/
│   └── provider.py            # Ollama/Qwen3 + HuggingFace fallback
├── tools/
│   ├── fraud_analysis.py      # Feature analysis + pattern detection
│   ├── risk_scoring.py        # Rule-based risk engine
│   └── transaction_tools.py   # In-memory transaction store
├── agents/
│   ├── fraud_agent.py         # Google ADK LlmAgent
│   └── orchestrator.py        # Multi-step pipeline orchestrator
├── mcp/
│   └── server.py              # FastMCP server (8 tools)
├── governance/
│   ├── audit.py               # Structured audit logging + PII masking
│   ├── policy.py              # Policy enforcement engine
│   └── monitor.py             # Prometheus metrics + drift detection
├── api/
│   ├── app.py                 # FastAPI app factory
│   └── routes/                # fraud / rag / governance / agent
└── tests/                     # pytest test suite
```

---

## License

MIT License — open-source, free for commercial use.
