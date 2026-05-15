# Architecture & Design

The Web Analyst Microservice adheres to **Domain-Driven Design (DDD)** principles and utilizes an **Event-Driven, Asynchronous Pipeline** to handle CPU-bound and I/O-bound scraping workloads.

## System Layers

### 1. Presentation (`/presentation`)
The REST API boundary. Built with FastAPI, this layer is responsible for defining route handlers, parsing HTTP payloads (Pydantic models), and returning standard HTTP status codes. It delegates all business logic to the Application layer.

### 2. Application (`/application`)
The orchestrator. It contains the use-cases and coordinates the flow of data:
- **`AnalysisService`**: The primary coordinator. It handles job submission, triggers extraction pipelines, and persists results.
- **`TaskQueue`**: An `asyncio`-based bounded queue. It absorbs traffic spikes and processes scraping jobs asynchronously across `N` background workers.
- **`extractor_utils`**: Pure, CPU-light functions for extracting structured intelligence (SEO, leads) from raw DOM.

### 3. Infrastructure (`/infrastructure`)
The outer boundary. This layer implements the interfaces defined by the Domain.
- **`BrowserPool`**: A bounded, thread-safe pool of Playwright browser contexts. It maintains an LRU cache for `session_id` reuse and handles graceful shutdown procedures.
- **`PlaywrightScraper`**: Executes headless Chromium. It applies stealth plugins, blocks heavy media files for bandwidth optimization, and extracts DOM snapshots.
- **Resilience Wrappers**: Uses `tenacity` (exponential backoff) and `circuitbreaker` to handle HTTP 429s, timeouts, and network instability.

### 4. Domain (`/domain`)
The core business logic. It contains pure data models (`PageSnapshot`, `AnalysisResult`) and the interface definitions (`BrowserPort`, `AnalysisRepository`). This layer imports nothing from other layers.

## Concurrency Model

The application leverages Python's `asyncio` event loop.
1. **HTTP Request Phase**: When a client requests an analysis, the route handler instantly generates a `job_id`, persists a `PENDING` state, and pushes the task onto the `TaskQueue`. This is non-blocking.
2. **Background Processing Phase**: `WORKER_COUNT` background tasks constantly pull from the queue. They acquire a browser context from the `BrowserPool` semaphore, execute the Playwright navigation, and write the `COMPLETED` result back to the database.

## Resilience

- **Circuit Breaker**: If a target domain fails continuously (e.g., WAF blocked), the circuit opens, failing fast to prevent resource exhaustion.
- **Exponential Backoff**: Transient network errors trigger retries with jittered backoffs.
- **LRU Session Cache**: Stateful sessions (`session_id`) are cached in memory. To prevent memory leaks, an LRU eviction policy automatically closes and purges old sessions when the cache reaches capacity.
