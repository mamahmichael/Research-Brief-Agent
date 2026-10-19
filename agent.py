from google import genai
from google.genai import types
from dotenv import load_dotenv
from ddgs import DDGS
import time

load_dotenv()
client = genai.Client()

MAX_TOOL_CALLS = 3 #guardrail: stop the loop from running forever

def web_search(query: str) -> str:
    """Runs a DuckDuckGo search. Retries once, and returns an error
    message instead of crashing if the search keeps failing."""
    last_error = None
    for attempt in range(2):
        try:
            with DDGS(timeout=10) as ddgs:
                results = ddgs.text(query, max_results=5)
            if not results:
                return "No results found."
            return "\n\n".join(
                f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}"
                for r in results
            )
        except Exception as e:
            last_error = e
            print(f"  (search attempt {attempt + 1} failed: {type(e).__name__})")
            time.sleep(2)
    return f"Search failed after retrying ({type(last_error).__name__}). No results available."

# Tell Gemini this tool exists and how to use it
search_tool = types.Tool(function_declarations = [
    types.FunctionDeclaration(
        name="web_search",
        description="Search the web for current information on a topic",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "the search query."}
            },
            "required": ["query"]
        },
        )
    ])

SYSTEM_PROMPT = (
    "You are a research assistant. Use web_search sparingly: at most 2 searches, "
    "then write a concise answer based on what you found. "
    "Mention which sources the information came from."
    "If a search fails or returns nothing useful, say so plainly instead of guessing."
)

search_config = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[search_tool],
)

# Same as above, but the model is not allowed to call tools
final_config = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[search_tool],
    tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(mode="NONE")
    ),
)

def run_agent(topic: str) -> str:
    """Runs the search loop for one topic and returns the final answer."""
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=topic)])]

    for step in range(MAX_TOOL_CALLS + 1):
        is_last = step == MAX_TOOL_CALLS
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents,
            config=final_config if is_last else search_config,
        )

        if not response.function_calls:
            return response.text

        call = response.function_calls[0]
        print(f"[step {step + 1}] Searching: {call.args['query']}")

        result_text = web_search(**call.args)

        contents.append(response.candidates[0].content)
        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_function_response(
                name=call.name,
                response={"result": result_text},
            )],
        ))

    return "No answer produced."


if __name__ == "__main__":
    print("Research Brief Agent (type 'quit' to exit)\n")
    while True:
        topic = input("Topic or question: ").strip()
        if topic.lower() in ("quit", "exit", "q"):
            break
        if not topic:
            print("Please enter a topic.\n")
            continue
        answer = run_agent(topic)
        print("\n=== ANSWER ===\n")
        print(answer)
        print("\n" + "-" * 40 + "\n")