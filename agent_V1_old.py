from google import genai
from google.genai import types
from dotenv import load_dotenv
from ddgs import DDGS

load_dotenv()
client = genai.Client()

MAX_TOOL_CALLS = 3 #guardrail: stop the loop from running forever

def web_search(query: str) -> str:
    "Runs a real DuckDuckGo search and returns formatted results"
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=5)
    if not results:
        return "No results found."
    return "\n\n".join(
        f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {['body']}"
        for r in results
    )

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

config = types.GenerateContentConfig(tools=[search_tool])

topic = "What is the current state of the small modular nuclear reactors in 2026?"
contents = [types.Content(role="user", parts=[types.Part.from_text(text=topic)])]

for step in range(MAX_TOOL_CALLS):
    response = client.models.generate_content(
        model = "gemini-3.6-flash",
        contents = contents,
        config = config,
    )

    if not response.function_calls:
        print("\n=== FINAL ANSWER ===\n")
        print(response.text)
        break

    call = response.function_calls[0]
    print(f"[[step {step+1}] Gemini wants to search: {call.args['query']}")

    result_text = web_search(**call.args)

    # Add the model's tool-call turn, then our tool-result turn
    contents.append(response.candidates[0].content)
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_function_response(
            name=call.name,
            response={"result": result_text},
        )],
    ))

else:
    print("Hit max tool call limit without a final answer.")