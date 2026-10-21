"""Research Brief Agent: searches the web and returns a structured brief.

Flow:
  1. research()    - Gemini decides what to search; results are numbered and
                     collected by our code.
  2. write_brief() - a second call turns the collected results into a
                     structured brief. The model only picks source NUMBERS;
                     the titles and URLs are attached by our code, so the
                     model cannot invent a source.
"""
import time

from dotenv import load_dotenv
from ddgs import DDGS
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv()
client = genai.Client()

MODEL = "gemini-3.6-flash"
MAX_TOOL_CALLS = 3  # hard limit on research steps per question


# -----------------------Schemas------------------------
class Source(BaseModel):
    id: int
    title: str
    url: str


class BriefDraft(BaseModel):
    """What the model is asked to produce."""

    summary: str = Field(description="A 2-4 sentence overview that answers the question.")
    key_points: list[str] = Field(description="3-6 short, specific findings.")
    source_ids: list[int] = Field(
        description="The [n] numbers of the search results actually relied on."
    )


class Brief(BaseModel):
    """The final result: model-written content plus code-attached sources."""

    topic: str
    summary: str
    key_points: list[str]
    sources: list[Source]


# ---------------------------Prompts-----------------------------
SEARCH_PROMPT = (
    "You are a research assistant. Use web_search at most 2 times to gather "
    "information on the user's question. Search results are numbered like [1], [2]. "
    "If a search fails or returns nothing useful, do not guess. "
    "When you have enough information, reply with just the word DONE."
)

WRITER_PROMPT = (
    "You write short, factual research briefs from search results. "
    "Use only information found in the results provided; do not add facts from memory. "
    "In source_ids, list the numbers (the [n] labels) of the results you actually "
    "relied on. If the results are missing or unhelpful, say so in the summary and "
    "leave key_points and source_ids empty."
)


# -----------------------Search tool---------------------
search_tool = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="web_search",
        description="Search the web for current information on a topic.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."}
            },
            "required": ["query"],
        },
    )
])

search_config = types.GenerateContentConfig(
    system_instruction=SEARCH_PROMPT,
    tools=[search_tool],
)


def search_web(query: str) -> list[dict]:
    """Runs a DuckDuckGo search. Retries once, then raises the last error."""
    last_error = None
    for attempt in range(2):
        try:
            with DDGS(timeout=10) as ddgs:
                return ddgs.text(query, max_results=5)
        except Exception as e:
            last_error = e
            print(f"  (search attempt {attempt + 1} failed: {type(e).__name__})")
            time.sleep(2)
    raise last_error


def run_search(query: str, sources: dict[int, Source]) -> str:
    """Runs a search, registers each result as a numbered source, and
    returns text for the model. Failures become plain text, not crashes."""
    try:
        results = search_web(query)
    except Exception as e:
        return f"Search failed ({type(e).__name__}). No results available."
    if not results:
        return "No results found."

    lines = []
    for r in results:
        url = r["href"]
        source = next((s for s in sources.values() if s.url == url), None)
        if source is None:  # new page: give it the next number
            source = Source(id=len(sources) + 1, title=r["title"], url=url)
            sources[source.id] = source
        lines.append(f"[{source.id}] {source.title}\nURL: {source.url}\nSnippet: {r['body']}")
    return "\n\n".join(lines)


# ----------------------The Agent-----------------------
def research(topic: str) -> tuple[str, dict[int, Source]]:
    """Lets the model search (up to MAX_TOOL_CALLS steps). Returns the
    collected results as text, plus the numbered source registry."""
    sources: dict[int, Source] = {}
    evidence: list[str] = []
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=topic)])]

    for step in range(MAX_TOOL_CALLS):
        response = client.models.generate_content(
            model=MODEL, contents=contents, config=search_config
        )
        if not response.function_calls:
            break  # model is done searching

        # Answer every tool call in this turn (the model may request several)
        reply_parts = []
        for call in response.function_calls:
            query = ((call.args or {}).get("query") or "").strip()
            print(f"[step {step + 1}] Searching: {query}")
            result_text = run_search(query, sources) if query else "No query was given."
            evidence.append(f"Search: {query}\n{result_text}")
            reply_parts.append(types.Part.from_function_response(
                name=call.name, response={"result": result_text}
            ))

        contents.append(response.candidates[0].content)
        contents.append(types.Content(role="user", parts=reply_parts))

    return "\n\n".join(evidence), sources


def write_brief(topic: str, evidence: str, sources: dict[int, Source]) -> Brief:
    """Turns the collected results into a validated, structured Brief."""
    prompt = (
        f"Question: {topic}\n\n"
        f"Search results:\n{evidence or '(no searches were run)'}"
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=WRITER_PROMPT,
            response_mime_type="application/json",
            response_schema=BriefDraft,
        ),
    )
    draft = response.parsed
    if not isinstance(draft, BriefDraft):
        raise ValueError("The model did not return a valid brief.")

    # Keep only numbers that really exist; titles/URLs come from our registry
    used = sorted({i for i in draft.source_ids if i in sources})
    return Brief(
        topic=topic,
        summary=draft.summary,
        key_points=draft.key_points,
        sources=[sources[i] for i in used],
    )


def run_agent(topic: str) -> Brief:
    evidence, sources = research(topic)
    return write_brief(topic, evidence, sources)


#------------------CLI-----------------
def print_brief(brief: Brief) -> None:
    print(f"\n=== {brief.topic} ===\n")
    print(brief.summary)
    print("\nKey points:")
    for point in brief.key_points:
        print(f"  - {point}")
    print("\nSources:")
    if brief.sources:
        for s in brief.sources:
            print(f"  [{s.id}] {s.title}\n      {s.url}")
    else:
        print("  (none)")


if __name__ == "__main__":
    print("Research Brief Agent (type 'quit' to exit)\n")
    while True:
        topic = input("Topic or question: ").strip()
        if topic.lower() in ("quit", "exit", "q"):
            break
        if not topic:
            print("Please enter a topic.\n")
            continue
        try:
            print_brief(run_agent(topic))
        except Exception as e:
            print(f"\nSomething went wrong: {type(e).__name__}: {e}")
        
        print("\n" + "-" * 40 + "\n")