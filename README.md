# NiveshIQ — AI Portfolio Intelligence Engine

NiveshIQ is an **AI-powered portfolio intelligence platform** that ingests stock transaction data, computes real-time portfolio analytics, and provides conversational AI insights via a multi-agent LangChain system powered by Google Vertex AI Gemini models.

---

## Table of Contents

1. [Tech Stack](#tech-stack)
2. [System Architecture](#system-architecture)
3. [Data Ingestion & Parsing Pipeline](#data-ingestion--parsing-pipeline)
4. [Market Data Service](#market-data-service)
5. [Holdings Calculation Engine](#holdings-calculation-engine)
6. [Portfolio History Service](#portfolio-history-service)
7. [Copilot Agent (Conversational AI)](#copilot-agent-conversational-ai)
8. [Review Agent (Portfolio Report Generation)](#review-agent-portfolio-report-generation)
9. [LLM & Tool Architecture](#llm--tool-architecture)
10. [API Endpoints](#api-endpoints)
11. [Scheduled Jobs](#scheduled-jobs)
12. [Authentication & Authorization](#authentication--authorization)
13. [Caching Strategy](#caching-strategy)
14. [Database Schema](#database-schema)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 15 (App Router), TypeScript, Tailwind CSS |
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy 2.0 |
| **Database** | Neon Serverless PostgreSQL + pgvector extension |
| **Cache** | Redis (via custom `cache_manager`) |
| **AI Models** | Google Vertex AI — Gemini 2.5 Flash-Lite, Flash, Pro |
| **AI Framework** | LangChain (`langchain-google-genai` with Vertex AI routing) |
| **Market Data** | Yahoo Finance (`yfinance`) |
| **Auth** | Neon Auth (cookie-based JWT) |
| **Deployment** | Backend: Vercel; Frontend: Vercel |

---

## System Architecture

```mermaid
graph TB
    subgraph "Frontend (Next.js)"
        UI[Next.js App Router]
        API_CLIENT[API Client Layer]
    end

    subgraph "Backend (FastAPI)"
        ROUTER[API Router]
        MIDDLEWARE[CORS / Auth Middleware]
        
        subgraph "Services Layer"
            HOLDINGS[HoldingsService]
            MARKET[MarketDataService]
            HISTORY[PortfolioHistoryService]
            USER[UserService]
        end
        
        subgraph "AI Agent Layer"
            APP_CTX[AppContext - Composition Root]
            COPILOT[CopilotAgent]
            REVIEW[ReviewAgent]
        end
        

    end

    subgraph "Data Stores"
        PG[(Neon PostgreSQL<br/>+ pgvector)]
        REDIS[(Redis Cache)]
    end

    subgraph "External Services"
        YF[Yahoo Finance<br/>yfinance]
        VERTEX[Vertex AI<br/>Gemini Models]
        GS[Google Search]
    end

    UI --> API_CLIENT
    API_CLIENT --> ROUTER
    ROUTER --> MIDDLEWARE
    MIDDLEWARE --> SERVICES
    MIDDLEWARE --> AI_AGENT_LAYER
    
    SERVICES --> PG
    SERVICES --> REDIS
    SERVICES --> YF
    
    AI_AGENT_LAYER --> SERVICES
    AI_AGENT_LAYER --> VERTEX
    AI_AGENT_LAYER --> GS
    
    APP_CTX --> COPILOT
    APP_CTX --> REVIEW
```

---

## Data Ingestion & Parsing Pipeline

When a user uploads a stock transaction file (Excel/CSV), the following pipeline executes:

```mermaid
flowchart LR
    A[User Uploads<br/>Excel/CSV File] --> B[File Parsing<br/>extract_text / parsing utils]
    B --> C{File Type?}
    C -->|XLSX| D[OpenPyXL Parser]
    C -->|CSV| E[CSV Reader]
    D --> F[Normalize Columns<br/>symbol, qty, price, type, date]
    E --> F
    F --> G[Validate & Clean<br/>- Strip whitespace<br/>- Convert data types<br/>- Handle missing values]
    G --> H[Create Transaction Records<br/>in PostgreSQL]
    H --> I[Trigger History Rebuild<br/>PortfolioHistoryService.rebuild_history]
    I --> J[Invalidate Cache<br/>for holdings, history, risk metrics]
    J --> K[Return Parsed<br/>Transaction Summary]
```

**Key implementation details:**
- The parsing logic lives in `backend/app/utils/parsing.py` and handles both `.xlsx` and `.csv` formats
- Each transaction is stored as a `Transaction` model row with fields: `symbol`, `quantity`, `price`, `fees`, `transaction_type` (BUY/SELL), `executed_at`
- After successful parsing, `PortfolioHistoryService.rebuild_history()` is called to reconstruct the daily valuation timeline from scratch
- All cached analytics (holdings, returns, risk metrics) are invalidated so they recompute on next access

---

## Market Data Service

The `MarketDataService` is the backbone of all price and metadata resolution. It implements a **three-tier fallback hierarchy** with concurrent bulk operations and exponential backoff.

```mermaid
flowchart TB
    REQ[Request: get_price / get_metadata / get_sector] --> CACHE{Redis Cache Hit?}
    CACHE -->|Yes| RETURN[Return Cached Value]
    CACHE -->|No| LOCK[Acquire Thread Lock<br/>per operation type]
    LOCK --> RECHECK{Re-check Cache<br/>under Lock}
    RECHECK -->|Hit| RETURN
    RECHECK -->|Miss| YF[Fetch from yfinance<br/>with exponential backoff<br/>max 3 retries]
    
    YF --> SUCCESS{yfinance<br/>Succeeded?}
    SUCCESS -->|Yes| SAVE_DB[Save to PostgreSQL<br/>MarketPrice table]
    SAVE_DB --> WARM_CACHE[Warm Redis Cache<br/>with appropriate TTLs]
    WARM_CACHE --> RETURN
    
    SUCCESS -->|No| DB_FALLBACK{DB Fallback<br/>Row Exists?}
    DB_FALLBACK -->|Yes| WARM_CACHE
    DB_FALLBACK -->|No| ERROR[Raise MarketDataNotFoundError]
```

### Cache TTL Strategy

| Field | TTL | Rationale |
|-------|-----|-----------|
| `price` | 300s (5 min) | Changes intraday |
| `day_low` / `day_high` | 300s (5 min) | Changes intraday |
| `company_name` / `sector` | 31,536,000s (1 year) | Static metadata |
| `market_cap` | 2,592,000s (30 days) | Changes slowly |
| `52w_low` / `52w_high` | 2,592,000s (30 days) | Changes slowly |

### Concurrent Bulk Operations

For bulk requests (e.g., fetching prices for 20 holdings), the service:
1. Checks cache for each symbol individually
2. For cache misses, uses `yfinance` bulk download (`yf.download()`) with exponential backoff
3. Saves all fetched data to DB and cache in a single batch transaction
4. For symbols that still fail, falls back to a single DB batch SELECT query
5. Thread locks (`_bulk_price_lock`, `_metadata_lock`) prevent thundering herd problems

### yfinance Retry Logic

```python
max_attempts = 3
backoff_factor = 2.0
# Attempt 1: immediate
# Attempt 2: after 2s
# Attempt 3: after 4s
```

---

## Holdings Calculation Engine

The `HoldingsService.calculate_holdings()` method computes the user's current portfolio from their transaction history:

```mermaid
flowchart TB
    START["calculate_holdings(user_id)"] --> CACHE{"Redis Cache Hit?"}

    CACHE -->|Yes| RETURN["Return Cached<br/>PortfolioHoldingsListResponse"]
    CACHE -->|No| TX["Fetch all Transactions<br/>for user, sorted by date"]

    TX --> LOOP

    subgraph TRANSACTION_SIM["Transaction Simulation"]
        direction TB

        LOOP["For each transaction"] --> TYPE{"Type?"}

        TYPE -->|BUY| BUY_CALC["Update quantity &<br/>weighted average cost<br/>Include fees in cost basis"]

        TYPE -->|SELL| SELL_CALC["Reduce quantity<br/>Calculate realized P&L<br/>Clamp to owned qty"]

        BUY_CALC --> NEXT["Next Transaction"]
        SELL_CALC --> NEXT

        NEXT --> LOOP
    end

    LOOP --> ACTIVE["Filter active holdings<br/>qty > 0"]

    ACTIVE --> BULK["Fetch live market prices<br/>& metadata in bulk"]

    BULK --> COMPUTE["Compute per-holding:<br/>- Market value<br/>- Unrealized P&L<br/>- Allocation %<br/>- Sector"]

    COMPUTE --> SORT["Sort by allocation %<br/>descending"]

    SORT --> CACHE_RES["Cache result for 900s"]

    CACHE_RES --> RETURN
```

**Key calculations:**
- **Average buy price** = total cost (including fees) / total quantity (weighted average)
- **Realized P&L** = sell_qty × (sell_price − avg_cost) − fees
- **Unrealized P&L** = market_value − holding_cost
- **Allocation %** = market_value / total_portfolio_value × 100

---

## Portfolio History Service

The `PortfolioHistoryService` maintains a daily valuation timeline for each user. It is the most computationally intensive service and uses **PostgreSQL row-level locking** to prevent concurrent rebuild conflicts.

```mermaid
flowchart LR

    subgraph Triggers
        T1[Transaction Upload]
        T2[API Request]
    end

    subgraph Historical_Rebuild["Historical Rebuild"]
        R1[Acquire Lock]
        R2[Replay Transactions]
        R3[Fetch Historical Prices]
        R4[Generate Daily Snapshots]
    end

    subgraph Performance_API["Performance Calculation"]
        P1[Validate Snapshot Coverage]
        P2[Refresh Latest Value]
        P3[Return Performance History]
    end

    T1 --> R1

    R1 --> R2
    R2 --> R3
    R3 --> R4

    T2 --> P1
    P1 -->|Missing History| R1
    P1 -->|History Available| P2
    R4 --> P2

    P2 --> P3
```

### Derived Analytics

The service computes these analytics from the daily history snapshots:

| Metric | Method | Description |
|--------|--------|-------------|
| **Returns History** | `get_returns_history()` | Daily values, costs, returns, cumulative return % |
| **Risk Metrics** | `calculate_risk_metrics()` | Sharpe ratio, Sortino ratio, volatility, max drawdown, VaR (95%/99%), CVaR |
| **Benchmark Comparison** | `compare_to_benchmark()` | Beta, Alpha, Correlation, Tracking Error, Information Ratio vs Nifty 50 |
| **Asset Covariance** | `calculate_asset_covariance()` | Covariance & correlation matrices for all active holdings |

**Risk-free rate used:** 6.5% annual (Indian context), converted to daily: 6.5% / 252

---

## Copilot Agent (Conversational AI)

The `CopilotAgent` is the conversational AI that answers user queries about their portfolio. It uses a **three-tier model architecture** with a query refactoring layer for robust multiturn handling.

### Three-Tier Architecture

```mermaid
flowchart TB
    USER["User Query"] --> HISTORY["Load Conversation Context<br/>from DB (up to 20 messages)"]
    
    subgraph REFACTOR["Query Refactoring - Gemini 2.5 Flash-Lite"]
        FLASHLITE["Flash-Lite Model<br/>Sees full history"]
        FLASHLITE --> CLASSIFY{"Classify & Refactor<br/>prefix output"}
        CLASSIFY -->|"META:"| META["Conversation summary<br/>→ inject history"]
        CLASSIFY -->|"HYBRID:"| HYBRID["Entity + previous pattern<br/>→ inject history"]
        CLASSIFY -->|"TOOLS:"| TOOLS["Data/live query<br/>→ force tool usage"]
        CLASSIFY -->|"ADVISOR:"| ADVISOR["Investment planning<br/>→ advisor prompt + tools"]
        CLASSIFY -->|"(no prefix)"| NORMAL["Standalone query<br/>→ no history to main model"]
    end
    
    HISTORY --> FLASHLITE
    
    META --> ROUTING
    HYBRID --> ROUTING
    TOOLS --> ROUTING
    ADVISOR --> ROUTING
    NORMAL --> ROUTING
    
    subgraph ROUTING["Tool Routing - Gemini 2.5 Flash"]
        FLASH["Fast LLM<br/>Tool Binding Enabled"]
        FLASH --> DECISION{"Need external data<br/>or computation?"}
        DECISION -->|"No"| PRO
        DECISION -->|"Yes"| EXEC["Execute Selected Tools<br/>in Parallel"]
        EXEC --> RESULTS["Return Tool Results"]
        RESULTS --> LOOP{"Need more?<br/>max 2 iterations"}
        LOOP -->|"Yes"| EXEC
        LOOP -->|"No"| PRO
    end
    
    subgraph TOOL_LAYER["Tool Layer"]
        TOOL1["Tool 1"]
        TOOL2["Tool 2"]
        TOOL3["Tool 3"]
        DOTS["..."]
        TOOLN["Tool N"]
    end
    
    EXEC --> TOOL_LAYER
    
    subgraph SYNTHESIS["Response Synthesis - Gemini 2.5 Pro"]
        PRO["Advanced LLM<br/>No Tool Access"]
        PRO --> STRUCTURE["Generate Structured Response<br/>Answer • Evidence • Next Steps"]
    end
    
    STRUCTURE --> STORE["Save Conversation State<br/>Database"]
    STORE --> STREAM["Stream Response<br/>to Client"]
    STREAM --> USER
```

### Query Refactoring Layer (New)

The **flash-lite model** acts as a dedicated query refactoring layer before any main model processing. It classifies each query into one of five types via a prefix system:

| Prefix | Meaning | History Injected? | Tools Forced? | Prompt Used |
|--------|---------|-------------------|---------------|-------------|
| `META:` | Conversation-about-itself ("summarize", "what did I ask") | ✅ | ❌ | AGENT_PROMPT |
| `HYBRID:` | Entity + previous pattern ("for TCS what you said earlier") | ✅ | ❌ | AGENT_PROMPT |
| `TOOLS:` | Data/live query ("what's the PE of HDFC Bank?") | ❌ | ✅ | AGENT_PROMPT |
| `ADVISOR:` | Investment planning ("create a plan for ₹10,000") | ❌ | ✅ | INVESTMENT_ADVISOR_PROMPT |
| *(none)* | Greetings, definitions, educational concepts | ❌ | ❌ | AGENT_PROMPT |

**Why this matters:** The main Flash/Pro models never see raw chat history for normal queries, preventing the hallucination where answering Q2 reproduces Q1's answer. Previous assistant answers are completely isolated from the inference context.

### Short Response / Clarification Handling

When the user provides a short confirmation response (e.g., "10000", "moderate", "yes"), the refactor layer uses the full chat history to **merge** this response into the original user intent, producing a complete standalone query. This handles multi-turn clarification flows naturally:

```
Turn 1: "Prepare plan for investing in individual stocks in Indian markets with ₹20k monthly budget"
Turn 2: "Medium risk and high growth"
→ Refactored: "Prepare an investment plan for individual stocks in Indian markets with 
   ₹20,000 monthly budget, medium risk tolerance, and high growth potential"
```

### Prompt Routing

Depending on the classification, the system selects the appropriate system prompt:
- **`AGENT_PROMPT`** — Default prompt for portfolio analysis, market data, and general financial queries
- **`INVESTMENT_ADVISOR_PROMPT`** — Expert advisor persona with structured investment planning workflow (profile understanding → actionable recommendations → risk management). Uses action-first output ordering and never explains generic financial concepts.

### Execution Flow (Detailed)

1. **History Loading**: Loads up to 20 most recent messages from the user's active `ChatSession`
2. **Query Refactoring (Flash-Lite)**: The cheap Flash-Lite model refactors (current query + history) into a standalone question, classified with a prefix
3. **Context Building**: `ContextManager.build_prompt()` assembles the appropriate system prompt + refactored query + tool results
4. **Tool Routing (Flash Model)**: The Flash model (with `bind_tools(TOOLS)`) decides whether to call tools or produce a direct answer
5. **Concurrent Execution**: Tool calls are executed in parallel via `ThreadPoolExecutor` (sync) or `loop.run_in_executor` (async streaming)
6. **Iteration**: Results are fed back to the Flash model for up to 2 iterations
7. **Final Synthesis (Pro Model)**: If tools were used, the Pro model synthesizes the gathered data into a structured JSON response
8. **Streaming**: For the streaming API, the response is parsed character-by-character to extract the `"answer"` field in real-time, handling escape sequences (`\n`, `\"`, etc.)

### Mandatory Tool Usage

When the refactor layer classifies a query as `TOOLS:` or `ADVISOR:`, a hard directive is injected into the prompt:

```
**MANDATORY TOOL USE:** This query was classified as needing current/live data.
Your training data is stale for this. You MUST call the relevant tools to fetch
up-to-date information before answering. Do NOT answer from memory.
```

This prevents the model from answering "recent news" queries from its training data instead of calling the news tools.



### Streaming Architecture

The `ask_copilot_stream()` method uses **Server-Sent Events (SSE)** with these event types:
- `data: {"type": "status", "text": "Thinking..."}`
- `data: {"type": "content", "text": "..."}` (streamed answer chunks)
- `data: {"type": "done", "payload": {...}}` (final structured payload)

---

## Review Agent (Portfolio Report Generation)

The `ReviewAgent` generates comprehensive portfolio review reports. Unlike the CopilotAgent, it uses a **single Pro model** with tool binding for all iterations:

```mermaid
flowchart TB

    START["Generate Insights Request<br>POST /api/v1/insights/generate"]
    LIMIT["Validate Request<br>Check Usage Limits"]
    PROMPT["Build Analysis Context<br>System Prompt + User Data"]

    START --> LIMIT
    LIMIT --> PROMPT
    PROMPT --> LLM


    subgraph ANALYSIS["Iterative Analysis Engine"]
        direction TB

        LLM["Advanced LLM<br>Tool Calling Enabled"]

        DECIDE{"Need Additional Data?"}

        LLM --> DECIDE

        DECIDE -->|"Yes"| EXEC["Parallel Tool Execution"]
        EXEC --> TOOL_LAYER
        TOOL_LAYER --> RESULT["Merge Tool Results<br>into Context"]
        RESULT --> LLM

        DECIDE -->|"No / Complete"| REPORT["Generate Final Report"]
    end


    subgraph TOOL_LAYER["Tool Layer"]
        direction LR

        T1["Tool 1"]
        T2["Tool 2"]
        T3["Tool 3"]
        TN["Tool N"]

        T1 --- T2 --- T3 --- TN
    end


    REPORT --> PARSE["Parse Structured Output<br>JSON Format"]

    PARSE --> SECTIONS["Extract Report Sections<br>Portfolio Summary<br>Holdings Analysis<br>Rebalancing Plan<br>Future Scenarios<br>Market Updates"]

    SECTIONS --> SAVE["Save Portfolio Review<br>Database + Usage Stats"]

    SAVE --> RETURN["Return Insights<br>to Client"]
```

### Report Structure

The generated report contains these sections:
- **portfolio_summary**: `current_value`, `total_pnl`, `total_pnl_percent`, `analysis` (strategic narrative)
- **holdings_analysis**: Per-holding analysis with action recommendations
- **rebalancing_plan**: Objective + step-by-step actions (BUY/SELL/REINVEST)
- **future_scenarios**: Market scenario projections
- **news_updates**: Relevant news items gathered via `google_web_search`
- **caveat**: Standard disclaimer text

Token usage (prompt, completion, total) is tracked and stored alongside the report.

---

## LLM & Tool Architecture

### Three-Tier Model Strategy

```mermaid
graph TB
    
    subgraph "Gemini 2.5 Flash-Lite"
        FL[Temperature: 0.2<br/>Max Tokens: 8192]
        TASKS_FL[Query refactoring & classification<br/>Short response merging<br/>Entity resolution]
    end
    
    subgraph "Gemini 2.5 Flash"
        F[Temperature: 0.2<br/>Max Tokens: 8192]
        TASKS_F[Tool routing & planning<br/>Function calling<br/>Data fetching decisions]
    end
    
    subgraph "Gemini 2.5 Pro"
        P[Temperature: 0.1<br/>Max Tokens: 8192]
        TASKS_P[Deep financial analysis<br/>Report writing<br/>Final answer synthesis<br/>Investment advisory]
    end
    
    FL --> F --> P
```

The three tiers are instantiated in `backend/app/core/llm.py`:
- `flash_lite_model` — Fastest, cheapest model for classification/refactoring
- `flash_model` — Tool routing and orchestration (bound with `bind_tools(TOOLS)`)
- `pro_model` — Final synthesis and deep analysis

### Tool Validation Decorator

Each tool is wrapped with the `@validate_tool` decorator that:
1. Validates input parameters against the Pydantic input schema
2. Executes the tool function
3. Validates the output against the Pydantic output schema
4. Wraps everything in a standardized `ToolResponseEnvelope`:
   ```json
   {
     "success": true/false,
     "timestamp": "2026-06-23T00:00:00Z",
     "source": "NiveshIQ",
     "data": { ... }
   }
   ```

---




## Authentication & Authorization

### Neon Auth Flow

1. User authenticates via **Neon Auth** (cookie-based JWT)
2. The `get_current_user` dependency extracts the JWT from cookies, validates it, and returns the `User` model
3. Guest users have a **token usage limit** enforced by `check_guest_token_limit()`

---

## Caching Strategy

The application uses **Redis** with a custom `cache_manager` for multi-layer caching:

```mermaid
flowchart TB
    subgraph "Cache Namespaces"
        MARKET[market_data:*<br/>- price, name, sector, cap<br/>]
        USER[user_cache:*<br/>- holdings_service<br/>- historical_performance<br/>- returns_history<br/>- risk_metrics<br/>- benchmark_comparison<br/>- asset_covariance]
    end
    
    subgraph "Cache Invalidation Triggers"
        UPLOAD[Transaction Upload] --> INVAL[Invalidate all<br/>user_cache:* keys]
        SCHED[Market Data Refresh] --> UPDATE_M[Update market_data:*<br/>price keys]
    end
```

| Cache Key Pattern | TTL | Invalidated When |
|-------------------|-----|------------------|
| `market_data:price:{symbol}` | 300s | On refresh |
| `market_data:name:{symbol}` | 1 year | Never (static) |
| `market_data:sector:{symbol}` | 1 year | Never (static) |
| `market_data:cap:{symbol}` | 30 days | On refresh |
| `user_cache:{user_id}:holdings_service` | 900s | On transaction upload |
| `user_cache:{user_id}:historical_performance` | 600s | On transaction upload |
| `user_cache:{user_id}:returns_history` | 600s | On transaction upload |
| `user_cache:{user_id}:risk_metrics` | 600s | On transaction upload |
| `user_cache:{user_id}:benchmark_comparison` | 600s | On transaction upload |
| `user_cache:{user_id}:asset_covariance` | 600s | On transaction upload |

---

## Database Schema

### Key Models

```mermaid
erDiagram
    User ||--o{ Transaction : has
    User ||--o{ WatchlistItem : has
    User ||--o{ PortfolioDailyHistory : has
    User ||--o{ PortfolioReview : has
    User ||--o{ ChatSession : has
    User ||--o{ UserProfile : has
    ChatSession ||--o{ ChatMessage : contains
    Transaction ||--o{ MarketPrice : references

    User {
        uuid id PK
        string email
        string name
        datetime created_at
    }

    UserProfile {
        uuid id PK
        uuid user_id FK
        string full_name
        string profession
        enum risk_appetite "low|moderate|high"
        enum time_horizon "short_term|medium_term|long_term"
        enum investment_goal "wealth_growth|retirement|savings"
        float monthly_investment_budget
    }

    Transaction {
        uuid id PK
        uuid user_id FK
        string symbol "e.g., RELIANCE.NS"
        enum transaction_type "BUY|SELL"
        float quantity
        float price
        float fees
        datetime executed_at
    }

    MarketPrice {
        string symbol PK "e.g., RELIANCE.NS"
        float price
        string company_name
        string sector
        float market_cap
        datetime updated_at
    }

    PortfolioDailyHistory {
        uuid id PK
        uuid user_id FK
        date captured_at
        float total_value
        float total_cost
    }

    PortfolioReview {
        uuid id PK
        uuid user_id FK
        text risk_summary
        jsonb diversification_summary
        jsonb rebalancing_ideas
        jsonb potential_stock_picks
        jsonb warnings
        jsonb market_impact
        jsonb evidence
        text disclaimers
        int prompt_tokens
        int completion_tokens
        int total_tokens
        datetime created_at
    }

    ChatSession {
        uuid id PK
        uuid user_id FK
        datetime created_at
        datetime last_message_at
    }

    ChatMessage {
        uuid id PK
        uuid session_id FK
        enum role "user|assistant"
        text content
        datetime created_at
    }

    WatchlistItem {
        uuid id PK
        uuid user_id FK
        string symbol
        string company_name
        float price_when_added
        datetime added_at
    }
```

### pgvector Extension

The database uses the `pgvector` extension (enabled at startup via `CREATE EXTENSION IF NOT EXISTS vector;`) for future AI embedding capabilities.

---

## Key Design Patterns & Optimizations

### 1. Composition Root (`AppContext`)
The `AppContext` class acts as the composition root, wiring together all models, services, and agents. It creates singleton instances of:
- `CopilotAgent` (with Pro, Flash, and Flash-Lite models)
- `ReviewAgent` (receives the full `AppContext` for backward compatibility)

### 2. Query Refactoring Layer
A dedicated Flash-Lite model refactors (current query + history) into a standalone question before it reaches the main model pipeline. This:
- **Prevents multiturn hallucination** — main model never sees previous assistant answers for normal queries
- **Classifies queries** into META / HYBRID / TOOLS / ADVISOR / normal categories
- **Routes to appropriate prompts** — investment planning queries use the expert advisor persona
- **Merges short clarifications** — confirmation responses are seamlessly blended back into the original query context

### 3. Prompt Override Routing
`ContextManager.build_prompt()` accepts a `prompt_override` parameter, enabling the system to use different system prompts for different query types without changing the pipeline logic. Currently supports `AGENT_PROMPT` (default) and `INVESTMENT_ADVISOR_PROMPT` (for planning queries).

### 4. Mandatory Tool Enforcement
When `requires_tools=True`, a hard directive is injected into the prompt telling the model it MUST call tools rather than answering from memory — used for news, live pricing, and investment planning queries.

### 5. Concurrent Tool Execution
Both agents execute tool calls concurrently using `ThreadPoolExecutor`:
```python
with concurrent.futures.ThreadPoolExecutor(max_workers=len(tool_calls)) as pool:
    futures = {pool.submit(self._run_single_tool, tc, db, user_id): tc for tc in tool_calls}
```

### 6. PostgreSQL Row-Level Locking
The `rebuild_history()` method uses `SELECT ... FOR UPDATE` to prevent concurrent history rebuilds from conflicting:
```python
db.execute(text("SELECT id FROM users WHERE id = :user_id FOR UPDATE;"), {"user_id": user_id})
```

### 7. Exponential Backoff
All yfinance API calls use exponential backoff with a factor of 2.0 and max 3 attempts:
```python
sleep_time = backoff_factor * (2 ** attempt)  # 2s, 4s, 8s
```

### 8. SSE Streaming with Real-Time JSON Parsing
The copilot streaming endpoint parses the LLM's JSON output character-by-character to extract the `"answer"` field in real-time, handling escape sequences without waiting for the full response.

### 9. Cached Tool Bindings
- `_TOOL_MAP` is built once at module load (not per request)
- `_LLM_WITH_SEARCH` is bound once at module load for Google search
- `_flash_with_tools` and `_pro_no_tools` are cached on `CopilotAgent.__init__`

### 10. Profile Override Rule
In the investment advisor prompt, the user's stated intent in their query always overrides profile data from `get_user_profile`. Profile data is used silently as a fallback — never quoted or acknowledged if the user has already provided the value.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `VERTEX_PROJECT_ID` | GCP project ID for Vertex AI |
| `VERTEX_LOCATION` | GCP location (default: `us-central1`) |
| `GOOGLE_APPLICATION_CREDENTIALS` | GCP service account JSON (inline or file path) |
| `NEON_AUTH_BASE_URL` | Neon Auth base URL |
| `NEON_AUTH_COOKIE_SECRET` | Secret for signing auth cookies |
| `REDIS_URL` | Redis connection string |
| `ALLOWED_CORS_ORIGINS` | Comma-separated CORS origins |

---

## Running Locally

Config .env file in backend.

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```
The backend runs on `http://localhost:8000` and the frontend on `http://localhost:3000`.

## IMPORTANT NOTES:

- The ChatBOT has certain limitations because of memory limit and limited tool supports. In future more tools will be added to make it robust.
- Currently there is noticeable delay in AI response which will be reduced in upcoming updates.
- The ChatBOT might hallucinate because of memory limit, in that case clear the history and try again.
- If the prompt generated is not satisfactory , try again after clearing history and re defining the prompt in detail