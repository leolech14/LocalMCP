# Technical Stack

> Last Updated: 2025-07-26
> Version: 1.0.0

## Core Technologies

### Application Framework
- **Framework:** FastAPI
- **Version:** >=0.104.0
- **Language:** Python 3.11+

### Database
- **Primary:** Redis (for caching and state)
- **Version:** >=5.0.0
- **ORM:** SQLAlchemy >=2.0.0 (for future persistent storage)

## Backend Stack

### Async Runtime
- **Framework:** asyncio with uvicorn
- **Version:** uvicorn >=0.24.0
- **Workers:** Multi-process with shared Redis state

### MCP Protocol
- **WebSockets:** websockets >=12.0
- **JSON-RPC:** jsonrpc >=3.0
- **Async Files:** aiofiles >=23.2.0

### Semantic Search
- **Vector Database:** FAISS
- **Version:** faiss-cpu >=1.7.4
- **Embeddings:** sentence-transformers >=2.2.2

### LLM Providers
- **OpenAI:** openai >=1.3.0
- **Anthropic:** anthropic >=0.8.0
- **Google:** google-generativeai >=0.3.0
- **Local Models:** transformers >=4.35.0 with torch >=2.1.0

## Infrastructure

### Container Orchestration
- **Platform:** Docker Compose
- **Services:** Redis, Prometheus, Grafana, Jaeger
- **Network:** Bridge network with service discovery

### Monitoring Stack
- **Metrics:** Prometheus with prometheus-client >=0.19.0
- **Visualization:** Grafana (latest)
- **Tracing:** Jaeger with OpenTelemetry
- **Logging:** structlog >=23.2.0

### Caching Infrastructure
- **L1 Cache:** In-memory LRU (Python native)
- **L2 Cache:** Redis >=5.0.0
- **Cache Library:** aiocache >=0.12.0

## Development Tools

### Code Quality
- **Formatter:** black >=23.11.0
- **Linter:** flake8 >=6.1.0
- **Type Checker:** mypy >=1.7.0
- **Pre-commit:** pre-commit >=3.5.0

### Testing
- **Framework:** pytest >=7.4.0
- **Async Testing:** pytest-asyncio >=0.21.0
- **Coverage:** pytest-cov >=4.1.0
- **HTTP Testing:** httpx >=0.25.0

### CLI & Utilities
- **CLI Framework:** click >=8.1.0
- **Rich Output:** rich >=13.7.0
- **Config:** python-dotenv >=1.0.0
- **YAML:** pyyaml >=6.0.1

## Circuit Breaker & Resilience

### Circuit Breaker
- **Primary:** Custom implementation (Elastic Circuit De-Constructor)
- **Fallback:** py-breaker >=0.7.0
- **Retry Logic:** tenacity >=8.2.0

### Error Handling
- **Structured Errors:** Custom error hierarchy
- **Graceful Degradation:** Multi-state circuit breaker
- **Retry Strategies:** Exponential backoff with jitter

## Deployment

### Package Management
- **Build System:** setuptools >=64
- **Package Manager:** pip
- **Virtual Environment:** venv (Python 3.11+)

### Repository
- **Code Repository URL:** https://github.com/leolech14/LocalMCP
- **Documentation:** GitHub Pages (planned)
- **CI/CD:** GitHub Actions (planned)