"""AI agent implementation using OpenRouter as a unified API."""

from openai import OpenAI

SYSTEM_PROMPT = (
    "You are playing a game of Coup. "
    "Respond ONLY with valid JSON matching the format requested. "
    "Do not include any text outside the JSON object."
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class Agent:
    """An AI agent that queries a model via OpenRouter."""

    def __init__(self, name, api_key, model):
        self.name = name
        self.api_key = api_key
        self.model = model
        self.private_thoughts = []
        self._client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
        )

    def query(self, prompt):
        """Send prompt to the model via OpenRouter and return the raw response text."""
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content

    def add_thought(self, thought):
        """Store a private thought for future prompting."""
        self.private_thoughts.append(thought)

    def get_thoughts_text(self):
        """Format accumulated private thoughts as a string."""
        if not self.private_thoughts:
            return "None yet."
        return "\n".join(f"- {t}" for t in self.private_thoughts)


def create_agent(name, api_key, model):
    """Create an Agent instance."""
    return Agent(name, api_key, model)
