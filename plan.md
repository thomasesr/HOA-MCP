# Plan: on-demand context, no hallucination

## Architecture

Multi-step reasoning loop (max 3 iterations):

```
User utterance
    → [1] Odysseus: what do I need? (tool_request JSON)
    → [2] Execute tool locally (entity search OR web search)
    → [3] Odysseus: final response/action (with tool results)
    → Execute HA action if any → speak
```

LLM is never asked to guess. It must declare what it needs first.

---

## Always-injected context (minimal, every request)

| Field | Source |
|---|---|
| Date + time | datetime.now() |
| User name | user_input.context.user_id → hass.auth.async_get_user() |
| Device / area | user_input.device_id → device_registry friendly name + area |
| HA location | hass.config.location_name, lat, lon |

No entity states. No weather. No device list.

---

## Tool actions LLM can request

### search_entities
LLM response:
```json
{"action": "search_entities", "query": "Luz do Quarto", "domain": "light"}
```
HOA-MCP executes: fuzzy-match query against friendly_name + entity_id across
hass.states.async_all(domain). Returns list of matches (entity_id, friendly_name, state, attrs).
Sends matches back to LLM for step 3.

### web_search
LLM response:
```json
{"action": "web_search", "query": "temperatura São Paulo agora"}
```
HOA-MCP executes: POST {odysseus_url}/api/search with JSON {"query": "..."},
returns context string + sources to LLM for step 3.

### call_service (final action)
LLM response after receiving entity search results:
```json
{"action": "call_service", "domain": "light", "service": "turn_off",
 "entity_id": "light.quarto_luz", "response": "Luz do Quarto apagada."}
```
HOA-MCP executes: hass.services.async_call, speaks response.

### none (direct answer)
```json
{"action": "none", "response": "São 14h37 de segunda-feira."}
```
No lookup needed. Speaks response directly.

---

## Example flows

### "Desliga a Luz do Quarto"
1. LLM → search_entities query="Luz do Quarto" domain="light"
2. HOA-MCP → [{entity_id: "light.quarto_luz", name: "Luz do Quarto", state: "on"}]
3. LLM → call_service domain=light service=turn_off entity_id=light.quarto_luz response="Apaguei a Luz do Quarto."
4. Execute → speak

### "Que temperatura está?"
1. LLM → search_entities query="weather" domain="weather"
2. HOA-MCP → [{entity_id: "weather.home", state: "cloudy", temperature: "22°C"}]
3. LLM → none response="Está 22°C e nublado."
4. Speak

### "Qual a capital da Austrália?"
1. LLM → none response="Camberra."  (no tool needed for factual knowledge)
4. Speak

### "Qual foi o resultado do jogo do Brasil ontem?"
1. LLM → web_search query="resultado jogo Brasil ontem"
2. HOA-MCP → POST /api/search → context string with search results
3. LLM → none response="Brasil venceu a Argentina por 2x1."
4. Speak

---

## Steps

### Step 1 — _build_context()
Only: date/time, user name (async lookup), device friendly name + area, HA location name.

### Step 2 — System prompt
Teach LLM the 4 actions: search_entities, web_search, call_service, none.
Strict: always return JSON, no other text.
On step 3 (has tool results): must return call_service or none — not another search.

### Step 3 — Reasoning loop in async_process
```
for iteration in range(3):
    response = await _call_odysseus(messages)
    parsed = parse_json(response)
    if parsed.action in (none, call_service): break
    tool_result = await _execute_tool(parsed)
    messages.append(tool_result as context)
execute final action → speak
```
messages list is local to the request (no session persistence).

### Step 4 — _search_entities(query, domain)
- hass.states.async_all(domain or None)
- Score each entity: exact match > contains > fuzzy (difflib.SequenceMatcher)
- Return top 5 matches as compact JSON list

### Step 5 — _web_search(query)
- POST {odysseus_url}/api/search json={"query": query}
- Bearer token in header
- Return context string (truncated to 1000 chars to limit tokens)

### Step 6 — _execute_service(parsed)
- domain, service, entity_id from parsed
- Extra attrs: brightness, rgb_color, color_temp, volume_level, hvac_mode, temperature
- hass.services.async_call(blocking=True)

### Step 7 — Syntax check + commit
