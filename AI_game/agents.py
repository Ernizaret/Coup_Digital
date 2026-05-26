"""AI agent implementation using OpenRouter and the Anthropic API.

Claude models are called directly via the Anthropic SDK to avoid OpenRouter
markup.  All other models continue to use the OpenAI SDK pointed at
OpenRouter.
"""

import anthropic
from openai import OpenAI

SYSTEM_PROMPT = (
    "You are playing a game of Coup. "
    "Respond ONLY with valid JSON matching the format requested. "
    "Do not include any text outside the JSON object."
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _is_claude_model(model):
    """Return True if *model* should be routed to the Anthropic API."""
    return model.startswith("claude")


def _build_cached_messages(prompt_sections):
    """Build system content blocks and a user message for prompt caching.

    Uses structured content blocks with explicit cache breakpoints placed on:
      1. Identity line (static within a game)
      2. Rules summary (static, only present when enabled)
      3. Strategy guide (static, only present when enabled)
      4. Game log (progressively grows, only appends)

    The decision prompt (game state, decision, response format) changes every
    query and is NOT cached.

    Args:
        prompt_sections: dict from build_prompt_sections() with keys
            "identity", "rules_summary" (optional), "strategy_guide"
            (optional), "game_log", "decision_prompt"

    Returns:
        (system_content, user_content) where both are lists of content-block
        dicts.  The caller is responsible for assembling these into the
        format required by their API (OpenRouter puts system_content inside
        a ``{"role": "system", ...}`` message; the Anthropic SDK passes it
        via the ``system=`` parameter).
    """
    # System content blocks: SYSTEM_PROMPT + identity with cache breakpoint
    system_content = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
        },
        {
            "type": "text",
            "text": prompt_sections["identity"],
            "cache_control": {"type": "ephemeral"},
        },
    ]

    # If rules summary is present, add it as a cached block in system content
    if prompt_sections.get("rules_summary"):
        system_content.append({
            "type": "text",
            "text": prompt_sections["rules_summary"],
            "cache_control": {"type": "ephemeral"},
        })

    # If strategy guide is present, add it as a cached block in system content
    if prompt_sections.get("strategy_guide"):
        system_content.append({
            "type": "text",
            "text": prompt_sections["strategy_guide"],
            "cache_control": {"type": "ephemeral"},
        })

    # User content blocks: game log (cached) + decision (not cached)
    user_content = []

    if prompt_sections["game_log"]:
        user_content.append({
            "type": "text",
            "text": prompt_sections["game_log"],
            "cache_control": {"type": "ephemeral"},
        })

    user_content.append({
        "type": "text",
        "text": prompt_sections["decision_prompt"],
    })

    return system_content, user_content


class Agent:
    """An AI agent that queries a model via OpenRouter or Anthropic directly.

    Claude models (those whose model name starts with ``claude``) are routed
    to the Anthropic API.  All other models are routed to OpenRouter via the
    OpenAI SDK.
    """

    def __init__(self, name, model, history_depth=2,
                 rules_summary=False, strategy_guide=False,
                 openrouter_api_key=None, anthropic_api_key=None):
        self.name = name
        self.model = model
        self.history_depth = history_depth
        self.rules_summary = rules_summary
        self.strategy_guide = strategy_guide
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cached_tokens = 0
        self.query_count = 0
        self.bluffs = 0
        self.bluffs_caught = 0
        self.challenges_issued = 0
        self.challenges_correct = 0
        self.card_guesses_total = 0
        self.card_guesses_correct = 0

        self._use_anthropic = _is_claude_model(model)

        if self._use_anthropic:
            self._client = anthropic.Anthropic(
                api_key=anthropic_api_key,
                timeout=150.0,
            )
        else:
            self._client = OpenAI(
                api_key=openrouter_api_key,
                base_url=OPENROUTER_BASE_URL,
                timeout=150.0,
            )

    # ------------------------------------------------------------------
    # Token-usage tracking
    # ------------------------------------------------------------------

    def _track_usage(self, usage):
        """Extract and accumulate token usage from an API response."""
        if not usage:
            return

        if self._use_anthropic:
            # Anthropic SDK field names
            self.prompt_tokens += getattr(usage, "input_tokens", 0) or 0
            self.completion_tokens += getattr(usage, "output_tokens", 0) or 0
            self.cached_tokens += (
                getattr(usage, "cache_read_input_tokens", 0) or 0
            )
        else:
            # OpenRouter / OpenAI SDK field names
            self.prompt_tokens += usage.prompt_tokens or 0
            self.completion_tokens += usage.completion_tokens or 0
            details = getattr(usage, "prompt_tokens_details", None)
            if details:
                self.cached_tokens += (
                    getattr(details, "cached_tokens", 0) or 0
                )

    # ------------------------------------------------------------------
    # Internal helpers for each API backend
    # ------------------------------------------------------------------

    def _query_openrouter(self, messages, extra_body=None):
        """Send *messages* to OpenRouter and return the response text."""
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=512,
        )
        if extra_body:
            kwargs["extra_body"] = extra_body
        response = self._client.chat.completions.create(**kwargs)
        self._track_usage(response.usage)
        return response.choices[0].message.content

    def _query_anthropic(self, system_content, user_content):
        """Send a request to the Anthropic messages API and return text."""
        response = self._client.messages.create(
            model=self.model,
            system=system_content,
            messages=[{"role": "user", "content": user_content}],
            temperature=0.7,
            max_tokens=512,
        )
        self._track_usage(response.usage)
        return response.content[0].text

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    def query(self, prompt):
        """Send a flat prompt string to the model.

        This is the legacy interface kept for backward compatibility.
        Prefer query_structured() for prompt-caching support.
        """
        self.query_count += 1

        if self._use_anthropic:
            return self._query_anthropic(
                system_content=SYSTEM_PROMPT,
                user_content=prompt,
            )
        else:
            return self._query_openrouter(messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ])

    def query_structured(self, prompt_sections):
        """Send structured prompt sections with cache_control breakpoints.

        Uses content-block format to enable prompt caching.  Claude models
        are called directly via the Anthropic SDK; all other models go
        through OpenRouter.

        Args:
            prompt_sections: dict from build_prompt_sections() with keys
                "identity", "game_log", "decision_prompt"

        Returns:
            Raw response text from the model.
        """
        system_content, user_content = _build_cached_messages(prompt_sections)
        self.query_count += 1

        if self._use_anthropic:
            return self._query_anthropic(system_content, user_content)
        else:
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ]
            return self._query_openrouter(
                messages,
                extra_body={
                    "provider": {
                        "order": ["Anthropic"],
                        "allow_fallbacks": True,
                    },
                },
            )

    def query_survey(self, prompt_sections):
        """Send a card-guess survey prompt and return the raw response.

        Uses the same structured message format and prompt caching as
        query_structured(). Token usage is accumulated into the agent's
        existing token counters.

        Args:
            prompt_sections: dict from build_survey_prompt_sections() with
                keys "identity", "rules_summary", "strategy_guide",
                "game_log", "decision_prompt"

        Returns:
            Raw response text from the model.
        """
        system_content, user_content = _build_cached_messages(prompt_sections)
        self.query_count += 1

        if self._use_anthropic:
            return self._query_anthropic(system_content, user_content)
        else:
            messages = [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ]
            return self._query_openrouter(
                messages,
                extra_body={
                    "provider": {
                        "order": ["Anthropic"],
                        "allow_fallbacks": True,
                    },
                },
            )


def create_agent(name, model, history_depth=2, rules_summary=False,
                 strategy_guide=False, openrouter_api_key=None,
                 anthropic_api_key=None,
                 api_key=None):
    """Create an Agent instance.

    Args:
        name: display name for the agent.
        model: model identifier string.
        history_depth: number of turns of history to include.
        rules_summary: whether to include the rules reference.
        strategy_guide: whether to include the strategy guide.
        openrouter_api_key: API key for OpenRouter (non-Claude models).
        anthropic_api_key: API key for the Anthropic API (Claude models).
        api_key: legacy alias for openrouter_api_key (backward compat).
    """
    # Support legacy callers that pass positional `api_key`
    if openrouter_api_key is None and api_key is not None:
        openrouter_api_key = api_key
    return Agent(name, model,
                 history_depth=history_depth,
                 rules_summary=rules_summary,
                 strategy_guide=strategy_guide,
                 openrouter_api_key=openrouter_api_key,
                 anthropic_api_key=anthropic_api_key)
