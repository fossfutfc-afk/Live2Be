# How Production & Research AI-Agent Memory Systems Represent and Use EMOTION
### A source-verified survey for a visual-novel game engine (Live2Be)

**Verification policy.** Every claim below is either (a) a verbatim quote from source code or a paper, with the file/field name and a URL, or (b) an exact formula with a URL. Claims I could not verify are collected in §9 and marked inline as **[UNVERIFIED]**. Nothing here is invented; where the paper and the shipped code disagree, I give both.

**Tooling note.** `raw.githubusercontent.com` and `arxiv.org/html` were intermittently unreachable from this environment; I verified code through the GitHub Contents API (`api.github.com/repos/.../contents/...`), the jsDelivr CDN, and direct PDF downloads, and papers through `ar5iv.labs.arxiv.org`. URLs given are the canonical human-readable ones.

---

## 1. Generative Agents (Park et al. 2023, "Smallville")

Paper: Park, O'Brien, Cai, Morris, Liang, Bernstein, *Generative Agents: Interactive Simulacra of Human Behavior*, UIST '23, **arXiv:2304.03442** — https://arxiv.org/abs/2304.03442 · full text: https://ar5iv.labs.arxiv.org/html/2304.03442
Code: https://github.com/joonspk-research/generative_agents

### 1.1 What a memory record actually is

> "The memory stream maintains a comprehensive record of the agent's experience. It is a list of memory objects, where each object contains **a natural language description, a creation timestamp, and a most recent access timestamp**."
> — §4.1, https://ar5iv.labs.arxiv.org/html/2304.03442

In code, `ConceptNode.__init__` (`reverie/backend_server/persona/memory_structures/associative_memory.py`) has exactly:

```
def __init__(self, node_id, node_type, depth, created, expiration,
             s, p, o, description, embedding_key, poignancy, keywords, filling):
```
with `self.poignancy = poignancy` (line 41) and `self.last_accessed = self.created` (line 33).
URL: https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/memory_structures/associative_memory.py

**There is no emotion, valence, arousal, sentiment or mood field.** The only affect-adjacent scalar is `poignancy`. (The repo *does* have an emoji generator, `generate_pronunciatio` → "a string of emoji that translates action description", but it is a display artefact for the map, not stored affect.)

### 1.2 `poignancy` / "importance" — exact definition, scale, who assigns it

**Scale:** integer 1–10. **Who assigns it:** an LLM (gpt-3.5-turbo), *at memory creation time*.

Paper prompt text (§4.1, verbatim):

> On the scale of 1 to 10, where 1 is purely mundane (e.g., brushing teeth, making bed) and 10 is extremely poignant (e.g., a break up, college acceptance), rate the likely poignancy of the following piece of memory.
> Memory: buying groceries at The Willows Market and Pharmacy
> Rating: \<fill in\>

> "This prompt returns an integer value of 2 for 'cleaning up the room' and 8 for 'asking your crush out on a date.' **The importance score is generated at the time the memory object is created.**"

**The shipped prompt differs** — and this matters, because the code runs *two different* prompts for events vs. chats. Verbatim from
`reverie/backend_server/persona/prompt_template/v2/poignancy_event_v1.txt`
(https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/prompt_template/v2/poignancy_event_v1.txt):

```
Here is a brief description of !<INPUT 0>!.
!<INPUT 1>!

On the scale of 1 to 10, where 1 is purely mundane (e.g., brushing teeth, making bed)
and 10 is extremely poignant (e.g., a break up, college acceptance), rate the likely
poignancy of the following event for !<INPUT 2>!.

Event: !<INPUT 3>!
Rate (return a number between 1 and 10):
```

and `poignancy_chat_v1.txt` (verbatim, note the **different few-shot anchors**):

```
On the scale of 1 to 10, where 1 is purely mundane (e.g., routine morning greetings)
and 10 is extremely poignant (e.g., a conversation about breaking up, a fight), rate
the likely poignancy of the following conversation for !<INPUT 2>!.
```

A third prompt `poignancy_thought_v1.txt` covers reflections. Dispatch logic in
`persona/cognitive_modules/reflect.py`:

```python
def generate_poig_score(persona, event_type, description):
  if "is idle" in description:
    return 1                                    # hard-coded: idle observations are mundane
  if event_type == "event" or event_type == "thought":
    return run_gpt_prompt_event_poignancy(persona, description)[0]
  elif event_type == "chat":
    return run_gpt_prompt_chat_poignancy(persona, persona.scratch.act_description)[0]
```

### 1.3 The retrieval score — exact formula and the real constants

**Paper version** (§4.1). Recency, relevance and importance are min-max normalised to [0,1], then:

> `score = α_recency · recency + α_importance · importance + α_relevance · relevance`
> "In our implementation, all αs are set to 1."

with

> "we treat recency as **an exponential decay function over the number of sandbox game hours** since the memory was last retrieved. **Our decay factor is 0.995.**"

**The shipped code disagrees on both the weights and the decay factor.** In
`reverie/backend_server/persona/cognitive_modules/retrieve.py`
(https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/cognitive_modules/retrieve.py):

```python
  # Note to self: test out different weights. [1, 1, 1] tends to work
  # decently, but in the future, these weights should likely be learned,
  # perhaps through an RL-like process.
  # gw = [1, 1, 1]
  # gw = [1, 2, 1]
  gw = [0.5, 3, 2]
  master_out = dict()
  for key in recency_out.keys():
    master_out[key] = (persona.scratch.recency_w*recency_out[key]*gw[0]
                     + persona.scratch.relevance_w*relevance_out[key]*gw[1]
                     + persona.scratch.importance_w*importance_out[key]*gw[2])
```

So the effective score is

```
score_i = recency_w · r̂_i · 0.5  +  relevance_w · v̂_i · 3  +  importance_w · î_i · 2
```

with `gw = [0.5, 3, 2]` mapping to **[recency, relevance, importance]** — i.e. **relevance is 6× recency and 1.5× importance**, the opposite emphasis from the paper's uniform "all αs are 1".

Recency itself (`extract_recency`) is

```python
  recency_vals = [persona.scratch.recency_decay ** i for i in range(1, len(nodes) + 1)]
```

i.e. `recency = d^i` where **`i` is the node's index in a list sorted by `last_accessed`** (so the most recently accessed node gets the *smallest* exponent and the highest value), and `d = recency_decay`. And the default is set in
`reverie/backend_server/persona/memory_structures/scratch.py` line 60 (https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/memory_structures/scratch.py):

```python
    self.recency_decay = 0.99
```

> **⚠ Two documented discrepancies between paper and code:**
> | quantity | paper | shipped code |
> |---|---|---|
> | decay factor | 0.995 | **0.99** |
> | component weights | all 1 | **recency 0.5, relevance 3, importance 2** |
>
> Also note the exponents are **rank**, not elapsed hours: the recency term is a rank discount against `last_accessed`, not the per-hour exponential the paper describes. Treat this as a bug-or-drift worth knowing before copying it.

Relevance (`extract_relevance`) is `cos_sim(node_embedding, focal_embedding)`; importance is simply `node.poignancy` (`extract_importance`). Each component is min-max normalised to [0,1] by `normalize_dict_floats(x, 0, 1)` before combination. Top-`n_count` (= 30) are taken. Retrieved nodes get `n.last_accessed = persona.scratch.curr_time` — **so recall mutates the memory** (this is the only mutation: recency updates, `poignancy` never does).

### 1.4 Reflection / "insight" and where emotion enters

**Trigger — sum of importance, threshold 150.** `scratch.py`:

```python
    self.importance_trigger_max = 150
    self.importance_trigger_curr = self.importance_trigger_max
    self.importance_ele_n = 0
```

`perceive.py` (lines 178–179) runs, per perceived event:

```python
      persona.scratch.importance_trigger_curr -= event_poignancy
      persona.scratch.importance_ele_n += 1
```

and `reflect.py`:

```python
def reflection_trigger(persona):
  if (persona.scratch.importance_trigger_curr <= 0 and
      [] != persona.a_mem.seq_event + persona.a_mem.seq_thought):
    return True
  return False
```

So the trigger is `Σ poignancy_of_new_events_since_last_reflection ≥ 150`, reset after firing (`importance_trigger_curr = importance_trigger_max; importance_ele_n = 0`). Since poignancy ∈ [1,10], this fires every ~15 (all-maximally-poignant) to 150 (all-mundane) observations. The paper: "we generate reflections when the sum of the importance scores for the latest events perceived by the agents exceeds a threshold (**150** in our implementation). In practice, our agents reflected roughly two or three times a day."

**Three-step reflection:**
1. **Focal points** — the last `importance_ele_n` statements (i.e. exactly the ones that accumulated to 150) are fed to `generate_focal_pt_v1.txt`:
   > `!<INPUT 0>!` / "Given only the information above, what are `!<INPUT 1>!` most salient high-level questions we can answer about the subjects in the statements?" (`n = 3`)
2. **Retrieve** 30 nodes per focal point via the same `new_retrieve`.
3. **Insights** — `insight_and_evidence_v1.txt` (https://github.com/joonspk-research/generative_agents/blob/main/reverie/backend_server/persona/prompt_template/v2/insight_and_evidence_v1.txt):
   ```
   Input:
   !<INPUT 0>!
   What !<INPUT 1>! high-level insights can you infer from the above statements?
   (example format: insight (because of 1, 5, 3))
   1.
   ```
   `n = 5`. Each insight is parsed with its **evidence pointers** (`evidence_node_id = [nodes[i].node_id for i in evi_raw]`), stored via `add_thought(... evidence)` alongside `thought_poignancy = generate_poig_score(persona, "thought", thought)` — i.e. **an insight is scored for poignancy by the same 1–10 LLM prompt**, so it can itself trigger the next reflection. Evidence links make a reflection tree (leaf = observation, internal node = abstraction).

**How emotion figures in:** *it doesn't, as emotion.* There is no affect variable anywhere in the loop. What exists is a **single scalar `poignancy` per node, produced by an LLM rating, used for three distinct purposes**: (1) the importance term in retrieval, (2) the accumulator that triggers reflection, (3) a salience weight on reflections. **Emotional salience is proxied, not modelled**, and it is always *absolute* (1–10 on a fixed scale) — never relative to the agent's own baseline. This is the structural gap that §8 is about.

---

## 2. Follow-up agent-memory frameworks: does the record carry emotion?

Summary table first; details below. "NONE" = verified absent from the schema and the prompts.

| System | explicit emotion field? | importance/affect-adjacent field | written when | mutable? | time decay? |
|---|---|---|---|---|---|
| **Generative Agents** | NONE | `poignancy` (int 1–10) | at ingest, by the summarizing LLM | poignancy **immutable**; `last_accessed` mutable on recall | yes, but only on *recency*, not importance (`recency_decay = 0.99`) |
| **A-Mem** (A-mem-sys) | NONE | NONE | — | `context`/`tags` rewritten by the *evolution* LLM on every `add_note`; content immutable | NONE |
| **A-Mem** (benchmark repo) | NONE | `importance_score: Optional[float] = None` → `= importance_score or 1.0` — **dead field** | never written by the LLM, never read by retrieval | technically assignable, nothing changes it | NONE |
| **MemGPT / Letta** | NONE | NONE | agent writes blocks itself via tool calls | **highly mutable** (self-editing `core_memory_*`) | NONE (only FIFO context eviction + char `limit`) |
| **Mem0** | NONE as a field; emotions stored *inside* the text | NONE | — | `text`/`metadata` updatable; identity keys immutable | NONE in OSS (`DECAY_FEATURE_ERROR_MESSAGE`); `expiration_date` is a hard TTL |
| **Zep / Graphiti** | NONE (hook: `attributes` free JSON) | NONE | — | `valid_at`/`invalid_at`/`expired_at` mutated by the invalidation LLM at ingest | NONE — logical invalidation only, records retained non-lossy |
| **LangMem / LangGraph** | NONE | NONE as a field; importance = inline `[IMPORTANT]` tags in `content` | label at extraction; `created_at/updated_at` on put | mutable via `manage_memory`; `RemoveDoc` semantics caller-defined | NONE (opt-in LangGraph `ttl` in minutes only) |
| **Cognee** | NONE | **`importance_weight: float \| None = 0.5`** and **`feedback_weight: float = 0.5`** | ingest default, then **rewritten by a batch "memify" task** from session QA feedback | **strictly mutable**: `w ← w + α(rating − w)` | NONE |
| **Emotional RAG** (§5.1) | **YES — `emotion_q` / `emotion_m^k`, 8-dim Plutchik, int 1–10** | n/a (the vector *is* the score) | at ingest, by GPT-3.5 scoring prompt | not re-scored on recall | NONE |
| **Sentipolis** (§5.3) | **YES — "PAD-derived emotion tags" on events and reflections** | `s(t)` = PAD triple | at ingest (fast) + on reflection (slow) | PAD decays / is updated | **YES** — emotion, `T½ = 120 min` |
| **DAM-LLM** (arXiv:2510.27418) | **YES — field `sentiment_profile`**: "Confidence scores for positive, negative, and neutral polarities", + `object_type`/`aspect`/entropy `H` | entropy `H` | at ingest by LLM | entropy drives compression (H<0.8 mature, H>1.4 pruned) | NONE, but entropy gates retention |

**The verified bottom line across all of these:** only **Emotional RAG**, **Sentipolis** and **DAM-LLM** store an explicit affect field, and only the first two use it in the retrieval score. Everything else is text + tags + a single scalar importance. Further explicit-affect records found in the wider literature: **MemEmo** (arXiv:2602.23944 — HUMAINE, **49 emotion categories** + polarities + 3 intensity levels; label `e_t` with `A_attr = ⟨Sub, Obj, Cause, Int⟩`), **MADial-Bench** (arXiv:2409.15240 — record columns literally `Time | Emotion | Scene | Event`, with emotion used to *trigger* proactive recall), **Human-Like Lifelong Memory** (arXiv:2603.29023 — a 2-dim (valence, arousal) "valence vector" inside a 5-part node vector), and **Memory Bear** (arXiv:2512.20651 — "emotional weight"; **[non-peer-reviewed, treat as weak evidence]**). **ES-MemEval** (arXiv:2602.01885) annotates an "emotion category" but **does not use it for retrieval** (bge-m3 top-4 sessions only) — a useful reminder that annotating emotion and *using* it are different claims.

### 2.1 A-Mem (agentic memory / Zettelkasten) — arXiv:2502.12110

Paper field set (Eq. 1, §3.1, https://ar5iv.labs.arxiv.org/html/2502.12110):

> `m_i = {c_i, t_i, K_i, G_i, X_i, e_i, L_i}` — "c_i represents the original interaction content, t_i is the timestamp of the interaction, K_i denotes LLM-generated keywords ..., G_i contains LLM-generated tags ..., X_i represents the LLM-generated contextual description ..., and L_i maintains the set of linked memories". Eq. 3: `e_i = f_enc[concat(c_i, K_i, G_i, X_i)]`.

Production code, `agentic_memory/memory_system.py` `class MemoryNote.__init__`
(https://github.com/WujiangXu/A-mem-sys/blob/main/agentic_memory/memory_system.py):

```
content, id=None, keywords=None, links=None, retrieval_count=None, timestamp=None,
last_accessed=None, context=None, evolution_history=None, category=None, tags=None
```

Defaults: `links = links or []` (a list, not a dict), `context = context or "General"`, `category = category or "Uncategorized"`, `timestamp = last_accessed = datetime.now().strftime("%Y%m%d%H%M")`, `retrieval_count = 0`, `evolution_history = []`. **There is no `embedding` attribute on the note** (the vector lives in the retriever). The Chroma payload is exactly: `id, content, keywords, links, retrieval_count, timestamp, last_accessed, context, evolution_history, category, tags`.

The field-defining prompt (`analyze_content`, verbatim):

```
Generate a structured analysis of the following content by:
  1. Identifying the most salient keywords (focus on nouns, verbs, and key concepts)
  2. Extracting core themes and contextual elements
  3. Creating relevant categorical tags

Format the response as a JSON object:
{
  "keywords": [ ... "Order from most to least important" ... ],
  "context": // one sentence summarizing: - Main topic/domain - Key arguments/points - Intended audience/purpose,
  "tags": [ ... "Include domain, format, and type tags" ... ]
}
```

**Answer to your question: A-Mem carries only text + keywords + tags + context + category + timestamps + links. No emotion, no valence, no arousal, no importance, no salience.** The `importance_score` field exists only in the older benchmark repo `WujiangXu/A-mem` (`memory_layer.py`, `self.importance_score = importance_score or 1.0`) and is dead: never emitted, never read by `SimpleEmbeddingRetriever.search` (raw cosine only), never decayed. A-mem-sys deleted it.

Its distinctive mechanism is **memory evolution**, whose LLM returns exactly:
`{"should_evolve": bool, "actions": [...], "suggested_connections": [...], "tags_to_update": [...], "new_context_neighborhood": [...], "new_tags_neighborhood": [[...]]}`. It rewrites neighbours' `context` and `tags` only (`neighbor_memory.tags = new_tags_neighborhood[i]`). A good independent caveat: "**memory evolution** is dangerous without explicit version history; link decisions are LLM-driven and can hallucinate structure" (https://github.com/lhl/agentic-memory/blob/main/ANALYSIS-arxiv-2502.12110-a-mem.md).

### 2.2 MemGPT / Letta — arXiv:2310.08560

**No affect, and — contrary to a common belief — no importance prompt either.** A full-text grep of the paper for `importance|emotion|sentiment|valence|arousal|decay|poignan` returns **0 matches**. The 1–10 poignancy scheme people remember from "MemGPT" is Park et al., cited only in Related Work.

The tier definitions are prompt text in `letta/prompts/system_prompts/memgpt_chat.py` (v0.16.8,
https://github.com/letta-ai/letta/blob/0.16.8/letta/prompts/system_prompts/memgpt_chat.py), verbatim:

> "**Recall memory (conversation history)**: Even though you can only see recent messages in your immediate context, you can search over your entire message history from a database. ... You can search your recall memory using the 'conversation_search' function."
> "**Core memory (limited size)**: Your core memory unit is held inside the initial system instructions file, and is always available in-context ... Persona Sub-Block: Stores details about your current persona ... Human Sub-Block: Stores key details about the person you are conversing with ... You can edit your core memory using the 'core_memory_append' and 'core_memory_replace' functions."
> "**Archival memory (infinite size)**: Your archival memory is infinite size, but is held outside your immediate context ... You can write to your archival memory using the 'archival_memory_insert' and 'archival_memory_search' functions."

Schemas (`letta/schemas/block.py`, https://github.com/letta-ai/letta/blob/0.16.8/letta/schemas/block.py):

```python
class Block(BaseBlock):
    value: str
    limit: int = CORE_MEMORY_BLOCK_CHAR_LIMIT
    label: Optional[str]   # "Label of the block (e.g. 'human', 'persona') in the context window."
    description: Optional[str]
    metadata: Optional[dict] = {}
    read_only: bool = False
    hidden: Optional[bool] = None
    tags: Optional[List[str]] = []
```

`letta/schemas/passage.py` (archival): `text`, `embedding`, `embedding_config`, `created_at`, `is_deleted`, `organization_id`, `archive_id`, `source_id`/`folder_id`, `file_id`, `file_name`, `metadata`, `tags`.

**Practical takeaway for a game engine: Letta's `Block.metadata` and `Passage.metadata` are untyped dicts — they are the sanctioned place to hang `{valence, arousal, mood, importance}` without fighting the schema.** Also note the only time-like mechanism is *context eviction*, not decay: at the *warning token count* (~70%) MemGPT injects memory pressure; at *flush token count* (~100%) "the queue manager evicts a specific count of messages (e.g., 50% of the context window), generates a new recursive summary".

### 2.3 Mem0 — arXiv:2504.19413

`mem0/configs/prompts.py` (https://github.com/mem0ai/mem0/blob/main/mem0/configs/prompts.py). Extraction (v1) returns only `{"facts": ["Name is John", "Is a Software engineer"]}` — "The response should be in json with a key as 'facts' and corresponding value will be a list of strings." v3's `ADDITIVE_EXTRACTION_PROMPT` returns:

```
{"memory": [
  {"id": "0", "text": "...", "attributed_to": "user", "linked_memory_ids": ["uuid-of-related-existing-memory"]},
  {"id": "1", "text": "...", "attributed_to": "assistant"}
]}
```
with `text` specified as "A contextually rich, self-contained factual statement (**15-80 words**)".

Consolidation (`DEFAULT_UPDATE_MEMORY_PROMPT`):
> "You are a smart memory manager which controls the memory of a system. You can perform four operations: (1) add into the memory, (2) update the memory, (3) delete from the memory, and (4) no change."
> `{"memory" : [{"id": "...", "text": "...", "event": "<ADD|UPDATE|DELETE|NONE>", "old_memory" : "..."}]}`

Stored record (`mem0/configs/base.py` `MemoryItem`): `id`, `memory`, `hash`, `metadata: Optional[Dict[str, Any]]`, `score`, `created_at`, `updated_at`. The vector payload adds `data`, `hash = hashlib.md5(data.encode()).hexdigest()`, `text_lemmatized`, scope keys `user_id/agent_id/run_id/actor_id`, optional `expiration_date`.

**Emotion verdict:** grep of the full 64 KB `prompts.py` and `memory/main.py` → `importance` = 0 hits, `sentiment`/`valence` = 0 hits. `emotion` appears only as instructed **text content**:

> "Preserve the FULL meaning including emotional reactions, motivations, and subjective experiences... KEEP: - Emotional states: 'scared but reassured', 'happy and thankful', 'liberated and empowered'"

**Decay verdict:** none in OSS; it is platform-gated. `mem0/memory/notices.py`: `DECAY_FEATURE_ERROR_MESSAGE = "The decay parameter is not supported by the OSS Memory SDK."`

### 2.4 Zep / Graphiti — arXiv:2501.13956

`graphiti_core/nodes.py` (https://github.com/getzep/graphiti/blob/main/graphiti_core/nodes.py):

```python
class Node(BaseModel, ABC):
    uuid: str; name: str; group_id: str; labels: list[str]; created_at: datetime
class EpisodicNode(Node):
    source: EpisodeType; source_description: str; content: str
    valid_at: datetime          # "datetime of when the original document was created"
    entity_edges: list[str]
    episode_metadata: dict[str, Any] | None   # "customer-defined metadata key-value pairs for filtering"
class EntityNode(Node):
    name_embedding: list[float] | None
    summary: str                # "regional summary of surrounding edges"
    attributes: dict[str, Any] = Field(default={},
        description='Additional attributes of the node. Dependent on node labels')
```

`graphiti_core/edges.py`:

```python
class EntityEdge(Edge):
    name: str            # "name of the edge, relation name"
    fact: str            # "fact representing the edge and nodes that it connects"
    fact_embedding: list[float] | None
    episodes: list[str]
    expired_at: datetime | None   # "datetime of when the node was invalidated"  [sic — it is on an edge]
    valid_at: datetime | None     # "datetime of when the fact became true"
    invalid_at: datetime | None   # "datetime of when the fact stopped being true"
    reference_time: datetime
    attributes: dict[str, Any]
```

Bitemporal semantics (paper §2.2.3, https://arxiv.org/html/2501.13956v1), verbatim:

> "the system tracks four timestamps: t′created and t′expired ∈ T′ monitor when facts are created or invalidated in the system, while tvalid and tinvalid ∈ T track the temporal range during which facts held true. **These temporal data points are stored on edges** alongside other fact information."
> "When the system identifies temporally overlapping contradictions, it **invalidates the affected edges by setting their tinvalid to the tvalid of the invalidating edge**."

**Affect verdict: NONE** — and no importance/strength score either. But Graphiti ships the cleanest extension point of any system here: `attributes` is declared "Dependent on node labels" / "...of edge name", `EntityNode.save()` merges it (`for k, v in (self.attributes or {}).items(): if k not in entity_data: entity_data[k] = v`), and `get_entity_node_from_record()` strips only seven reserved keys (`uuid, name, group_id, name_embedding, summary, created_at, labels`). So `{"valence": -0.6, "arousal": 0.8, "importance": 0.9}` round-trips on Neo4j/FalkorDB/Neptune. **Decay: none** — time acts only as *logical invalidation*; episodes are kept non-lossy.

### 2.5 LangMem

Docs (https://langchain-ai.github.io/langmem/concepts/conceptual_guide/) define Semantic (Collection vs Profile), Episodic ("observation/thoughts/action/result"), Procedural. The default record schema is `schemas: Sequence[S] = (Memory,)`, and a run yields e.g. `ExtractedMemory(id="27e9…", content=Memory(content="[IMPORTANT] User prefers to be called Lex…"))`.

**No numeric importance or sentiment field exists.** The docs state the *principle* and implement nothing:

> "Finally, memory relevance is more than just semantic similarity. **Recall should combine similarity with 'importance' of the memory, as well as the memory's 'strength', which is a function of how recently/frequently it was used.**"

Importance is instead encoded as **inline text tags inside `content`** (`[IMPORTANT]`, `[BACKGROUND]`, `[HOBBY]`, `[PERSONALITY]`) driven by a developer instruction such as `instructions="Extract all noteworthy facts, events, and relationships. Indicate their importance."` Deletion returns `RemoveDoc(json_doc_id=...)`, and the docs explicitly say the caller defines semantics: "you can control what 'removal' means, be that a soft or hard delete, or simply a **down-weighting** of the memory."

LangGraph store (`libs/checkpoint/langgraph/store/base/__init__.py`): `Item(value: dict[str, Any], key, namespace: tuple[str, ...], created_at, updated_at)`; `SearchItem` adds `score: float | None`; `put(namespace, key, value, index=None, ttl=None)` where `ttl` is "Time to live in minutes ... refreshes on both read operations ... and write operations" and `supports_ttl = False` by default. **No decay constant.**

### 2.6 Cognee

`cognee/infrastructure/engine/models/DataPoint.py` (https://github.com/topoteretes/cognee/blob/main/cognee/infrastructure/engine/models/DataPoint.py):

```python
id: UUID                     # deterministic uuid5(NAMESPACE_OID, f"{cls.__name__}:{joined}") via identity_fields
created_at: int; updated_at: int        # ms epoch
ontology_valid: bool = False
ontology_uri: str | None
version: int = 1
topological_rank: int | None = 0
valid_to: int | None = None   # "Bi-temporal validity: ms epoch when this fact was superseded
                              #  (via close_node); None = still current. Not the same as
                              #  Event/Interval time_to (when an event occurred)."
metadata: MetaData = {"index_fields": []}
type: str
belongs_to_set: "list[DataPoint] | list[str] | None"
source_pipeline / source_task / source_node_set / source_user / source_content_hash
feedback_weight: float = 0.5
importance_weight: float | None = 0.5
```

This is the **only system surveyed with an explicit numeric `importance_weight`**. It is mutable, and the writer is a *batch* task, not the summarizer — `cognee/tasks/memify/apply_feedback_weights.py`:

```python
def normalize_feedback_score(feedback_score: int) -> float:
    """Map feedback score 1..5 to 0..1."""
    return (feedback_score - 1) / 4

def stream_update_weight(previous_weight, normalized_rating, alpha):
    updated = float(previous_weight) + alpha * (normalized_rating - float(previous_weight))
    final_score = max(0.0, min(1.0, float(updated)))
    return round(final_score, FEEDBACK_WEIGHT_DECIMALS)   # = 4

async def apply_feedback_weights(data, alpha: float = 0.1):
```

i.e. `w ← w + α(r − w)`, α = 0.1, clip [0,1]. It updates the graph nodes/edges that *answered* a session QA (`used_graph_element_ids={"node_ids": [...], "edge_ids": [...]}`), is idempotent per QA, and the integration test pins the arithmetic: 0.5 + 0.1·(1−0.5) = **0.55**. **No emotion field; no time decay** (only `valid_to` supersession).

---

## 3. Cognitive-architecture and affective-computing memory models

### 3.1 ACT-R: base-level activation, and why emotion is *absent* from it

Primary source used: Brasoveanu, *Intro to the ACT-R subsymbolic level for declarative memory* (2015) — https://people.ucsc.edu/~abrsvn/ACT-R_subsymbolic_3.pdf

**Activation equation** (eq. 1), verbatim:

> `A_i = B_i + Σ_j∈C W_j S_ji` — "for a chunk i and elements j that are part of the current goal chunk."

**Base-level learning equation** (eq. 2), verbatim:

> `B_i = log( Σ_{k=1..n} t_k^(−d) ) = log( Σ_{k=1..n} 1 / t_k^d )` — "**since usually d = 0.5**, where t_k is the time since the k-th practice/access of chunk i."

Three encoded properties (eq. 9, quoting Anderson & Schooler 1991 p. 407 and Anderson et al. 2004 p. 1042), verbatim:
> "a. the strength of a memory trace provides an encoding of its **need odds** — memory performance (base-level activation tracks log odds);
> b. the strengths from individual presentations **sum** to produce a total strength ...;
> c. strengths of individual presentations **decay as a power function of the time** (the fact that the impact on odds of an individual presentation decays as a power function produces the **power law of forgetting**)."

**Attentional weighting** (eq. 11): `W_j = W/n` — "W is usually set to 1, so the attention weights are usually 1/n, where n is the number of sources of activation/terms."

**Associative strength** (eq. 12): `S_ji ≈ log( prob(i|j) / prob(i) )`, "usually set to `S − log(fan_j)`, where fan_j is the number of facts associated with term j. **S is usually set to 2.**"

**Retrieval probability and latency** (eqs. 13–15), verbatim:

> `P_i = 1 / (1 + e^(−(A_i − t)/s))` — "where s is the noise parameter and is typically set at about **0.4**, and t the retrieval threshold."
> `T_i = F e^(−A_i)` — "where F is the latency factor."
> `F ≈ 0.35 e^t` — "i.e., the retrieval latency at threshold (when A_i = t) is approximately **0.35 seconds**."

**Partial matching — [UNVERIFIED in the source I could open].** The canonical ACT-R form is `A_i = B_i + Σ_j W_j S_ji + Σ_l P M_li` with mismatch penalty `P · (1 − M_li)` per mismatching slot, `P ≈ 1`, `M_li = sim(v_l, d_l) ∈ [−1,1]` — but the Brasoveanu notes cover only the activation / base-level / associative / probability / latency chain, not the PM term. Do not treat the PM constants as sourced here.

**How does ACT-R handle *emotional* salience? It does not.** There is no affect term in `A_i`. Emotional salience can only enter ACT-R via (a) a higher `B_i` from more/frequent encoding (arousal → more rehearsals), or (b) an extra `+Σ W_j S_ji` associative source. This is precisely why the affective-memory implementations below bolt a **separate** arousal-modulated consolidation multiplier onto the power law rather than modifying `B_i` — see §3.3.

### 3.2 Arousal vs valence as SEPARATE axes; amygdala modulation; Yerkes–Dodson

- **Separate axes is the consensus operational model.** The NRC-VAD lexicon page states the standard framing verbatim: "Several influential factor analysis studies have shown that the primary dimensions of word meaning are valence, arousal, and dominance (VAD) (Osgood et al., 1957; Russell, 1980, 2003)" — "valence is the positive–negative or pleasure–displeasure dimension; arousal is the excited–calm or active–passive dimension; and dominance is the powerful–weak or 'have full control'–'have no control' dimension." (https://saifmohammad.com/WebPages/nrc-vad.html)
- **Two routes to emotional memory** — the canonical citation for valence and arousal recruiting distinguishable neural routes is Kensinger & Corkin, *Two routes to emotional memory: Distinct neural processes for valence and arousal*, PNAS 101(9):3310–3315 — https://www.pnas.org/doi/abs/10.1073/pnas.0306408101 **[UNVERIFIED — abstract page only; I did not open the full text, so I quote no numbers from it]**.
- **Amygdala modulation account (McGaugh / Cahill & McGaugh).** There is **no explicit memory-strength equation** in this literature in any form I could open. The `emotional-memory` project cites it as the *justification* for its parabola (§3.3) with the docstring reference "(McGaugh 2004; Yerkes & Dodson 1908)", but the formula is the implementer's, not McGaugh's.
- **Yerkes–Dodson inverted U.** Also not formalised in the source literature I could reach. Notably, Mather et al. (2016, *Behav Brain Sci* 39:e228, https://pmc.ncbi.nlm.nih.gov/articles/PMC5780186/) list "**Inverted-U curve**" in their Table R2 as an **open** item: "A direct examination of inverted-U curve effects with NE would be of interest. It is not clear if the functional shift seen at high levels of arousal is uniquely, or even critically, due to high NE levels..." So **[UNVERIFIED as a canonical equation]** — the only explicit inverted-U formula I found is the implementation below.
- **Arousal-biased competition (Mather & Sutherland 2011)** — https://pmc.ncbi.nlm.nih.gov/articles/PMC3110019/. Verbatim: "Arousal **amplifies the effects of competition**, improving perception of high priority information and weakening perception of low priority information." **The paper contains no equation**; it explicitly delegates the formula: "a computational model can quantify how surprising each location on a feature map is by comparing beliefs about what is likely to be in that location before and after seeing the information (Baldi & Itti, 2010)."

### 3.3 The one explicit arousal→memory-strength formula that exists (and it is an implementation)

`github.com/gianlucamazza/emotional-memory`, `src/emotional_memory/appraisal.py`
(https://github.com/gianlucamazza/emotional-memory/blob/main/src/emotional_memory/appraisal.py), verbatim:

```python
def consolidation_strength(arousal: float, mood_arousal: float) -> float:
    """Arousal-modulated consolidation strength (Yerkes-Dodson inverted-U).

    Effective arousal blends encoding arousal (70%) with background
    mood arousal (30%). Peak consolidation near effective_arousal=0.7.

    A floor of 0.1 ensures even calm, mundane memories have a minimum
    consolidation chance — otherwise events with effective_arousal < 0.2
    would get zero strength and be immediately prunable.

    Returns a value in [0.1, 1.0].
    """
    effective = 0.7 * max(0.0, min(1.0, arousal)) + 0.3 * max(0.0, min(1.0, mood_arousal))
    # Inverted parabola with peak=1.0 at x=0.7
    raw = -4.0 * (effective - 0.7) ** 2 + 1.0
    return max(0.1, min(1.0, raw))
```

i.e.

```
A_eff = 0.7·clamp(A_encode,0,1) + 0.3·clamp(A_mood,0,1)
S     = clamp( 1 − 4·(A_eff − 0.7)² , 0.1, 1.0 )
```

Peak `S = 1.0` at `A_eff = 0.7`; `S = 0.1` floor. A fidelity test pins the shape: "the peak (effective=0.7) is reached at enc_arousal ≈ 0.571 — safely in the interior" (https://github.com/gianlucamazza/emotional-memory/blob/v0.11.1/benchmarks/fidelity/test_yerkes_dodson.py).

**Arousal → decay rate**, `src/emotional_memory/decay.py`
(https://github.com/gianlucamazza/emotional-memory/blob/main/src/emotional_memory/decay.py), verbatim formula block:

```
effective_decay = base_decay
                  * (1 - arousal_modulation * arousal_at_encoding)
                  * (1 / (1 + retrieval_boost * retrieval_count))

strength(t) = initial_strength * elapsed_seconds ^ (-effective_decay * power)
strength(t) = max(strength(t), min(floor, initial))   # if arousal > threshold
```

with `DecayConfig` defaults, verbatim: `base_decay = 0.5` ("Power-law decay exponent baseline. Higher = faster decay."), `arousal_modulation = 0.5` ("How much high arousal slows decay. 0 = no effect, 1 = fully suppressed at max arousal."), `retrieval_boost = 0.1` ("Reduction in decay exponent per retrieval (spacing effect)."), `floor_arousal_threshold = 0.7`, `floor_value = 0.1`, `min_seconds = 1.0`, `power = 1.0`.

It is honest about its own deviation from ACT-R, verbatim:
> "Note: the spacing effect here attenuates the decay *exponent* per retrieval (`1 / (1 + retrieval_boost * retrieval_count)`) rather than summing per-trace power-law activations as in canonical ACT-R (`B = ln Σ tⱼ^(-d)`). The direction matches ACT-R (more retrievals → slower forgetting); the functional form is a tractable operationalization, not the trace-sum model."

**This is the single most copyable equation pair in this whole report: an inverted-U consolidation weight (`S`) times a power-law retention (`t^(−d_eff)`) with arousal and rehearsal both attenuating the exponent.**

### 3.4 Bayesian surprise — the exact formula

Itti & Baldi, *Bayesian Surprise Attracts Human Attention*, NIPS 2005 — http://papers.nips.cc/paper/2822-bayesian-surprise-attracts-human-attention.pdf (journal version: Vision Research 49(10):1295–1306, https://pubmed.ncbi.nlm.nih.gov/18834898/). Verbatim:

> `P(M|D) = [ P(D|M) / P(D) ] · P(M)`
> `S(D, M) = KL( P(M|D), P(M) ) = ∫_M P(M|D) · log[ P(M|D) / P(M) ] dM`
> "Therefore we formally measure surprise elicited by data as some distance measure between the posterior and prior distributions. This is best done using the relative entropy or Kullback-Leibler (KL) divergence. Thus, **surprise is defined by the average of the log-odd ratio**."
> "A unit of surprise — a 'wow' — may then be defined for a single model M as the amount of surprise corresponding to a two-fold variation between P(M|D) and P(M), i.e., as log P(M|D)/P(M) (with log taken in base 2)."

Crucially for the "baseline vs deviation" question, the paper already contains the anti-outlier caveat:

> "Although D is a strong outlier, it carries very little information regarding whether M or M′ is the better model, and therefore very little surprise. Thus **an outlier detection method would strongly focus attentional resources onto D, although D is a false positive.**"

Empirical scale (verbatim): "Over **72%** of all human saccades were targeted to locations predicted to be more surprising than on average. When only considering saccades where two, three, or four observers agreed on a common gaze target, this figure rose to **76%, 80%, and 84%**"; surprise scored "nearly **20% better** than the second-best metric (saliency) and **60%** better than the best static metric (entropy)", p < 10⁻¹⁰⁰.

**Related prediction-error formulas (all verified):**

| Model | Formula | URL |
|---|---|---|
| Shannon surprisal | `−log p(x)` — "information content is defined by the negative of the logarithm of probability" | Yanagisawa 2021, https://www.frontiersin.org/journals/computational-neuroscience/articles/10.3389/fncom.2021.698252/full |
| Free-energy (Gaussian) | `F_n = G_n + U_n = A_F δ² + B_F`, with `δ := x̄ − η` = "prediction error, which represents the difference between the prior mean and the likelihood peak"; `A_F := (1/2)·n/(n s_p + s_l)` | Yanagisawa 2021, eqs. 24–26, https://www.frontiersin.org/journals/computational-neuroscience/articles/10.3389/fncom.2021.698252/xml |
| Variational novelty/exploration | `Q(π\|s_t) = −D_KL[ P(s_T \| s_t, π) ‖ P(s_T \| m) ]` = `−H[P(s_T\|s_t,π)] + E[ln P(s_T\|m)]` | Schwartenbeck et al. 2013, https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2013.00710/full |
| Surprise reward shaping | `r'(s,a,s') = r + η( log P_{φ_t}(s'\|s,a) − log P_{φ_{t−k}}(s'\|s,a) )` | Achiam & Sastry, arXiv:1703.01732, https://ar5iv.labs.arxiv.org/html/1703.01732 |
| Plain prediction-error baseline | `r_+(s,a,s') = ‖ s' − μ_φ(s,a) ‖₂` | ibid. eq. 12 |

The Yanagisawa model is especially interesting because **the person-specific knob is the prior variance `s_p`**: "The model prediction of the predictability effect explains how **personal knowledge and experience as factors of prior uncertainty** change the optimal arousal potential (a peak of the Wundt curve)." That is the closest thing in the verified literature to a *personalised* inverted-U.

### 3.5 Flashbulb memory

Brown & Kulik's definition, quoted verbatim in Sharot et al. 2007: memories "for the circumstance in which one first learned of a very surprising and consequential event", "which contain a subset of six canonical features: **place, ongoing activity, informant, own affect, other affect, and aftermath**" (page 73 of ref. 1) — https://pmc.ncbi.nlm.nih.gov/articles/PMC1713166/

The same paper's *deflationary* findings, verbatim: "like normal memories, **flashbulb memories are susceptible to forgetting**, perhaps **at the same rate as other memories**"; "The only characteristic of flashbulb memories that has yet to be challenged is the **vividness** of the memory"; "for longer retention intervals (≈3 years), **emotional involvement** rather than rehearsal predicts the enhancement in accuracy". Numbers: 24 participants ~3 years post-9/11; Downtown group (n=12) mean 2.08 mi from WTC (SD 1.16) vs Midtown (n=10) 4.53 mi (SD 3), t(19)=2.5, P<0.025; distance ↔ recollective-experience enhancement **r = −0.67, P<0.05**; **83%** of Downtown vs **40%** of Midtown showed higher left-amygdala activation; **41%** of Downtown vs **0%** of Midtown mentioned direct personal threat.

**Engine lesson: don't build a "flashbulb" special case. The literature says the *vividness* is special, not the retention curve.** No decay-constant fit exists in this paper.

### 3.6 Peak–end rule: how the PEAK (not the mean) is computed

The modern computational form is **explicit local-extremum detection + softmax attention**, not a hand-tuned `peak + 0.5·end`. Li et al., *Peak-End-Net*, arXiv:2607.13941 — https://ar5iv.labs.arxiv.org/html/2607.13941. Verbatim:

> **Definition 1 (Peak and Valley)**: frame t is a PEAK if `s_t > s_(t−1)` and `s_t > s_(t+1)`; a VALLEY if `s_t < s_(t−1)` and `s_t < s_(t+1)`.
> `r^peak_t = ReLU(s_t − s_(t−1)) · ReLU(s_t − s_(t+1)) · s_t`
> `r^valley_t = ReLU(s_(t−1) − s_t) · ReLU(s_(t+1) − s_t) · (1 − s_t)`
> `r^end_t = exp(−λ d_t) · s_t`, where `d_t = (T − t)/T` and `λ = T/K`
> `r_t = σ(r_base) + α·r^peak_t + β·r^valley_t + γ·r^end_t` (α, β, γ learnable)
> `f_video = Σ_t w_t f_t`, with `w_t = exp(r_t) / Σ_j exp(r_j)`

> "By construction, peak and valley are mutually exclusive. **The product of the left and right difference terms amplifies local trends, thereby suppressing trivial fluctuations and highlighting clear local extrema.**"
> "To account for the end effect of the peak-end rule, we assign larger weights to frames closer to the end... we adopt an exponentially decaying function."

**The three-zero-derivative / "local maximum" convention is the Kolmogorov-style peak convention you asked about: a sample is a peak iff it strictly exceeds both neighbours.** The `ReLU(ΔL)·ReLU(ΔR)` product form means an interior local max with a *tiny* rise and a *huge* fall is scored `tiny × huge` — i.e. the score is the **geometric mean of rise and fall**, which is exactly the "distinctive, not merely high" behaviour you want.

**Warning from RL, with numbers.** Veselý et al., *Trace-Mediated Peak Bias*, arXiv:2606.04735 — https://ar5iv.labs.arxiv.org/html/2606.04735. In a Two-Door MDP with `τ_steady: r_t = 2 for t ∈ [1,10]` vs `τ_peak: r_3 = 10, r_10 = 6, 0 elsewhere`, γ = 0.95: `V*(S_0|τ_steady) ≈ 16.05` but `V*(S_0|τ_peak) ≈ 12.81` — yet agents *prefer* the peak trajectory. Verbatim: "**At intermediate eligibility trace depths, agents irrationally prefer trajectories with high-magnitude reward 'peaks' over alternatives with higher cumulative returns.** This provides a mechanistic account of the Peak-End Rule" and "The sub-optimal preference for the Peak trajectory is most acute at intermediate trace depths (**0.15 < λ < 0.50**)". **Use this as your quantitative justification for keeping a *mean* term alongside any peak term.**

**[UNVERIFIED]** I found no published closed form for the classic `(peak + end)/2` or PEAK/SM "serial memory" models; the Kahneman cold-pressor "69% chose to repeat" figure is also unverified (primary paper paywalled). Do not quote those.

### 3.7 Characteristic vs distinctive expression: display rules, Duchenne, masking

- **Display rules.** "[We] coined the phrase **display rule** to refer to the conventions, norms, and habits that develop regarding the management of emotio[n]…" — Ekman & Friesen, indexed from Ekman's own chapter PDF (http://www.paulekman.com/wp-content/uploads/2013/07/Biological-And-Cultural-Contributions-To-Body-And-Facial-Mov.pdf). The snippet is truncated and the PDF was not fetchable, so **treat the definition as [PARTIALLY VERIFIED]**. The canonical citation is Ekman & Friesen (1969), *Semiotica* 1:49–98.
- **Duchenne criteria — verified, verbatim** (Girard, Shandar, Liu, Cohn, Yin & Morency, ACII 2019, https://par.nsf.gov/biblio/10170565/media/xml):
  > "the **Duchenne smile is composed of the lip corner puller action unit (AU12) and the cheek raiser action unit (AU6)**. **All smiles involve AU12** ... but Duchenne smiles also involve AU6, which lifts the cheeks, narrows the eyes, and wrinkles the outer eye corners (hence the 'smiling eyes'). **Smiles without AU6 are called non-Duchenne smiles** and are hypothesized to be disconnected from genuine positive emotion (e.g., **false, miserable, or masking** negative emotion)."
- **The genuineness claim is empirically contested — and the numbers matter a lot for your design.** Same paper, verbatim: "the **Duchenne smile is likely an artifact of smile intensity** rather than a reliable and unique indicator of genuine positive emotion." Supporting figures: BP4D+, 136 participants, 751 smile events; **AU6–AU12 intensity r = 0.64**; controlling for AU12 intensity reduced the AU6→amusement effect by **64%** and the amusement→AU6 effect by **79%**; and Krumhuber & Manstead's test — "**rates of Duchenne and non-Duchenne smiles were very similar in both conditions** [amusing stimuli vs feigned amusement]. So, AU6 did not discriminate between felt and false smiles. **However, it did discriminate between weak and intense smiles**."
- **Timing is a better discriminator than co-occurrence.** Perusquía-Hernández et al., arXiv:2008.08791 — https://ar5iv.labs.arxiv.org/html/2008.08791, verbatim: "AU6 was active **before** AU12 **above 80% of the time in the spontaneous block; and above 60% of the time in the posed block**."
- **[UNVERIFIED / CONTRADICTED]** The widely repeated "only 10–20% of smiles are Duchenne" is **not supported** by the sources above (Girard et al. report Duchenne smiles "occur at high rates when participants feel negative emotion or feign positive emotion"; Perusquía-Hernández et al. measured ~90% AU6/AU12 co-occurrence). Do not build on that number.
- **[UNVERIFIED]** quantitative AU criteria for the "masking smile" (e.g. AU12+AU4), and any statistic for "habitual smile frequency per person".

---

## 4. Emotion taxonomies usable as a classification dimension

> **Verification status.** The numeric/label inventories below for **GoEmotions, Plutchik, PAD, Russell and NRC-VAD are verified** from the sources cited. **Ekman's exact label list, OCC's exact 22 tokens, EmoBank's annotation scale, Warriner et al.'s corpus details, and Russell's exact octant labels are marked [UNVERIFIED]** — those primary sources were paywalled or unreachable in this session, so I will not assert their counts. Where a *system* uses a taxonomy, that usage **is** verified and quoted.

### 4.0 GoEmotions — the full verified label set

Demszky, Movshovitz-Attias, Ko, Cowen, Nemade, Ravi, *GoEmotions: A Dataset of Fine-Grained Emotions*, ACL 2020, **arXiv:2005.00547** — https://ar5iv.labs.arxiv.org/html/2005.00547

Verbatim: "We introduce GoEmotions, the largest manually annotated dataset of **58k English Reddit comments, labeled for 27 emotion categories or Neutral**." Summary statistics table: "Number of examples 58,009 · **Number of emotions 27 + neutral** · Number of unique raters 82 · **Number of raters / example 3 or 5** · Number of labels per example: 1 → 83%, 2 → 15%, 3 → 2%, 4+ → .2%". "Most of the examples (83%) have a single emotion label... **The Neutral category makes up 26% of all emotion labels**". The label interface "Raters were free to select multiple emotions" → **multi-label**. Data + code: https://github.com/google-research/google-research/tree/master/goemotions

The 27 labels, recovered from the verified Table 3 grouping and the Table 1/§5.1 text, **grouped by the paper's own a-priori sentiment assignment**:

| positive (12) | negative (11) | ambiguous (4) |
|---|---|---|
| admiration, amusement, approval, caring, desire, excitement, gratitude, joy, love, optimism, pride, relief | anger, annoyance, disappointment, disapproval, disgust, embarrassment, fear, grief, nervousness, remorse, sadness | confusion, curiosity, realization, surprise |

The paper also publishes a free **Ekman-level collapse** of its own taxonomy, verbatim: "The Ekman level further divides the taxonomy using the Neutral label and the following 6 groups: **anger** (maps to: anger, annoyance, disapproval), **disgust** (maps to: disgust), **fear** (maps to: fear, nervousness), **joy** (all positive emotions), **sadness** (maps to: sadness, disappointment, embarrassment, grief, remorse) and **surprise** (all ambiguous emotions)." Baseline BERT F1: **.46** on the 27 labels, **.64** on the Ekman grouping, **.69** on sentiment.
**[UNVERIFIED]** GoEmotions' licence (the HF dataset card was unreachable) — check before shipping.

**Why this matters for a VN engine:** GoEmotions natively contains **`embarrassment`**, **`desire`** and **`curiosity`** — three of your eight keys (`embarrassed`, `strive`-adjacent, `expectant`-adjacent) that Ekman-6 and Plutchik-8 cannot express at all — plus `amusement` for `laugh` as distinct from `joy` for `smile`. Its published Ekman collapse means you can ship a 27-way tagger and still render a 6-way fallback. Its downside: it is a **text** taxonomy built from Reddit, so `serious`, `pensive` and `strive` have no label, and the emotional register is internet-comment, not visual-novel.

### 4.1 The taxonomy actually used by serious memory systems (this is the verified part)

| System | Taxonomy used | Representation | Scale |
|---|---|---|---|
| **Emotional RAG** (arXiv:2410.23041) | **Plutchik's 8** | 8-dim emotion vector | integer **1–10** per dimension |
| **Sentipolis** (arXiv:2601.18027) | **PAD (continuous)** → **Plutchik-style label** via KNN | 3-dim PAD + categorical label | PAD ∈ **[−1,1]³** |
| **emotional-memory** (Mazza) | **PAD** (Mehrabian/Russell) | `CoreAffect(valence, arousal, dominance)` | valence [−1,1], arousal [0,1], dominance [0,1] |
| **PsychoAgent** (arXiv:2608.07438) | scalar affect salience | `w_j ∈ [0,1]` per trace | [0,1] |
| **Generative Agents** | none | scalar `poignancy` | int 1–10 |
| A-Mem, MemGPT, Mem0, Zep, LangMem, Cognee | **none** | — | — |

**Emotional RAG** (Dong/Bai et al., ICKG 2024, https://ar5iv.labs.arxiv.org/html/2410.23041) — verbatim:
> "The output is an emotional vector of the query, which is an **8-dimensional vector containing 8 different emotional states, i.e., joy, acceptance, fear, surprise, sadness, disgust, anger, and anticipation**. The 8 emotional states are defined according to **the emotion circle in [Plutchik]**. **The value of each dimension is an integer between 1 and 10**, which measures the intensity of the emotional state."

**Sentipolis** — verbatim:
> "Each agent maintains a continuous emotion state in the **Pleasure-Arousal-Dominance (PAD)** space... where each dimension lies in **[−1,1]**."
> "we first perform **k-Nearest Neighbor (KNN) on real human PAD data points** to help the model interpret the semantic meaning of PAD values. Given the agent's current PAD coordinate, we retrieve the nearest human reference points and map the state to a **Plutchik-style emotional label**."

**Why the split?** The verified pattern is: **dimensional (PAD/VAD) for the stored state, categorical (Plutchik/Ekman) for the prompt.** Sentipolis states the reason verbatim: "Downstream LLM prompts [benefit] from human-interpretable emotion cues, so we translate the agent's continuous PAD state into a semantically meaningful emotion label and description... This process yields a categorical, human-readable anchor **rather than exposing the LLM to raw continuous numbers**." And separately: "Representation choice supports this interpretation: mapping continuous PAD coordinates to interpretable descriptors **makes emotion both controllable and contextually enactable**." This is exactly the two-layer architecture a VN engine wants: numbers for the engine, words for the LLM.

**PAD specifics (verified).** Mehrabian's three scales, verbatim from Sentipolis §3.2: "The **Pleasure-Displeasure Scale** measures how pleasant or unpleasant one feels about something. The **Arousal-Nonarousal Scale** measures how energized or soporific one feels. The **Dominance-Submissiveness Scale** represents how controlling versus controlled one feels [Mehrabian 1980]."

> **⚠ The PAD normaliser is convention-dependent — derive it, never copy it.** This is the one constant in the report where I found a genuine cross-source conflict, so treat it carefully:
>
> - `emotional-memory` uses **√6 ≈ 2.449**, and its source states the derivation explicitly, verbatim: *"Maximum Euclidean distance in the 3-D PAD space (single source of truth): valence [-1, 1] (range 2), arousal [0, 1] (range 1), dominance [0, 1] (range 1) => sqrt(2\*\*2 + 1\*\*2 + 1\*\*2) = sqrt(6) ~= 2.449. Any code normalising a CoreAffect.distance() into a [0, 1] similarity must use this value; a stale 2-D max (sqrt(5) ~= 2.236, pre-dominance) over-penalises..."* — with `CoreAffect` clamping `valence ∈ [−1,1]` and `arousal, dominance ∈ [0,1]` (`src/emotional_memory/affect.py`, https://github.com/gianlucamazza/emotional-memory/blob/main/src/emotional_memory/affect.py). **So √6 is correct for that package's asymmetric ranges.**
> - Sentipolis instead declares **all three axes on [−1,1]** ("where each dimension lies in [−1,1]"), for which the cube diagonal is **√12 = 2√3 ≈ 3.464**, not 2.449.
> - A third convention exists: "while pleasure and dominance take positive and negative values (between -1 and 1), **arousal is always positive (between 0 and 1)**" (Carbo & Molina, https://ar5iv.labs.arxiv.org/html/2401.14436) — which is `emotional-memory`'s convention, so **the split is a real lineage difference in the PAD literature, not an error in either source.**
>
> **Consequence for your engine:** if you normalise `similarity = max(0, 1 − dist/D_max)`, you must set `D_max` from *your own* axis ranges, or mood-congruence similarity silently miscalibrates. Fix your ranges once — recommended: **valence ∈ [−1,1], arousal ∈ [0,1], dominance ∈ [0,1] → D_max = √6 ≈ 2.449** — and make it a single named constant with the derivation in a comment, exactly as the reference implementation does. Do not carry a normaliser across codebases: a `D_max` imported from a [−1,1]³ system (√12 ≈ 3.464) would compress all similarity scores toward 1 and quietly flatten the mood-congruence signal. **[√6 is verified as that package's constant along with its derivation; it is NOT a universal PAD constant, and I found no source claiming it is one.]**

**The 8 PAD octants are verified — from a facial Action-Unit→PAD library, which is the most directly useful source in this whole section for a VN engine.**

**A published PAD→basic-emotion lookup table does exist** (Table 1, attributing Russell & Mehrabian 1977), verbatim values from https://ar5iv.labs.arxiv.org/html/2401.14436: joy (0.75, 0.48, 0.35); sad (−0.63, 0.27, −0.33); surprise (0.40, 0.67, −0.13); fearful (−0.64, 0.60, −0.43); angry (−0.51, 0.59, 0.25). The matching **nearest-emotion weighting formula** (Becker-Asano & Wachsmuth pattern), verbatim: `w_e = (1 − (d_e − Δ_e)/(φ_e − Δ_e))` — "where d_e stands for the distance between the current PAD 3d position of the agent and of each basic emotion, **Δ_e is the minimum threshold to activate an emotion** and **φ_e establishes the point of saturation**"; nearest = `argmin d_e`. **The per-emotion activation threshold `Δ_e` is worth stealing:** it lets `strive` require a genuine goal-pursuit configuration rather than firing on any high-arousal state, which is exactly the discrimination your key vocabulary needs.

**The octant names are the wrong vocabulary but the right geometry.** Mapping your keys onto the PAD octants: `smile`/`laugh` → **EXUBERANT** (and `laugh` vs `smile` = *distance from neutral*, which is the intensity distinction Ekman, GoEmotions and OCC all structurally cannot make); `depressed` → **BORED**; `serious` → **DISDAINFUL**; `embarrassed` → **ANXIOUS**; `expectant` → **DEPENDENT**; `strive` → **HOSTILE**. Every key lands in a distinct, semantically defensible region — **the mismatches are naming failures, not representational ones, so rename the octants to your VN keys rather than abandoning PAD.** The one genuine collision is `pensive` vs `depressed`, which both fall in the low-valence/low-arousal region; separate them on `dominance` or accept that `pensive` needs a non-affective (cognitive/register) tag.

**[UNVERIFIED]** Mehrabian's own range statement — Mehrabian 1996 (*Current Psychology* 14(4):261–292, DOI 10.1007/BF02686918) is paywalled, so the range conventions above are verified only through the two secondary sources cited.

**Plutchik (verified structurally).** From the Emotional RAG usage above, the 8 primary emotions are joy, acceptance/trust, fear, surprise, sadness, disgust, anger, anticipation — and the four **opposition axes** are joy–sadness, trust–disgust, fear–anger, anticipation–surprise. Verbatim: "**Intensity:** The cone's vertical dimension represents intensity – emotions intensify as they move from the outside to the center of the wheel… For example, anger at its least level of intensity is annoyance. At its highest level of intensity, anger becomes rage. Or, a feeling of boredom can intensify to loathing if left unchecked." (https://www.6seconds.org/2022/03/13/plutchik-wheel-emotions/) — so **Plutchik does have a structural intensity axis** (the cone's vertical dimension), which is why it is the only classical discrete taxonomy that can express `smile` (joy) vs `laugh` (high-intensity joy). Dyad rule, verbatim: "anticipation and joy combine to be optimism. Joy and trust combine to be love."
> **⚠ A naming trap that matters for you:** Plutchik's `pensiveness` is a **low-intensity sadness** label ("a little sad"), *not* "thoughtful". If your `pensive` art key means a reflective chin-stroke, adopting Plutchik's word would actively mislead annotators. Note also that the same secondary source uses both "acceptance" and "trust" for one primary — pick one token and freeze it.

**[PARTIALLY VERIFIED]** The full 24-term intensity table (serenity→joy→ecstasy; acceptance→trust→admiration; apprehension→fear→terror; distraction→surprise→amazement; pensiveness→sadness→grief; boredom→disgust→loathing; annoyance→anger→rage; interest→anticipation→vigilance) — only the `annoyance→anger→rage` and `boredom→loathing` tiers were quotable; the tier tables were behind CAPTCHA/403.

**NRC-VAD (verified, and the licence is the important part).** "The NRC Valence, Arousal, and Dominance (VAD) Lexicon includes a list of **more than 20,000 English words** and their valence, arousal, and dominance scores. For a given word and a dimension (V/A/D), **the scores range from 0 (lowest V/A/D) to 1 (highest V/A/D)**. The lexicon with its fine-grained real-valued scores was created by manual annotation using **Best–Worst Scaling**." Version 2.1 (March 2025) covers "over 55k English Terms" (arXiv:2503.23547); v1 is Mohammad, ACL 2018 ("20,000 English Words", https://aclanthology.org/P18-1017/). Machine-translated versions exist for 100+ languages (Google Translate, Aug 2022 — "some of the translations may still be incorrect or they may simply be transliterations").
**Licence — read this before shipping:** the download is labelled "**(Non-Commercial Use Only -- Research or Educational)**", and the Terms of Use state verbatim: "**No Redistribution:** Do not redistribute the data. Direct interested parties to the lexicon home page. You may not rent or license the use of the lexicon nor otherwise permit third party to use it." and "**Commercial License:** If interested in commercial use of the lexicon, contact the author." Terms are governed by Canadian NRC; the page also carries the notice "Copyright (C) 2011 National Research Council Canada (NRC)".
URL: https://saifmohammad.com/WebPages/nrc-vad.html

**[UNVERIFIED]** OCC's exhaustive 22-token list and its intensity *variables*; Sentipolis's enumerated Plutchik label list and literal field name; Ekman's exact label list **and its licence**; EmoBank's raw-vs-rescaled CSV values; Warriner et al.'s exact scale anchors and licence; Russell's exact 8 octant labels and his verbatim "distributed in a circular order" phrasing; the GoEmotions dataset-card licence. Sources for these were paywalled or unreachable in this session; see §9 for per-item reasons.

**Verified in this category (added in a second pass):**
- **Ekman is 7, not 6, in current usage.** Verbatim: "Dr. Ekman identified the six basic emotions as anger, surprise, disgust, enjoyment, fear, and sadness. His research shows the strongest evidence to date of a seventh emotion, which is contempt." (https://www.paulekman.com/universal-emotions/) Note the label drift: the classic six said **happiness**, the current site says **enjoyment**. **No numeric intensity axis.** The "Atlas of Emotions" is **not** a 5×5 grid — it is five "emotion continents", verifiably: "The Emotions Atlas is based on the consensus among scientists (in the choice of the five emotion continents…)" and "Each emotion names a number of related but different states. These states vary not only in their nature, but in **their intensity**." (http://atlasofemotions.org/)
- **OCC's trichotomy and count are confirmed verbatim**: "Ortony, Clore, and Collins [17] presented a cognitive structure of emotions which characterizes **22 emotion types** (e.g. joy, hope, disappointment, distress and fear). According to their 'OCC' theory, emotions are valenced reactions which can be turned on by **outcome of events, outcome of agents' actions, or attributes of objects**." (https://ar5iv.labs.arxiv.org/html/2105.05589) Structural conditions, verbatim: Joy = "pleased about a desirable consequence of event"; Distress = "displeased about an undesirable consequence of event"; **Hope = "pleased about the prospect of a desirable consequence of event"**; Fear = "displeased about the prospect of an undesirable consequence of event"; Satisfaction = "pleased about the confirmation of the prospect of a desirable consequence"; Disappointment = "displeased about the disconfirmation of the prospect of a desirable consequence". Bonus disambiguation, verbatim: "satisfaction is different… joy can be triggered whenever the agent becomes certain that the goal is achievable, although not fulfilled yet." **[UNVERIFIED]** the exhaustive 22-token list (only present as an image) — the standard decomposition sums to exactly 22 (joy, distress | happy-for, resentment, gloating, pity | hope, fear, satisfaction, fears-confirmed, relief, disappointment | pride, shame | admiration, reproach | gratification, remorse, gratitude, anger | love, hate → 2+4+6+2+2+4+2), but most of those tokens were not seen verbatim in-session. **[UNVERIFIED / likely wrong]** the common claim of "3 intensity variables": only a *global* variable **sense of reality** was verified ("The sense of reality variable is linked to the degree that an emotion-inducing situation seems real to an agent"), and the standard reading is **two** categories (global: sense of reality, proximity, unexpectedness, arousal; plus local per-type variables) — so treat "3" as unsourced.
- **EmoBank is 5-point, not 6-point**, and carries a two-perspective annotation your design should note. Verbatim: "a corpus of 10k English sentences balancing multiple genres, which we annotated with dimensional emotion metadata in the Valence-Arousal-Dominance (VAD) representation format" and "**We changed the 9-point SAM scales to 5-point scales**… in order to reduce the cognitive load" (https://ar5iv.labs.arxiv.org/html/2205.01996). Corpus: 10,548 raw → 10,062 filtered sentences; 5 annotators × 3 dims × **2 perspectives** = 30 ratings/sentence. Ranges [1,5], neutral 3. **Licence verified verbatim: "This work is licensed under CC-BY-SA 4.0"** (https://github.com/JULIELab/EmoBank) — ⚠️ **share-alike propagates to any derived lexicon you distribute.** Best used as training/eval data for your VAD regressor, not as a shipped artefact. Note the **reader-vs-writer perspective split** ("reader = what the player feels, writer = what the character feels") is exactly the distinction a VN needs, and the reader perspective was the better-annotated one.
- **Warriner et al. (2013) N = 13,915 English lemmas is confirmed** (https://link.springer.com/article/10.3758/s13428-012-0314-x); the 9-point scale is well-supported indirectly (EmoBank states its instructions follow the Warriner lexicon and that it downscaled "the 9-point SAM scales"), but the exact anchors and licence are **[UNVERIFIED]**.
- **NRC-VAD scale is `[0,1]`, not `[−1,1]`** — "the scores range from 0 (lowest V/A/D) to 1 (highest V/A/D)" — **so rescale with `2x − 1` before storing into a PAD triple whose valence is `[−1,1]`.** A silent off-by-rescale here would put your "neutral" at +0.5 valence.
- **The SAM manikins are copyrighted artwork** (Lang 1994; EmoBank needed granted access) — **do not ship them** in a UI even though the *scale* is free to use.

### 4.2 Which taxonomy to actually use, given the above

The verified evidence supports a **three-layer** choice, because no single taxonomy covers your vocabulary:

1. **Stored state → PAD (3 floats).** Only dimensional model that separates `embarrassed` (low dominance) from `strive` (+arousal, **+dominance**); the substrate for mood-congruent similarity by construction; what both production affect-memory systems use. Normaliser: `sqrt(6) ≈ 2.449`.
2. **LLM-visible label → Plutchik-8 + intensity tier** (verified as Emotional RAG's and Sentipolis's choice), because a discrete label is what the model can act on: "This process yields a categorical, human-readable anchor **rather than exposing the LLM to raw continuous numbers**."
3. **Text→affect scorer → GoEmotions-28 (or a VAD lexicon)** — GoEmotions covers `embarrassment`, `amusement`, `curiosity` and `desire`, which is closer to your key set than anything else off the shelf.
4. **Appraisal → inspiration from OCC**, because OCC is the only taxonomy in your list where `hope` (→`expectant`), `shame` (→`embarrassed`) and `pride`/`gratification` (→`strive`) are *structural conditions* rather than perception labels — which matters because your engine generates emotion from events, it does not classify it from faces. **OCC is also the only scheme in this entire section that models `strive` at all** ("pleased about the prospect of a desirable consequence of event" is goal-pursuit-with-uncertain-outcome as a first-class computational state), and its conditions are computable **from your existing `events.jsonl` stream with no extra annotation call**. **[UNVERIFIED]** the exhaustive 22-token list (see §4.1).

### 4.3 How well each taxonomy actually covers YOUR 8 keys (scored comparison)

Scores count keys the taxonomy can express *cleanly* (`smile`, `laugh`, `serious`, `pensive`, `embarrassed`, `depressed`, `expectant`, `strive`):

| Taxonomy | clean | which keys it gets | the keys it cannot express |
|---|---|---|---|
| **PAD (as named regions)** | **8/8 regions** | all 8 land in distinct octants (EXUBERANT / DISDAINFUL / ANXIOUS / DEPENDENT / BORED / HOSTILE) | only `pensive` collides with `depressed` |
| **GoEmotions 28** | 5/8 | `smile`=joy, `laugh`=amusement, `embarrassed`=**embarrassment** (literal), `depressed`=sadness+grief, `expectant`≈optimism/desire/curiosity | `pensive`, `strive`, and `serious` only via `disapproval` |
| **Plutchik + intensity** | 4/8 | `smile`=joy, `laugh`=ecstasy, `expectant`=anticipation, `pensive`=**pensiveness** (⚠️ means *mildly sad*) | `serious`, `embarrassed`, `strive`, `depressed` only via sadness |
| **OCC 22** | 4/8 | `expectant`=**hope** (exact), `strive`=hope+pride (**only scheme with it**), `depressed`=distress/disappointment, `smile`=joy | `laugh` (no intensity), `pensive`, and it has no face vocabulary at all |
| **Ekman 7** | 1/8 | `depressed`=sadness | everything else (no intensity axis → cannot split `smile`/`laugh`) |
| **Russell 2-D V×A** | ~6/8 regions | most keys as regions | cannot separate `expectant` from `strive` — both are +V/+A; **needs dominance** |
| **Word lexicons (EmoBank, Warriner, NRC-VAD)** | 0/8 as labels | — | wrong granularity; use only as the text→VAD *scorer*, never as the label set |

**The conclusion this table forces:** your 8 keys are **not a member of any published taxonomy** — they are a mix of affect (`smile`, `laugh`, `embarrassed`, `depressed`), register (`serious`, `pensive`), and *goal-state* (`expectant`, `strive`) labels. Two consequences:
- **`strive` is the key that breaks every borrowed scheme.** It is not an emotion in any of the eight; it is a goal-pursuit state, and `expectant`/`strive` are only separable on **dominance**. This is the strongest argument for PAD as the internal representation.
- **`laugh` vs `smile` is purely an intensity distinction**, which Ekman, GoEmotions and OCC structurally cannot make — only Plutchik's cone tiers and PAD's *distance from neutral* can. Since your engine already assigns one key per record, encode the tier explicitly (e.g. `joy:0.4` vs `joy:0.9`) rather than hoping a label carries it.

### 4.4 Mapping taxonomies onto a VN facial-expression key vocabulary
Target keys: `smile / laugh / serious / pensive / embarrassed / depressed / expectant / strive`.

| Taxonomy | smile | laugh | serious | pensive | embarrassed | depressed | expectant | strive | verdict |
|---|---|---|---|---|---|---|---|---|---|
| **GoEmotions** (verified, §4.0) | ✅ joy | ✅ **amusement** (distinct from joy) | ❌ | ❌ | ✅ **embarrassment** | ✅ sadness | ✅ curiosity (≈expectant) | ⚠️ desire/optimism; no dominance axis | **28 labels, multi-label, has a published Ekman collapse** — the best off-the-shelf *text* tagger for your vocabulary |
| **Ekman 6** (joy, sadness, fear, disgust, anger, surprise [+contempt]) | ✅ joy | ⚠️ joy (no intensity split) | ❌ | ❌ | ❌ | ⚠️ sadness | ❌ | ❌ | too coarse; 3/8 keys unrepresentable |
| **GoEmotions 28** (verified, see §4.0) | ✅ joy | ✅ **amusement** (distinct from joy) | ❌ | ❌ | ✅ **embarrassment** | ✅ sadness | ✅ **curiosity** | ⚠️ desire/optimism (no dominance) | **best off-the-shelf *text* tagger for your vocabulary**; ships a published Ekman collapse |
| **Plutchik 8 + intensity** | ✅ joy | ✅ joy-high (ecstasy) | ❌ | ⚠️ anticipation-low? | ❌ | ✅ sadness | ✅ anticipation | ✅ anticipation-high | **best discrete fit after OCC**; the intensity tier is what buys you `smile` vs `laugh` |
| **Russell circumplex (V×A)** | ✅ +V | ✅ +V, high A | ⚠️ −V/low A ≈ serious | ⚠️ low A, ~0 V | ⚠️ −V, high A (≈anxious; not embarrassment) | ✅ −V, low A | ✅ +V, high A | ❌ (striving is a *goal* state, not an affect) | **best dimensional fit; the natural home for all 8 keys as regions, and the natural substrate for mood-congruent recall** |
| **PAD (Mehrabian)** | ✅ +P | ✅ +P, +A | ⚠️ +D, −P | ⚠️ −A | ⚠️ −P, +A, **−D is the discriminator** | ✅ −P, −A | ✅ +P, +A, −D | ✅ **+A, +D, −P** (striving = high arousal + high dominance, valence-neutral/negative) | **the only taxonomy where `strive` and `embarrassed` are separable**: strive = high D, embarrassed = low D |
| **OCC 22** | ✅ joy | ✅ joy (intensity var) | ⚠️ reproach? | ⚠️ | ✅ **shame/embarrassment is a first-class type** | ✅ distress | ✅ **hope is a first-class type** | ✅ **hope + pride** | **the only taxonomy with native tokens for `embarrassed`, `expectant` and `strive`** — because OCC is a *cognitive-appraisal* taxonomy, not a perception taxonomy |
| **GoEmotions 27/28, EmoBank, Warriner, NRC-VAD** | text-only | | | | | | | | lexicons give you *word* VAD, not a *character's* state taxonomy — use as the text→VAD scorer, not as the label set |

**Recommendation from this table:** use **PAD as the stored state** (3 floats, cheap, supports mood-congruent similarity by construction, and — per §5 — is what the only two production affect-memory systems actually use), and use **Plutchik-8 + an intensity tier as the LLM-visible label** (verified as what Emotional RAG and Sentipolis do), with **OCC only as inspiration for the appraisal step** that produces PAD from an event (Sentipolis and the `emotional-memory` project both build their PAD from appraisal dimensions, not from a classifier).

---

## 5. Emotion-conditioned retrieval ("mood-congruent recall"): how it is actually implemented

### 5.1 The paper: Emotional RAG — the only published mood-congruent RAG I could verify

Huang, Lan, Sun, Shi, Bai, *Emotional RAG: Enhancing Role-Playing Agents through Emotional Retrieval*, ICKG 2024, **arXiv:2410.23041** — https://ar5iv.labs.arxiv.org/html/2410.23041 · code: https://github.com/BAI-LAB/EmotionalRAG

Motivation, verbatim:
> "Inspired by the **Mood-Dependent Memory** theory, which indicates that people recall an event better if they somehow reinstate during recall the original emotion they experienced during learning... According to the Mood-Dependent Memory theory, which was proposed by psychologist **Gordon H. Bower in 1981**: *people recall an event better if they somehow reinstate and recall the original emotion they experienced during learning*."

**Exact scheme.** Query and each memory both get a **semantic** embedding and an **8-dim Plutchik emotion vector (1–10)**:

> `emotion_q = 𝒢(q)`, `emotion_m^k = 𝒢(m_k)` — "This process is accomplished through **GPT-3.5**... an 8-dimensional vector containing 8 different emotional states, i.e., joy, acceptance, fear, surprise, sadness, disgust, anger, and anticipation. The value of each dimension is an integer between 1 and 10."

Similarities:

> `score_semantic^k = ℰ(semantic_q, semantic_m^k)` (Euclidean or cosine)
> `score_emotional^k = 1 − 𝒞(emotion_q, emotion_m^k)` where "𝒞 is a function of the cosine similarity of two vectors. The smaller the distance score_emotional^k is, the more similar the emotions..."

**Four fusion strategies** for `score_final^k = ℳ(score_semantic^k, score_emotional^k)`:

| Strategy | Name | What it is |
|---|---|---|
| **C-A** | combination, **add** | `score_semantic + score_emotional` — soft **weighted sum**, both signals simultaneously |
| **C-M** | combination, **multiply** | `score_semantic × score_emotional` — **multiplicative gating** |
| **S-S** | **semantic first** | retrieve top-k by semantic, then **rerank** by emotional |
| **S-E** | **emotional first** | retrieve top-k by emotional, then rerank by semantic |

> "Finally, the **top 10 memory fragments** with the smallest distance scores (i.e., the highest similarity) are used for retrieval augmentation."

**Answer to your "hard filter / soft boost / quota / rewrite" question: it is a soft boost or a rerank — never a hard filter, never a query rewrite, and there is no quota.** The only filter-like element is the top-10 cut.

**Results and which strategy won** (verbatim): "(1) Emotional RAG variants with **all retrieval strategies (except the C-A strategy in BFI evaluation)** achieve better results in MBTI and BFI evaluations... (2) Different retrieval strategies are applicable to different evaluations. For example, in the BFI personality evaluation, the **sequential strategy (S-S) performs the best**, while in the MBTI task, the **combination strategy (C-A) exhibits the best performance**." Magnitudes on Qwen-72B / InCharacter: MBTI Acc(Dim) 0.7438 → 0.7934, Acc(Full) 0.3438 → 0.4688; BFI Acc(Dim) 0.6815 → 0.7261. On GPT-3.5 the gains were ~zero for BFI — a useful caution that **the effect is model-dependent**.

Note the paper uses **cosine distance on an 8-dim 1–10 vector**, which is sensitive to overall intensity, not just *pattern*: a memory that is intensely happy and a query that is intensely happy score alike, but so do two vectors that are both uniformly 1–10-scaled. **[My own analysis, not the paper's.]** If you want pattern-not-intensity, use Pearson correlation or z-score each vector first.

### 5.2 The implementation: `emotional-memory`'s six-signal adaptive-weight scorer

This is the most complete published *code* for mood-congruent retrieval I found.
`src/emotional_memory/retrieval.py` (https://github.com/gianlucamazza/emotional-memory/blob/main/src/emotional_memory/retrieval.py)

**Six linear signals, weighted sum** (verbatim):
```python
base_weights: list[float] = [0.35, 0.25, 0.15, 0.10, 0.10, 0.05]
"""Weights for [semantic, mood_congruence, affect_proximity,
momentum_alignment, recency, resonance_boost]. Must have exactly 6 elements."""
```
and the module docstring:
> `s1 — semantic`; `s2 — mood congruence (mood-congruent recall, Bower 1981)`; `s3 — affect proximity`; `s4 — momentum alignment`; `s5 — recency / decay score (ACT-R power-law)`; `s6 — resonance boost (spreading activation, Collins & Loftus 1975)`
> "They are combined by a **weighted sum** without cross-signal normalization, so the weights do not map linearly to per-signal influence, and s6's small magnitude makes the resonance boost weak." *(the authors' own honest caveat)*

Individual signals (verbatim):
```python
def _mood_congruence(current: MoodField, snapshot: MoodField) -> float:
    """...Maps PAD distance [0, max_dist] → similarity [1, 0].
    max_dist = sqrt(6) ≈ 2.449 for the 3-D PAD space"""
    dist = current.distance(snapshot)
    return max(0.0, 1.0 - dist / _MAX_MOOD_DIST)

def _affect_proximity(current: CoreAffect, encoded: CoreAffect) -> float:
    dist = current.distance(encoded)
    return max(0.0, 1.0 - dist / _MAX_AFFECT_DIST)

def _momentum_alignment(current, encoded) -> float:
    # cosine similarity of 3D velocity vectors; returns 0.5 if either is ~zero
    return (cos + 1.0) / 2.0
```

So the **exact mood-congruence weight** is `s2 = max(0, 1 − ‖PAD_now − PAD_at_encoding‖ / 2.449)`, and it is scored against an **immutable `mood_snapshot`** ("s2 (mood congruence) uses the immutable `mood_snapshot`"), while `s3` uses the **reconsolidation-mutable `core_affect`** — a deliberate separation worth copying.

**The mood→weight modulation — this is the part you should steal.** Verbatim, `AdaptiveWeightsConfig`:
```python
    # Negative mood: weight shift from semantic → emotional signals
    negative_mood_strength: float = 0.15
    negative_mood_center: float = -0.5
    negative_mood_sharpness: float = 5.0
    # High arousal: weight shift from semantic → momentum alignment
    high_arousal_strength: float = 0.10
    high_arousal_center: float = 0.7
    high_arousal_sharpness: float = 5.0
    # Calm/neutral: weight shift from emotional → semantic
    calm_strength: float = 0.15
    calm_valence_width: float = 0.2
    calm_arousal_center: float = 0.3
    calm_sharpness: float = 5.0
```
with
```python
def _smooth_gate(x, center, sharpness):
    """Smooth sigmoid gate via tanh, centred at center. ... Returns values in [0, 1]."""
    return 0.5 * (1.0 + math.tanh(sharpness * (x - center)))

def adaptive_weights(mood, base, config=None):
    """Mood acts as a weight modulator — not a hard filter but a continuous
    shaping of what signals dominate retrieval (inspired by mood-congruent
    recall research, Bower 1981)."""
    w = np.array(base, dtype=float)
    # Negative mood: sigmoid activates below negative_mood_center
    neg = _smooth_gate(mood.valence, cfg.negative_mood_center, -cfg.negative_mood_sharpness)
    w[1] += cfg.negative_mood_strength * neg * (2.0 / 3.0)   # mood congruence
    w[2] += cfg.negative_mood_strength * neg * (1.0 / 3.0)   # affect proximity
    w[0] -= cfg.negative_mood_strength * neg                 # semantic
    # High arousal: sigmoid activates above high_arousal_center
    aro = _smooth_gate(mood.arousal, cfg.high_arousal_center, cfg.high_arousal_sharpness)
    w[3] += cfg.high_arousal_strength * aro                  # momentum
    w[0] -= cfg.high_arousal_strength * aro                  # semantic
    # Calm/neutral: Gaussian over valence x inverted sigmoid over arousal
    valence_calm = math.exp(-((mood.valence / cfg.calm_valence_width) ** 2))
    arousal_calm = _smooth_gate(mood.arousal, cfg.calm_arousal_center, -cfg.calm_sharpness)
    calm = valence_calm * arousal_calm
    w[0] += cfg.calm_strength * calm
    w[1] -= cfg.calm_strength * calm * (2.0 / 3.0)
    w[2] -= cfg.calm_strength * calm * (1.0 / 3.0)
    # Clamp negatives and normalise; fall back to uniform if all signals cancel
    w = np.clip(w, 0.0, None)
    total = float(w.sum())
    w = w / total if total > 0 else np.full(6, 1.0 / 6.0)
    return np.asarray(w, dtype=np.float64)
```

**This is the answer to "how do you turn current mood into a rerank weight":** you don't touch the candidate scores; you **re-weight the score *dimensions* as a normalised convex combination whose coefficients are smooth (tanh/Gaussian) functions of the current mood** — then `score = Σ w_k · s_k`. Because `w` is renormalised to sum to 1, the result stays calibrated, and because the gates are `tanh`/Gaussian rather than `if` statements, **there is no discontinuity anywhere in mood space** (their explicit stated design goal: "sharpness ... a value of ~50 approximates the old hard-threshold behaviour; the default of 5.0 produces a smooth transition"). Also note the *directional* claim they encode, which is a real psychological hypothesis: **negative mood → emotional signals dominate; high arousal → momentum dominates; calm → semantic dominates.**

The same file also implements query-type routing (`QueryClassifierConfig`: "Routing selects the *starting* weights, it does not bypass adaptive weighting: the routed vector replaces `base_weights` and is then still modulated by the current mood"), which is a third, orthogonal lever — mood routing × query-type routing.

### 5.3 Sentipolis: emotion-tagged memory + decay

Verbatim (https://ar5iv.labs.arxiv.org/html/2601.18027):
> "To make emotion consequential for future behavior, we couple emotion to memory by **storing events and reflections together with their PAD-derived emotion tags**."
> "this paragraph is injected into the prompt to ground dialog and reflection in the agent's current emotion state."
> Decay: `s(t + Δt) = s(t) · 2^(−Δt / T½)`, with "**exponential decay of emotion states toward neutrality at every time step. Emotion decays with a half-life of 120 minutes.**" (simulation stride Δ = 20 min, T = 36 steps = 720 min.)
> "when agents store events with PAD-derived emotion tags, **retrieval preferentially surfaces emotionally salient encounters, creating positive feedback loops that reinforce emergent clusters.**"

Reported coupling is measurable: weighted reciprocity r_w ≈ 0.87–0.89; modularity Q_T ≈ 0.22; and Emotional Continuity improves by **+222%** (GPT-5.2/Sonnet evaluator) over the non-emotional Generative Agents baseline. Model-dependent caveat, verbatim: "the same architectural intervention that produces **85% believability gains in GPT-5.2** causes **26% degradation in GPT-4o-mini**, suggesting that the deployment of emotion-aware architectures on lower-capacity backbones may require additional calibration." And a good warning against over-weighting self-emotion: "when models attend too strongly to their own emotional state, they may become less responsive to their conversation partner's emotional cues."

### 5.4 PsychoAgent: the best published *fusion* pattern — semantic gate then salience rank

Amanlou et al., *PsychoAgent: An Affect-Sensitive Cognitive Architecture for Conflict-Aware Memory in LLM Agents*, arXiv:2608.07438 — https://arxiv.org/html/2608.07438v2. Verbatim equations:

```
N_t^pre = TopK_30( sim( φ(q_t^A), φ(k_j) ) )          # 30 semantic candidates
N_t^A   = TopK_10( sort_↓{ w_j : k_j ∈ N_t^pre } )    # then top-10 by stored salience w_j ∈ [0,1]
```
> "Affective retrieval first returns k_pre = 30 semantic candidates ... and then keeps the k_A = 10 candidates with greatest salience ... **Semantic preselection prevents an intense but unrelated memory from dominating.**"

Results (verbatim): critical retrieval rate **0.933 ± 0.058** (full) vs **0.500 ± 0.100** (semantic-affective ablation) vs **0.667 ± 0.115** (single-memory RAG); Friedman Q = 6.00, **p = .0278** over 3 scenarios — and note the honest weakness: "each pairwise Wilcoxon raw p = .25, Holm-adjusted p = .75" with only 27 outputs and 5 raters.

**This "filter-then-rank-by-salience" two-stage pattern is the single best template for your quota/boost question: the hard gate is on *relevance*, the soft rank is on *emotion*.** That inverts the naive design (hard-filter on emotion), and it is what makes mood-congruence safe.

### 5.5 Emotion-aware recommender systems — the standard fusion taxonomy

Emotional RAG's four strategies (C-A add, C-M multiply, S-S rerank, S-E rerank) **are** the standard score-fusion taxonomy you asked about: weighted sum (additive), multiplicative gating, and two cascaded rerank orders. The verified evidence on *which* to pick is that it is task-dependent (S-S best on BFI, C-A best on MBTI), and that **additive fusion was the only variant that could *hurt*** ("all retrieval strategies except the C-A strategy in BFI evaluation"). Practical reading: **multiplicative gating is the safe default when emotional similarity is a *quality* signal; additive is only safe if the two scores are on the same scale and non-negatively correlated.** Note also `emotional-memory`'s explicit warning about weighted sums without cross-signal normalisation (§5.2).

---

## 6. Baseline vs deviation — the key question

### 6.1 Direct answer

**No published work scores *events* by deviation from a person- or character-specific emotional baseline as the salience/decay signal.** I searched personalized/idiographic emotion baseline modelling, affective chronometry, surprise/salience-as-prediction-error, Bayesian surprise applied to affect, abnormality detection in affective time series, and display rules/Duchenne — and there is **no paper that defines "this event was emotionally salient *for this character*" as a deviation-from-baseline term.** What exists is four partial pieces, each one transplantable:

1. **DynAffect** models the *state* as deviation from a personal attractor, but never scores an event.
2. **Bayesian surprise** gives the right *form* (deviation of your posterior from your prior) but the "baseline" is a belief distribution, not an emotional set-point.
3. **`emotional-memory`** has *both* a personal baseline (exponential regression to `baseline_valence/arousal/dominance`) *and* an arousal-modulated decay — but the decay uses **absolute** arousal, not deviation.
4. **Achiam & Sastry's learning-progress reward** is the cleanest drop-in formula for "score this event by how far it moved *this agent's own model*", and it self-annihilates as the model converges.

The gap is real and it is the opportunity.

### 6.2 The baseline, formula-verified

**DynAffect** (Kuppens, Oravecz & Tuerlinckx 2010, *JPSP* 99(6):1042–1060, doi 10.1037/a0020962; equations verified via their verbatim restatement in Wood et al. 2017, https://pmc.ncbi.nlm.nih.gov/articles/PMC6433426/):

```
(1)  y_p(t) = θ_p(t) + ε_p(t)
     dθ_p(t) = β_p (μ_p − θ_p(t)) dt + σ_p dW(t)
(2)  γ_p = σ_p² / (2 β_p)
(3)  μ_p = α_μ x_p + e_pμ
(4)  log(γ_p) = α_γ x_p + e_p,log(γ)
(5)  log(β_p) = α_β x_p + e_p,log(β)
```
Verbatim: "the person-specific **attractor point** is captured by μ_p. Assuming intrinsic regulation, **anytime there is a discrepancy between the current affect state and attractor point (i.e., when [μ_p − θ_p(t)] ≠ 0), the affect system restores the system to the attractor point**." · "the restorative force ... is scaled by β_p (constrained to be > 0), the person-specific **attractor strength**. Formally, `e^(−β·Δt)` gives the continuous-time exponential autocorrelation function" · "γ_p = σ_p²/2β_p, which indicates the total extent of **BPS-related reactivity**". Renaming map, verbatim: "the *attractor point* (previous label = **home base**)".

> **Your character baseline is `μ_p`; the deviation is `μ_p − θ_p(t)`; inertia is `β_p` (low β = high inertia).** Discretised: `θ_t = θ_(t−1) + β(μ − θ_(t−1)) + ε_t`. **[The Euler–Maruyama discretisation is my derivation, not a quote — the 2010 paper is paywalled.]**

**Emotional inertia** as an AR(1) slope (Kuppens, Allen & Sheeber 2010, *Psych Science* 21(7):984–991, doi 10.1177/0956797610372634; formalism verified via Hamaker & Grasman 2015, https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2014.01492/full):
```
y_ti = μ_i + a_ti ;  μ_i = μ + u_0i ;  a_ti = φ_i · a_(t−1),i + e_ti ;  φ_i = φ + u_1i
```
Verbatim: "The autoregressive parameter φ_i relates the outcome variable to itself at the preceding occasion, and thus represents the **inertia** of the person." · "an autoregressive parameter close to zero implies that there is little carryover ... and recovery is thus instant, an autoregressive parameter close to one implies that there is considerable carryover" · "this parameter typically lies somewhere between **0 and 0.6**" · "individual differences in inertia in emotions and affect are positively related to **neuroticism and depression**".
**Structural point that matters:** `a_ti` is *defined as the deviation from the person's own mean* — **baseline and deviation are two separate terms in the model.** That is the architecture to copy.

**Variability indices** (Jahng, Wood & Trull 2008, *Psych Methods* 13(4):354–375; formulas verified from the R `psych::mssd` docs which cite Jahng et al.):
```
MSSD  = Σ (x_i − x_(i+1))² / (n − lag)        # lag = 1 by default
RMSSD = sqrt(MSSD)
```
Verbatim on the `psych` page: "Since the mssd is just twice the variance - the autocorrelation, it is thus possible to also find the autocorrelation for a particular lag." → i.e. **`MSSD ≈ 2σ²(1 − r₁)`**, a direct bridge from a variability index to AR(1) inertia — **use this to estimate a character's `φ_i` and `σ_i` from a log of remembered emotions.** (https://search.r-project.org/CRAN/refmans/psych/html/mssd.html)

**A working baseline implementation** — `emotional-memory`, `src/emotional_memory/mood.py`
(https://github.com/gianlucamazza/emotional-memory/blob/main/src/emotional_memory/mood.py):

```
regressed = baseline + (current − baseline) * exp(−t·ln2 / half_life)
effective_half_life = base_half_life_seconds * (1 + inertia * inertia_scale)
effective_alpha     = alpha * (1 − inertia)
new = (1 − eff_alpha)·base + eff_alpha·core_affect
```
Defaults, verbatim: `base_half_life_seconds = 3600.0` ("Base half-life in seconds (default 1 hour...)"), `inertia_scale = 2.0`, `baseline_valence = 0.0` ("Resting valence attractor (neutral)."), `baseline_arousal = 0.3` ("Resting arousal attractor (**not zero — resting alertness, not inert**)."), `baseline_dominance = 0.5` ("Resting dominance attractor (balanced perceived control)."), `alpha = 0.1`. Note the docstring: "**Effective half-life is modulated by inertia: high-inertia moods resist regression (as in trauma or persistent elation).**" — the *same* inertia semantics as Kuppens, arrived at independently. **`baseline_arousal = 0.3` rather than 0 is a nice detail: a character at rest is not inert.**

### 6.3 Deviation as a score — the formulas that exist

| What you want | Verified formula | Source |
|---|---|---|
| Deviation of an event from a belief | `S(D,M) = ∫ P(M\|D) log[P(M\|D)/P(M)] dM` | Itti & Baldi, http://papers.nips.cc/paper/2822-bayesian-surprise-attracts-human-attention.pdf |
| Deviation as a quadratic in prediction error | `F_n = A_F δ² + B_F`, `δ = x̄ − η` | Yanagisawa 2021 eq. 26, https://www.frontiersin.org/journals/computational-neuroscience/articles/10.3389/fncom.2021.698252/xml |
| "How far did this move *my own* model" | `r' = r + η( log P_{φ_t}(s'\|s,a) − log P_{φ_{t−k}}(s'\|s,a) )` | Achiam & Sastry eq. 8, https://ar5iv.labs.arxiv.org/html/1703.01732 |
| Plain distance from a learned mean | `r_+ = ‖ s' − μ_φ(s,a) ‖₂` | ibid. eq. 12 |
| Restoring pull toward the personal baseline | `dθ = β_p(μ_p − θ_p)dt + σ_p dW` | DynAffect, https://pmc.ncbi.nlm.nih.gov/articles/PMC6433426/ |
| A personalised sensitivity threshold on deviation | `d(y,p) = log f_B(y\|y,K) − log f_B(y\|p,K)`; changepoint iff `d(y_t,p_t) > C`; "The parameter **C governs the twitchiness** of the model predictions. If C is large, only very dramatic changepoints will be detected" | Steyvers & Brown, NIPS 2005, http://papers.nips.cc/paper/4928-prediction-and-change-detection.pdf |

**The transplantable synthesis (my construction, not published):** define a character's baseline `μ_c = (P,A,D)` and per-axis scale `σ_c` from their memory log (or hand-author it), then score an event's affect `x` as

```
z      = (x − μ_c) / σ_c                       # per-axis, sign preserved
salience = ‖z‖₂                                 # magnitude of deviation  (Achiam eq. 12 form)
       or  = Σ_k z_k² / 2                        # quadratic free-energy form (Yanagisawa eq. 26)
congruence = max(0, 1 − ‖x − mood_now‖ / 2.449)  # mood-congruent retrieval (emotional-memory §5.2)
```
and then feed `salience` into the decay exponent, replacing absolute arousal in the verified
`effective_decay = base_decay · (1 − λ·arousal)`:
```
effective_decay = base_decay · (1 − λ · clamp(‖z‖₂ / z_max, 0, 1))
```
> **⚠ This substitution is UNPUBLISHED. I am not aware of any paper that does it.** It is a composition of verified pieces, and it should be validated empirically. Its appeal: a *habitual* strong expression (high `x` but close to `μ_c`) yields small `z` and therefore normal decay, while a *rare* expression of the same absolute intensity yields large `z` and slow decay — which is exactly the "habitual signature expression must not dominate" requirement.

**[UNVERIFIED]:** any published `z = (x − μ_person)/σ_person` used as an *emotional-salience trigger* (the pattern is ubiquitous engineering practice but I found no citable primary source that publishes it as a salience definition); affective chronometry (Davidson) parameters; ESM statistical-process-control formulas; any equation in McGaugh / Mather & Sutherland / Richter-Levin for arousal→strength.

### 6.4 The appraisal → PAD bridge (needed to make §6.3 usable)

A baseline is only useful if you can produce a PAD coordinate from an *event*. The only implementation I found with a **published, empirically fitted** mapping is `emotional-memory`, `src/emotional_memory/appraisal_schema.py` (https://github.com/gianlucamazza/emotional-memory/blob/main/src/emotional_memory/appraisal_schema.py). Its `AppraisalVector` is Scherer's CPM reduced to five clamped dimensions ("loosely based on Scherer's Stimulus Evaluation Checks", per the `appraisal.py` docstring):

```
novelty          [-1,+1]   "fully expected ↔ totally new"
goal_relevance   [-1,+1]   "obstructs ↔ furthers goals"
coping_potential [ 0, 1]   "helpless ↔ full control"
norm_congruence  [-1,+1]   "violates norms ↔ conforms"
self_relevance   [ 0, 1]   "irrelevant ↔ highly self-relevant"
```

and `_scherer_project` maps it to PAD — **verbatim coefficients**:

```python
    valence = (
        0.4805 * dims["goal_relevance"]
        + 0.1862 * dims["norm_congruence"]
        + 0.1643 * coping_signed
        + 0.0179 * dims["novelty"]
    )
    arousal = (
        0.3694 * abs(dims["novelty"])
        + 0.1357 * (1.0 - dims["coping_potential"])
        + 0.2208 * dims["self_relevance"]
        + 0.1399
    )
    return CoreAffect(valence=valence, arousal=arousal, dominance=dims["coping_potential"])
```

Three things make this worth copying and three caveats make it worth copying *carefully*:

- **The coefficients are fitted, not theoretical.** The file's own comment records the fit quality: against "EmoBank (N=300) it is better correlated on every axis — **valence r=0.79** (near-zero bias), **arousal r=0.58**, **dominance r=0.43** — vs the SEC→projection's 0.70 / 0.23 / 0.31". So this is a *validated* mapping, and the validation target is a human-norm corpus.
- **Note the intercepts and the structure.** `arousal` has a baseline of **0.1399** (a neutral event is not zero-arousal — the same instinct as `baseline_arousal = 0.3` in §6.2), and `dominance` is simply `= coping_potential`, which is a clean, interpretable choice: **how much control the character has *is* their dominance.** That single assignment is what lets `strive` (+D) differ from `embarrassed` (−D) from the same event.
- **The docstring is explicit about what is missing**, verbatim: "Scherer's 'intrinsic pleasantness' relevance check is not modelled, so valence is derived from goal_relevance + norm_congruence + coping only; and the arousal projection **excludes goal-relevance *magnitude*, so a high-stakes but expected event is rated low-arousal.**" Read that as a design warning: **if you want "the stakes were high even though it went as expected" to matter, you must add a goal-relevance magnitude term to arousal, or the engine will treat a routine-but-critical moment as calm.**

**Practical recipe for your engine:** have the *cheap annotation layer* (your two-pass `emotion_annotate`, which already runs per board) emit the five Scherer dimensions instead of — or in addition to — a single emotion key; project to PAD with the coefficients above; then compute `z = (PAD − μ_character)/σ_character` (§6.3) for salience, and `mood_congruence = max(0, 1 − ‖PAD_now − PAD_at_encoding‖/2.449)` (§5.2) for retrieval. One annotation call yields both the retrieval key and the salience score.
*Tradeoff:* you are replacing a small, already-working discrete key vocabulary with five floats, which costs tokens and invites annotation drift. Mitigate by keeping the discrete key as the **rendering** output and the five dimensions as the **engine** output — the same numbers-for-the-engine / words-for-the-LLM split that Sentipolis documents.

### 6.5 Characteristic vs distinctive expression — the design consequence

Combine §3.7 with §6.2 and the recipe writes itself:

- **Characteristic** = high-frequency, low-deviation. A character who smiles constantly has `smile` at their `μ_c` on the pleasure axis, so `z_smile ≈ 0` → **low salience → normal decay → the habitual smile does not accumulate into "the most important memory of the relationship."**
- **Distinctive** = low-frequency, high-deviation, and (per the timing evidence) *early* AU6 relative to AU12: "AU6 was active before AU12 above 80% of the time in the spontaneous block; and above 60% of the time in the posed block" (https://ar5iv.labs.arxiv.org/html/2008.08791).
- **Do not use AU6-presence as a genuineness flag** — "the Duchenne smile is likely an artifact of smile intensity" (Girard et al., ACII 2019).

---

## 7. Practical implementation notes

### 7.1 Where the score is written, and whether it is mutable

| System | Where the emotion/importance score is written | Mutable? | Decay of importance/affect? |
|---|---|---|---|
| **Generative Agents** | **At ingest**, by the summarizing LLM (`generate_poig_score` → `run_gpt_prompt_event_poignancy`), stored as `ConceptNode.poignancy` | `poignancy` **immutable** (no code path ever writes it again). `last_accessed` **mutable on recall** (`n.last_accessed = persona.scratch.curr_time`) | Decay applies to **recency only** (`recency_decay = 0.99`), computed at read time, not stored |
| **A-Mem** | N/A — no score. `keywords`/`context`/`tags` written at ingest by `analyze_content` | `context`/`tags` **mutable by the evolution LLM on every `add_note`** ("memory evolution"); `content` immutable | NONE |
| **MemGPT/Letta** | Nothing is auto-scored; the **agent writes memory itself** via tool calls at inference time | Highly mutable by design (`core_memory_replace`, passage update/delete) | NONE (FIFO context eviction + recursive summary only) |
| **Mem0** | No score. Extraction at ingest by LLM; `created_at/updated_at` by the store | `text`/`metadata`/`expiration_date` mutable; identity keys immutable | NONE in OSS — decay is platform-only, and `expiration_date` is a **hard TTL**, not a curve |
| **Zep/Graphiti** | No score. `valid_at` set at ingest by the temporal-extraction LLM | `valid_at`/`invalid_at`/`expired_at` mutated by the **invalidation LLM at ingest of a contradicting edge**; `summary`/`attributes` regenerated on resolution | NONE — time is logical invalidation, and records are retained non-lossy |
| **LangMem** | `[IMPORTANT]` etc. written **at extraction** by LLM; `created_at/updated_at` by the store | Yes, via `manage_memory` / `memory_manager(enable_inserts/updates/deletes)`; `RemoveDoc` semantics are caller-defined ("soft or hard delete, or simply a **down-weighting**") | NONE as a formula; opt-in `ttl` in minutes only |
| **Cognee** | `feedback_weight`/`importance_weight` default at ingest, then **rewritten by the batch `memify` task `apply_feedback_weights`** from session QA feedback — **not** by the summarizer, **not** on read | **Strictly mutable**: `w ← w + α(r − w)`, α = 0.1, clip [0,1], 4 dp | NONE (bi-temporal `valid_to` supersession only) |

### 7.2 Ebbinghaus / forgetting curves in agent frameworks

- **`emotional-memory` is the only surveyed system with real decay**, and it is a **power law, not Ebbinghaus exponential** — deliberately: "Memory strength decays as a power function of elapsed time: `strength(t) = initial * t^(−d)`", citing "Anderson, J. R. (1983). *The Architecture of Cognition*", with the fidelity test asserting the log-log linearity `R² > 0.99` (which is what distinguishes a power law from an exponential). Its own comparison of the two, from the ACT-R notes: `P = A·e^(−bT)` (exponential) vs `P = A·T^(−b)` (power), and "Instead, we see a power function" — Ebbinghaus's own 1913 retention data are better fit by a power law. (https://github.com/gianlucamazza/emotional-memory/blob/46330c6877f3a7eece4639040cd546b262eb3de4/benchmarks/fidelity/test_decay_power_law.py)
- **MemoryBank** is the framework usually credited with importing the Ebbinghaus curve into LLM agents; Emotional RAG cites it as such, verbatim: "the **Ebbinghaus forgetting curve** has inspired the development of **MemoryBank**, facilitating the implementation of a more anthropomorphic memory scheme." **[The MemoryBank paper's own formula and constants were not verified in this session — UNVERIFIED.]**
- **No mainstream agent framework decays *emotion*.** Sentipolis decays the *state* (`2^(−Δt/T½)`, T½ = 120 min), `emotional-memory` decays *strength*, and everyone else decays nothing. **Affect decay and memory decay are separate mechanisms in every system I found**; nothing couples them except `emotional-memory` (through arousal modulating the decay exponent).

### 7.3 The patterns worth noting across the whole survey

1. **Almost nobody stores emotion.** Of nine systems, **zero** have an `emotion` field; **one** (Cognee) has a numeric `importance_weight`; **one** (Generative Agents) has `poignancy`. The three systems that *do* model affect (Emotional RAG, Sentipolis, `emotional-memory`) all had to build it themselves.
2. **Two-stage relevance-then-emotion is the winning retrieval shape** (PsychoAgent's `TopK_30 semantic → TopK_10 salience`; Emotional RAG's S-S/S-E rerank orders). Hard-filtering on emotion is never done.
3. **The extension points are `metadata`/`attributes` dicts** — Letta `Block.metadata`/`Passage.metadata`, Graphiti `attributes`, LangGraph `Item.value`, Mem0 `metadata`. If you build on any of these, put `{valence, arousal, dominance, mood_snapshot, salience, importance}` there.
4. **Scores are written at ingest by the summarizer in every system except Cognee**, which is the only one that updates weights from *outcome* feedback in a batch pass. **If you want feedback-driven affect, Cognee's `w ← w + α(r − w)` is the pattern.**

---

## 8. What a game engine should copy

Ten concrete recommendations, ordered by leverage. Tradeoffs are stated honestly, including where I am extrapolating.

**1. Store affect as a PAD triple plus an immutable encoding-time mood snapshot, not as a label.**
`CoreAffect(valence ∈ [−1,1], arousal ∈ [0,1], dominance ∈ [0,1])` + `mood_snapshot` (same shape, never updated). Labels are for the prompt; numbers are for the engine. **Fix `D_max = √6 ≈ 2.449` for these ranges and derive it in a comment — do not import a normaliser** (§4.1). If you ingest a VAD lexicon scored on [0,1] (NRC-VAD), rescale with `2x − 1` first or your "neutral" lands at +0.5 valence.
*Tradeoff:* you must maintain two parallel representations and a PAD→label mapping (Sentipolis does this with KNN over human PAD data). The payoff is that `dominance` is the only axis that separates `embarrassed` (low D) from `expectant` (low D, +A, ~0 P) from `strive` (+A, **+D**, −P) — a 2-D valence×arousal model cannot express your vocabulary. *Verified precedent:* Sentipolis §3.2/§3.4; `emotional-memory` `affect.py` with `MAX_PAD_DISTANCE = sqrt(6) ≈ 2.449`. **To produce the triple from an event, use the fitted Scherer→PAD projection in §6.5** (`valence = 0.4805·goal_relevance + 0.1862·norm_congruence + 0.1643·coping_signed + 0.0179·novelty`; `arousal = 0.3694·|novelty| + 0.1357·(1−coping) + 0.2208·self_relevance + 0.1399`; `dominance = coping_potential`), which is validated against EmoBank at valence r = 0.79 / arousal r = 0.58 / dominance r = 0.43 — and note its documented blind spot: "the arousal projection excludes goal-relevance *magnitude*, so a high-stakes but expected event is rated low-arousal." If high stakes matter to you, add that term.

**1b. Define your 8 expression keys as NAMED REGIONS in PAD space, and encode intensity explicitly in the key.**
Do not try to map the 8 keys onto a published taxonomy — §4.3 shows none of the eight schemes covers them (`strive` and `serious` are absent from all of them; `expectant` vs `strive` needs dominance; `serious`/`pensive` are register, not affect). Instead pick one point per key in PAD (e.g. `embarrassed` → low P, high A, **low D**; `strive` → low P, high A, **high D**; `expectant` → ~0 P, high A, **low D**) and classify by nearest region using a **per-key activation threshold**, verbatim pattern from the literature: `w_e = (1 − (d_e − Δ_e)/(φ_e − Δ_e))` where "Δ_e is the minimum threshold to activate an emotion and φ_e establishes the point of saturation", nearest = `argmin d_e`. The threshold is what stops `strive` firing on any high-arousal state.
**And carry intensity separately** (`joy:0.4` = `smile` vs `joy:0.9` = `laugh`), because `laugh` vs `smile` is an intensity-only distinction that Ekman, GoEmotions and OCC structurally cannot express — only Plutchik's cone tiers and PAD distance-from-neutral can.
*Tradeoff:* you are inventing a private taxonomy, so you lose the ability to reuse off-the-shelf emotion classifiers directly and must validate the region boundaries yourself. Mitigate by keeping GoEmotions-28 (or a VAD lexicon) as the *text→PAD scorer* feeding the regions, so the regions are the engine's contract while the scorer stays swappable. One concrete trap: **do not name a key `pensive` expecting "thoughtful" and then adopt Plutchik's `pensiveness` upstream — that label means *mildly sad*.** `pensive` and `depressed` also collide in PAD (both low-P/low-A); separate them on dominance or tag `pensive` as a non-affective register.

**2. Score an episode's emotional peak with the `ReLU(ΔL)·ReLU(ΔR)` product form, and always keep a mean term alongside it.**
`peak_score = max_t [ ReLU(s_t − s_(t−1)) · ReLU(s_t − s_(t+1)) · s_t ]` over the episode's affect trace (strict local max, i.e. `s_t > s_(t±1)`), then blend: `episode_affect = κ·peak_score + (1−κ)·mean_t(s_t)`.
*Why the product:* it is the geometric mean of rise and fall, so a slow drift to a high plateau scores near zero while a sharp spike scores high — "the product of the left and right difference terms amplifies local trends, thereby suppressing trivial fluctuations" (Peak-End-Net, arXiv:2607.13941). *Why you must keep the mean:* in the verified Two-Door MDP, peak-weighted value estimation makes agents prefer a trajectory worth `V* ≈ 12.81` over one worth `≈ 16.05`, with the pathology worst for `0.15 < λ < 0.50` (Trace-Mediated Peak Bias, arXiv:2606.04735). *Tradeoff:* κ is a real design knob with a documented failure zone; start κ ≈ 0.5 and tune. **[UNVERIFIED]** the classic `(peak+end)/2` form — I could not find a published closed form, so don't cite one.

**3. Score salience as DEVIATION FROM THE CHARACTER'S OWN BASELINE, not absolute intensity. This is the recommendation that answers "a habitual signature expression must not dominate".**
```
z         = (x_affect − μ_character) / σ_character          # per-axis
salience  = clamp(‖z‖₂ / z_ref, 0, 1)
```
where `μ_character` is that character's habitual PAD (e.g. the cheerful idol has `μ_P = +0.6`, `μ_A = +0.2`; the gloomy one has `μ_P = −0.3`), and `σ_character` is their emotional variability (per-axis; see rec 4).
*Why this is the right shape:* a character who smiles constantly has `smile ≈ μ` → `z ≈ 0` → **low salience → normal decay → their default smile never becomes a "core memory."** The same absolute smile from a character who never smiles has `z` large → high salience. The *only* systems today that get close are DynAffect's attractor deviation `μ_p − θ_p(t)` ("anytime there is a discrepancy between the current affect state and attractor point..., the affect system restores the system") and Yanagisawa's `F_n = A_F δ² + B_F` with `δ = x̄ − η`.
*Tradeoff, stated plainly:* **this specific composition is unpublished.** The pieces are verified; the combination is not. Budget for an A/B against the naive absolute-intensity baseline before committing. Secondary risk: a character with a *flat* baseline (`σ_character ≈ 0`) will score every twitch as maximally salient — so floor `σ_character` (e.g. `max(σ, 0.1)`) and clip `salience`.

**4. Estimate `μ_character` and `σ_character` from the character's own memory log, with hand-authored priors and a slow update.**
Start from authored `μ, σ`; then update from the accumulated affect trace with `μ ← μ + η(x − μ)` and `σ² ← σ² + η((x − μ)² − σ²)`, η small (0.02–0.05). Use `MSSD ≈ 2σ²(1 − r₁)` to derive both variability and inertia `φ` from a single memory log (verified on the R `psych::mssd` page, citing Jahng et al. 2008), and expect `φ ∈ [0, 0.6]` ("this parameter typically lies somewhere between 0 and 0.6").
*Tradeoff:* a baseline that adapts too fast destroys the very deviation signal you want (the habit becomes invisible again); too slow and the character cannot grow. **Make η a per-character authored value and never let `μ` move more than some authored distance per chapter** — otherwise a character's signature expression silently re-normalises itself away, which is the exact failure you are trying to prevent.

**5. Feed salience into the decay exponent; keep the power law, not an exponential.**
```
effective_decay = base_decay · (1 − λ·salience) · 1/(1 + retrieval_boost·recall_count)
strength(t)     = initial_strength · elapsed_seconds^(−effective_decay)
strength(t)     = min(strength(t), initial_strength)          # decay must never boost
if salience ≥ salience_floor_threshold:
    strength(t) = max(strength(t), min(floor_value, initial_strength))
```
Verified defaults to start from: `base_decay = 0.5`, `arousal_modulation → λ = 0.5`, `retrieval_boost = 0.1`, `floor_arousal_threshold = 0.7 → salience_floor_threshold ≈ 0.7`, `floor_value = 0.1`, `power = 1.0`.
*Why power law:* Ebbinghaus's own retention data are better fit by `P = A·T^(−b)` than by `P = A·e^(−bT)`, and the fidelity test asserts log-log linearity `R² > 0.99`. *Tradeoff:* power-law memory is unbounded in the log — you need the floor and a hard prune threshold, and the floor means "a few memories never die", which you should want but must cap.

**6. Implement mood-congruent recall as a RE-WEIGHTING OF SCORE DIMENSIONS, not as a filter and not as a fixed emotional bonus.**
```
base_weights = [0.35 semantic, 0.25 mood_congruence, 0.15 affect_proximity,
                0.10 momentum,   0.10 recency,          0.05 resonance]
mood_congruence = max(0, 1 − ‖PAD_now − PAD_at_encoding‖ / 2.449)   # immutable snapshot
# then modulate base_weights by current mood using tanh/Gaussian gates, and RENORMALISE:
neg  = 0.5(1 + tanh(−5·(valence + 0.5)))   # negative mood → emotional signals dominate
w[mood_congruence] += 0.15·neg·(2/3) ; w[affect_prox] += 0.15·neg·(1/3) ; w[semantic] -= 0.15·neg
calm = exp(−(valence/0.2)²) · 0.5(1 + tanh(−5·(arousal − 0.3)))       # calm → semantic dominates
w[semantic] += 0.15·calm ; w[mood_congruence] -= 0.15·calm·(2/3) ; w[affect_prox] -= 0.15·calm·(1/3)
w = clip(w, 0, None) ; w /= w.sum()   # fall back to uniform if the sum is 0
```
*Why smooth gates:* "sharpness ... a value of ~50 approximates the old hard-threshold behaviour; the default of 5.0 produces a smooth transition centred at the given point" — no discontinuity anywhere in mood space, so no visible "the character suddenly started reminiscing" cliff. *Why renormalise:* it keeps the ranking calibrated as mood varies. *Tradeoff:* you lose the interpretability of a plain sum, and the mood→dimension directions (negative→emotional, calm→semantic) are the implementer's psychological hypothesis, not established fact — treat them as tunable, and log `raw_signals` and `weighted_signals` separately so you can debug *why* a memory surfaced (the reference implementation returns exactly that decomposition).

**7. Gate on relevance, rank on emotion — never filter on emotion. (This is your "quota/boost not hard filter" answer.)**
Two stages: `TopK_30` by semantic similarity first, then take `TopK_10` from those by salience (PsychoAgent: "Semantic preselection prevents an intense but unrelated memory from dominating" — CRR 0.933 vs 0.500 for the ablation). If you want a *quota*, apply it at stage 2 as a **floor**, not a ceiling: guarantee at least 1 slot to the top emotionally-congruent memory **that already passed stage 1**, and let the rest be pure relevance. Never let mood exclude a relevant memory outright.
*Tradeoff:* the two-stage shape means a strongly congruent but semantically distant memory can never surface — which is a feature for coherence and a bug for "the character suddenly remembers something that seems out of nowhere". If you want that effect deliberately, add a third, low-weight, explicitly-random "intrusive memory" channel rather than loosening the gate.

**8. Use multiplicative gating (C-M) rather than additive fusion (C-A) when combining semantic × emotional similarity, unless you have normalised both.**
Emotional RAG's own results are the evidence: all four strategies helped **except** additive on BFI, and `emotional-memory` documents the reason for weighted sums generally — "combined by a weighted sum **without cross-signal normalization**, so the weights do not map linearly to per-signal influence."
*Tradeoff:* multiplication is a soft AND, so a zero on either axis kills the score (`score = 0` for an emotionally flat but perfectly relevant memory). Mitigate with `score = semantic · (ε + (1−ε)·emotional_similarity)`, ε ≈ 0.2.

**9. Score the mood-congruence signal against an IMMUTABLE encoding-time mood snapshot; let a separate, mutable `core_affect` carry reconsolidation.**
`s2 = f(mood_now, mood_snapshot_immutable)` for retrieval; `s3 = f(affect_now, core_affect_mutable)` for reconsolidation, updated as `alpha = min(ape · learning_rate, 0.5); core_affect.lerp(current_affect, alpha)` with `ape = ‖expected − observed‖₂` and a Pearce–Hall adaptive learning rate: `target_lr = clamp(ape, 0.05, 0.80); new_lr = clamp(lr + 0.2·(target_lr − lr), 0.05, 0.80)`.
*Why:* if the retrieval key itself mutates on every recall, mood-congruent recall becomes a self-reinforcing feedback loop with no fixed point — the memory drifts to whatever mood you happened to be in when you last recalled it. The reference implementation calls this out explicitly ("s2 (mood congruence) uses the immutable `mood_snapshot` and ... s3 ... `tag.core_affect`, which reconsolidation makes [mutable]").
*Tradeoff:* more fields, and `mood_snapshot` grows stale relative to the character's arc. Accept it: staleness is the point.

**10. Write `salience`/`importance` ONCE at ingest from the annotation pass, keep it immutable, and update relevance-like quantities on recall — with one exception: give the player's choices a Cognee-style feedback path.**
`s ← clamp(s + α(r − w), 0, 1)` with α = 0.1 and `r = (feedback_score − 1)/4` from a 1–5 signal, applied only to memories that were actually *used* in the turn that earned the feedback, idempotent per turn.
*Why immutable-at-ingest:* every system surveyed does it this way (Generative Agents, A-Mem, Mem0, Zep, LangMem), and mutation-by-recall is exactly what makes A-Mem's "memory evolution" dangerous — "**memory evolution** is dangerous without explicit version history; link decisions are LLM-driven and can hallucinate structure." *Why the exception:* Cognee is the only system with outcome-driven weights, and the feedback path is where the *player's* notion of "this moment mattered" enters — which is strictly better information than the LLM's poignancy guess.
*Tradeoff:* mutable salience breaks append-only purity. Keep the *event history* append-only (your project already does), write the learned weights to a derived snapshot, and keep the per-turn update idempotent so a replay is a no-op.

### Two things NOT to copy

- **Don't use a uniform 1–10 LLM "poignancy" rating as your only salience signal** (Generative Agents). It is absolute, character-independent, uncalibrated across calls, and — critically for you — it makes the habitual smile and the once-in-a-route genuine smile score identically. It is fine as *one* weak prior; it cannot be the peak detector.
- **Don't use presence of AU6 as a "genuine emotion" flag.** "the Duchenne smile is likely an artifact of smile intensity rather than a reliable and unique indicator of genuine positive emotion" (ACII 2019), with the intensity confound quantified at 64%/79% effect reduction. If you want a distinctiveness signal from the expression layer, use **AU onset order/dynamics** ("AU6 was active before AU12 above 80% of the time in the spontaneous block; and above 60% of the time in the posed block") or simply deviation from that character's own expression histogram.

---

## 9. Things I could NOT verify (explicit)

Grouped by cause. Do not cite these as established.

**Access-blocked (paywall / 403 / PDF unfetchable):**
1. **Ekman's exact label list is now VERIFIED (7 labels: anger, contempt, disgust, enjoyment, fear, sadness, surprise)** — see §4.1; the remaining gap is his licence and any verbatim quote from Ekman 1992 itself.
2. **OCC's exhaustive 22-token list** (only present as an image in the source I could open) and its **"3rd" intensity variable** — the standard reading is *two* categories (global: sense of reality, proximity, unexpectedness, arousal; plus local per-type), so treat "3" as unsourced. The count (22) and the trichotomy **are** verified.
3. **Sentipolis's enumerated Plutchik label list and its literal persistence field name** — Appendix A.2 truncates before the list in both the arXiv and ar5iv renderings and the ACL PDF was unfetchable after 4 attempts. Whether they store the continuous PAD triple or the discrete label on the memory record is therefore **[UNVERIFIED]** ("PAD-derived emotion tags" suggests the label, with PAD kept as agent state).
4. **GoEmotions' dataset-card licence** — the label set is verified (§4.0) but **every** fetch to huggingface.co failed with a transport error, so the commonly reported Apache-2.0 is unconfirmed. **Check the card's licence field before shipping.**
5. **EmoBank's raw-vs-rescaled CSV values** — the paper's [1,5] scale **is** verified ("We changed the 9-point SAM scales to 5-point scales"), but whether the released file is rescaled is not. **Warriner et al.'s exact 9-point anchors + licence**; **Russell's exact 8 octant labels** and his verbatim "distributed in a circular order" phrasing (JPSP 1980 paywalled; the V×A claim is attributable only second-hand).
6. **Plutchik's full 24-term intensity table** — only the `annoyance→anger→rage` and `boredom→loathing` tiers were quotable; the rest of the tiers were CAPTCHA/403-blocked.
7. **Mehrabian's own range statement** (Mehrabian 1996 is paywalled) — the PAD range conventions and `D_max` are verified only through two secondary sources; see the ⚠ box in §4.1.
8. **MemoryBank's Ebbinghaus formula and constants** — only the secondary claim from Emotional RAG's related work.
9. **Kensinger & Corkin (PNAS 2004)** "Two routes to emotional memory" — abstract page only; no numbers quoted.
10. **Mather & Sutherland (2011) competition equation** — the paper contains **no** equation (verified by reading it); it delegates to Bayesian surprise. So there is no formula to cite, not merely one I failed to find.
11. **McGaugh / Cahill & McGaugh / Richter-Levin "emotional tagging"** — no explicit arousal→memory-strength equation exists in anything I could open. The only explicit inverted-U formula found is the `emotional-memory` implementation (§3.3).
12. **Affective chronometry (Davidson)** parameters — no formula found at all.
13. **The full Ekman & Friesen (1969) display-rule definition sentence** — snippet truncated mid-word; the sentence I quote is [PARTIALLY VERIFIED].
14. **Masking-smile / miserable-smile AU criteria** (e.g. AU12+AU4) and any "habitual smile frequency per person" statistic.
15. **Kahneman's cold-pressor "69% chose to repeat the long trial"** figure and the primary-paper quotes.
16. **DynAffect's verbatim equations from the 2010 paper itself** — verified only through a paper that restates them; the Euler–Maruyama discretisation in §6.2 is my derivation.
17. **No peer-reviewed 2024–2026 survey tabulating per-system emotion field names exists** — so §2's table is assembled from primary sources, not inherited from a prior survey. That is a strength (it is first-hand) but it means completeness is not guaranteed.

**Actively contradicted by better sources (do not use):**
18. **"Only 10–20% of smiles are Duchenne"** — contradicted by Girard et al. ACII 2019 and Perusquía-Hernández et al. (§3.7).
19. **MemGPT having an importance/poignancy prompt** — a full-text grep returns 0 matches; that scheme is Park et al.'s (§2.2).
20. **"PEAK" and "SM (serial memory)" as named published aggregation models**, and any published `(peak+end)/2` closed form (§3.6).
21. **"The PAD maximum distance is √6 ≈ 2.449" stated as a universal constant** — it is `emotional-memory`'s constant for its *asymmetric* ranges (valence [−1,1], arousal/dominance [0,1]), with the derivation in its own source comment. For a symmetric [−1,1]³ space (Sentipolis's convention) the cube diagonal is **√12 = 2√3 ≈ 3.464**. Derive `D_max` from your own ranges; never import it (§4.1).
22. **"EmoBank is a 6-point scale"** — the paper says it changed "the 9-point SAM scales to **5-point** scales" (§4.1).
23. **"Ekman's Atlas of Emotions is a 5×5 grid"** — it is five emotion "continents", each naming an intensity-ranked set of states (§4.1).
24. **"OCC has 3 intensity variables"** — only a *global* category is verified (sense of reality, proximity, unexpectedness, arousal); the standard reading is two categories. Unverified.
25. **arXiv:1710.00107 as the EmoBank id** — that is a nuclear-physics paper; EmoBank is **arXiv:2205.01996** / EACL 2017 (https://aclanthology.org/E17-2092/).

**Structural conclusions that are negative findings, not gaps:**
26. **No published system scores an event by deviation from a personal emotional baseline** (§6.1) — this is the main result of the §6 search, not a failure to search.
27. **No published `z = (x − μ_person)/σ_person` used as an emotional-salience trigger** — the pattern is standard engineering practice but I found no citable primary source that publishes it *as a salience definition*.
28. **No mainstream agent-memory framework has an explicit emotion field** (§7.3, item 1) — verified across nine systems, and only **three** affect-carrying systems were found in the wider literature at all (§2 summary table).
29. **No single published taxonomy covers the 8 VN expression keys** (§4.3) — `strive` and `serious` are absent from every scheme, and `laugh` vs `smile` requires an intensity axis that only Plutchik's tiers and PAD distance provide. The 8 keys are best treated as **named regions in PAD space**, not as membership in a published taxonomy.

**Environment limitations:** `raw.githubusercontent.com` and `arxiv.org/html` were intermittently unreachable (worked around via the GitHub Contents API, jsDelivr CDN, and `ar5iv`); the GitHub API's unauthenticated rate limit (~60 req/h) was hit mid-session. MDPI, Springer, Wiley, ScienceOpen, Wikipedia, Hindawi, nearly all publisher PDFs, and **huggingface.co in every form** were unreachable throughout, and PMC returned reCAPTCHA intermittently. Items 1–7 above were limited by these blocks, which is why several are *incomplete* rather than negative findings.

---

### Source index (primary, all consulted directly)

Code: [generative_agents](https://github.com/joonspk-research/generative_agents) · [A-mem-sys](https://github.com/WujiangXu/A-mem-sys) · [A-mem](https://github.com/WujiangXu/A-mem) · [letta](https://github.com/letta-ai/letta/tree/0.16.8) · [mem0](https://github.com/mem0ai/mem0) · [graphiti](https://github.com/getzep/graphiti) · [langmem](https://github.com/langchain-ai/langmem) · [langgraph](https://github.com/langchain-ai/langgraph) · [cognee](https://github.com/topoteretes/cognee) · [emotional-memory](https://github.com/gianlucamazza/emotional-memory) · [EmotionalRAG](https://github.com/BAI-LAB/EmotionalRAG)

Papers: [Park et al. 2023 (2304.03442)](https://arxiv.org/abs/2304.03442) · [Xu et al., A-Mem (2502.12110)](https://arxiv.org/abs/2502.12110) · [Packer et al., MemGPT (2310.08560)](https://arxiv.org/abs/2310.08560) · [Chhikara et al., Mem0 (2504.19413)](https://arxiv.org/abs/2504.19413) · [Rasmussen et al., Zep (2501.13956)](https://arxiv.org/abs/2501.13956) · [Huang et al., Emotional RAG (2410.23041)](https://arxiv.org/abs/2410.23041) · [Fu et al., Sentipolis (2601.18027)](https://arxiv.org/abs/2601.18027) · [Amanlou et al., PsychoAgent (2608.07438)](https://arxiv.org/abs/2608.07438) · [Demszky et al., GoEmotions (2005.00547)](https://arxiv.org/abs/2005.00547) · [Itti & Baldi, Bayesian Surprise](http://papers.nips.cc/paper/2822-bayesian-surprise-attracts-human-attention.pdf) · [Yanagisawa 2021](https://www.frontiersin.org/journals/computational-neuroscience/articles/10.3389/fncom.2021.698252/full) · [Schwartenbeck et al. 2013](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2013.00710/full) · [Achiam & Sastry 2017](https://ar5iv.labs.arxiv.org/html/1703.01732) · [Peak-End-Net (2607.13941)](https://ar5iv.labs.arxiv.org/html/2607.13941) · [Trace-Mediated Peak Bias (2606.04735)](https://ar5iv.labs.arxiv.org/html/2606.04735) · [Sharot et al. 2007](https://pmc.ncbi.nlm.nih.gov/articles/PMC1713166/) · [Girard et al., ACII 2019](https://par.nsf.gov/biblio/10170565/media/xml) · [Perusquía-Hernández et al.](https://ar5iv.labs.arxiv.org/html/2008.08791) · [Brasoveanu, ACT-R notes](https://people.ucsc.edu/~abrsvn/ACT-R_subsymbolic_3.pdf) · [DynAffect restatement](https://pmc.ncbi.nlm.nih.gov/articles/PMC6433426/) · [Hamaker & Grasman 2015](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2014.01492/full) · [Mather & Sutherland 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC3110019/) · [NRC-VAD Lexicon](https://saifmohammad.com/WebPages/nrc-vad.html)
