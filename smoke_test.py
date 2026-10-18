from google import genai
from dotenv import load_dotenv
load_dotenv() # reads GEMINI_API_KEY from your .env file
client = genai.Client() # automatically picks up GEMINI_API_KEY
response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents="Say hello and confirm that you are working, in one sentence"
)

print(response.text)