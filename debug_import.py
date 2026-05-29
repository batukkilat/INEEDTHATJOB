"""Run with: python3 debug_import.py path/to/resume.pdf"""
import sys
from profile.importer import extract_text, parse_resume, save_to_profile
from db.database import get_session

path = sys.argv[1] if len(sys.argv) > 1 else None
if not path:
    print("Usage: python3 debug_import.py path/to/resume.pdf")
    sys.exit(1)

content = open(path, "rb").read()
print(f"--- extracting text from {path} ---")
text = extract_text(content, path)
print(text[:500])
print(f"... ({len(text)} chars total)\n")

print("--- calling LLM ---")
result = parse_resume(text)
import json
print(json.dumps(result, indent=2))

if result:
    print("\n--- saving to DB ---")
    with next(get_session()) as session:
        counts = save_to_profile(session, result)
    print("Saved:", counts)
else:
    print("\nLLM returned empty result — nothing to save")
