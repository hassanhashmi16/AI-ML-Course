# Project 1: Meeting Notes Summarizer — Steps

## Overview

A CLI tool that takes a meeting transcript and returns a structured summary (action items, decisions, key points, attendees) using an LLM + Pydantic validation.

## System Architecture

```
transcript.txt → CLI script → Gemini SDK → Pydantic model (direct structured output) → formatted output
```

The flow: file input → prompt construction → API call → parse structured response → validate with Pydantic → display

## Steps

### Step 1: Project folder + requirements.txt

Create the project directory and dependency file.

### Step 2: Define Pydantic models

Create `models.py` with the data structures for the meeting summary output:
- `ActionItem` (task, owner, deadline)
- `Decision` (description, rationale)
- `KeyPoint` (topic, detail)
- `MeetingSummary` (title, date, attendees, action_items, decisions, key_points, summary)

### Step 3: Set up LLM client

Create `client.py` that loads the API key from environment variables and initializes the Anthropic or OpenAI client.

### Step 4: Write the system prompt

Create `prompt.py` with the system prompt that instructs the LLM to extract structured information from meeting transcripts.

### Step 5: Core function — transcript to structured summary

Create `summarizer.py` with the main function that:
1. Takes raw transcript text
2. Calls the LLM with the prompt
3. Parses the structured response
4. Validates it with Pydantic
5. Returns the validated `MeetingSummary` object

### Step 6: CLI entry point

Create `main.py` that:
1. Reads the transcript file path from command line arguments
2. Calls the summarizer function
3. Prints the structured output in a readable format

### Step 7: Error handling

Add graceful handling for:
- Missing API key
- API errors (rate limits, timeouts)
- Pydantic validation failures
- File not found

### Step 8: Test with a sample transcript

Run the tool with a sample transcript to verify everything works end-to-end.
