# Design: Website RAG Chatbot UI

> Zero-build frontend specification. High trust, extreme readability, and fast interaction.

## 1. Principles

- **Answer First, Sources Attached**: Direct, authoritative answers with interactive citation pills directly beneath.
- **Visual Fallback Contrast**: Fallback bubbles use distinct styling (amber warning banner) so reviewers immediately recognize when the bot declined.
- **Zero Build Step**: Pure HTML5, vanilla JavaScript (`fetch`), Tailwind CSS via CDN, and Marked.js via CDN. Instant loading without npm build dependencies.
- **Type-Safe Contract**: Frontend strictly aligns with backend Pydantic models (`ChatRequest`, `ChatResponse`, `SourceItem`).
- **Responsive Parity**: 100% usable on desktop laptops, tablets, and mobile viewports.
- **Interactive Discovery**: A slide-over or modal drawer displaying all covered catalog products from `GET /api/products`.

## 2. Layout Structure

```text
┌────────────────────────────────────────────────────────┐
│ Header: "Company Knowledge Assistant"      [📦 Products]│
├────────────────────────────────────────────────────────┤
│                                                        │
│  (bot)  Welcome message                                │
│         Suggestion Chips:                              │
│         [💳 Credit Cards] [💰 Savings Balance]        │
│         [⚖️ Compare Cards] [🚫 Transfer Money]         │
│                                                        │
│                                                (user)  │
│                                 "Compare Duo and Skywards"
│                                                        │
│  (bot)  Comparison Table / Breakdown                   │
│         • Duo Card: AED 0 fee with conditions...       │
│         • Skywards: AED 700 annual fee...              │
│                                                        │
│         Sources:                                       │
│         [🔗 Duo Credit Card ↗ (Crawled: 2026-11-18)]   │
│         [🔗 Skywards Card ↗ (Crawled: 2026-11-18)]     │
│                                                        │
├────────────────────────────────────────────────────────┤
│ [ Type your question...                        ] [Send]│
└────────────────────────────────────────────────────────┘
```

## 3. Design Tokens (Dark / Clean Modern Theme)

| Token | Hex | Usage |
|---|---|---|
| `--bg-main` | `#0B0F19` | Main page background (deep navy/slate) |
| `--surface-card` | `#111827` | Bot response card, input bar background |
| `--surface-user` | `#2563EB` | User message bubble (royal blue) |
| `--text-primary` | `#F9FAFB` | Primary headings and response text |
| `--text-muted` | `#9CA3AF` | Timestamps, metadata, footnotes |
| `--border-subtle` | `#1F2937` | Card borders and input outlines |
| `--accent-gold` | `#F59E0B` | Fallback bubble border and warning tag |
| `--accent-gold-bg` | `rgba(245, 158, 11, 0.08)` | Fallback bubble background |
| `--pill-bg` | `#1E293B` | Citation source pill background |
| `--pill-hover` | `#334155` | Citation hover state |

All color pairings exceed WCAG 2.1 AA contrast requirements (minimum 4.5:1 ratio).

## 4. Component Specifications

### 1. Bot Response Bubble
- Surface: `#111827` with 1px border `#1F2937`.
- Markdown: Rendered cleanly with `marked.min.js`. Tables formatted with border outlines and alternating row fills.
- Source Row: Displayed directly beneath the markdown text. Each item is an interactive chip with link icon (`🔗`), sanitized page title, and "Last crawled" badge. Opens in new tab with `rel="noopener noreferrer"`.

### 2. Fallback Response Bubble
- Border: `#F59E0B` (amber).
- Background: `rgba(245, 158, 11, 0.08)`.
- Tag: `⚠️ Out of Scope / Not Found on Site`.
- Copy: Explicit explanation of why the question cannot be answered from site data.

### 3. Suggestion Chips
Pills rendered above the input on initial session load to easily demo all 5 assignment categories:
- *"Which credit cards do you offer?"* (Product Discovery)
- *"What is the minimum balance for a Savings Account?"* (Single Fact)
- *"How do Duo and Skywards cards differ on annual fees?"* (Comparison)
- *"And what is its eligibility?"* (Multi-turn Follow-up)
- *"Can you transfer AED 500 to my account?"* (Out of Scope / Fallback)

### 4. Covered Products Drawer / Modal
- Triggered by the **[📦 Products]** button in the header.
- Calls `GET /api/products` and groups products by category.
- Clicking any product automatically populates the chat input with *"Tell me about [Product Name]"*.

### 5. Loading State
- Three-dot pulse animation inside a bot bubble.
- Send button and input input field temporarily disabled to prevent duplicate submissions.

## 5. Client Behavior & Security

- **Session Continuity**: `session_id` generated via `crypto.randomUUID()` upon load, retained in memory for multi-turn conversational context.
- **XSS Prevention**: Model-generated text is parsed through Marked with HTML tags stripped or escaped. Sources and URLs are populated exclusively from verified API metadata.
- **Keyboard Navigation**: Enter to submit, Shift+Enter for newline. Auto-focus returns to input following response delivery.
