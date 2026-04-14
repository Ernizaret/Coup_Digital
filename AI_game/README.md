# Coup — AI Agent Battle

Watch AI models play Coup against each other. All models are accessed through [OpenRouter](https://openrouter.ai/), a unified API that supports hundreds of models from OpenAI, Anthropic, Google, and more.

## Prerequisites

- Python 3.8+
- An OpenRouter account and API key ([get one here](https://openrouter.ai/keys))

## Setup

### 1. Install dependencies

From the project root:

```bash
pip install -r requirements.txt
```

This installs the `openai` package (used to communicate with OpenRouter's API).

### 2. Create your config file

Copy the example config:

```bash
cp ai_config.json.example ai_config.json
```

### 3. Add your OpenRouter API key and choose models

Edit `ai_config.json`:

```json
{
    "api_key": "sk-or-v1-your-key-here",
    "agents": {
        "ChatGPT": "openai/gpt-4o",
        "Claude": "anthropic/claude-sonnet-4-20250514",
        "Gemini": "google/gemini-2.0-flash-001",
        "Perplexity": "perplexity/sonar"
    }
}
```

- **`api_key`** — Your OpenRouter API key. This single key is used for all agents.
- **`agents`** — A mapping of display names to OpenRouter model IDs. Each entry becomes a selectable agent in the setup window.

### Customizing agents

You can add, remove, or rename agents freely. The display name (the key) is what appears in the game — the value is the OpenRouter model ID.

For example, to add Grok and a second ChatGPT variant:

```json
{
    "api_key": "sk-or-v1-your-key-here",
    "agents": {
        "ChatGPT": "openai/gpt-4o",
        "ChatGPT Mini": "openai/gpt-4o-mini",
        "Claude": "anthropic/claude-sonnet-4-20250514",
        "Gemini": "google/gemini-2.0-flash-001",
        "Perplexity": "perplexity/sonar",
        "Grok": "x-ai/grok-3-latest"
    }
}
```

Browse available models at [openrouter.ai/models](https://openrouter.ai/models).

## Running the Game

From the project root:

```bash
python -m AI_game
```

### Setup window

A Tkinter window will open where you:

1. **Add agents** — Click the `+ AgentName` buttons to add agents to the game (2–6 players).
2. **Arrange turn order** — Select an agent in the list and use Move Up / Move Down to reorder. Use Remove to take one out.
3. **Start** — Click "Start Game" when ready (requires at least 2 agents).

### Spectating

Once the game starts, the setup window closes and the game plays out in the terminal. You'll see:

- Each agent's public speech and chosen action
- Game events (challenges, blocks, eliminations)
- A status summary after each turn showing coins and remaining influence
- The final winner announcement

Each agent is color-coded in the terminal output for readability.

## Notes

- **API costs** — Each agent decision is one API call. A typical game runs 30–80 calls total depending on player count and how many challenges/blocks occur.
- **Rate limits** — If an API call fails, the game retries up to 3 times. If all retries fail, the agent defaults to the first available option.
- **`ai_config.json` is gitignored** — Your API key will not be committed.
