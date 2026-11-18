# Design: Website RAG Chatbot UI

> Zero-build frontend specification. A WhatsApp-familiar shell that renders verified banking answers as structured blocks. High trust, extreme readability, fast interaction.

## 1. Principles

- **Answer First, Sources Attached**: A direct lead-in, then structured blocks, then the citation drawer directly beneath.
- **Render What Was Verified**: The browser never parses markdown and never composes prose. It draws a typed view model produced server-side, so the screen cannot display a figure the pipeline did not verify.
- **Familiar Shell**: A messaging-app frame (header with presence, bubbles, ticks, pill input, typing dots) removes the learning curve of a chat product. The visual language is Emirates NBD's, not a generic dashboard.
- **Visual Fallback Contrast**: Refusals use an amber bubble, an amber `Not covered by the site` badge, and no cards or specs, so a reviewer can spot a decline instantly.
- **Zero Build Step**: Pure HTML5, vanilla JavaScript (`fetch`), and inline CSS. No npm, no bundler, no CDN runtime dependency: the page loads as one file and works offline of third-party scripts.
- **Type-Safe Contract**: The browser consumes exactly one Pydantic model, `UIChatResponse`, plus `GET /api/products` for the coverage pill.
- **Responsive Parity**: 100% usable from 360 px phones to desktop; the card rail scrolls horizontally with snap points, and the shell becomes a rounded panel at ≥768 px.

## 2. Layout Structure

```text
┌──────────────────────────────────────────────────────────────┐
│ (L) Lexi • Emirates NBD  ✔        [📦 21 Verified Products]  │
│     Qdrant Hybrid RAG • Sources verified      [☀] [↻]        │
├──────────────────────────────────────────────────────────────┤
│                    Today • Grounded Banking Session          │
│                                                              │
│  ┌────────────────────────────────────────────────┐          │
│  │ [DISCOVERY]                                    │          │
│  │ Here is an overview of the verified Credit...  │          │
│  │ ┌───────────┐ ┌───────────┐ ┌───────────┐      │          │
│  │ │ CARD      │ │ CARD      │ │ CARD      │  →   │          │
│  │ │ name      │ │ name      │ │ name      │      │          │
│  │ │ fee pill  │ │ fee pill  │ │ fee pill  │      │          │
│  │ │ Check →   │ │ Check →   │ │ Check →   │      │          │
│  │ └───────────┘ └───────────┘ └───────────┘      │          │
│  │ 🔗 Verified Sources (3) ▾                      │          │
│  │ 👍 👎            Thanks            14:32       │          │
│  └────────────────────────────────────────────────┘          │
│                                                              │
│                          ┌──────────────────────────────┐    │
│                          │ Which credit cards...?  ✓✓   │    │
│                          └──────────────────────────────┘    │
├──────────────────────────────────────────────────────────────┤
│ [What savings and account options...] [Compare Million...] → │
│ ( Ask about credit cards, fees, accounts, or eligibility... )│
└──────────────────────────────────────────────────────────────┘
```

## 3. Design Tokens

Two themes share one token set; the toggle writes `data-theme` on `<html>` and persists the choice in `localStorage`.

| Token | Dark | Light | Usage |
|---|---|---|---|
| `--bg-outer` | `#060b0e` | `#d1d7db` | Page behind the app shell |
| `--bg-chat` | `#0b141a` | `#efeae2` | Conversation surface |
| `--bg-bot-bubble` | `#202c33` | `#ffffff` | Bot bubble |
| `--bg-user-bubble` | `#005c4b` | `#d9fdd3` | User bubble |
| `--bg-card` | `#162026` | `#f7f8fa` | Product card, spec tile, sources panel |
| `--bg-input` | `#202c33` | `#ffffff` | Pill input |
| `--text-primary` | `#e9edef` | `#111b21` | Body copy |
| `--text-secondary` | `#8696a0` | `#54656f` | Labels, timestamps, metadata |
| `--accent-emerald` | `#00a884` | `#008069` | Primary accent, send button, source links |
| `--accent-gold` | `#f59e0b` | `#b45309` | Comparison badge, fallback bubble |
| `--accent-blue` | `#38bdf8` | `#0284c7` | FACT badge |
| `--border-subtle` | `rgba(255,255,255,.08)` | `rgba(0,0,0,.08)` | Bubble and panel borders |

Body copy and key labels meet WCAG 2.1 AA contrast in both themes. Colour is never the only signal: fallback also changes the badge text and removes the cards.

## 4. Component Specifications

### 1. Header
- Frosted bar (`backdrop-filter: blur(14px)`), circular emerald avatar with a pulsing presence dot, verified tick, and a two-line identity: product name, then grounding status.
- Coverage pill `📦 <n> Verified Products` is populated from `GET /api/products` and hides itself when the catalog is empty. The number is never hardcoded.
- Theme toggle (sun icon) and new-session reset (circular arrow, starts a fresh `session_id` and greeting).

### 2. Bot Response Bubble
- Surface uses `--bg-bot-bubble` with a hairline border and a 4 px top-left corner, matching the user bubble's mirrored corner.
- Meta row: intent badge (`FACT` blue, `DISCOVERY` emerald, `COMPARISON` gold) rendered from the server's routed intent. No badge is drawn when the payload has no intent (the greeting).
- Blocks are rendered in this fixed order, each omitted when empty: **intro → spec grid → product cards → bullets → sources → footer**.

| Payload field | Rendered as |
|---|---|
| `intro` | Single escaped paragraph; no markdown on the client |
| `specs[]` | Auto-fit grid of label/value tiles (FACT answers) |
| `cards[]` | Horizontal snap carousel of product cards (DISCOVERY, COMPARISON) |
| `bullets[]` | `ul.clean-list` with one escaped item per line |
| `sources[]` | Collapsible drawer: `🔗 Verified Sources (n) ▾`, each row showing title and crawl date |
| `next_chips[]` | Replaces the quick-reply rail under the conversation |

### 3. Product Card
- Category eyebrow (10 px, uppercase, emerald), product name, fee pill (emerald) and requirement pill (neutral), one-line highlight.
- `Check eligibility →` sends *"Tell me about &lt;product&gt; fees and eligibility"*; the product name travels in a `data-ask` attribute, never in an inline handler.
- Cards come from the catalog, so the link and the fee always describe the same record.

### 4. Spec Grid (FACT)
- Two to four tiles of `label` / `value`, drawn from the server-parsed detail table.
- Values are escaped text, so a scraped figure can never inject markup.

### 5. Sources Drawer
- Collapsed by default behind a pill button; toggling adds `.open` to the list panel.
- Each row is `title` + `last_crawled`, linked with `target="_blank"` and `rel="noopener noreferrer"`.
- A URL is rendered only if it parses to `http:` or `https:`. Anything else is dropped rather than shown as a dead link.

### 6. Feedback Row
- `👍` / `👎` post `{interaction_id, rating}` to `POST /api/feedback`, then show `Thanks` / `Flagged` inline.
- The buttons are per-answer, so a rating is always attached to the exact turn it judged. A failed post shows `Not saved` instead of pretending the rating was stored.
- Feedback is written to `data/feedback.jsonl` for offline review. It does not train or mutate the index.

### 7. Fallback Bubble
- Border `--accent-gold` at 45% strength, background `--accent-gold-soft`.
- Badge: `Not covered by the site`.
- Body: the server's refusal copy, unmodified. No cards, no specs, no sources.
- Quick replies switch to recovery chips so the user is never left without a next step.

### 8. Suggestion Chips
- A horizontally scrollable rail above the input; hidden scrollbar, snap-free, one line.
- Every chip is drawn from the golden eval set, so each one is known to route and answer correctly:

| Chip | Demonstrates |
|---|---|
| *What credit cards and commercial cards are available?* | Product Discovery |
| *What savings and account options can I open?* | Product Discovery (accounts) |
| *Compare Millionaire Account versus standard savings accounts* | Comparison |
| *What is the annual fee of U By Emaar Signature Credit Card?* | Single Fact |
| Recovery chips after a refusal | Out of Scope → back on topic |

Multi-turn demos are typed manually (`"types of credit card?"` then `"tell me all"`); the server resolves continuations, so the client keeps no topic state.

### 9. Input Dock
- Pill input with emerald focus ring, circular emerald send button, disabled while a turn is in flight.
- Enter submits; the field clears on send and regains focus when the answer lands.

### 10. Loading State
- Three-dot bounce inside a bot-styled bubble, removed as soon as the response or an error replaces it.

### 11. Error Bubble
- Amber fallback styling with a `Connection problem` badge and the actual failure reason, plus the command that starts the backend.
- There is no simulated-answer mode: if the API is unreachable the UI says so instead of inventing a response.

## 5. Render Contract

```json
POST /api/chat/ui  { "session_id": "...", "message": "..." }
```

```json
{
  "interaction_id": "9f2c1a4b7e05",
  "intent": "DISCOVERY",
  "answerable": true,
  "cache_hit": false,
  "intro": "Here is an overview of the verified Credit Cards available with Emirates NBD:",
  "specs": [],
  "cards": [
    {
      "name": "noon One Visa Credit Card",
      "category": "Credit Cards",
      "fee": "Free for Life",
      "requirement": "Minimum Salary: AED 5,000",
      "highlight": "Up to 5% unlimited cashback on noon, NowNow & SIVVI.",
      "url": "https://www.emiratesnbd.com/en/cards/credit-cards/noon-one-visa-credit-card"
    }
  ],
  "bullets": [],
  "sources": [
    { "title": "Emirates NBD Credit Cards", "url": "https://...", "last_crawled": "2026-11-18" }
  ],
  "next_chips": ["What savings and account options can I open?"]
}
```

`cache_hit` is part of the contract and always `false` today: no verified-answer cache exists, and the badge only appears if a future cache reports a real hit.

## 6. Client Behavior & Security

- **Session Continuity**: `session_id` from `crypto.randomUUID()` on load (with a timestamp fallback), retained in memory for multi-turn context. The reset button mints a new one.
- **Follow-Up Continuity**: The client always sends raw user text. Bare continuations ("tell me all", "yes please", "list them") and elliptical follow-ups ("any other") are resolved server-side against conversation history, so the UI keeps no topic state.
- **No Client-Side Generation**: The page contains no canned answers, no demo data and no fallback prose about products. Structure and wording both arrive from the API.
- **XSS Prevention**: Every dynamic value is inserted through a single `escapeHtml()` helper; no user or model text is ever assigned with `innerHTML`. Source URLs pass a protocol allowlist.
- **No Inline Handlers**: Card, source and feedback interactions use `data-*` attributes with one delegated listener, so a product name cannot break out into executable markup.
- **Keyboard & Focus**: Enter submits, focus returns to the input after each turn, and the conversation scrolls to the newest bubble.
