from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

gemini_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)
def ask_llm(user_text):
    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_text
        )
        return response.text
    except Exception as e:
        print("LLM error:", e)
        return "Sorry, I encountered an error while processing your request."

print(
    ask_llm("Hello, my name is Abdul Hadi.")
)