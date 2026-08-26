# Code Migration Engine — Project Meta Document

---

## The Story Behind It

During my internship at **Cloud Offis**, I was handed a task that many engineers dread: migrate an entire codebase from one version of Spring Boot to another. It wasn't just a version bump — it meant rewriting configurations, updating deprecated APIs, restructuring dependency trees, and manually verifying every file. It was slow, error-prone, and deeply repetitive.

Halfway through that task, a thought hit me: *why is a human doing this?* The rules for migration are mostly knowable. The patterns are consistent. The errors are predictable. This is exactly the kind of problem software should solve.

That frustration became the seed of this project — a **LLM-powered code migration engine** that takes an entire codebase, understands its structure, and converts it from one programming language to another, file by file, with human oversight built in at the right moment.

---

## What This Project Does

The Migration Engine is a **backend API service** that accepts a GitHub repository URL or a ZIP file of source code, and converts it from one programming language to another.

Current supported migration paths:
- Python → JavaScript
- JavaScript → Python
- JavaScript → TypeScript

The engine does not blindly send every file to an LLM. It first **understands the codebase** — parses every file, maps dependencies, ranks files by complexity and risk, presents a plan to the human, waits for approval, and only then begins converting files in the correct dependency order. If a converted file fails validation, it retries with context about what broke. If it still fails after retries, it flags the file for human review and moves on.

The result is a ZIP download of converted files with a full migration report.

---

## The Pipeline — How a Migration Actually Runs

Every migration is a **stateful, multi-step pipeline** implemented as a graph. Think of it as an assembly line where each station does one job, and the line can pause mid-run for a human to review before continuing.

```
Input (GitHub URL or ZIP)
        │
        ▼
   [ INGEST ]         Clone the repo or extract the ZIP. Walk every file.
        │
        ▼
   [ PROFILE ]        Parse every source file with a grammar-based parser.
                      Extract: functions, classes, imports, complexity score.
        │
        ▼
   [ CLASSIFY ]       Build a dependency map between files.
                      Detect circular dependencies.
                      Decide if the codebase is too large/complex to warn about.
        │
        ▼
   [ RANK ]           Sort files into a safe processing order —
                      dependencies before the files that import them.
                      Assess risk level of each file (low / medium / high).
        │
        ▼
   [ AWAIT APPROVAL ] ← Human-in-the-loop gate.
                      Show the full risk plan. Pause. Wait for the user to say GO.
        │
        ▼
   [ PICK NEXT ]      Pick the next unconverted file from the plan.
        │
        ▼
   [ GATHER CONTEXT ] Collect already-converted dependencies to give the LLM
                      reference implementations for what this file imports.
        │
        ▼
   [ GENERATE ]       Call the LLM with a structured prompt.
                      Convert the source file to the target language.
        │
        ▼
   [ VALIDATE ]       Check syntax. Check types. Run the target language's
                      own tooling (ast.parse, node --check, tsc --noEmit).
        │
        ├── PASS ──▶ [ COMMIT ]       Write converted file to disk. Loop back.
        │
        ├── FAIL ──▶ [ SELF-CORRECT ] Tell the LLM what broke. Retry up to 3×.
        │
        └── EXHAUSTED ▶ [ FLAG ]      Mark file for human review. Move on.
                              │
                              ▼
                        [ DONE ]      Write migration_report.json and .md
```

---

## Technologies Used — and Why Each One Specifically

---

### 1. LangGraph
**What it is:** A graph-based orchestration framework for LLM workflows built on top of LangChain.

**Where it's used:** The entire pipeline above is a LangGraph `StateGraph`. Every box in the diagram is a LangGraph node. The arrows between them are edges. Conditional routing (e.g. pass/fail/retry) is handled by LangGraph's conditional edge system.

**Why LangGraph and not alternatives:**

The key requirement was a pipeline that could **pause mid-run and resume later**. This is non-trivial. A simple for-loop or a task queue can run steps sequentially, but they cannot pause at step 6, wait for a human to click approve, survive a server restart, and then pick up exactly where they left off.

LangGraph solves this through two mechanisms:
- `interrupt()` — pauses the graph at any node and serialises the entire state to disk
- `Command(resume=True)` — resumes from that exact checkpoint

Alternatives considered:
- **Celery + Redis**: Good for task queues, but has no native concept of mid-task human interrupts or graph-shaped workflows. You'd have to build all of that yourself.
- **Prefect / Airflow**: Built for data pipelines and scheduled jobs, not interactive LLM workflows. Heavy infrastructure overhead.
- **Plain Python**: Fine for a linear script, but adding retry loops, conditional branching, state persistence, and human-in-the-loop would require building a mini-framework from scratch.

**Future:** If the migration scope grows to multi-agent (e.g. one agent analyses, another converts, another reviews), LangGraph's multi-agent support makes that a natural extension.

---

### 2. Groq + LLaMA 3.3 70B
**What it is:** Groq is an inference API that runs open-source LLMs at very high speed. LLaMA 3.3 70B is the specific model used.

**Where it's used:** The `generate` node calls Groq's API via `langchain-groq` to convert each source file. The `self_correct` node calls it again with error context when validation fails.

**Why Groq specifically:**

Speed matters here. Each file in the migration goes through generate → validate → possibly self-correct → generate again. If each LLM call takes 10 seconds, a 50-file repo takes forever. Groq's inference hardware (Language Processing Units) delivers responses in 1–3 seconds for most files.

**Why LLaMA 3.3 70B and not GPT-4o or Claude:**

LLaMA 3.3 70B is available on Groq's free tier, making this project runnable by anyone with a free API key. The model is strong enough for code migration tasks — it understands Python, JavaScript, and TypeScript deeply.

**Alternative — OpenAI GPT-4o or Claude Sonnet:** Both are stronger models, especially for complex code. The engine is model-agnostic (you swap `GROQ_MODEL` in `.env`). A future upgrade path is to use Claude or GPT-4o for high-risk files and a cheaper/faster model for simple files.

**Future:** When budget allows, route high-risk files (complexity_class = "complex") to a stronger model like Claude Opus while keeping simple files on a fast, cheap model.

---

### 3. FastAPI
**What it is:** A modern Python web framework for building APIs. Auto-generates OpenAPI (Swagger) docs.

**Where it's used:** Every interaction with the migration engine goes through FastAPI — submitting jobs, checking status, approving plans, downloading results, and streaming real-time progress via WebSockets.

**Why FastAPI and not Flask or Django:**

FastAPI is async-native and generates interactive Swagger docs automatically at `/docs`. Since we removed the frontend, Swagger becomes the primary interface for testing and demonstrating the engine. With Flask, you'd have to build that documentation separately. Django is far heavier than needed for a pure API service.

The async support also matters — the migration pipeline runs in background threads while FastAPI continues serving other requests (status polls, WebSocket pings) without blocking.

**Alternative — Flask:** Simpler but synchronous by default, no auto-generated docs, requires more boilerplate for WebSocket support.

**Future:** No planned change. FastAPI scales well and the Swagger UI serves as a recruiter-friendly demo interface without needing a frontend.

---

### 4. Tree-sitter
**What it is:** A grammar-based incremental parser that produces concrete syntax trees for source code. Has grammars for Python, JavaScript, TypeScript, and 100+ other languages.

**Where it's used:** The `profile` node uses tree-sitter to parse every source file before conversion. It extracts functions, classes, imports, and dependency relationships. The `validate` node uses tree-sitter to check if the converted code has any structural syntax errors (ERROR or MISSING nodes in the AST).

**Why tree-sitter and not regex or Python's `ast` module:**

- Python's `ast` module only works for Python. The engine needs to parse Python, JavaScript, and TypeScript — three different languages.
- Regex is fragile. Extracting all imports from a JavaScript file with regex breaks on multi-line imports, comments, string literals that look like imports, and dynamic `require()` calls.
- Tree-sitter produces a real syntax tree with node types, positions, and child relationships. You can query it precisely: "give me all `import_statement` nodes" without worrying about edge cases.
- Tree-sitter handles partial/broken code gracefully — it marks errors in the tree rather than throwing an exception, which is useful when validating LLM-generated code that might have minor issues.

**Alternative — Language-specific parsers (esprima for JS, mypy for types):** Used in addition, not instead. Tree-sitter handles structural parsing; language-specific tools handle deeper type checking.

**Future:** As more language pairs are added (e.g. Java, Go, Rust), tree-sitter grammars exist for all of them. Adding a new language means writing one new `LanguageExtractor` class — the rest of the pipeline stays unchanged.

---

### 5. NetworkX
**What it is:** A Python library for creating and analysing graphs (nodes, edges, paths, cycles).

**Where it's used:** The `classify` node builds a directed dependency graph where each node is a file and each edge means "file A imports file B." NetworkX then:
- Detects circular imports (`nx.simple_cycles()`)
- Computes processing order (`nx.topological_sort()`) — so files are converted in an order where all their dependencies are converted first
- Breaks cycles when they exist (removes minimum edges to make the graph acyclic)

**Why NetworkX:**

Dependency ordering is a classic graph problem (topological sort). Building this from scratch is error-prone. NetworkX provides battle-tested implementations plus cycle detection in a few lines.

**Alternative — Build your own DFS:** Possible but unnecessary. Maintaining a correct topological sort with cycle detection and edge removal in custom code adds complexity with no benefit.

**Why this matters for the project:** Converting a file that imports another file before that other file is converted means the LLM has no reference for what the imported module looks like in the target language. The dependency ordering ensures the LLM always gets context from already-converted dependencies.

**Future:** No planned change.

---

### 6. Model Context Protocol (MCP)
**What it is:** An open standard (created by Anthropic) that defines how AI models communicate with external tools and data sources. An MCP server exposes tools that an LLM agent can discover and call.

**Where it's used:** Six internal MCP servers handle specific responsibilities:
- `plan_manager_server` — tracks migration plan state, file statuses, retry history
- `validation_server` — syntax and type checking
- `code_analysis_server` — AST parsing and dependency graph queries
- `filesystem_server` — safe file read/write with a command allowlist
- `github_server` — git operations and GitHub PR creation
- `pipeline_server` — drives the entire LangGraph pipeline end-to-end (start a migration from a repo URL, poll status, approve the plan, fetch the final report) so an external MCP client can run a full migration, not just call individual tools

**Current state — Real MCP servers with stdio transport:** All six servers use `FastMCP` from the `mcp` SDK. Each server runs as a standalone subprocess communicating over stdio. They are registered in Claude Desktop's `claude_desktop_config.json` and verified working — Claude Desktop calls tools like `parse_file`, `check_syntax`, and `clone_repo` as real MCP tool calls.

**`pipeline_server` specifically:** the other five servers expose atomic building blocks (parse this file, check this syntax, clone this repo). `pipeline_server` wraps the same compiled LangGraph `graph` the FastAPI service uses, so an agent like Claude Desktop can drive a whole migration through four tools — `start_migration`, `get_migration_status`, `approve_migration`, `get_migration_result` — instead of re-implementing the pipeline's sequencing itself. Each tool call returns immediately (the graph runs on a background thread) so a multi-minute conversion never blocks an MCP tool call or hits a client-side timeout; the caller polls `get_migration_status` for progress, exactly like the FastAPI job endpoints do.

The graph nodes continue to call the same functions directly as Python imports (no overhead from going through the protocol for internal calls). The transport layer is an additional capability layered on top — it does not replace or change how the pipeline works internally.

**Two modes of operation:**
- **Internal (pipeline):** Graph nodes import and call functions directly — fast, zero protocol overhead
- **External (Claude Desktop / any MCP client):** Functions are exposed as MCP tools over stdio — callable from any MCP-compatible agent

**Why real transport matters:**

Without transport, `mcp.run()` was a no-op. The servers could not be discovered or called by anything outside the FastAPI process. With real `FastMCP`, each server can be launched independently and connected to Claude Desktop, a test harness, or any future AI agent — without changing any internal code.

**Why not just use plain Python modules:** Plain modules work for internal calls but cannot be discovered or called by external agents. MCP structure enforces clean input/output contracts on every function and makes the tools composable beyond this project.

**Alternative — LangChain Tools:** Would work for LangChain-specific agents but ties the tool definitions to LangChain's ecosystem. MCP is model-agnostic and protocol-agnostic.

**Demonstrated end-to-end:** Claude Desktop was connected to all five servers. Claude called `parse_file` on a Python function and returned the correct AST analysis (complexity score, function list, line count) — confirming the full MCP stack works outside the FastAPI pipeline.

---

### 7. GitPython
**What it is:** A Python library for interacting with Git repositories programmatically.

**Where it's used:** The `ingest` node uses GitPython to clone the source repository (`--depth 1` for speed). The `github_server` MCP server uses it to create branches, stage files, commit, and push.

**Why GitPython and not subprocess git calls:**

GitPython provides a clean Python API with error handling. Raw subprocess calls require manually parsing git's stdout/stderr and handling edge cases for paths, credentials, and return codes.

**Alternative — `dulwich`:** Pure-Python Git implementation. GitPython is more mature with broader documentation.

**Why `--depth 1`:** Migration only needs the current state of the files, not the full history. Shallow clone is dramatically faster for large repos.

**Future:** When the GitHub PR feature is fully activated (currently implemented but optional), GitPython handles the full commit → push → PR creation flow.

---

### 8. Pydantic + Pydantic-Settings
**What it is:** Pydantic is a Python data validation library. Pydantic-Settings extends it to load configuration from environment variables and `.env` files.

**Where it's used:**
- `config.py` — all application settings (API keys, model name, workspace path, limits) are a Pydantic `BaseSettings` class. Values come from environment variables or `.env` files automatically.
- `code_analysis/models.py` — `ParsedFile`, `FunctionInfo`, `ClassInfo`, `ImportInfo` are Pydantic models that flow through the entire pipeline as validated, typed data structures.
- FastAPI uses Pydantic models for request/response validation automatically.

**Why Pydantic:**

In a pipeline where data flows through 12+ nodes, having untyped dicts everywhere leads to bugs that are hard to trace. Pydantic models enforce that every piece of data has the expected shape. If a node outputs a field with the wrong type, Pydantic raises an error immediately at that node rather than silently passing bad data forward.

**Alternative — dataclasses:** Python's built-in dataclasses don't validate types at runtime and have no JSON serialisation built in. Pydantic does both.

**Future:** No planned change.

---

### 9. Docker + Docker Compose
**What it is:** Docker packages the application into a container with all its dependencies. Docker Compose defines how to run that container.

**Where it's used:** `docker-compose.yml` defines a single `fastapi` service built from `backend/Dockerfile`. The Dockerfile installs Python 3.10, git (needed for cloning), and all Python dependencies. A named volume `workspace_data` persists converted files across container restarts.

**Why Docker:**

The engine has an unusual dependency: it needs `git` installed at the OS level (to clone repos), plus Python 3.10, plus tree-sitter grammars that need C compilation at install time (`build-essential`). On a fresh machine, this setup takes many steps. With Docker, it's one command: `docker compose up`.

For a recruiter or hiring manager trying to run the project, Docker is the difference between "it works first try" and "spend an hour debugging PATH and compiler issues."

**Alternative — Virtual environment only:** Works for development but requires the reviewer to have git, Python 3.10, and a C compiler already installed. Docker removes all those assumptions.

**Future:** If the project scales to handle concurrent migrations, the Docker setup can be moved to Kubernetes with minimal changes.

---

### 10. SQLite (via LangGraph SqliteSaver)
**What it is:** A lightweight, file-based relational database. No server required.

**Where it's used:** LangGraph's `SqliteSaver` uses SQLite at `workspace/checkpoints.sqlite` to persist graph state at every node. This is what enables the human-in-the-loop `interrupt()` to survive server restarts.

**Why SQLite and not PostgreSQL or Redis:**

The checkpoint store is used by a single process (the FastAPI server). It doesn't need to be shared across multiple servers, doesn't need to handle concurrent writes from many clients, and doesn't need to store large amounts of data. SQLite is a file. No server to set up, no connection string to configure, no additional Docker service.

**Alternative — PostgreSQL:** LangGraph also supports a Postgres checkpointer. This would be the right choice if the service scaled to multiple FastAPI instances behind a load balancer, since all instances would need access to the same checkpoint store.

**Future:** If horizontal scaling becomes a requirement, swap `SqliteSaver` for `AsyncPostgresSaver` (LangGraph provides this). The rest of the code doesn't change.

---

## Skills Demonstrated

| Skill | Where in the Project | Why It Matters |
|---|---|---|
| **LLM Application Design** | Full pipeline — prompt engineering in `generate.py` and `self_correct.py`, context assembly in `gather_context.py` | Shows ability to go beyond calling an API — structuring prompts, managing context windows, handling failures |
| **Agentic AI / LangGraph** | `pipeline.py`, all graph nodes, `await_approval.py` interrupt | Human-in-the-loop patterns and stateful multi-step LLM workflows are cutting-edge in applied AI |
| **Software Architecture** | Separation into API / graph / code_analysis / ingestion / mcp_servers layers | Clean layer separation makes the codebase readable and extensible |
| **AST Parsing** | `code_analysis/` — tree-sitter extractors for Python, JS, TS | Understanding syntax trees is a depth signal — most engineers work at the text level |
| **Graph Algorithms** | `dependency_graph.py` — topological sort, cycle detection, cycle breaking | Applied graph theory to a real engineering problem |
| **REST API Design** | `routes.py` — 9 endpoints with clear semantics, proper HTTP status codes | FastAPI + auto-generated Swagger docs |
| **Real-time Streaming** | `websockets.py` — per-job WebSocket rooms with asyncio queues | Bridges sync (LangGraph) and async (FastAPI) execution models |
| **MCP / Tool Design** | Six real FastMCP servers with stdio transport, connected to and verified working in Claude Desktop — including `pipeline_server`, which exposes the full LangGraph pipeline as four tools | Full MCP stack — not just pattern, but working transport, live tool calls, and end-to-end agentic orchestration |
| **Containerisation** | `Dockerfile`, `docker-compose.yml` | Production-readiness, one-command setup |
| **Python Async** | Thread-per-job model, `asyncio.run_coroutine_threadsafe`, queue draining | Deep Python concurrency — not just `async def` |

---

## What is Not Here (and Why)

**No frontend.** The original project had a React frontend and a Node.js BFF relay. Both were removed to keep the codebase focused on the core engine logic — which is what demonstrates engineering depth. The Swagger UI at `/docs` serves as the interface for testing and demonstration.

**No database for job persistence.** Jobs are stored in memory (`_jobs` dict in `routes.py`). This means jobs are lost on server restart. This was an intentional simplification — the BFF layer previously handled MongoDB persistence, and removing the BFF without replacing the persistence means in-memory only. A SQLite or Postgres job store would be the natural next addition.

**No authentication.** Any caller can submit a migration job. For a production service, JWT or API key authentication would be needed before any route.

---

## If I Were to Continue Building This

**Near-term (1–2 weeks):**
- Add job persistence (SQLite or Postgres) so jobs survive server restarts
- Add more language pairs (Java → Kotlin is a natural fit given the Spring Boot origin story)
- Add MCP resources (expose migration plan and progress as readable MCP resources, not just tools)

**Medium-term (1–2 months):**
- Route complex files to a stronger model (Claude Opus / GPT-4o) automatically
- Add a diff view in the result — side-by-side original vs converted
- Support partial migration (convert only selected files or directories)

**Long-term:**
- Multi-agent architecture — one agent plans, one converts, one reviews — coordinated by LangGraph's multi-agent support
- Framework migration support (not just language — e.g. Express → FastAPI, Spring Boot 2 → Spring Boot 3)
- This would directly solve the original problem from the internship

---

*Built by Vishwa Pujara — inspired by a Spring Boot migration task at Cloud Offis.*
