import os

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

print("Credentials:", SERVICE_ACCOUNT_FILE)
print("Calendar:", CALENDAR_ID)

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/calendar"]
)

calendar = build(
    "calendar",
    "v3",
    credentials=credentials
)

try:
    result = calendar.calendars().get(
        calendarId=CALENDAR_ID
    ).execute()

    print("\nSUCCESS!")
    print("Calendar name:", result.get("summary"))
    print("Calendar ID:", result.get("id"))
    print("Timezone:", result.get("timeZone"))

except Exception as e:
    print("\nFAILED!")
    print(type(e).__name__)
    print(e)