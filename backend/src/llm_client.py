import requests

try:
    from .config import DEFAULT_MODEL, OLLAMA_URL
except ImportError:  # pragma: no cover
    from config import DEFAULT_MODEL, OLLAMA_URL


class OllamaClient:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model

    def generate(self, prompt: str) -> str:
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=120,
            )
            response.raise_for_status()
            payload = response.json()
            return payload.get("response", "").strip()
        except Exception:
            return (
                "I could not generate a reply because the Ollama inference service is not available. "
                "Please start Ollama and ensure the model is pulled."
            )
