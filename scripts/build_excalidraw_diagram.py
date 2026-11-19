"""
Builds the comprehensive Excalidraw workflow architecture diagram for Lexi (Emirates NBD Hybrid RAG)
following coleam00/excalidraw-diagram-skill specifications.

Architecture covers:
1. Multi-Stage Ingestion Pipeline & Synthetic Catalog Anchors
2. LangGraph Conversational State Machine (7-Node Pipeline)
3. 5-Tier Defensive Guardrail System
4. Dual-Runtime Cloud Deployment (FastAPI Local vs Vercel Serverless)
5. Evidence Artifacts (Real Schemas, RRF formulas, and Query Rewrites)
"""

import json
from pathlib import Path

def create_element_id(prefix: str, count: int) -> str:
    return f"{prefix}_{count}"

def main():
    elements = []
    
    # Color palette
    PRIMARY_FILL = "#3b82f6"
    PRIMARY_STROKE = "#1e3a5f"
    SECONDARY_FILL = "#60a5fa"
    START_FILL = "#fed7aa"
    START_STROKE = "#c2410c"
    SUCCESS_FILL = "#a7f3d0"
    SUCCESS_STROKE = "#047857"
    DECISION_FILL = "#fef3c7"
    DECISION_STROKE = "#b45309"
    AI_FILL = "#ddd6fe"
    AI_STROKE = "#6d28d9"
    WARNING_FILL = "#fee2e2"
    WARNING_STROKE = "#dc2626"
    ARTIFACT_BG = "#1e293b"
    TITLE_COLOR = "#1e40af"
    SUBTITLE_COLOR = "#3b82f6"
    TEXT_MUTED = "#64748b"
    TEXT_LIGHT_FILL = "#374151"
    TEXT_DARK_FILL = "#ffffff"
    LINE_STROKE = "#94a3b8"

    seed_counter = 10000

    def get_seed():
        nonlocal seed_counter
        seed_counter += 7
        return seed_counter

    def make_free_text(id_str, x, y, text, font_size=16, color=TITLE_COLOR, align="left", width=300, height=25):
        return {
            "type": "text",
            "id": id_str,
            "x": x, "y": y,
            "width": width, "height": height,
            "text": text,
            "originalText": text,
            "fontSize": font_size,
            "fontFamily": 3,
            "textAlign": align,
            "verticalAlign": "top",
            "strokeColor": color,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "seed": get_seed(),
            "version": 1,
            "versionNonce": get_seed(),
            "isDeleted": false if "false" in locals() else False,
            "groupIds": [],
            "boundElements": None,
            "link": None,
            "locked": False,
            "containerId": None,
            "lineHeight": 1.25
        }

    def make_box_with_text(id_box, id_text, x, y, w, h, text, fill, stroke, text_color=TEXT_LIGHT_FILL, font_size=15, roundness=3, stroke_style="solid", stroke_width=2):
        box = {
            "type": "rectangle",
            "id": id_box,
            "x": x, "y": y, "width": w, "height": h,
            "strokeColor": stroke,
            "backgroundColor": fill,
            "fillStyle": "solid",
            "strokeWidth": stroke_width,
            "strokeStyle": stroke_style,
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "seed": get_seed(),
            "version": 1,
            "versionNonce": get_seed(),
            "isDeleted": False,
            "groupIds": [],
            "boundElements": [{"id": id_text, "type": "text"}],
            "link": None,
            "locked": False,
            "roundness": {"type": roundness} if roundness else None
        }
        text_el = {
            "type": "text",
            "id": id_text,
            "x": x + 10, "y": y + (h - (font_size * 1.5)) / 2,
            "width": w - 20, "height": font_size * 1.5,
            "text": text,
            "originalText": text,
            "fontSize": font_size,
            "fontFamily": 3,
            "textAlign": "center",
            "verticalAlign": "middle",
            "strokeColor": text_color,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "seed": get_seed(),
            "version": 1,
            "versionNonce": get_seed(),
            "isDeleted": False,
            "groupIds": [],
            "boundElements": None,
            "link": None,
            "locked": False,
            "containerId": id_box,
            "lineHeight": 1.25
        }
        return box, text_el

    def make_arrow(id_arrow, start_id, end_id, points, stroke=PRIMARY_STROKE, stroke_width=2, stroke_style="solid", label=""):
        arrow = {
            "type": "arrow",
            "id": id_arrow,
            "x": points[0][0], "y": points[0][1],
            "width": abs(points[-1][0] - points[0][0]),
            "height": abs(points[-1][1] - points[0][1]),
            "strokeColor": stroke,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": stroke_width,
            "strokeStyle": stroke_style,
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "seed": get_seed(),
            "version": 1,
            "versionNonce": get_seed(),
            "isDeleted": False,
            "groupIds": [],
            "boundElements": None,
            "link": None,
            "locked": False,
            "points": [[p[0] - points[0][0], p[1] - points[0][1]] for p in points],
            "startBinding": {"elementId": start_id, "focus": 0, "gap": 4} if start_id else None,
            "endBinding": {"elementId": end_id, "focus": 0, "gap": 4} if end_id else None,
            "startArrowhead": None,
            "endArrowhead": "arrow"
        }
        return arrow

    def make_section_boundary(id_str, x, y, w, h, title, subtitle=""):
        box = {
            "type": "rectangle",
            "id": id_str,
            "x": x, "y": y, "width": w, "height": h,
            "strokeColor": "#cbd5e1",
            "backgroundColor": "#f8fafc",
            "fillStyle": "solid",
            "strokeWidth": 1.5,
            "strokeStyle": "dashed",
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "seed": get_seed(),
            "version": 1,
            "versionNonce": get_seed(),
            "isDeleted": False,
            "groupIds": [],
            "boundElements": [],
            "link": None,
            "locked": True,
            "roundness": {"type": 3}
        }
        t_el = make_free_text(f"{id_str}_title", x + 20, y + 16, title, font_size=20, color=TITLE_COLOR, width=w-40)
        elements.append(box)
        elements.append(t_el)
        if subtitle:
            s_el = make_free_text(f"{id_str}_sub", x + 20, y + 42, subtitle, font_size=13, color=TEXT_MUTED, width=w-40)
            elements.append(s_el)

    def make_code_artifact(id_box, id_text, x, y, w, h, title, code_str, text_color="#38bdf8"):
        box = {
            "type": "rectangle",
            "id": id_box,
            "x": x, "y": y, "width": w, "height": h,
            "strokeColor": "#334155",
            "backgroundColor": ARTIFACT_BG,
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "seed": get_seed(),
            "version": 1,
            "versionNonce": get_seed(),
            "isDeleted": False,
            "groupIds": [],
            "boundElements": [{"id": id_text, "type": "text"}],
            "link": None,
            "locked": False,
            "roundness": {"type": 3}
        }
        title_el = make_free_text(f"{id_box}_head", x + 12, y + 10, f"// {title}", font_size=12, color="#94a3b8", width=w-24)
        text_el = {
            "type": "text",
            "id": id_text,
            "x": x + 12, "y": y + 32,
            "width": w - 24, "height": h - 42,
            "text": code_str,
            "originalText": code_str,
            "fontSize": 12,
            "fontFamily": 3,
            "textAlign": "left",
            "verticalAlign": "top",
            "strokeColor": text_color,
            "backgroundColor": "transparent",
            "fillStyle": "solid",
            "strokeWidth": 1,
            "strokeStyle": "solid",
            "roughness": 0,
            "opacity": 100,
            "angle": 0,
            "seed": get_seed(),
            "version": 1,
            "versionNonce": get_seed(),
            "isDeleted": False,
            "groupIds": [],
            "boundElements": None,
            "link": None,
            "locked": False,
            "containerId": id_box,
            "lineHeight": 1.25
        }
        elements.extend([box, title_el, text_el])

    # =========================================================================
    # DIAGRAM HEADER (Level 1: Summary Banner)
    # =========================================================================
    elements.append(make_free_text("diag_main_title", 60, 40, "Lexi: Emirates NBD Hybrid RAG State Machine & Ingestion Workflow", font_size=28, color=TITLE_COLOR, width=1200))
    elements.append(make_free_text("diag_main_desc", 60, 78, "Production Visual Architecture Diagram | coleam00/excalidraw-diagram-skill | LangGraph 7-Node State Machine | Qdrant Hybrid RRF | 5-Tier Defense", font_size=15, color=TEXT_MUTED, width=1200))

    # Summary Flow Ribbon across top
    make_section_boundary("sec_summary_flow", 60, 120, 2460, 90, "Level 1: End-to-End Summary Pipeline (Multi-Zoom Overview)", "Continuous pipeline from Raw Web Crawl to Stateful Verification")
    
    summary_nodes = [
        ("sum_1", "1. Crawl & Ingest", START_FILL, START_STROKE),
        ("sum_2", "2. Clean & Catalog", SECONDARY_FILL, PRIMARY_STROKE),
        ("sum_3", "3. Rewriter Node", AI_FILL, AI_STROKE),
        ("sum_4", "4. Router Gate", DECISION_FILL, DECISION_STROKE),
        ("sum_5", "5. Hybrid Search", PRIMARY_FILL, PRIMARY_STROKE),
        ("sum_6", "6. Grader Gate", DECISION_FILL, DECISION_STROKE),
        ("sum_7", "7. Generator Node", AI_FILL, AI_STROKE),
        ("sum_8", "8. Server Citations", SUCCESS_FILL, SUCCESS_STROKE),
        ("sum_9", "9. User Verification", SUCCESS_FILL, SUCCESS_STROKE),
    ]
    cur_x = 90
    for idx, (nid, nlabel, nfill, nstroke) in enumerate(summary_nodes):
        b, t = make_box_with_text(nid, f"{nid}_t", cur_x, 155, 210, 40, nlabel, nfill, nstroke, font_size=13, text_color=TEXT_LIGHT_FILL if nfill != PRIMARY_FILL else TEXT_DARK_FILL)
        elements.extend([b, t])
        if idx < len(summary_nodes) - 1:
            arr = make_arrow(f"arr_sum_{idx}", nid, summary_nodes[idx+1][0], [[cur_x + 210, 175], [cur_x + 250, 175]], stroke=LINE_STROKE)
            elements.append(arr)
        cur_x += 270

    # =========================================================================
    # SECTION 1: OFFLINE MULTI-STAGE INGESTION & CATALOG ANCHORS (Left Room)
    # =========================================================================
    sec1_x = 60
    sec1_y = 240
    sec1_w = 660
    sec1_h = 1040
    make_section_boundary("sec_ingestion", sec1_x, sec1_y, sec1_w, sec1_h, "1. Offline Ingestion & Synthetic Catalog Anchors", "Crawling, DOM Cleansing, Hierarchical Breadcrumb Chunking & Directory Matrix Synthesis")

    # Timeline layout for Ingestion
    t1_x = sec1_x + 40
    t1_y = sec1_y + 90
    
    # Node 1: Crawler
    b_crawl, t_crawl = make_box_with_text("ing_crawl", "ing_crawl_t", t1_x, t1_y, 240, 65, "Firecrawl + TinyFish Crawler\n(Max Concurrency=4, Retries=3)", START_FILL, START_STROKE, font_size=13)
    elements.extend([b_crawl, t_crawl])

    # Node 2: DOM Cleaner
    b_clean, t_clean = make_box_with_text("ing_clean", "ing_clean_t", t1_x, t1_y + 110, 240, 75, "Strict DOM Stripper\n(Strips <nav>, cookie chrome,\n& 'Would you like to talk?')", SECONDARY_FILL, PRIMARY_STROKE, font_size=13)
    elements.extend([b_clean, t_clean])
    elements.append(make_arrow("arr_ing_1", "ing_crawl", "ing_clean", [[t1_x + 120, t1_y + 65], [t1_x + 120, t1_y + 110]], stroke=START_STROKE))

    # Node 3: Hierarchy Chunker
    b_chunk, t_chunk = make_box_with_text("ing_chunk", "ing_chunk_t", t1_x, t1_y + 230, 240, 65, "Hierarchy Chunker\n(600 chars, 100 overlap, H1>H2)", PRIMARY_FILL, PRIMARY_STROKE, text_color=TEXT_DARK_FILL, font_size=13)
    elements.extend([b_chunk, t_chunk])
    elements.append(make_arrow("arr_ing_2", "ing_clean", "ing_chunk", [[t1_x + 120, t1_y + 185], [t1_x + 120, t1_y + 230]], stroke=PRIMARY_STROKE))

    # Node 4: Synthetic Master Directory Anchors (Hero concept of step 1)
    b_anchor, t_anchor = make_box_with_text("ing_anchor", "ing_anchor_t", t1_x, t1_y + 340, 240, 85, "Master Catalog Anchors\n(Pre-indexed Category Matrices\nPrevent Top-K List Collapse)", DECISION_FILL, DECISION_STROKE, font_size=13)
    elements.extend([b_anchor, t_anchor])
    elements.append(make_arrow("arr_ing_3", "ing_chunk", "ing_anchor", [[t1_x + 120, t1_y + 295], [t1_x + 120, t1_y + 340]], stroke=PRIMARY_STROKE))

    # Node 5: FastEmbed Dual Indexing
    b_qdrant, t_qdrant = make_box_with_text("ing_qdrant", "ing_qdrant_t", t1_x, t1_y + 470, 240, 75, "Qdrant Cloud Hybrid Store\nDense: BGE-Small (384d)\nSparse: BM25 Lexical", AI_FILL, AI_STROKE, font_size=13)
    elements.extend([b_qdrant, t_qdrant])
    elements.append(make_arrow("arr_ing_4", "ing_anchor", "ing_qdrant", [[t1_x + 120, t1_y + 425], [t1_x + 120, t1_y + 470]], stroke=DECISION_STROKE))

    # Node 6: SQLite Knowledge Graph
    b_kg, t_kg = make_box_with_text("ing_kg", "ing_kg_t", t1_x, t1_y + 590, 240, 65, "SQLite Knowledge Graph\n(Product - Fee - KFS Triples)", SECONDARY_FILL, PRIMARY_STROKE, font_size=13)
    elements.extend([b_kg, t_kg])
    elements.append(make_arrow("arr_ing_5", "ing_anchor", "ing_kg", [[t1_x + 120, t1_y + 425], [t1_x + 40, t1_y + 520], [t1_x + 40, t1_y + 590]], stroke=DECISION_STROKE))

    # Evidence Artifacts in Section 1 (Right side of left room)
    make_code_artifact("art_catalog_json", "art_catalog_json_t", sec1_x + 320, sec1_y + 90, 310, 220, "Synthetic Catalog Anchor Chunk", 
"""{
  "product_name": "All Credit Cards",
  "category": "credit_cards",
  "is_master_anchor": true,
  "matrix": [
    {"name": "U By Emaar Signature", "fee": 0, "sal": 15000},
    {"name": "Emirates NBD Duo", "fee": 0, "sal": 12000},
    {"name": "Skywards Infinite", "fee": 1575, "sal": 30000}
  ]
}""", text_color="#4ade80")

    make_code_artifact("art_chunk_spec", "art_chunk_spec_t", sec1_x + 320, sec1_y + 340, 310, 205, "Cleaned Chunk Metadata",
"""{
  "chunk_id": "card_u_by_emaar_chunk_02",
  "url": "https://emiratesnbd.com/cards/...",
  "kfs_url": "https://emiratesnbd.com/kfs/...",
  "hierarchy": "Cards > U By Emaar > Fees",
  "category": "credit_cards",
  "dirty_h2_tags_stripped": true
}""", text_color="#38bdf8")

    make_code_artifact("art_rrf_formula", "art_rrf_formula_t", sec1_x + 320, sec1_y + 575, 310, 160, "Reciprocal Rank Fusion (RRF)",
"""// Hybrid Rank Score Algorithm
RRF_Score(doc, query) = 
  SUM_{m in [Dense, Sparse]} (
    1.0 / (60 + Rank_m(doc, query))
  )

Threshold Gate: Score >= 0.35""", text_color="#facc15")


    # =========================================================================
    # SECTION 2: ONLINE LANGGRAPH CONVERSATIONAL STATE MACHINE (Center Hero)
    # =========================================================================
    sec2_x = 750
    sec2_y = 240
    sec2_w = 1100
    sec2_h = 1040
    make_section_boundary("sec_langgraph", sec2_x, sec2_y, sec2_w, sec2_h, "2. LangGraph Stateful Conversational State Machine", "Multi-Turn Query Rewriter, Intent Classifier, Parallel Retrieval, Grader, & Grounded Synthesis")

    # Entry: User Message
    b_user, t_user = make_box_with_text("lg_user", "lg_user_t", sec2_x + 40, sec2_y + 90, 240, 55, "User Banking Query\n('tell me all', 'what about fees?')", START_FILL, START_STROKE, font_size=13)
    elements.extend([b_user, t_user])

    # Node 1: contextualize_query
    b_rewriter, t_rewriter = make_box_with_text("lg_rewriter", "lg_rewriter_t", sec2_x + 40, sec2_y + 190, 240, 75, "1. contextualize_query\n(Inspects last 6 turns, resolves\npronouns to standalone banking query)", AI_FILL, AI_STROKE, font_size=13)
    elements.extend([b_rewriter, t_rewriter])
    elements.append(make_arrow("arr_lg_1", "lg_user", "lg_rewriter", [[sec2_x + 160, sec2_y + 145], [sec2_x + 160, sec2_y + 190]], stroke=START_STROKE))

    # Evidence: Query Rewrite Example
    make_code_artifact("art_rewrite_ex", "art_rewrite_ex_t", sec2_x + 320, sec2_y + 90, 420, 175, "Conversational Memory Resolution",
"""// Follow-Up Query Transformation
Input Turn 1: "types of credit card?"
Input Turn 2: "tell me all"

state["standalone_query"] = 
  "List all Emirates NBD credit cards with their 
   annual fees, minimum salary, and key perks."

// Prevents cross-category drift!""", text_color="#38bdf8")

    # Node 2: route_intent
    b_router, t_router = make_box_with_text("lg_router", "lg_router_t", sec2_x + 40, sec2_y + 310, 240, 75, "2. route_intent Gate\n(Pydantic Structured Output:\nDISCOVERY, FACT, COMPARE, FALLBACK)", DECISION_FILL, DECISION_STROKE, font_size=13)
    elements.extend([b_router, t_router])
    elements.append(make_arrow("arr_lg_2", "lg_rewriter", "lg_router", [[sec2_x + 160, sec2_y + 265], [sec2_x + 160, sec2_y + 310]], stroke=AI_STROKE))

    # Fan-Out to 3 Retrieval Strategies
    b_ret_disc, t_ret_disc = make_box_with_text("ret_disc", "ret_disc_t", sec2_x + 40, sec2_y + 440, 240, 65, "DISCOVERY Branch\n(limit=25, Deduped to 1-2 chunks/card,\nCategory Matrix Anchor Attached)", SECONDARY_FILL, PRIMARY_STROKE, font_size=12)
    b_ret_fact, t_ret_fact = make_box_with_text("ret_fact", "ret_fact_t", sec2_x + 310, sec2_y + 440, 240, 65, "FACT Branch\n(limit=6, Strict Product Entity Pinning,\nCross-Card Fact Isolation)", SECONDARY_FILL, PRIMARY_STROKE, font_size=12)
    b_ret_comp, t_ret_comp = make_box_with_text("ret_comp", "ret_comp_t", sec2_x + 580, sec2_y + 440, 240, 65, "COMPARISON Branch\n(Bilateral Partitioned Search, limit=4/card,\nIsolate & Merge Contexts)", SECONDARY_FILL, PRIMARY_STROKE, font_size=12)
    elements.extend([b_ret_disc, t_ret_disc, b_ret_fact, t_ret_fact, b_ret_comp, t_ret_comp])

    elements.append(make_arrow("arr_fan_disc", "lg_router", "ret_disc", [[sec2_x + 110, sec2_y + 385], [sec2_x + 110, sec2_y + 440]], stroke=DECISION_STROKE))
    elements.append(make_arrow("arr_fan_fact", "lg_router", "ret_fact", [[sec2_x + 160, sec2_y + 385], [sec2_x + 430, sec2_y + 410], [sec2_x + 430, sec2_y + 440]], stroke=DECISION_STROKE))
    elements.append(make_arrow("arr_fan_comp", "lg_router", "ret_comp", [[sec2_x + 210, sec2_y + 385], [sec2_x + 700, sec2_y + 410], [sec2_x + 700, sec2_y + 440]], stroke=DECISION_STROKE))

    # Convergence into Node 4: grade_documents
    b_grader, t_grader = make_box_with_text("lg_grader", "lg_grader_t", sec2_x + 310, sec2_y + 560, 240, 75, "4. grade_documents Gate\n(RRF Score >= 0.35 & Semantic\nGrounding Confidence Check)", DECISION_FILL, DECISION_STROKE, font_size=13)
    elements.extend([b_grader, t_grader])

    elements.append(make_arrow("arr_conv_disc", "ret_disc", "lg_grader", [[sec2_x + 160, sec2_y + 505], [sec2_x + 360, sec2_y + 560]], stroke=PRIMARY_STROKE))
    elements.append(make_arrow("arr_conv_fact", "ret_fact", "lg_grader", [[sec2_x + 430, sec2_y + 505], [sec2_x + 430, sec2_y + 560]], stroke=PRIMARY_STROKE))
    elements.append(make_arrow("arr_conv_comp", "ret_comp", "lg_grader", [[sec2_x + 700, sec2_y + 505], [sec2_x + 500, sec2_y + 560]], stroke=PRIMARY_STROKE))

    # Grader Fallback Branch
    b_fallback, t_fallback = make_box_with_text("lg_fallback", "lg_fallback_t", sec2_x + 60, sec2_y + 690, 210, 65, "Fallback Response\n(Safe Out-of-Scope\nBanking Guidance)", WARNING_FILL, WARNING_STROKE, font_size=13)
    elements.extend([b_fallback, t_fallback])
    elements.append(make_arrow("arr_fail_grader", "lg_grader", "lg_fallback", [[sec2_x + 310, sec2_y + 600], [sec2_x + 160, sec2_y + 600], [sec2_x + 160, sec2_y + 690]], stroke=WARNING_STROKE))

    # Node 5: generate_response (Intent-Specialized)
    b_gen, t_gen = make_box_with_text("lg_generator", "lg_generator_t", sec2_x + 310, sec2_y + 690, 240, 85, "5. generate_response\n(Gemini 2.5 Flash Synthesis:\n• DISCOVERY -> Markdown Catalog Table\n• FACT -> Structured Spec Card\n• COMPARE -> Head-to-Head Matrix)", AI_FILL, AI_STROKE, font_size=12)
    elements.extend([b_gen, t_gen])
    elements.append(make_arrow("arr_pass_grader", "lg_grader", "lg_generator", [[sec2_x + 430, sec2_y + 635], [sec2_x + 430, sec2_y + 690]], stroke=SUCCESS_STROKE))

    # Node 6: build_citations
    b_cit, t_cit = make_box_with_text("lg_citations", "lg_citations_t", sec2_x + 310, sec2_y + 830, 240, 65, "6. build_citations Gate\n(Deterministic Server Assembly:\nVerified Product URLs & KFS links)", SUCCESS_FILL, SUCCESS_STROKE, font_size=13)
    elements.extend([b_cit, t_cit])
    elements.append(make_arrow("arr_gen_cit", "lg_generator", "lg_citations", [[sec2_x + 430, sec2_y + 775], [sec2_x + 430, sec2_y + 830]], stroke=AI_STROKE))

    # Final Verified Response
    b_out, t_out = make_box_with_text("lg_output", "lg_output_t", sec2_x + 310, sec2_y + 940, 240, 55, "Verified Grounded Answer\n(Zero Hallucinated Specs/URLs)", SUCCESS_FILL, SUCCESS_STROKE, font_size=13)
    elements.extend([b_out, t_out])
    elements.append(make_arrow("arr_cit_out", "lg_citations", "lg_output", [[sec2_x + 430, sec2_y + 895], [sec2_x + 430, sec2_y + 940]], stroke=SUCCESS_STROKE))
    elements.append(make_arrow("arr_fb_out", "lg_fallback", "lg_output", [[sec2_x + 160, sec2_y + 755], [sec2_x + 160, sec2_y + 965], [sec2_x + 310, sec2_y + 965]], stroke=WARNING_STROKE))

    # Evidence: LangGraph AgentState Definition (Right side of center room)
    make_code_artifact("art_agent_state", "art_agent_state_t", sec2_x + 600, sec2_y + 560, 460, 280, "LangGraph AgentState (TypedDict)",
"""class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    chat_history: list[dict[str, str]]
    latest_query: str
    standalone_query: str     # Rewritten banking query
    intent: Literal["DISCOVERY", "FACT", "COMPARISON", "FALLBACK"]
    category_filter: Optional[str]
    target_product: Optional[str]
    retrieved_docs: list[Document]
    confidence_score: float
    answer: str
    citations: list[dict[str, str]]""", text_color="#4ade80")

    make_code_artifact("art_gen_template", "art_gen_template_t", sec2_x + 600, sec2_y + 860, 460, 150, "Intent-Specific Template Rules",
"""// DISCOVERY -> Multi-Row Table Output:
| Card Name | Annual Fee | Min. Salary | Key Reward |
| :--- | :--- | :--- | :--- |
| U By Emaar Signature | Free | AED 15,000 | 1.25 Upoints |

// FACT -> Grounded Specification Box:
### Official Product Specifications
- Annual Fee: Free for Life
- Minimum Salary: AED 15,000""", text_color="#facc15")


    # =========================================================================
    # SECTION 3: 5-TIER DEFENSE & DUAL DEPLOYMENT PARITY (Right Room)
    # =========================================================================
    sec3_x = 1880
    sec3_y = 240
    sec3_w = 640
    sec3_h = 1040
    make_section_boundary("sec_defense", sec3_x, sec3_y, sec3_w, sec3_h, "3. Defensive Guardrails & Dual Cloud Deployment", "Five-Tier Safety Architecture, FastAPI Dev Benchmarks, and Vercel Serverless Parity")

    # 5-Tier Defense Stack
    def_x = sec3_x + 40
    def_y = sec3_y + 90
    
    tiers = [
        ("tier1", "Tier 1: Prompt Injection Firewall", "Regex + Semantic Jailbreak Filter\nBlocks instruction overrides & system prompt dumps", WARNING_FILL, WARNING_STROKE),
        ("tier2", "Tier 2: Vector Confidence Gate", "RRF Confidence Score >= 0.35\nRejects low-relevance queries before generation", DECISION_FILL, DECISION_STROKE),
        ("tier3", "Tier 3: Pydantic Schema Gate", "Strict Enum Validation for Categories & Entities\nEnsures all outputs stay inside bank catalog", PRIMARY_FILL, PRIMARY_STROKE),
        ("tier4", "Tier 4: Numerical AED Currency Guard", "Regex extraction verifying salary & fee figures\nMust strictly exist in retrieved context chunks", SECONDARY_FILL, PRIMARY_STROKE),
        ("tier5", "Tier 5: Server-Verified Citations", "Zero LLM-generated URLs\nAll links programmatically built from verified metadata", SUCCESS_FILL, SUCCESS_STROKE),
    ]

    for idx, (tid, ttitle, tdesc, tfill, tstroke) in enumerate(tiers):
        b, t = make_box_with_text(tid, f"{tid}_t", def_x, def_y + (idx * 90), 300, 75, f"{ttitle}\n({tdesc})", tfill, tstroke, font_size=11)
        elements.extend([b, t])
        if idx < len(tiers) - 1:
            arr = make_arrow(f"arr_tier_{idx}", tid, tiers[idx+1][0], [[def_x + 150, def_y + (idx * 90) + 75], [def_x + 150, def_y + ((idx + 1) * 90)]], stroke=tstroke)
            elements.append(arr)

    # Deployment Dual-Runtime Parity
    dep_y = def_y + 480
    make_free_text("dep_head", def_x, dep_y, "Dual-Runtime Deployment Parity", font_size=18, color=TITLE_COLOR, width=540)

    b_local, t_local = make_box_with_text("dep_local", "dep_local_t", def_x, dep_y + 35, 260, 85, "Local FastAPI Dev Server\n(Port 8000, Uvicorn, SQLite KG,\n90/90 Pytest, 15/15 Golden Eval)", PRIMARY_FILL, PRIMARY_STROKE, text_color=TEXT_DARK_FILL, font_size=12)
    b_vercel, t_vercel = make_box_with_text("dep_vercel", "dep_vercel_t", def_x + 280, dep_y + 35, 260, 85, "Vercel Serverless Prod\n(/api/index.py, Fluid Compute,\nStateless Parity, <1.2s Cold Start)", SUCCESS_FILL, SUCCESS_STROKE, font_size=12)
    elements.extend([b_local, t_local, b_vercel, t_vercel])

    # Evidence: Benchmark Results & Pydantic Schema
    make_code_artifact("art_benchmark", "art_benchmark_t", def_x, dep_y + 140, 540, 160, "Production Verification Benchmark (100% Pass)",
"""======================== 15 passed in 26.83s ========================
Query 1: "about your products?" -> DISCOVERY (Overview + Table) [PASS]
Query 2: "types of credit card?" -> DISCOVERY (18 Cards Matrix) [PASS]
Query 3: "tell me all" -> Contextualized Standalone Rewriter    [PASS]
Regression Suite: 90 / 90 tests passing (100.0%)
Zero single-document collapse | Zero dirty UI chrome leaks""", text_color="#4ade80")

    make_code_artifact("art_pydantic_schema", "art_pydantic_schema_t", def_x, dep_y + 320, 540, 140, "Pydantic Schema Gate Definition",
"""class IntentClassificationOutput(BaseModel):
    intent: Literal["DISCOVERY", "FACT", "COMPARISON", "FALLBACK"]
    category: Optional[Literal["credit_cards", "accounts", "loans", "wealth"]]
    product_names: list[str] = Field(default_factory=list)
    comparison_targets: Optional[list[str]] = None
    confidence: float = Field(ge=0.0, le=1.0)""", text_color="#38bdf8")

    # Final wrap-up
    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {
            "viewBackgroundColor": "#ffffff",
            "gridSize": 20
        },
        "files": {}
    }

    out_path = Path("docs/architecture_workflow.excalidraw")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"Generated {len(elements)} elements in {out_path.resolve()}")

    # Also copy to brain artifact directory
    brain_path = Path(r"C:\Users\PRATYUSH\.gemini\antigravity\brain\89ef14e7-7130-44e6-b2c0-2d37a54dc431\architecture_workflow.excalidraw")
    brain_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"Copied to artifact dir: {brain_path}")

if __name__ == "__main__":
    main()
