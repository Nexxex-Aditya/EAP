# EAP — Agentic Excel Report Automation Platform

Enterprise-grade automation platform for NielsenIQ Discover + Excel reporting workflows. EAP dynamically translates natural language business requests into highly controlled execution graphs, integrating LLM reasoning with deterministic browser and Excel operations.

## Architecture & Core Tenets

EAP was built following a strict 50-point engineering directive emphasizing observability, safety, and deterministic control.

- **Domain-First & Model-Neutral** — Business logic relies on standard interfaces, not vendor SDKs. The **Model Gateway** uses capability-based routing (e.g., requesting a model with `STRUCTURED_EXTRACTION` or `REASONING`) rather than hardcoding model names. It seamlessly integrates with OpenAI, Anthropic, NVIDIA, and local OSS models.
- **Graph-Orchestrated** — Execution workflows are built dynamically by the `GraphBuilder` based on the request and target template capabilities.
- **Execution Evidence & Honest Status** — No "fake success." Every action produces an `ExecutionEvidence` record with intent, action, observation, and verification. Graph nodes without handlers correctly return `NOT_IMPLEMENTED`.
- **Governance & Policy Engine** — LLMs cannot autonomously execute high-risk actions. The `PolicyEngine` enforces browser domain whitelists, file access limits, macro whitelists, and tool restrictions, escalating destructive actions for human approval.
- **Skill Architecture** — All operations (Discover interactions, Excel formatting, Macros) are encapsulated as `Skills` that follow a strict lifecycle: `Permissions → Preconditions → Execute → Verify → Recover`.
- **Persistent Memory Pipeline** — The 6-tier memory system (`OBSERVED -> CANDIDATE -> TESTED -> VALIDATED -> APPROVED -> PROMOTED`) safely acquires business vocabulary and prevents hallucinated term resolution.

## Quick Start

### Installation

```bash
# Install the package with developer and LLM dependencies
pip install -e ".[dev,llm]"

# Install Chromium browser binaries for Playwright
playwright install chromium
```

### Running the Test Suite

EAP has a robust test suite covering core domain contracts, execution graphs, semantic resolution, memory promotion, governance, and skills.

```bash
python -m pytest tests/ -v
```

### Starting the API Server

The project includes a built-in REST API powered by FastAPI.

```bash
uvicorn eap.apps.api.main:app --reload
```
Once running, navigate to [http://localhost:8000/docs](http://localhost:8000/docs) to access the Swagger UI for testing endpoints.

## Project Structure

```
src/eap/
├── core/          # Domain contracts, error taxonomy (15 categories), events
│   └── governance/# Policy Engine, risk levels, and permission handling
├── adapters/      # Abstract interfaces
│   ├── llm/       # Model Gateway & LiteLLM implementation
│   ├── browser/   # Playwright deterministic adapter & semantic UI recovery
│   └── excel/     # Windows COM (pywin32) integration
├── orchestration/ # Dynamic graph execution and evidence tracking
├── skills/        # Atomic, verifiable operations (Base, Discover, Excel)
├── agents/        # Planner, resolver, qc, repair engines
├── ingestion/     # Workbook scanner, spec parser (MD, PDF, DOCX)
├── knowledge/     # Client policies, templates, QC rules
├── qc/            # Honest QC reporting (Numerical, Formula, Visual, Naming)
├── memory/        # Semantic, episodic, and failure memory stores
└── apps/          # FastAPI application, routing, background workers
```

## Setup for Different LLM Providers

Because of the `ModelGateway` and `LiteLLMAdapter`, EAP works out of the box with any OpenAI-compatible endpoint. Set your environment variables depending on your provider of choice:

**NVIDIA Nemotron (via OpenAI compatible endpoint):**
```bash
export OPENAI_API_BASE="https://integrate.api.nvidia.com/v1"
export OPENAI_API_KEY="nvapi-..."
```

**Anthropic:**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**OpenAI:**
```bash
export OPENAI_API_KEY="sk-..."
```
For more information, see `adit.md`.
