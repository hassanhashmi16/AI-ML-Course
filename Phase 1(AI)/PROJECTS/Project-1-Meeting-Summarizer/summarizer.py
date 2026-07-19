import google.generativeai as genai
from client import model
from prompt import SYSTEM_PROMPT
from models import MeetingSummary


def summarize(transcript: str) -> MeetingSummary:
    response = model.generate_content(
        [SYSTEM_PROMPT, transcript],
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=MeetingSummary,
        ),
    )

    return response.parsed
