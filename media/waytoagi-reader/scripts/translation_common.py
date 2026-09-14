"""OpenAI-compatible transport shared by the two standalone translators."""
import json
import urllib.request


def post_translation(host, model, prompt, lines, timeout, max_tokens):
    if not host.lower().startswith(("http://", "https://")):
        raise ValueError("Translation host must use HTTP or HTTPS")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Translate to English:\n\n" + "\n".join(lines)},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{host.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read())
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("Translation response has no usable choice")
    choice = choices[0]
    content = (choice.get("message") or {}).get("content")
    if choice.get("finish_reason") != "stop":
        raise ValueError(f"Incomplete translation: {choice.get('finish_reason')}")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Translation response has no text")
    return content.strip()
