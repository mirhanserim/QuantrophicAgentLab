"""Manual smoke test: can the local Ollama model call a tool? (needs `ollama serve`)"""

from pathlib import Path
from ollama import chat

WORKSPACE = Path(__file__).resolve().parents[2] / "workspace"


def list_files() -> str:
    """List all files inside the agent workspace."""
    files = []

    for path in WORKSPACE.rglob("*"):
        if path.is_file():
            files.append(str(path.relative_to(WORKSPACE)))

    if not files:
        return "Workspace is empty."

    return "\n".join(files)


messages = [
    {
        "role": "user",
        "content": "Workspace içinde hangi dosyalar olduğunu kontrol et."
    }
]

response = chat(
    model="qwen3:8b",
    messages=messages,
    tools=[list_files],
)

print("MODEL RESPONSE:")
print(response.message)

if response.message.tool_calls:
    for call in response.message.tool_calls:
        if call.function.name == "list_files":
            result = list_files()

            print("\nTOOL CALLED:")
            print("list_files()")

            print("\nTOOL RESULT:")
            print(result)
