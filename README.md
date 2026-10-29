# Research Brief Agent

A tool-calling AI agent in Python. You give it a topic or question, it decides what to search for, reads the results, and returns a structured brief: a summary, key points, and a list of sources with real URLs.

Built with Gemini, DuckDuckGo search, and FastAPI. There's no agent framework, just the official SDK and a plain loop, so every step of the agent's behavior is visible in the code.

> **Status: deployed, still in progress.** The agent runs from the command line and as an HTTP API protected by an API key, hosted on Render's free tier. A request timeout, rate limiting, and automated tests are still planned (see [Roadmap](#roadmap)).

**Live API docs:** https://research-brief-agent-kyjk.onrender.com/docs

The docs page is open to view, but `POST /brief` needs an API key, which isn't shared publicly because each request spends a limited Gemini quota. To try the agent yourself, run your own copy using the steps below. The service sleeps when idle, so the first load can take about a minute.

## What works today

- Structured briefs: summary, key points, and sources, validated with Pydantic
- Sources come from the actual search results. The model picks result numbers, and the code attaches the real titles and URLs, so a source can't be invented
- Gemini decides on its own whether to search, and what to search for (up to 3 research steps per question)
- HTTP API (`POST /brief`) with input validation and clean error responses
- API key required on `/brief`
- Resilience: search failures are retried once, temporary Gemini server errors are retried with backoff, and quota limits produce a clear message instead of a stack trace
- Deployed on Render's free tier
- Interactive command-line mode for quick testing

## How it works

```
question
   |
   v
research()   Gemini decides what to search (up to 3 steps)
   |         each result is numbered [1], [2], ... and stored with its real URL
   v
write_brief()   a second call turns the numbered results into JSON:
   |            summary, key_points, and the numbers of the results it used
   v
Brief        the code looks up each number and attaches the title and URL
```

1. The question goes to Gemini along with one tool, `web_search`.
2. Each search result is numbered and stored by the code. The model sees the numbers, titles, URLs, and snippets.
3. Once the model stops searching (or reaches the step limit), a separate call writes the brief from those results only.
4. The model returns source *numbers*. Numbers that don't exist are dropped, and the sources in the final brief are built from the stored results.

## Requirements

- Python 3.11 or newer
- A free Gemini API key from [Google AI Studio](https://aistudio.google.com) (no credit card needed)

## Setup

```powershell
# 1. Clone and enter the project
git clone <your-repo-url>
cd research-brief-agent

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file
copy .env.example .env         # macOS/Linux: cp .env.example .env
# then edit .env and fill in both values (see below)
```

On Windows PowerShell, if activating the virtual environment fails with an execution policy error, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

### Environment variables

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Your key from Google AI Studio |
| `API_KEY` | The key callers must send in the `X-API-Key` header. Make your own: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `PYTHON_VERSION` | Hosting only, not read by the app. Sets the Python version on Render. Needs a full version such as `3.13.5` |

`.env` is listed in `.gitignore` and is never committed. Don't put keys directly in any `.py` file.

## Usage

### Check your setup

```
python smoke_test.py
```

Makes one call to Gemini to confirm the key, model name, and network connection work.

### Command line

```
python agent.py
```

```
Topic or question: What are the main benefits and risks of intermittent fasting?
[step 1] Searching: ...
```

Type `quit` to exit.

### HTTP API

```
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive documentation. Click **Authorize**, paste your `API_KEY`, and try `POST /brief` from the page.

Or call it directly (macOS/Linux):

```
curl -X POST http://127.0.0.1:8000/brief \
  -H "X-API-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"topic": "What are the main benefits and risks of intermittent fasting?"}'
```

PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/brief `
  -Headers @{ "X-API-Key" = "your_api_key" } `
  -ContentType "application/json" `
  -Body '{"topic": "What are the main benefits and risks of intermittent fasting?"}'
```

Example response (abbreviated and illustrative):

```json
{
  "topic": "What are the main benefits and risks of intermittent fasting?",
  "summary": "...",
  "key_points": ["...", "..."],
  "sources": [
    { "id": 1, "title": "Example page title", "url": "https://example.com/page" }
  ]
}
```

### Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/brief` | `X-API-Key` | Research a topic (3 to 500 characters) and return a brief |
| `GET` | `/health` | none | Service check. Makes no model calls |
| `GET` | `/` | none | Redirects to `/docs` |

### Responses from `/brief`

| Status | Meaning |
|---|---|
| `200` | The brief |
| `401` | Missing or wrong API key |
| `422` | Invalid input (for example, a topic that's too short). No model call is made |
| `429` | Gemini quota or rate limit reached. The message says which, and when to retry |
| `502` | The agent failed for another reason. Details are logged on the server, not returned |
| `503` | `API_KEY` isn't set on the server, so all requests are refused |

## Deploying to Render (free tier)

Settings for running your own copy on [Render](https://render.com):

| Setting | Value |
|---|---|
| Source | Your GitHub repo, `main` branch |
| Instance type | Free |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health check path | `/health` |
| Environment variables | `GEMINI_API_KEY`, `API_KEY`, `PYTHON_VERSION` |

Set the keys in Render's Environment settings. Never commit them.

Notes for the free tier:

- Free web services spin down after 15 minutes of inactivity, and the first request after that can take about a minute while the service wakes up.
- If the build fails with an unexpected package error, check the Python version first. Render's default can differ from the version you tested on, so set `PYTHON_VERSION` to match.
- The Gemini free-tier quota still applies, so a hosted demo can only answer a few questions per day.

## Project structure

```
research-brief-agent/
├── agent.py          # research loop, brief writing, interactive CLI
├── agent_V1_old.py   # earlier version of the agent, kept for comparison
├── main.py           # FastAPI app: validation, API key check, error mapping
├── smoke_test.py     # one-call check that the API key and model work
├── requirements.txt  # pinned dependencies
├── .env.example      # template for your local .env
└── .gitignore
```

## Build log

The project is developed in small steps, and each row below is a stage that was committed separately.

| Stage | What changed | Problem it solved |
|---|---|---|
| Setup check | Environment and a one-call smoke test | Confirms the key, SDK, and network work before any agent logic exists |
| Tool-calling loop | Search loop with a step cap and a forced final answer | The first loop hit its step limit and returned nothing |
| Interactive CLI | Input loop, `run_agent()`, retrying search | Hardcoded topic. One search timeout crashed the whole agent |
| Structured briefs | Separate research and writing steps, numbered sources, Pydantic `Brief` | Sources were written by the model and couldn't be checked |
| Reliability | Retry on Gemini server errors, clear message on quota limits | A busy model or a spent daily quota crashed the request or dumped raw JSON |
| HTTP API | FastAPI endpoint, input validation, error mapping | The agent could only be used from a terminal |
| API key | `X-API-Key` check that refuses requests if no key is configured | A public URL would let anyone spend the Gemini quota |

## Known limitations

- **Sources are real, but not checked against claims.** Every source is a page the search actually returned, and the model can't invent one. The code does not verify that a source supports the point it's attached to, so treat sources as "pages the model read".
- **Search quality varies.** DuckDuckGo search is free and needs no key, but it can time out, return thin results, or occasionally block requests. Results are short snippets, not full pages.
- **The free tier is small.** At the time of writing, the free limit for the model in use was 20 requests per day, and each question uses up to 4 calls. Check your own limits at [ai.dev/rate-limit](https://ai.dev/rate-limit). Limits can differ by model and change over time.
- **Requests are slow.** A brief can take 15 to 40 seconds, and there's no per-request timeout yet.
- **One shared API key.** There are no per-user keys and no rate limiting. If the key leaks, generate a new one and update it everywhere it's set.
- **Model names change.** Google retires model names over time, and a retired name returns a `404` error. If that happens, update `MODEL` in `agent.py` and the model name in `smoke_test.py`.
- **No automated tests yet.**

## Roadmap

- [x] Structured output (summary, key points, sources) with sources taken from the real search results
- [x] HTTP API with FastAPI
- [x] Input validation and clean error responses
- [x] API key protection on the endpoint
- [x] Deployment to Render's free tier
- [ ] Request timeout and basic rate limiting
- [ ] A small set of evaluation cases and automated tests

## Tech stack

Python, [`google-genai`](https://pypi.org/project/google-genai/) (Gemini SDK), [`ddgs`](https://pypi.org/project/ddgs/) (DuckDuckGo search), [FastAPI](https://fastapi.tiangolo.com/) and Uvicorn, Pydantic, `python-dotenv`.
