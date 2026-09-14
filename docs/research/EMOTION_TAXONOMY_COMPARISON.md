# Emotion Taxonomies for a VN Facial-Expression Key + Mood-Congruent Memory

Research date: 2026. All quotes verbatim from the cited page. `COULD NOT VERIFY` marks items I could not confirm from a retrievable source in this session (several major publishers — Wikipedia, PMC, MDPI, Hindawi, Springer, most PDFs — were unreachable or CAPTCHA/403-gated).

**Target keys to reason about:** `smile / laugh / serious / pensive / embarrassed / depressed / expectant / strive`

---

## 1. Ekman's six basic emotions (Ekman & Friesen)

**Labels: 6 basic + 1 later (contempt) = 7 "universal emotions".** The Paul Ekman Group's own FAQ is explicit and is the cleanest citation for the 6-vs-7 question:

> "Dr. Ekman identified the six basic emotions as anger, surprise, disgust, enjoyment, fear, and sadness. His research shows the strongest evidence to date of a seventh emotion, which is contempt."
> — <https://www.paulekman.com/universal-emotions/>

The same page's headline list is now **7**: Anger, Contempt, Disgust, Enjoyment, Fear, Sadness, Surprise, and states:

> "Of all the human emotions we experience, there are seven universal emotions that we _all_ feel, transcending language, regional, cultural, and ethnic differences."

Note the label drift: the classic 1970s list said **happiness**; PEG's current site says **enjoyment**. Both refer to the same slot, so a VN key map must pick one string.

**Evidence base.** Ekman & Friesen's universality claim rests on cross-cultural judgement studies of photographed facial configurations plus fieldwork in Papua New Guinea (the Fore). The PEG page frames the evidence only qualitatively — "research shows the strongest evidence to date of seven universal facial expressions" and "transcending language, regional, cultural, and ethnic differences" (<https://www.paulekman.com/universal-emotions/>). The primary statement is Ekman, P. (1992), "An Argument for Basic Emotions", *Cognition & Emotion* 6(3–4):169–200, DOI `10.1080/02699939208411068` — **COULD NOT VERIFY a verbatim quote from the paper itself**; the DOI landing page and the full text were not retrievable with these tools (the paper is widely cited, e.g. in EmoBank's reference list at <https://ar5iv.labs.arxiv.org/html/2205.01996>).

**The 5×5 "Atlas of Emotions" expansion — the "5×5" framing is not accurate; verify before relying on it.** The Atlas is organised as **5 emotion "continents"**, not 25 cells:

> "The Emotions Atlas is based on the consensus among scientists (in the choice of the five emotion continents and the relationship of emotions to moods, personality and psychopathology)…"
> — <http://atlasofemotions.org/>

The five are anger, fear, disgust, sadness, enjoyment (confirmed independently at <https://www.centrepleineconscience.fr/meditation-pleine-conscience-mbsr/atlas-emotions-ligne>: "cinq émotions les plus universelles : la colère, la peur, le dégoût, la tristesse et la joie"). Intensity is a real axis of the Atlas — but as an ordering *within* each emotion, not as a second grid dimension:

> "Each emotion names a number of related but different states. These states vary not only in their nature, but in their intensity."
> — <http://atlasofemotions.org/>

The Atlas also has a **"Partially-Charted Emotions"** category: "Half or less than half of emotion scientists believe there is convincing evidence that each of the following is an emotion" (<http://atlasofemotions.org/>) — this is where contempt and the other non-consensus candidates sit. **COULD NOT VERIFY** a literal 5×5 = 25 grid of states from any source; treat "5×5" as a loose description of "5 emotions × N intensity-ranked states each".

**Intensity/arousal axis:** No numeric axis. Intensity exists only as the informal mild→intense ordering of the Atlas states (above) and in Ekman's "emotion families … variations on a shared theme" (<https://www.paulekman.com/universal-emotions/>).

**Designed for:** annotating **human facial expression** (and cross-cultural universality), not text classification, and not agent generation. This is the taxonomy's whole point.

**Licence / availability:** The *theory* is a published scientific model, free to use as a conceptual scheme (facts/ideas are not copyrightable). The PEG **website text, images and the Feelings Field Guide are commercial products** and are not licensed for redistribution. **Explicit licence statement and any redistributable machine-readable artefact: COULD NOT VERIFY** — PEG sells training tools and does not publish a CC licence. Practical consequence: you may implement "6/7 basic emotions" freely, but you must not scrape PEG's photographs or copy its page text into your repo.

**Verdict for the VN keys.** Expresses: `smile` (enjoyment, weak — see below), `depressed` (sadness — the only well-matched key), and partially `serious` (no entry; closest is anger/contempt as a stand-in for sternness). Cannot express: `laugh` (no intensity distinction — enjoyment covers both the smile and the laugh), `pensive` (no contemplative/neutral-absorbed state at all), `embarrassed` (absent from both the 6 and the 7), `expectant` (absent; anticipation is Plutchik's, not Ekman's), `strive` (no goal-directed/effort state — it is not an emotion in this model). **Score: 1 of 8 clean, ~2 partial.** Its real value here is as a *facial* vocabulary that your art pipeline will already have, not as a dialogue-tagging scheme.

---

## 2. Plutchik's wheel of emotions (Plutchik 1980)

**Labels: 8 primary emotions**, arranged as 4 bipolar pairs:

> "Dr. Plutchik proposed that there are eight primary emotions that serve as the foundation for all others: joy, sadness, acceptance, disgust, fear, anger, surprise, and anticipation."
> — <https://www.6seconds.org/2022/03/13/plutchik-wheel-emotions/>

The 8 primaries are **not** the pairs; the pairs are the opposition structure:

> "Joy is the opposite of Sadness. … Fear is the opposite of Anger. … Anticipation is the opposite of Surprise. … Disgust is the opposite of Trust."
> — <https://www.6seconds.org/2022/03/13/plutchik-wheel-emotions/>

So the four **axes** are joy–sadness, trust–disgust, fear–anger, surprise–anticipation. Note the same page uses **"acceptance"** and **"trust"** interchangeably for the 8th primary — a naming hazard if you key art assets off the string.

**Intensity axis: YES — and it is structural, not optional.** Plutchik's cone has three dimensions (intensity / similarity / polarity); intensity is the **vertical** one:

> "**Intensity:** The cone's vertical dimension represents intensity – emotions intensify as they move from the outside to the center of the wheel, which is also indicated by the color: The darker the shade, the more intense the emotion. For example, anger at its least level of intensity is annoyance. At its highest level of intensity, anger becomes rage. Or, a feeling of boredom can intensify to loathing if left unchecked."
> — <https://www.6seconds.org/2022/03/13/plutchik-wheel-emotions/>

Similarity = angular proximity on the wheel; polarity = the opposites above. The 8 primaries sit in the **second circle**, with a third (outer, mildest) and first (inner, most intense) ring:

> "**Primary:** The eight sectors are designed to indicate that there are eight primary emotions… Primary emotions are located in the second circle."
> — <https://www.6seconds.org/2022/03/13/plutchik-wheel-emotions/>

**Full 24-term intensity tier list — PARTIAL.** I verified two full tiers verbatim (annoyance → anger → rage; boredom → loathing, above) and the existence of "3 degrees of intensity" per primary (the standard presentation, e.g. the table "Plutchik's 8 basic emotions with 3 degrees of intensity each", <https://pmc.ncbi.nlm.nih.gov/articles/PMC8409663/table/pone.0256503.t001/> — **CAPTCHA-blocked, COULD NOT VERIFY contents**). The widely reproduced full table is:

| Primary | mild (outer) | basic (middle) | intense (inner) |
|---|---|---|---|
| joy | serenity | joy | ecstasy |
| trust / acceptance | acceptance | trust | admiration |
| fear | apprehension | fear | terror |
| surprise | distraction | surprise | amazement |
| sadness | pensiveness | sadness | grief |
| disgust | boredom | disgust | loathing |
| anger | annoyance | anger | rage |
| anticipation | interest | anticipation | vigilance |

**Only the joy, anger, sadness, disgust and trust rows are partially corroborated by the source above; the remaining cells are the standard Plutchik listing but I could NOT VERIFY them verbatim from a retrievable primary/authoritative source in this session.** Treat the table as a starting draft and re-verify before shipping.

**Dyads (mixtures):** "anticipation and joy combine to be optimism. Joy and trust combine to be love." (<https://www.6seconds.org/2022/03/13/plutchik-wheel-emotions/>) — the primary citation is Plutchik, R. (1980), "A general psychoevolutionary theory of emotion", *Emotion: Theory, Research and Experience* 1(3):3–33 (bibliographic entry confirmed in EmoBank's reference list, <https://ar5iv.labs.arxiv.org/html/2205.01996>).

**Designed for:** generating/modelling **agent and animal behaviour** — it is explicitly psychoevolutionary ("Plutchik studied animals, and he proposed a psychoevolutionary classification approach for general emotional responses", <https://www.6seconds.org/2022/03/13/plutchik-wheel-emotions/>). It is heavily reused for text classification (see §9 Emotional RAG) but was not built for it.

**Licence / availability:** The model is a published theory, freely implementable. There is **no canonical licensed machine-readable label file**. **Explicit licence for the wheel graphic/name: COULD NOT VERIFY**; the 6seconds page markets an eBook and a poster, so the *artwork* is not free.

**Verdict for the VN keys — the best fit of the classical eight.** Expresses: `smile` (joy, basic tier), `laugh` (joy → ecstasy tier, or the joy+trust → love dyad), `depressed` (sadness/grief tier), and — uniquely — **`pensive` is a literal Plutchik label**: *pensiveness* is the mild tier of sadness. `expectant` maps to **anticipation** (and its intense tier *vigilance*), the closest thing in any classical taxonomy to "waiting for something". Cannot express: `serious` (no stern/reserved state; anger is the nearest but that is a different affect), `embarrassed` (no embarrassment, shame, or self-consciousness slot anywhere), `strive` (anticipation is passive expectancy, not effortful goal-pursuit). **Score: 4 of 8 clean (`smile`, `laugh`, `pensive`, `expectant`), 1 partial (`depressed` via grief/sadness tier), 3 misses.**

---

## 3. Russell's circumplex model of affect (Russell 1980)

**The exact quote "emotions are distributed in a circular order": COULD NOT VERIFY.** I could not retrieve the paper text (JPSP 39(6), Dec 1980; APA PsycNET landing page <https://psycnet.apa.org/doiLanding?doi=10.1037%2Fh0077714> is paywalled and the full text was unreachable). **Do not quote that string as verbatim** until someone obtains the PDF. What I *can* attribute to Russell 1980 is the dimensional claim, via secondary sources:

> "…along affective dimensions (valence and arousal) that underpin the circumplex model of affect [Russell 2003]; [Buechel and Hahn 2017]."
> — GoEmotions, §2.2, <https://ar5iv.labs.arxiv.org/html/2005.00547>

> "…many formalizations [Russell 1980] [Watson and Tellegen 1985] include at least a second dimension, noted as arousal, that represents the (positive) level of intensity/excitement regarding to the given emotion."
> — Carbo & Molina, <https://ar5iv.labs.arxiv.org/html/2401.14436>

**The 8 octants (45° sectors) and their labels: COULD NOT VERIFY.** The commonly reproduced rendering is pleasure (0°), excitement (45°), arousal (90°), distress (135°), displeasure (180°), depression (225°), sleepiness (270°), relaxation (315°) — note this is a *rotation of the same 8 primary emotion words used as angular anchors*, which is why the sector labels look like emotions rather than dimensions. I found no retrievable source confirming this list this session; treat it as unverified. (The user's draft listing — "pleasure(0°) aroused, excitement(45°), arousal(90°)" — appears to conflate the anchor word with a qualifier; there is one label per 45° sector, not two.)

**Intensity/arousal axis: YES** — arousal is one of the two axes by definition, orthogonal to valence.

**"The model used by most dimensional sentiment tools" — partially supported.** Verifiable support: the NRC-VAD lexicon grounds itself in this lineage — "Several influential factor analysis studies have shown that the primary dimensions of word meaning are valence, arousal, and dominance (VAD) (Osgood et al., 1957; Russell, 1980, 2003)" (<https://saifmohammad.com/WebPages/nrc-vad.html>) — and EmoBank is a VAD corpus (<https://ar5iv.labs.arxiv.org/html/2205.01996>). The stronger claim that the *circumplex* (as opposed to the broader valence–arousal tradition) is what most tools implement is a fair generalisation but **COULD NOT VERIFY as a citable statistic**.

**Designed for:** modelling **human affect structure** (self-reported affective states, factor-analysed). It was taken up by text classification later; it is not a face-annotation scheme and not an agent-behaviour generator.

**Licence / availability:** the model is a free scientific theory; **no licensed artefact, no HuggingFace/GitHub canonical release. COULD NOT VERIFY any licence statement.**

**Verdict for the VN keys.** As a *key vocabulary* it expresses nothing directly — it has no discrete labels, so it cannot name `smile` or `pensive`. Its role in this project is the orthogonal one: it is the **right representation for the mood-congruent memory side**, because a (valence, arousal) point is continuous, cheap to average across a scene, and directly usable as a retrieval similarity term. Two of your 8 keys do map onto it usefully as coordinates: `smile`/`laugh` sit in the high-valence high-arousal quadrant, `depressed` in low-valence low-arousal. `strive` and `expectant` are *not* separable in VA — they differ in dominance, which this 2D model lacks (see §4). **Score: 0 of 8 as a label set; strong as a memory-retrieval vector.**

---

## 4. PAD / Mehrabian

**Exact 3 axes and ranges — your belief is mostly right but there is a real split in the literature.** The canonical framing is P = pleasure, A = arousal, D = dominance; the modern PAD work (Sentipolis) confirms the symmetric cube:

> "each dimension lies in [−1,1]"
> — Sentipolis, arXiv:2601.18027, <https://arxiv.org/abs/2601.18027> (via <https://aclanthology.org/2026.findings-acl.368/>)

But an equally cited applied variant restricts arousal to a non-negative range:

> "while pleasure and dominance take positive and negative values (between -1 and 1), arousal is always positive (between 0 and 1)"
> — Carbo & Molina, <https://ar5iv.labs.arxiv.org/html/2401.14436>

**So: P ∈ [−1,1], D ∈ [−1,1] are safe; A ∈ [−1,1] vs A ∈ [0,1] depends on which lineage you follow.** Pick one and document it, because it changes every distance you compute. Primary citation: Mehrabian, A. (1996), "Pleasure-arousal-dominance: A general framework for describing and measuring individual differences in temperament", *Current Psychology* 14(4):261–292, DOI `10.1007/BF02686918` (<https://www.semanticscholar.org/paper/4dd5d605ff615e9be0362eb29d39029a62d4c134>) — **COULD NOT VERIFY the paper's own range statement** (paywalled).

**The 8 PAD octants — your 8 labels are CORRECT.** Verified verbatim, and from the single most relevant source for your use case (a facial-expression → PAD octant library driven by Facial Action Units):

> "we defined a set of rules, which associated Action Units (AUs) to each octant of the Mehrabian's Pleasure-Arousal-Dominance (PAD) space and classifies the emotional state into: **DOCILE**, **HOSTILE**, **ANXIOUS**, **DISDAINFUL**, **BORED**, **EXUBERANT**, **DEPENDENT** and **RELAXED**."
> — <https://raw.githubusercontent.com/jsebaf/facetomood/main/README.md>

That library also supplies a **3-level hierarchy** which is directly reusable as a coarse fallback when your annotation is uncertain: 8 moods → "four moods: **ELATED**, **CALM**, **ANXIOUS** and **BORED**" → "**POSITIVE** and **NEGATIVE**" (<https://raw.githubusercontent.com/jsebaf/facetomood/main/README.md>).

**SAM (Self-Assessment Manikin) — 9-point confirmed, indirectly but solidly.** EmoBank states it modified the standard instrument:

> "We changed the 9-point SAM scales to 5-point scales (see Figure 2) in order to reduce the cognitive load during decision making for crowdworkers."
> — <https://ar5iv.labs.arxiv.org/html/2205.01996>

Attribution goes to Bradley & Lang (1994), "Measuring emotion: The self-assessment manikin and the semantic differential", *J. Behav. Ther. Exp. Psychiatry* 25(1):49–59 (reference list, same URL).

**PAD → basic-emotion mapping table: YES, one exists and here it is.** Table 1 of Carbo & Molina, attributed to Russell & Mehrabian 1977:

| Emotion | Pleasure | Arousal | Dominance |
|---|---|---|---|
| joy | 0.75 | 0.48 | 0.35 |
| sad | −0.63 | 0.27 | −0.33 |
| surprise | 0.40 | 0.67 | −0.13 |
| fearful | −0.64 | 0.60 | −0.43 |
| angry | −0.51 | 0.59 | 0.25 |

— <https://ar5iv.labs.arxiv.org/html/2401.14436>

**The standard PAD → nearest-basic-emotion formula.** The literature pattern is: compute the Euclidean distance from the agent's current PAD point to each emotion's prototype point, then convert distance to an activation weight through a threshold/saturation pair (Becker-Asano & Wachsmuth 2010):

> w_e = ( 1 − (d_e − Δ_e) / (φ_e − Δ_e) )
>
> "where d_e stands for the distance between the current PAD 3d position of the agent and of each basic emotion, Δ_e is the minimum threshold to activate an emotion and φ_e establishes the point of saturation of each emotion"
> — <https://ar5iv.labs.arxiv.org/html/2401.14436>

The "nearest" emotion is simply the prototype minimising d_e (equivalently maximising w_e). The same paper confirms the textbook cube picture: "In the PAD model, an emotion is then represented by a point in a three dimensional space."

**Maximum PAD Euclidean distance / normalisation = sqrt(6) ≈ 2.449 — COULD NOT VERIFY, and the arithmetic looks wrong.** The corner-to-corner diagonal of the [−1,1]³ cube is √(2²+2²+2²) = √12 = 2√3 ≈ **3.464**, not 2.449. √6 ≈ 2.449 would be the diagonal if each axis spanned [0,1] (√(1+1+1)=√3≈1.732, still not it) or if you were taking √3 × √2. **Do not hard-code √6 as "the maximum".** Compute the normaliser from your own axis ranges: for P,A,D ∈ [−1,1] use 2√3; if you adopt the Carbo variant with A ∈ [0,1], the maximum is √(4+1+4) = 3. Derive it, don't cite it.

**Designed for:** *generating* agent behaviour and describing **individual differences / temperament** — the 1996 paper is explicitly about "describing and measuring individual differences in Temperament" (<https://www.semanticscholar.org/paper/4dd5d605ff615e9be0362eb29d39029a62d4c134>). It is also the standard human **self-report** instrument (SAM). It is the only taxonomy here that is natively both a mood-state vector *and* a face-readable octant scheme.

**Licence / availability:** the model is a free scientific theory. **The SAM figures are copyrighted** — "Copyright of the original SAM by Peter J. Lang 1994" (<https://ar5iv.labs.arxiv.org/html/2205.01996>); EmoBank needed a grant of access: "We thank The Center for the Study of Emotion and Attention, University of Florida, for granting us access to the Self-Assessment-Manikin (SAM)." **Do not ship SAM artwork without permission.** The `facetomood` library is the only code artefact found; its README notes "This repository includes OpenCV source files. For OpenCV licence details see [OpenCv licence file](opencv/LICENCE)" but states **no licence for the PAD/AU rule set itself — COULD NOT VERIFY.**

**Verdict for the VN keys — the strongest overall fit for a *facial* key vocabulary.** Because it is 3-dimensional and continuous, you get intensity for free (distance from neutral), which is exactly what your `smile` vs `laugh` and `serious` vs `depressed` distinctions need and what Ekman/GoEmotions cannot give you. Directly expressible as octants: `smile`/`laugh` (EXUBERANT, +P+A+D), `depressed` (BORED, −P−A−D), `serious` (partially DISDAINFUL, −P−A+D — stern/reserved), and `strive` (HOSTILE, −P+A+D, is the closest: high arousal + high dominance + negative valence is the "driving against resistance" region — but it is a stretch, and HOSTILE is a bad name for a sympathetic character's effort). Weak on: `pensive` (needs low-arousal + slightly-negative-valence + low-dominance — lands in BORED/DEPENDENT territory, so it will collide with `depressed` unless you add a separate contemplative flag), `embarrassed` (−P, +A, −D → ANXIOUS octant, which is the right *region* but the label says "anxious"), `expectant` (+P, +A, −D → DEPENDENT — again right region, wrong name). **Score: ~4 of 8 clean, and the failures are naming failures not geometry failures** — which is the key insight: PAD gets you the *right region* for all 8, and you rename the octants to your VN keys.

---

## 5. OCC (Ortony, Clore & Collins 1988)

**Exact count: 22 emotion types — CONFIRMED with a verbatim quote.**

> "Ortony, Clore, and Collins [17] presented a cognitive structure of emotions which characterizes 22 emotion types (e.g. joy, hope, disappointment, distress and fear). According to their 'OCC' theory, emotions are valenced reactions which can be turned on by outcome of events, outcome of agents' actions, or attributes of objects."
> — Gholizadeh Ansari et al., arXiv:2105.05589, <https://ar5iv.labs.arxiv.org/html/2105.05589>

**Three branches — CONFIRMED**, in the ar5iv paper's wording: "outcome of events, outcome of agents' actions, or attributes of objects". The commonly cited wording you gave ("consequences of events / actions of agents / aspects of objects") is the same trichotomy with different nouns; both appear in the literature. The same source adds the goal/appraisal framing: "emotions are valenced reactions which can be turned on by…" and, for the intensity/goal machinery, "Π = ⟨Des, Praisew, DesOther, Liking⟩ is a tuple of appraisal dimensions according to the OCC theory. This determines how an event is appraised in terms of its desirability, praiseworthiness, desirability by others and liking."

**Structural conditions — verbatim (Table 1, arXiv:2105.05589):**

| Type | OCC specification |
|---|---|
| Joy | "pleased about a desirable consequence of event" |
| Distress | "displeased about an undesirable consequence of event" |
| Hope | "pleased about the prospect of a desirable consequence of event" |
| Fear | "displeased about the prospect of an undesirable consequence of event" |
| Satisfaction | "pleased about the confirmation of the prospect of a desirable consequence" |
| Disappointment | "displeased about the disconfirmation of the prospect of a desirable consequence" |

The same paper gives a worked disambiguation of joy vs satisfaction that is directly useful for a VN: "satisfaction is different. It is defined as being pleased about the confirmation of the prospect of a desirable consequence… joy can be triggered whenever the agent becomes certain that the goal is achievable, although not fulfilled yet."

**The canonical 22-token list — PARTIALLY VERIFIED.** The *count* (22) and the *branch structure* are verified verbatim. The exhaustive token list was **not** retrievable: the full OCC tree appears only as an image (Figure 1, "OCC structure of emotions [17]", <https://ar5iv.labs.arxiv.org/html/2105.05589>) and the primary book is paywalled (Cambridge Core chapter "Factors Affecting the Intensity of Emotions" returned "Temporary Disruption", <https://www.cambridge.org/core/books/abs/cognitive-structure-of-emotions/factors-affecting-the-intensity-of-emotions/9191DA2B2C5ABC60AEE5D49B1288623F>). The standard decomposition, which sums exactly to 22 and matches every partial source I saw:

- **Consequences of events** (well-being, self): joy, distress — *(both verified verbatim)*
- **Consequences of events** (fortunes-of-others): happy-for, resentment, gloating, pity
- **Consequences of events** (prospects-relevant): hope, fear, satisfaction, fears-confirmed, relief, disappointment — *(hope, fear, satisfaction, disappointment verified verbatim)*
- **Actions of agents** (self): pride, shame
- **Actions of agents** (other): admiration, reproach
- **Actions of agents** (compound, attribution × consequence): gratification, remorse, gratitude, anger
- **Aspects of objects**: love, hate

2 + 4 + 6 + 2 + 2 + 4 + 2 = **22** ✓. **The tokens I did not see quoted in this session are: happy-for, resentment, gloating, pity, fears-confirmed, relief, pride, shame, admiration, reproach, gratification, remorse, gratitude, anger, love, hate.** They are the standard OCC set and the arithmetic closes, but re-verify against the book before freezing the enum.

**Intensity variables — COULD NOT VERIFY the full set of three.** I confirmed that OCC does distinguish intensity structure and that a **global** intensity variable *sense of reality* exists — "The sense of reality variable is linked to the degree that an emotion-inducing situation seems real to an agent" (<https://ualberta.scholaris.ca/server/api/core/bitstreams/28d0acdf-1e07-46ca-9459-09e694696517/content> — PDF, text only via search snippet) — and the Cambridge chapter is literally titled "Factors Affecting the Intensity of Emotions". The standard description is **global intensity variables** (sense of reality, proximity, unexpectedness, arousal) vs **local intensity variables** (per-emotion-type, e.g. desirability/likelihood/effort for joy-distress). **The "third" variable you half-remember: COULD NOT VERIFY.** The most likely candidate is that OCC treats *arousal* as one of the global variables rather than as a third separate category — i.e. there may be only two categories, not three. Do not assert "3 intensity variables" without the book.

**Designed for:** *generating* agent behaviour and for cognitive-appraisal modelling. OCC is the canonical engine of computational emotion in agent architectures; arXiv:2105.05589 uses it to generate emotions in game-testing agents, and a 3D-game case study is its worked example.

**Licence / availability:** the book is **copyrighted, paid, and not redistributable** (Cambridge University Press). The taxonomy-as-ideas is free to implement; **no licensed machine-readable label file exists. COULD NOT VERIFY any free artefact.**

**Verdict for the VN keys — the best fit for *story* keys, the worst for *face* keys.** OCC is unique in expressing `expectant` and `strive` properly, because it is the only taxonomy here with a **prospect/confirmation** structure and an **effort/praiseworthiness** structure:
- `expectant` = **hope** ("pleased about the prospect of a desirable consequence of event") — exact match, better than Plutchik's anticipation because it carries the goal-directedness.
- `strive` = the desirability × likelihood × effort region around **hope + pride** (pride = approving one's own action), plus the unresolved-prospect state; OCC is the only scheme where "working toward a goal with uncertain outcome" is a first-class computational state rather than an emotion word.
- `smile` / `laugh` = joy (with intensity carried by the global intensity variables, not the type).
- `depressed` = distress (and **disappointment** when it is prospect-driven — a much better narrative fit than generic sadness).
- `serious` = partially **reproach**/disapproval-flavoured, or the absence of joy/distress.

Cannot express: `pensive` (no contemplative state), `embarrassed` (shame exists but is *self-directed disapproval about one's own action*, which is close — arguably a partial match), `smile` vs `laugh` intensity split (types carry no intensity; you need the global/local variables wired up). **Score: 4 of 8 clean (`expectant`, `strive`, `depressed`, `smile`), 2 partial (`serious`, `embarrassed`), 2 misses (`laugh` as distinct from `smile`, `pensive`).** OCC is *also* the only scheme whose structural conditions can be computed from your event stream rather than annotated — a significant architectural advantage given a two-pass annotation layer.

---

## 6. GoEmotions (Demszky et al. 2020, arXiv:2005.00547)

**Count: 27 emotions + `neutral` = 28 categories. Your 27-vs-28 question resolves as: 27 *emotions*, 28 *labels* counting neutral.** Both framings appear in the paper itself:

> "We introduce GoEmotions, the largest manually annotated dataset of 58k English Reddit comments, labeled for 27 emotion categories or Neutral."
> — abstract, <https://ar5iv.labs.arxiv.org/html/2005.00547>

> "| Number of examples | 58,009 | / | Number of emotions | 27 + neutral |"
> — Table 2, same URL

**Full label list, verbatim from the official README (best citation — it is the canonical artefact):**

> "The emotion categories are: _admiration, amusement, anger, annoyance, approval, caring, confusion, curiosity, desire, disappointment, disapproval, disgust, embarrassment, excitement, fear, gratitude, grief, joy, love, nervousness, optimism, pride, realization, relief, remorse, sadness, surprise_."
> — <https://cdn.jsdelivr.net/gh/google-research/google-research@master/goemotions/README.md>

That is exactly 27. Note it contains **`embarrassment`** — one of your 8 keys — which almost no other taxonomy here has.

**Multi-label: YES, confirmed.** Raters could select several; the model uses a sigmoid loss:

> "Raters were free to select multiple emotions, but were asked to only select those ones for which they were reasonably confident that it is expressed in the text."
> — <https://ar5iv.labs.arxiv.org/html/2005.00547>

> "We add a dense output layer on top of the pretrained model for the purposes of finetuning, with a sigmoid cross entropy loss function to support multi-label classification."
> — same URL

Label cardinality: 83% of examples have 1 label, 15% have 2, 2% have 3, 0.2% have 4+ (Table 2). Also relevant for a mood-congruent memory store: the paper **already publishes a hierarchy** — a 4-way sentiment level (positive/negative/ambiguous/neutral) and an Ekman level, with the explicit mapping "_sadness_ (maps to: _sadness_, _disappointment_, _embarrassment_, _grief_, _remorse_)" and "_joy_ (all _positive_ emotions)" (<https://ar5iv.labs.arxiv.org/html/2005.00547>). That gives you a ready-made coarse fallback tier.

**Intensity/arousal axis: NO — explicitly rejected.** "We do not want to include emotions that are too similar, since that makes the annotation task more difficult." Intensity is present only as *correlation structure* between labels, discovered post hoc: "emotions that are related in intensity (e.g. _annoyance_ and _anger_, _joy_ and _excitement_, _nervousness_ and _fear_) have a strong positive correlation" (<https://ar5iv.labs.arxiv.org/html/2005.00547>). **So `smile` vs `laugh` is *not* recoverable from a GoEmotions label** — you would need `joy` vs `amusement` plus `excitement`, which is a heuristic, not an axis.

**Designed for:** **classifying text** — it is the only taxonomy in this document built from the ground up for text-based emotion classification, and the paper is explicit that no prior work had identified principal categories for emotion recognition *in the domain of text*.

**Licence / availability.** HuggingFace: <https://huggingface.co/datasets/google-research-datasets/go_emotions>. **The licence is widely reported as Apache-2.0, but COULD NOT VERIFY — every fetch to `huggingface.co` (dataset page, raw README, `/api/datasets/...`, `datasets-server`) failed with a transport error in this session.** The GitHub home is `google-research/google-research/tree/master/goemotions` (<https://github.com/google-research/google-research/tree/master/goemotions>); the top-level google-research repo is Apache-2.0, but **verify the dataset card's own licence field before shipping.** Data size: 58,009 examples; filtered split 43,410 train / 5,426 dev / 5,427 test.

**Verdict for the VN keys — the best *text*-native fit, with one glaring hole.** Expresses: `smile` (joy), `laugh` (amusement — and unlike Ekman, GoEmotions has *both*, though it does not tell you which is "bigger"), `embarrassed` (**embarrassment** — a literal label, the only taxonomy here that has it), `depressed` (sadness + grief + disappointment, with the published Ekman-level mapping giving you the rollup), `expectant` (partially: **anticipation** is absent, but **optimism** + **desire** + **curiosity** together occupy the region), `serious` (partially: **disapproval** / **realization** / low-arousal `neutral`). Cannot express: `pensive` (no contemplative state; `neutral` and `realization` are the nearest, and `realization` is an event, not a mood), `strive` (no effort/goal-pursuit state; `determination`-like labels were deliberately excluded to reduce overlap). **Score: 5 of 8 clean, 2 partial, 1 miss.** The `neutral` label is itself a real asset: VN narration contains a lot of affectively flat lines and GoEmotions gives you a principled place to put them.

---

## 7. EmoBank (Buechel & Hahn, EACL 2017)

**Correction to the arXiv ID you supplied: `arXiv:1710.00107` is not EmoBank** — it resolves to "Correlated Prompt Fission Data in Transport Simulations" (Talou et al., Los Alamos), a nuclear physics review (<https://ar5iv.labs.arxiv.org/html/1710.00107>). **The correct preprint is `arXiv:2205.01996`**, <https://ar5iv.labs.arxiv.org/html/2205.01996>. The original venue is EACL 2017, <https://aclanthology.org/E17-2092/>.

**Annotation scheme: VAD, but on a 5-point — not 6-point — modified SAM.**

> "We describe EmoBank, a corpus of 10k English sentences balancing multiple genres, which we annotated with dimensional emotion metadata in the Valence-Arousal-Dominance (VAD) representation format."
> — abstract, <https://ar5iv.labs.arxiv.org/html/2205.01996>

> "We changed the 9-point SAM scales to 5-point scales (see Figure 2) in order to reduce the cognitive load during decision making for crowdworkers."
> — same URL

So your "6-point Likert?" guess is wrong in both directions: the **standard SAM is 9-point**, and EmoBank **modified it to 5-point**. Each sentence got **5 annotators per dimension per perspective = 30 ratings per sentence** ("a total of 30 ratings were gathered per sentence (five ratings for each of the three VAD dimensions and two annotation perspectives, Writer and Reader)"). One contaminating artefact worth knowing: the rating (1,1,1) was "heavily overrepresented… We interpret this skewed coding distribution as a bias mainly due fraudulent responses", and ~10% of ratings were deleted on that basis.

**Corpus size: 10,548 raw → 10,062 filtered sentences.** Genre-balanced across news headlines (Se07), blogs, essays, fiction, letters, newspapers, travel guides (Table 1). The paper claims it is "by far the largest corpus for dimensional emotion models".

**Bi-representational bonus:** the Se07 subset also carries **Ekman's six basic emotions on a [0,100] scale** — "Se07, on the other hand, bears annotations according to Ekman's six Basic Emotion (see Section 2) on a [0,100] scale, respectively" — and the paper demonstrates a kNN mapping between VAD and the 6 basic emotions that reaches or beats human agreement for Joy, Anger, Sadness and Fear (Table 3; average model r = .52 vs human IAA r = .54). **This is a directly useful, empirically validated VAD↔categorical bridge for your project.**

**Valence/arousal/dominance ranges:** the corpus stores **aggregated mean ratings on the 1–5 scale** (neutral = 3; the paper defines emotionality as "the absolute difference of a sentence's aggregated rating from the neutral rating (3, in our case)"). So **the EmoBank range is [1,5], not [−1,1]** — you must rescale to feed a PAD-style store. **COULD NOT VERIFY** whether the released CSV stores the raw 1–5 means or a rescaled variant; check `corpus/emobank.csv` before wiring it in.

**Designed for:** **classifying/annotating text**, with an explicit defence of the dimensional format for NLP. It is *not* a face scheme and not an agent-builder.

**Licence / availability: CC-BY-SA 4.0 — CONFIRMED verbatim.**

> "This work is licensed under CC-BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/"
> — <https://raw.githubusercontent.com/JULIELab/EmoBank/master/README.md>

GitHub: <https://github.com/JULIELab/EmoBank>. **Note the share-alike obligation** — CC-BY-SA propagates to derivative distributions, which matters if you ever ship a derived emotion lexicon. The paper's own text says "EmoBank is freely available for academic purposes", but the README's CC-BY-SA 4.0 is the operative licence.

**Verdict for the VN keys.** Like Russell, EmoBank gives you **no labels at all** — it is a VAD vector corpus, so it cannot name any of your 8 keys. Its value is threefold and real: (a) it is the **best available training/eval data for the memory-side VAD regressor**; (b) the Se07 subset gives you **supervised VAD→Ekman-6 mapping** for free; (c) it validates the reader-vs-writer distinction — **`reader` emotion is the better-annotated perspective** (r = .634 vs .605) with higher emotionality. For a VN, the *writer* perspective corresponds to the character speaking and the *reader* perspective to the player perceiving — EmoBank explicitly models both, which is exactly the split your engine needs if you ever want mood-congruent retrieval keyed on the *player's* felt mood rather than the character's. **Score: 0 of 8 as a label set; highest-value training source for the vector side.**

---

## 8. Warriner, Kuperman & Brysbaert (2013) and the NRC-VAD lexicon (Mohammad 2018)

### 8a. Warriner et al. 2013

**Exact N: 13,915 English lemmas — CONFIRMED.** Citation: Warriner, A. B., Kuperman, V., & Brysbaert, M. (2013), "Norms of valence, arousal, and dominance for 13,915 English lemmas", *Behavior Research Methods* 45(4):1191–1207, DOI `10.3758/s13428-012-0314-x` (<https://link.springer.com/article/10.3758/s13428-012-0314-x>; PubMed 23404613). The N and title are corroborated across every index I hit, including EmoBank's reference list ("Norms of valence, arousal, and dominance for 13,915 English lemmas. Behavior Research Methods, 45(4):1191–1207", <https://ar5iv.labs.arxiv.org/html/2205.01996>).

**9-point scale: COULD NOT VERIFY verbatim from the paper** — Springer redirects to `idp.springer.com` and the PDF is unfetchable with these tools. The 9-point SAM provenance is nonetheless solid by way of EmoBank's statement that it "changed the **9-point SAM scales** to 5-point scales" and that its instructions "are based on the ones used by [Warriner et al.] for creating their highly influential VAD lexicon" (<https://ar5iv.labs.arxiv.org/html/2205.01996>) — i.e. Warriner used the 9-point SAM. Treat "9-point" as well-supported but re-confirm the exact anchors (1–9, neutral 5) from the paper's Method before relying on it numerically.

**Where to get it:** the Springer article page (<https://link.springer.com/article/10.3758/s13428-012-0314-x>); a McMaster repository copy (<https://digitalcommons.mcmaster.ca/handle/11375/22965>); it is also redistributed inside **JULIELab/XANEW** (<https://github.com/JULIELab/XANEW/blob/master/README.md>) and indexed in **concepticon/norare-data**, which documents the variable names — e.g. `ENGLISH_VALENCE_MEAN_FEMALE`, "Mean value of valence ratings on…" (<https://github.com/concepticon/norare-data/blob/0d6704377cc364d3d94c8605c7dc20b2de378c02/norare.tsv>). **Licence: COULD NOT VERIFY** — check the Springer page's licence field and the XANEW repo; academic norm-norms datasets are usually free for research but are not always explicitly licensed.

### 8b. NRC-VAD (Mohammad 2018)

**Exact N: 20,000+ English words for v1 (2018); 55,000+ for v2.1 (March 2025) — CONFIRMED, with the version distinction made explicit on the project page.**

> "The NRC Valence, Arousal, and Dominance (VAD) Lexicon includes a list of more than 20,000 English words and their valence, arousal, and dominance scores. For a given word and a dimension (V/A/D), the scores range from 0 (lowest V/A/D) to 1 (highest V/A/D). The lexicon with its fine-grained real-valued scores was created by manual annotation using Best–Worst Scaling."
> — <https://saifmohammad.com/WebPages/nrc-vad.html>

**Scale: continuous [0,1] — note this is NOT the [−1,1] PAD cube.** Any PAD store must rescale (`2x − 1`). The page also confirms the dimension definitions: "valence is the positive–negative or pleasure–displeasure dimension; arousal is the excited–calm or active–passive dimension; and dominance is the powerful–weak or 'have full control'–'have no control' dimension."

Papers: Mohammad, S. M. (2018), "Obtaining Reliable Human Ratings of Valence, Arousal, and Dominance for 20,000 English Words", ACL 2018 (<https://aclanthology.org/P18-1017/>); and v2, "NRC VAD Lexicon v2: Norms for Valence, Arousal, and Dominance for over 55k English Terms", arXiv:2503.23547 (<https://arxiv.org/abs/2503.23547>).

**Licence: your belief is CONFIRMED — free for research, NOT redistributable, commercial use requires a separate licence.** Verbatim from the Terms of Use:

> "**Research Use:** The lexicon mentioned in this page can be used freely for non-commercial research and educational purposes."
> "**No Redistribution:** Do not redistribute the data. Direct interested parties to the lexicon home page. You may not rent or license the use of the lexicon nor otherwise permit third parties to use it."
> "**Commercial License:** If interested in commercial use of the lexicon, contact the author: saif.mohammad@nrc-cnrc.gc.ca"
> — <https://saifmohammad.com/WebPages/nrc-vad.html>

The download links themselves are labelled "(Non-Commercial Use Only -- Research or Educational)". **This is a commercial-restricted licence and a real problem for a shippable game** — you cannot bundle NRC-VAD with the engine, and if your game is commercial you need a licence from NRC. Also note v2.1 (March 2025) is the current release and the page carries an ethics/data statement (<https://saifmohammad.com/WebDocs/EmoLex-Ethics-Data-Statement.pdf>).

**Verdict on both (memory side, not key side).** Neither names any of your 8 keys. Both are **word-level** resources, so they are the wrong granularity for tagging dialogue lines directly — their correct use is as (a) a features/prior source for a VAD regressor that tags whole lines, and (b) a **fast fallback**: for a line with no trained-model coverage, average the NRC-VAD or Warriner vectors of its content words and use that as the memory vector. Warriner's 13,915 lemmas are the better choice if you need dominance and want an academically free artefact; NRC-VAD is larger and more reliable but is licence-encumbered for commercial use.

---

## 9. What serious memory/agent systems actually use

### 9a. Emotional RAG (arXiv:2410.23041) — **CONFIRMED, your description is accurate**

> "The output is an emotional vector of the query, which is an 8-dimensional vector containing 8 different emotional states, i.e., **joy, acceptance, fear, surprise, sadness, disgust, anger, and anticipation**. The 8 emotional states are defined according to the emotion circle in [28]. The value of each dimension is an **integer between 1 and 10**, which measures the intensity of the emotional state."
> — <https://ar5iv.labs.arxiv.org/html/2410.23041>

Those 8 are exactly **Plutchik's 8 primaries** ("the emotion circle in [28]" = Plutchik). So: Plutchik's 8, as an 8-dim vector, values 1–10 — **all three parts of your claim verified**. Stored per memory fragment as `emotion_m^k` alongside `semantic_m^k`. Retrieval:

> score_semantic^k = ℰ(semantic_q, semantic_m^k)
> score_emotional^k = 1 − 𝒞(emotion_q, emotion_m^k)
> score_final^k = ℳ(score_semantic^k, score_emotional^k)

with four fusion strategies — combination (add C-A, multiply C-M) and sequential (semantic-first S-S: memories "retrieved based on their semantic scores and then re-ranked according to their emotional scores"; emotional-first S-E) — keeping "the top 10 memory fragments". Motivation is Bower's Mood-Dependent Memory theory. Datasets: InCharacter (32 roles), CharacterEval (31), Character-LLM (9). Code: <https://github.com/BAI-LAB/EmotionalRAG>. **Exact literal JSON/persistence field name: COULD NOT VERIFY** — the paper names only the vector variables.

**Why this matters for you:** it is the cleanest precedent that an 8-dim Plutchik vector + cosine on the emotion channel, fused into the retrieval score, measurably improves persona consistency — and it is essentially the architecture your digest/RAG layer would need.

### 9b. Sentipolis (arXiv:2601.18027) — **REAL, not a fake ID**

Verified at <https://arxiv.org/abs/2601.18027> and published as Findings of ACL 2026 (<https://aclanthology.org/2026.findings-acl.368/>): "Sentipolis: Emotion-Aware Agents for Social Simulations" (Fu, Chen, Xiao, Xuan, Busso, Diab), submitted 25 Jan 2026, v2 21 Apr 2026.

**Emotion model: continuous PAD.** Each of the three dimensions "lies in [−1,1]" — this is the citation that confirms your PAD range belief. Decay is exponential with a **120-minute half-life**: `s(t+Δt) = s(t) · 2^(−Δt/T½)`.

**How emotion feeds retrieval — matches your "cumulative poignancy" recollection:**

> "we couple emotion to memory by storing events and reflections together with their PAD-derived emotion tags"
> "emotion-tagged retrieval resurfaces affectively relevant experiences at generation time"

Emotion also **triggers** slow reflection updates. And the PAD→label step is a KNN over human anchors: "KNN on real human PAD data points … map the state to a **Plutchik-style emotional label**".

**The exact enumerated Plutchik label list and the literal field name: COULD NOT VERIFY.** They live in Appendix A.2; arXiv HTML and ar5iv truncate before the appendix and the ACL PDF is binary and unfetchable with these tools (4 attempts). **Open question for anyone picking this up:** whether Sentipolis stores the *continuous PAD triple* or the *discrete Plutchik label* on the memory record — the paper's wording ("PAD-derived emotion tags") suggests the label, with PAD retained as agent state. That distinction matters architecturally.

### 9c. Other agent-memory systems with an explicit affect field

| System | Field name | Label set / vector | Role in retrieval | Verified |
|---|---|---|---|---|
| **Emotional RAG** (2410.23041) | `emotion_q`, `emotion_m^k` | 8-dim Plutchik (joy, acceptance, fear, surprise, sadness, disgust, anger, anticipation), ints 1–10 | **RE-RANK / fuse** into `score_final` | ✅ <https://ar5iv.labs.arxiv.org/html/2410.23041> |
| **Sentipolis** (2601.18027) | PAD-derived "emotion tags" | continuous PAD ∈ [−1,1]³ → Plutchik-style label via KNN | **RETRIEVE + TRIGGER** reflection | ✅ range/mechanism; ⚠️ label list unverified — <https://arxiv.org/abs/2601.18027> |
| **DAM-LLM** (2510.27418) | `sentiment_profile` (also `object_type`, `aspect`, entropy H) | 3-way polarity confidence: positive / negative / neutral | **FILTER** (metadata exact-match on object_type+aspect) then semantic **RE-RANK**; entropy **TRIGGERS** compression (H<0.8 mature, H>1.4 pruned) | ✅ <https://ar5iv.labs.arxiv.org/html/2510.27418> |
| **MemEmo** (2602.23944) | emotion label `e_t` + `A_attr = ⟨Sub, Obj, Cause, Int⟩` | EARL/HUMAINE: **49 emotion categories** + polarities + 3 intensity levels (high/medium/low) | **Emotion Affective Retrieval** benchmark | ✅ <https://arxiv.org/abs/2602.23944> |
| **Memory Bear** (2512.20651) | "emotional weight" | none specified | raises retrieval priority | ⚠️ industry preprint, no formula — <https://arxiv.org/abs/2512.20651> |
| **MADial-Bench** (2409.15240) | memory record columns: **Time \| Emotion \| Scene \| Event** | "four situations: **happy, sad, anxious, and disappointed** emotion of the user" (18 emotional categories were curated; 5 scenes) | emotion **TRIGGERS** proactive recall | ✅ <https://arxiv.org/abs/2409.15240> |
| **Human-Like Lifelong Memory** (2603.29023) | per-KG-node "valence vector", 5 components | **2-dim (valence, arousal)** inside the node vector | emotional charge is 1 of 6 salience channels that can "independently protect information" → **TRIGGER** promotion; spreading activation retrieves | ✅ design paper only, no implementation — <https://arxiv.org/abs/2603.29023> |

**Notably NOT emotion-aware (verified against the memory-object definition):**

- **Generative Agents** (Park et al., 2304.03442) — **no affect field at all.** The memory object is "a natural language description, a creation timestamp, and a most recent access timestamp"; the code's `ConceptNode` fields are `created, expiration, last_accessed, subject, predicate, object, description, embedding_key, poignancy, keywords, filling` (<https://raw.githubusercontent.com/joonspk-research/generative_agents/main/reverie/backend_server/persona/memory_structures/associative_memory.py>). **The field people mistake for emotion is `poignancy`** — it is an *importance* scalar rated 1–10 ("On the scale of 1 to 10 … rate the likely poignancy of the following piece of memory"), and it is what **triggers** reflection: "we generate reflections when the sum of the importance scores for the latest events perceived by the agents exceeds a threshold (150 in our implementation)". Retrieval is `score = α_recency·recency + α_importance·importance + α_relevance·relevance`, and **the paper and the released code disagree on the weights** — the paper says "In our implementation, all αs are set to 1", while the code uses `gw = [0.5, 3, 2]` (<https://raw.githubusercontent.com/joonspk-research/generative_agents/main/reverie/backend_server/persona/cognitive_modules/retrieve.py>); `extract_importance` literally returns `node.poignancy`. Recency decay factor 0.995. **This is the key negative result for your design: the most-copied agent memory architecture in the field has no emotion channel — its "poignancy" is importance, not affect.**
- **MemoryBank** (2305.10250) — no emotion field; emotion appears only inside summarisation prompts; retrieval is dual-tower dense/FAISS with Ebbinghaus forgetting `R = e^(−t/S)`.
- **A-Mem** (2502.12110) — note fields `{c_i, t_i, K_i, G_i, X_i, e_i, L_i}`, no emotion; cosine top-k.
- **Mem0** (2504.19413), **Zep** (2501.13956), **MemGPT/Letta** (2310.08560), **MemoRAG** (2409.05591) — no emotion channel in any of them.
- **ES-MemEval** (2602.01885) — EvoEmo sessions carry an "emotion category" annotation, but **the label set is COULD NOT VERIFY** (it sits in an appendix beyond the truncation point) and it is **not** used as a retrieval field — retrieval is pure semantic ("a dense retriever (bge-m3) retrieves the top-4 most relevant full-session contexts from a FAISS index"). Code: <https://github.com/slptongji/ES-MemEval>.

**No peer-reviewed 2024–2026 survey was found that tabulates per-system emotion field names — COULD NOT VERIFY.** The closest is MemEmo's Table 1, which compares frameworks on emotion-analysis *capabilities* rather than field names.

**Bottom line for your architecture:** the only *verified* systems that both store an explicit affect field **and** use affect in the retrieval score are **Emotional RAG** (8-dim Plutchik 1–10, cosine on emotion vectors, fused/re-ranked with semantics) and **DAM-LLM** (`sentiment_profile` 3-way polarity, entropy-gated). **Sentipolis** is the strongest PAD-tagged-memory precedent and the closest analogue to a character-driven VN, but its exact label list and field name remain unverified.

---

## 10. Comparison table

| Taxonomy | #labels | Intensity / arousal axis? | Built for | Licence / availability | Can express `smile` / `laugh` / `serious` / `pensive` / `embarrassed` / `depressed` / `expectant` / `strive`? | URL |
|---|---|---|---|---|---|---|
| **Ekman basic emotions** | **6** basic (anger, surprise, disgust, enjoyment, fear, sadness) + **contempt** as 7th universal | ✗ No numeric axis; informal mild→intense ordering only in the Atlas states | **Face annotation** (cross-cultural facial expression) | Theory free; **PEG site text/images/Field Guide are commercial**; no machine-readable artefact. Licence statement **COULD NOT VERIFY** | ✗ **1/8** — `depressed` only. ✗ `smile` vs `laugh` (no intensity), ✗ `serious`, ✗ `pensive`, ✗ `embarrassed`, ✗ `expectant`, ✗ `strive` | <https://www.paulekman.com/universal-emotions/> · <http://atlasofemotions.org/> |
| **Plutchik's wheel** | **8** primaries (joy, trust/acceptance, fear, surprise, sadness, disgust, anger, anticipation) = **24** including 3 intensity tiers | **✓ YES — intensity is a structural cone dimension** (vertical); ratings in the tier word itself, no numeric scale | **Agent/animal behaviour generation** (psychoevolutionary), widely reused for text | Theory free; no canonical licensed label file; **wheel artwork is sold, licence COULD NOT VERIFY** | **4/8 ✓** `smile`(joy) `laugh`(ecstasy) `pensive`(**pensiveness — literal label**) `expectant`(anticipation) · ~`depressed`(grief) · ✗ `serious` ✗ `embarrassed` ✗ `strive` | <https://www.6seconds.org/2022/03/13/plutchik-wheel-emotions/> |
| **Russell circumplex** | **0** discrete labels (**8** octants, unverified) | **✓ YES — arousal is axis #2**, orthogonal to valence | **Human affect structure** (self-report, factor analysis); the lineage most dimensional sentiment tools sit in | Theory free; **no licensed artefact**; licence **COULD NOT VERIFY** | ✗ **0/8 as labels.** As a vector: `smile`/`laugh` = +V+A, `depressed` = −V−A; **cannot separate `expectant` from `strive`** (needs dominance) | <https://psycnet.apa.org/doiLanding?doi=10.1037%2Fh0077714> · <https://ar5iv.labs.arxiv.org/html/2005.00547> |
| **PAD / Mehrabian** | **8** octants (EXUBERANT, DEPENDENT, RELAXED, DOCILE, ANXIOUS, HOSTILE, DISDAINFUL, BORED) + 4-level and 2-level rollups | **✓ YES — arousal is axis #2; 3 continuous axes** P∈[−1,1], D∈[−1,1], A∈[−1,1] *or* [0,1] — **two variants in the literature** | **Agent generation** (3D emotion space + temperament) *and* **self-report** (9-point SAM) *and* **face-readable** (AU→octant) | Theory free; **SAM artwork is copyrighted** (Lang 1994) — permission needed; `facetomood` code licence **COULD NOT VERIFY** | **~4/8 ✓** `smile`/`laugh`(EXUBERANT) `depressed`(BORED) `serious`(DISDAINFUL) · `embarrassed`→ANXIOUS region, `expectant`→DEPENDENT region, `strive`→HOSTILE region (**right geometry, wrong names — rename the octants**) · ✗ `pensive` (collides with `depressed`) | <https://ar5iv.labs.arxiv.org/html/2401.14436> · <https://raw.githubusercontent.com/jsebaf/facetomood/main/README.md> · <https://www.semanticscholar.org/paper/4dd5d605ff615e9be0362eb29d39029a62d4c134> |
| **OCC** | **22** emotion types (count ✓ verified; full token list partially verified) across 3 branches | ~ Intensity structure exists (global + local variables); **numeric scale none**; the "3rd variable" is **COULD NOT VERIFY** | **Agent generation** (cognitive appraisal; computational emotion architectures) | **Book is copyrighted & paid (CUP)**; no free artefact; **COULD NOT VERIFY** any licence | **4/8 ✓** `expectant`(**hope — exact**) `strive`(hope+pride, the only scheme with goal-pursuit as a state) `depressed`(distress/disappointment) `smile`(joy) · ~`serious`(reproach) ~`embarrassed`(shame) · ✗ `laugh` (no intensity) ✗ `pensive` | <https://ar5iv.labs.arxiv.org/html/2105.05589> · <https://www.cambridge.org/core/books/abs/cognitive-structure-of-emotions/factors-affecting-the-intensity-of-emotions/9191DA2B2C5ABC60AEE5D49B1288623F> |
| **GoEmotions** | **27** emotions **+ `neutral` = 28** labels | ✗ **Explicitly rejected** (overlap-limited taxonomy); intensity only as post-hoc label correlations | **Text classification** (built from scratch for text; the only one) | HuggingFace <https://huggingface.co/datasets/google-research-datasets/go_emotions>; **reported Apache-2.0 but COULD NOT VERIFY** (all HF fetches failed) | **5/8 ✓** `smile`(joy) `laugh`(amusement) `embarrassed`(**embarrassment — literal**) `depressed`(sadness+grief) ~`expectant`(optimism+desire) ~`serious`(disapproval/neutral) · ✗ `pensive` ✗ `strive` | <https://ar5iv.labs.arxiv.org/html/2005.00547> · <https://cdn.jsdelivr.net/gh/google-research/google-research@master/goemotions/README.md> |
| **EmoBank** | **0** discrete (VAD vector); + Ekman-6 on the Se07 subset | **✓ YES — V, A, D**, **5-point** modified SAM (standard SAM is 9-point); range **[1,5]**, neutral 3 | **Text classification / annotation** (dimensional NLP corpus) | **CC-BY-SA 4.0 ✓ confirmed** (share-alike propagates!) — <https://github.com/JULIELab/EmoBank> | **0/8 as labels.** Vector + a validated **VAD→Ekman-6 kNN bridge** (r=.52 vs human .54). **`reader` perspective is better annotated** — the split a VN actually needs | <https://ar5iv.labs.arxiv.org/html/2205.01996> · <https://raw.githubusercontent.com/JULIELab/EmoBank/master/README.md> |
| **Warriner 2013** | **13,915** lemmas × VAD | **✓ YES** — 9-point SAM (*well-supported, exact anchors COULD NOT VERIFY*) | **Human norming** (word-level affective norms) | Springer <https://link.springer.com/article/10.3758/s13428-012-0314-x>; also in XANEW & norare-data; **licence COULD NOT VERIFY** | **0/8 as labels.** Word-level: use as VAD features / fallback averaging for untagged lines. The commercially safer VAD source of the two | <https://link.springer.com/article/10.3758/s13428-012-0314-x> · <https://digitalcommons.mcmaster.ca/handle/11375/22965> |
| **NRC-VAD** | **20,000+** words (v1, 2018); **55,000+** terms (v2.1, Mar 2025) | **✓ YES** — V, A, D continuous **[0,1]** (not [−1,1]) | **Human norming** (word-level; Best–Worst Scaling) | **⚠️ NON-COMMERCIAL ONLY + NO REDISTRIBUTION ✓ confirmed verbatim; commercial licence required** — <https://saifmohammad.com/WebPages/nrc-vad.html> | **0/8 as labels.** Same role as Warriner, larger + more reliable, but **licence-encumbered — do not bundle in a commercial build** | <https://saifmohammad.com/WebPages/nrc-vad.html> · <https://aclanthology.org/P18-1017/> |

---

## 11. The two-sided recommendation this comparison supports

The eight target keys split cleanly into **two different jobs**, and no single taxonomy does both well:

**Job A — the facial-expression key (`smile / laugh / serious / pensive / embarrassed / depressed / expectant / strive`).**
These are *not* a classical emotion taxonomy. They are **mood/attitude/register** labels, closer to Plutchik's intensity tiers than to Ekman's basics. The evidence:
- `pensive` is **literally a Plutchik tier word** (mild sadness) — which is a warning, because in Plutchik it means "a little sad", not "thoughtful". If your art for `pensive` is a reflective chin-stroke, Plutchik's word will mislead any annotator who knows the model.
- `strive` is not an emotion in any of the eight schemes. It is a *goal-directed effort state* — OCC's prospect + praiseworthiness structure is the only place it lives, and OCC has no face.
- `laugh` vs `smile` is an **intensity** distinction, which only Plutchik (tier words) and PAD (distance from neutral) can make; Ekman, GoEmotions and OCC cannot.
- `embarrassed` exists **only** in GoEmotions (as `embarrassment`).
- `expectant` is best served by **OCC's hope** (prospect of a desirable consequence), second-best by Plutchik's anticipation, and only as a *region* by PAD (DEPENDENT octant).

Practical consequence: use **PAD as the internal representation** (it has intensity for free, it is face-readable via the `facetomood` AU→octant precedent, and every one of your 8 keys lands in a distinct region), and treat your 8 keys as **named points/regions in PAD space** rather than as members of any published taxonomy. If you must cite one published scheme for the key vocabulary, **Plutchik** covers the most keys (4/8 clean) and **GoEmotions** covers the most text-native ones (5/8 clean) — but neither covers `strive`, and `strive` plus `serious` are the two keys that force you to extend any borrowed scheme.

**Job B — mood-congruent memory retrieval.**
Use a **continuous VAD vector**, not a label. Verified precedent: Emotional RAG fuses a cosine-on-emotion-vector term with the semantic score and beats semantic-only retrieval; DAM-LLM filters on metadata then re-ranks; Sentipolis uses PAD ∈ [−1,1]³ with a 120-minute half-life decay and PAD-derived tags on memory records. Note that **Generative Agents — the most-copied memory architecture — has no emotion channel at all**; its `poignancy` field is *importance*, not affect, and is best understood as the reflection trigger, not as a mood signal. If you want mood-congruence you are adding a channel, not reusing one.

Two licence traps to route around: **NRC-VAD is non-commercial and non-redistributable** (a real problem for a shippable game — prefer Warriner, or license from NRC), and **EmoBank's CC-BY-SA 4.0 is share-alike**, so a derived lexicon you distribute must carry the same licence. **SAM artwork is copyrighted** (Lang 1994) and EmoBank itself had to request access — do not ship the manikins.

**Open items to resolve before implementation** (all marked `COULD NOT VERIFY` above): the exact OCC 22-token list and its third intensity variable; Sentipolis's enumerated label list and literal field name; the GoEmotions dataset-card licence; the exact Russell 1980 quote and octant labels; the Plutchik tiers not corroborated above; and the provenance of the `√6` PAD normaliser, which the arithmetic suggests should be `2√3 ≈ 3.464` for a [−1,1]³ cube.
