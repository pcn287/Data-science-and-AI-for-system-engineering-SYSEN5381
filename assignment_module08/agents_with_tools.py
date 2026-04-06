# agents_with_tools.py — one tool (calculate_average) and one agent that can call it

import json

import ollama

MODEL = "smollm2:1.7b"


# ----- THE TOOL (plain Python the model is allowed to invoke) -----


def calculate_average(numbers):
    if isinstance(numbers, str):
        numbers = json.loads(numbers)
    nums = [float(x) for x in numbers]
    if not nums:
        return 0.0
    return sum(nums) / len(nums)


# Description Ollama needs so the model knows the tool exists and how to call it
TOOL = {
    "type": "function",
    "function": {
        "name": "calculate_average",
        "description": "Return the mean of a list of numbers.",
        "parameters": {
            "type": "object",
            "required": ["numbers"],
            "properties": {
                "numbers": {"type": "array", "items": {"type": "number"}},
            },
        },
    },
}


# ----- THE AGENT (sends chat to Ollama; runs the tool when the model asks) -----


def agent(question: str) -> str:
    """
    Sends your question to the model with the tool available.
    If the model requests calculate_average, we run it in Python and send the result back,
    then get the model's final answer.
    """
    messages = [
        {
            "role": "system",
            "content": "If the user needs an average, call calculate_average with numbers=[...].",
        },
        {"role": "user", "content": question},
    ]

    reply1 = ollama.chat(model=MODEL, messages=messages, tools=[TOOL])
    msg1 = reply1.message
    messages.append(msg1.model_dump(exclude_none=True))

    if not msg1.tool_calls:
        return msg1.content or ""

    for call in msg1.tool_calls:
        raw = call.function.arguments
        args = json.loads(raw) if isinstance(raw, str) else dict(raw)
        result = calculate_average(args["numbers"])
        messages.append(
            {"role": "tool", "tool_name": call.function.name, "content": str(result)}
        )

    reply2 = ollama.chat(model=MODEL, messages=messages, tools=[TOOL])
    return reply2.message.content or ""


if __name__ == "__main__":
    # --- Your question goes here (edit this string) ---
    my_question = "What is the average of 12, 18, and 24?"

    print("Tool test (no Ollama):", calculate_average([10, 20, 30]))
    print("Agent answer:", agent(my_question))
