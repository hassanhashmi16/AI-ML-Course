import sys
from summarizer import summarize

if len(sys.argv) < 2:
    print("Usage: python main.py <transcript_file>")
    sys.exit(1)

file_path = sys.argv[1]

try:
    with open(file_path, "r", encoding="utf-8") as f:
        transcript = f.read()
except FileNotFoundError:
    print(f"Error: File '{file_path}' not found")
    sys.exit(1)

try:
    summary = summarize(transcript)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)

print(f"Title: {summary.title}")
print(f"Date: {summary.date}")
print(f"Attendees: {', '.join(summary.attendees)}")
print(f"\nSummary: {summary.summary}")

if summary.key_points:
    print("\nKey Points:")
    for kp in summary.key_points:
        print(f"  • {kp.topic}: {kp.detail}")

if summary.action_items:
    print("\nAction Items:")
    for ai in summary.action_items:
        owner = f" (owner: {ai.owner})" if ai.owner else ""
        deadline = f" (deadline: {ai.deadline})" if ai.deadline else ""
        print(f"  ☐ {ai.task}{owner}{deadline}")

if summary.decisions:
    print("\nDecisions:")
    for d in summary.decisions:
        rationale = f" — {d.rationale}" if d.rationale else ""
        print(f"  • {d.description}{rationale}")
