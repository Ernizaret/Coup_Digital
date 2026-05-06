"""AI agent implementation using OpenRouter as a unified API."""

from openai import OpenAI

SYSTEM_PROMPT = (
    "You are playing a game of Coup. "
    "Respond ONLY with valid JSON matching the format requested. "
    "Do not include any text outside the JSON object."
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _build_cached_messages(prompt_sections):
    """Build messages with cache_control breakpoints for OpenRouter/Anthropic.

    Uses structured content blocks with explicit cache breakpoints placed on:
      1. Rules summary (static, never changes within a game)
      2. Private thoughts (progressively grows, only appends)
      3. Game log (progressively grows, only appends)

    The decision prompt (game state, decision, response format) changes every
    query and is NOT cached.

    Args:
        prompt_sections: dict from build_prompt_sections() with keys
            "rules_summary", "private_thoughts", "game_log", "decision_prompt"

    Returns:
        list of message dicts suitable for the chat completions API.
    """
    # System message: SYSTEM_PROMPT + rules summary with cache breakpoint
    system_content = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
        },
        {
            "type": "text",
            "text": prompt_sections["rules_summary"],
            "cache_control": {"type": "ephemeral"},
        },
    ]

    # User message: private thoughts + game log (both cached) + decision (not cached)
    user_content = []

    if prompt_sections["private_thoughts"]:
        user_content.append({
            "type": "text",
            "text": prompt_sections["private_thoughts"],
            "cache_control": {"type": "ephemeral"},
        })

    user_content.append({
        "type": "text",
        "text": prompt_sections["game_log"],
        "cache_control": {"type": "ephemeral"},
    })

    user_content.append({
        "type": "text",
        "text": prompt_sections["decision_prompt"],
    })

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


class Agent:
    """An AI agent that queries a model via OpenRouter."""

    def __init__(self, name, api_key, model):
        self.name = name
        self.api_key = api_key
        self.model = model
        self.private_thoughts = []
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0
        self.query_count = 0
        self._client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
        )

    def _track_usage(self, usage):
        """Extract and accumulate token usage from an API response."""
        if not usage:
            return
        self.prompt_tokens += usage.prompt_tokens or 0
        self.completion_tokens += usage.completion_tokens or 0
        # OpenRouter returns cached token count in prompt_tokens_details
        details = getattr(usage, "prompt_tokens_details", None)
        if details:
            self.cached_tokens += getattr(details, "cached_tokens", 0) or 0

    def query(self, prompt):
        """Send a flat prompt string to the model via OpenRouter.

        This is the legacy interface kept for backward compatibility.
        Prefer query_structured() for prompt-caching support.
        """
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=512,
        )
        self.query_count += 1
        self._track_usage(response.usage)
        return response.choices[0].message.content

    def query_structured(self, prompt_sections):
        """Send structured prompt sections with cache_control breakpoints.

        Uses content-block format to enable prompt caching on OpenRouter for
        Anthropic models. Non-Anthropic models receive the same content blocks
        (the cache_control field is simply ignored by other providers).

        Args:
            prompt_sections: dict from build_prompt_sections() with keys
                "rules_summary", "private_thoughts", "game_log", "decision_prompt"

        Returns:
            Raw response text from the model.
        """
        messages = _build_cached_messages(prompt_sections)

        # extra_body passes provider routing to OpenRouter; the openai client
        # forwards unknown kwargs as additional JSON fields in the request body.
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=512,
            extra_body={
                "provider": {
                    "order": ["Anthropic"],
                    "allow_fallbacks": True,
                },
            },
        )
        self.query_count += 1
        self._track_usage(response.usage)
        return response.choices[0].message.content

    def add_thought(self, thought):
        """Store a private thought for future prompting. keep it short and concise."""
        self.private_thoughts.append(thought)

    def get_thoughts_text(self):
        """Format accumulated private thoughts as a string."""
        if not self.private_thoughts:
            return "None yet."
        return "\n".join(f"- {t}" for t in self.private_thoughts)


def create_agent(name, api_key, model):
    """Create an Agent instance."""
    return Agent(name, api_key, model)
