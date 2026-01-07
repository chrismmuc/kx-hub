# Epic 6: AI-Powered Blogging Engine

**Goal:** Build an intelligent blogging assistant that transforms Knowledge Base content into polished blog articles. The engine helps identify core ideas, generates article structures, creates drafts with proper referencing, and supports iterative article development.

**Business Value:** Enables a complete workflow from knowledge synthesis to published content. Transforms passive reading/highlighting into active content creation. Closes the loop: Read → Highlight → Synthesize → Publish.

**Dependencies:** Epic 2 (Knowledge Cards), Epic 4 (Source-Based Knowledge Graph)

**Status:** Planned

---

## Architecture Decision: Article-Centric Workflow

### Why an Article Engine?

| Problem | Solution |
|---------|----------|
| Knowledge accumulates but isn't synthesized | Article writing forces deep synthesis |
| Highlights scattered across sources | Articles consolidate related ideas |
| No output from reading habit | Publishable content as tangible output |
| Context lost between writing sessions | Persistent article state with history |

### Core Principles

1. **KB-Native**: All article ideas emerge from existing Knowledge Base content
2. **Iterative Development**: Articles evolve over multiple sessions (not one-shot generation)
3. **Source Attribution**: Every claim links back to KB sources
4. **Claude-First**: Primary interface is Claude (Claude Code / Claude Desktop)
5. **Export to Obsidian**: Final output as Markdown in Obsidian vault

### Workflow Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Article Development Workflow                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. IDEATION          2. STRUCTURE          3. DRAFTING             │
│  ┌───────────┐        ┌───────────┐        ┌───────────┐            │
│  │ KB Search │───────▶│ Outline   │───────▶│ Section   │            │
│  │ + Sources │        │ Generation│        │ Expansion │            │
│  └───────────┘        └───────────┘        └───────────┘            │
│       │                     │                    │                   │
│       ▼                     ▼                    ▼                   │
│  ┌───────────┐        ┌───────────┐        ┌───────────┐            │
│  │ Idea Log  │        │ Article   │        │ Article   │            │
│  │ (Firestore)│       │ Document  │        │ Versions  │            │
│  └───────────┘        └───────────┘        └───────────┘            │
│                                                  │                   │
│  4. REFINEMENT        5. REVIEW             6. PUBLISH              │
│  ┌───────────┐        ┌───────────┐        ┌───────────┐            │
│  │ Edit with │───────▶│ Consistency│──────▶│ Obsidian  │            │
│  │ Claude    │        │ Check     │        │ Export    │            │
│  └───────────┘        └───────────┘        └───────────┘            │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Schema

### Articles Collection (new)
```
articles/
  {article_id}:  # e.g., "second-brain-for-developers"
    title: "Building a Second Brain for Developers"
    slug: "second-brain-for-developers"
    status: "idea" | "outline" | "drafting" | "review" | "published"

    # Content
    outline: [
      {section: "Introduction", notes: "Hook with problem..."},
      {section: "The PARA Method", notes: "Explain structure..."}
    ]
    current_draft: "# Building a Second Brain..."  # Markdown

    # Source Attribution
    source_ids: ["building-a-second-brain", "the-para-method"]
    chunk_references: [
      {chunk_id: "chunk-123", section: "Introduction", quote: "..."}
    ]

    # Metadata
    word_count: 1250
    target_word_count: 2000
    tags: ["productivity", "pkm", "developers"]
    series_id: null | "productivity-series"

    # History
    created_at: timestamp
    updated_at: timestamp
    published_at: timestamp | null

    # Development Log
    sessions: [
      {date: "2026-01-02", action: "Created outline", notes: "..."},
      {date: "2026-01-03", action: "Wrote introduction", notes: "..."}
    ]
```

### Article Ideas Collection (new)
```
article_ideas/
  {idea_id}:
    title: "Developer Productivity ist Fokus-Zeit, nicht Velocity"
    
    # THE CORE INSIGHT - what makes this idea unique
    thesis: "Deine Highlights zeigen: Deep Work Blocks (90min) + Cognitive Load Metriken 
             ergeben zusammen ein besseres Productivity-Framework als DORA."
    
    # Your unique angle - why only YOU can write this
    unique_angle: "Kombination von Cal Newports Deep Work mit Platform Engineering Metriken - 
                   diese Verbindung macht sonst niemand."
    
    # Concrete highlights that support the thesis
    key_highlights: [
      {
        quote: "90min Deep Work blocks outperform fragmented coding sessions",
        source: "Deep Work",
        author: "Cal Newport"
      },
      {
        quote: "Measure developer cognitive load, not just DORA metrics",
        source: "4 North Star Metrics for Platform Engineering Teams",
        author: "Humanitec"
      },
      {
        quote: "Context switching costs 23 minutes to regain focus",
        source: "Maker's Schedule",
        author: "Paul Graham"
      }
    ]
    
    # Why now?
    timeliness: {
      recency: "Du hast diese 3 Sources in den letzten 2 Wochen gelesen",
      trending: true,  # Tavily shows current interest
      trending_context: "5 aktuelle Artikel zu 'Developer Experience' in den letzten 30 Tagen"
    }
    
    # Sources and metadata
    source_ids: ["deep-work", "platform-eng-metrics", "makers-schedule"]
    strength: 0.92
    status: "suggested" | "accepted" | "rejected" | "converted"
    suggested_at: timestamp
    
    # Medium-Scores
    medium_scores: {
      linkedin_post: 0.5,
      linkedin_article: 0.9,
      blog: 0.85,
      newsletter: 0.7,
      twitter_thread: 0.4,
      substack: 0.8
    }
```

### Article Series Collection (new)
```
article_series/
  {series_id}:
    title: "Productivity Deep Dive"
    description: "A 5-part series on modern productivity"
    article_ids: ["article-1", "article-2"]
    status: "planning" | "in_progress" | "complete"
    created_at: timestamp
```

---

## Story 6.1: High-Quality Article Idea Generation

**Status:** Planned

**Summary:** Generate high-quality article ideas that go beyond simple topic suggestions. Each idea contains a concrete thesis, your unique angle based on YOUR highlights, and supporting quotes from your KB.

### What Makes a High-Quality Idea?

| Element | Bad Example | Good Example |
|---------|-------------|--------------|
| **Title** | "Deep Work Article" | "Developer Productivity ist Fokus-Zeit, nicht Velocity" |
| **Thesis** | (missing) | "Deep Work Blocks + Cognitive Load Metriken = besseres Framework als DORA" |
| **Unique Angle** | (missing) | "Kombination die nur DU machen kannst basierend auf deinen Highlights" |
| **Evidence** | "3 sources" | 3 konkrete Zitate aus deinen Highlights |
| **Timeliness** | (missing) | "Gelesen vor 2 Wochen + Thema trending" |

### Why This Matters

Eine Idee ist nicht "schreib über X". Eine Idee ist:

> "Deine Highlights zeigen einen Zusammenhang zwischen A und B. 
> Das ist dein einzigartiger Insight. Hier sind 3 Zitate die das stützen.
> Das Thema ist gerade relevant weil..."

**Das Ziel:** Wenn du eine Idee siehst, weißt du sofort:
1. Was ist die These?
2. Warum kann nur ICH das schreiben?
3. Welche meiner Highlights fließen ein?
4. Warum jetzt?

### Supported Publication Mediums

| Medium | Description | Typical Length |
|--------|-------------|----------------|
| `linkedin_post` | Short, hook-driven, personal insights | < 1300 chars |
| `linkedin_article` | Professional deep-dives | 800-2000 words |
| `blog` | SEO-optimized, permanent reference | 1000-3000 words |
| `newsletter` | Curated, personal voice | 500-1500 words |
| `twitter_thread` | Punchy, numbered takeaways | 5-15 tweets |
| `substack` | Essay-style, analytical | 1000-2500 words |

### Medium Score Calculation

Scores are calculated from primary signals available in the KB:

| Signal | Measurement | Impact |
|--------|-------------|--------|
| Source Count | 1-2 vs 3+ | Few → Post, Many → Article/Blog |
| Chunk Count | 1-3 vs 5+ | Few → short, Many → long |
| Topic Breadth | Number of distinct tags | Narrow → Post, Broad → Blog |
| Contradictions | Relationships with `contradicts` type | Yes → good for discussion/essay |

### Algorithm

```
1. Find source clusters with strong connections:
   - Sources with "extends" or "contradicts" relationships
   - Sources that share tags/concepts
   - Recent highlights (topic is fresh in mind)

2. Extract key takeaways from Knowledge Cards:
   - Pull the strongest takeaways from each source
   - Find patterns: What concepts appear across sources?
   - Identify contradictions (great for thesis development)

3. Generate thesis using LLM:
   - Input: Top takeaways from related sources
   - Prompt: "What unique insight emerges from combining these highlights?"
   - Output: Concrete thesis statement (not just a topic)

4. Identify unique angle:
   - What combination of sources is unusual?
   - What perspective does the user bring?
   - Why can only THIS user write this article?

5. Select supporting highlights:
   - Pick 2-4 concrete quotes that support the thesis
   - Include author and source for credibility
   - Prioritize memorable/quotable highlights

6. Assess timeliness:
   - How recently were these sources read?
   - Is the topic trending? (optional Tavily check)
   - Any current events that make this relevant?

7. Calculate medium scores based on:
   - Source count → long-form vs short
   - Contradiction presence → discussion/essay format
   - Topic breadth → post vs article
```

### MCP Tool: `suggest_article_ideas`

Unified tool for both automatic discovery and manual idea input.

```python
suggest_article_ideas(
    # Filters
    min_sources: int = 2,        # Minimum KB sources to draw from
    focus_tags: list = None,     # Optional: filter by tags
    limit: int = 5,              # Number of suggestions
    
    # Storage
    save: bool = True,           # False = preview only
    
    # Web enrichment (optional)
    enrich_with_web: bool = False,  # Add trending/competition analysis
    
    # Manual idea input
    topic: str = None,           # Evaluate a specific topic
    source_ids: list = None      # Use specific sources
) -> {
    "ideas": [
        {
            "idea_id": "idea-123",
            
            # THE IDEA (not just a topic!)
            "title": "Developer Productivity ist Fokus-Zeit, nicht Velocity",
            "thesis": "Deep Work Blocks (90min) + Cognitive Load Metriken ergeben 
                       zusammen ein besseres Productivity-Framework als DORA.",
            "unique_angle": "Kombination von Cal Newports Deep Work mit Platform 
                            Engineering Metriken - diese Verbindung macht sonst niemand.",
            
            # YOUR HIGHLIGHTS that support the thesis
            "key_highlights": [
                {
                    "quote": "90min Deep Work blocks outperform fragmented coding sessions",
                    "source": "Deep Work",
                    "author": "Cal Newport"
                },
                {
                    "quote": "Measure developer cognitive load, not just DORA metrics",
                    "source": "4 North Star Metrics for Platform Engineering Teams",
                    "author": "Humanitec"
                },
                {
                    "quote": "Context switching costs 23 minutes to regain focus",
                    "source": "Maker's Schedule",
                    "author": "Paul Graham"
                }
            ],
            
            # WHY NOW?
            "timeliness": {
                "recency": "Diese 3 Sources in den letzten 2 Wochen gelesen",
                "trending": true,
                "trending_context": "5 aktuelle Artikel zu 'Developer Experience'"
            },
            
            # Metadata
            "sources": ["deep-work", "platform-eng-metrics", "makers-schedule"],
            "strength": 0.92,
            "suggested_at": "2026-01-05T10:30:00Z",
            
            # Which format fits best?
            "medium_scores": {
                "linkedin_article": 0.9,
                "blog": 0.85,
                "substack": 0.8,
                "newsletter": 0.7,
                "linkedin_post": 0.5,
                "twitter_thread": 0.4
            }
        }
    ]
}
```

**Usage patterns:**
- `suggest_article_ideas()` → Auto-generate 5 high-quality ideas from entire KB
- `suggest_article_ideas(focus_tags=["productivity"])` → Ideas only from productivity sources
- `suggest_article_ideas(topic="Deep Work for Developers")` → Develop THIS topic into a full idea
- `suggest_article_ideas(enrich_with_web=True)` → Include trending/competition analysis

### MCP Tool: `list_ideas`

```python
list_ideas(
    status: str = None,  # Optional filter: "suggested" | "accepted" | "rejected"
    limit: int = 20
) -> {
    "ideas": [
        {
            "idea_id": "idea-123",
            "title": "Deep Work for Developers",
            "suggested_at": "2026-01-05T10:30:00Z",
            "strength": 0.92,
            "status": "suggested",
            "source_count": 3,
            "top_mediums": [
                {"medium": "linkedin_article", "score": 0.9},
                {"medium": "blog", "score": 0.8},
                {"medium": "substack", "score": 0.75}
            ]
        }
    ]
}
```

### MCP Tool: `accept_idea` / `reject_idea`

```python
accept_idea(idea_id: str) -> {"status": "accepted", "idea_id": "..."}
reject_idea(idea_id: str) -> {"status": "rejected", "idea_id": "..."}
```

### Tasks

1. [ ] Find source clusters with relationships (extends/contradicts)
2. [ ] Extract top takeaways from Knowledge Cards
3. [ ] LLM prompt: Generate thesis from combined takeaways
4. [ ] LLM prompt: Identify unique angle ("why only YOU can write this")
5. [ ] Select 2-4 supporting highlights with quotes
6. [ ] Calculate timeliness (recency + optional trending check)
7. [ ] Calculate medium scores
8. [ ] Create `article_ideas` Firestore collection
9. [ ] Implement `suggest_article_ideas` MCP tool
10. [ ] Implement `list_ideas`, `accept_idea`, `reject_idea` tools
11. [ ] Optional: Infografik-Generierung (siehe unten)

### Optional: Infografik-Generierung mit Gemini 3 Pro Image

Generiere automatisch eine Infografik zur Artikel-Idee.

**Voraussetzung:** LLM-Abstraktion erweitern um `generate_image()` Methode:

```python
# src/llm/base.py - neue abstrakte Methode
@abstractmethod
def generate_image(
    self,
    prompt: str,
    config: Optional[ImageGenerationConfig] = None,
) -> ImageResponse:
    """Generate image from prompt (only supported by Gemini 3 Pro Image)."""
    pass
```

**Prompt-Template** (komplette Idee als Kontext):

```python
INFOGRAPHIC_PROMPT = """
Create a professional infographic for a blog article.

ARTICLE IDEA:
Title: {title}
Thesis: {thesis}
Unique Angle: {unique_angle}

KEY INSIGHTS TO VISUALIZE:
{key_highlights_formatted}

VISUAL REQUIREMENTS:
- Modern, clean, minimalist flat lay style
- Clear visual flow showing how the insights connect to the thesis
- Highlight the thesis as the central conclusion
- Include author attributions for credibility
- Professional typography, readable text
- Aspect ratio: 16:9
- Resolution: 4K for sharp text
"""
```

**Nutzung:**

```python
suggest_article_ideas(generate_infographic=True) -> {
    "ideas": [{
        ...
        "infographic": {
            "image_url": "gs://kx-hub/ideas/idea-123.png",
            "prompt_used": "Create a professional infographic...",
            "model": "gemini-3-pro-image"
        }
    }]
}
```

**Tasks für Infografik:**
1. [ ] Erweitere `BaseLLMClient` um `generate_image()` Methode
2. [ ] Implementiere `GeminiImageClient` für Gemini 3 Pro Image
3. [ ] Infografik-Prompt-Template erstellen
4. [ ] Upload zu GCS und URL in Firestore speichern

### Success Metrics

- Each idea has a concrete thesis (not just a topic)
- Each idea has 2-4 supporting highlights with quotes
- Each idea explains WHY this user can uniquely write it
- 80%+ of ideas rated as "I could start writing this now"
- Response time < 10 seconds (LLM call included)
- Optional: Infografik visuell ansprechend und inhaltlich korrekt

---

## Story 6.2: Article Structure & Outline Generation

**Status:** Planned

**Summary:** Generate structured article outlines with section headers, key points per section, and source references.

### Outline Generation Process

```
1. Gather source material:
   - Retrieve all chunks from selected source_ids
   - Include knowledge cards for each source
   - Fetch relationship data between sources

2. Analyze for structure:
   - Identify main themes across sources
   - Find logical flow (chronological, compare/contrast, problem/solution)
   - Detect key quotes/highlights to feature

3. Generate outline:
   - Create 4-7 sections with headers
   - Add bullet points per section
   - Link each point to source chunks
   - Suggest word count per section
```

### MCP Tool: `create_article_outline`
```python
create_article_outline(
    idea_id: str = None,              # From idea log
    # OR manual specification:
    title: str = None,
    source_ids: list = None,

    style: str = "analytical",         # analytical | tutorial | opinion | comparison
    target_length: str = "medium"      # short (~800) | medium (~1500) | long (~3000)
) -> {
    "article_id": "second-brain-for-developers",
    "outline": [
        {
            "section": "Introduction",
            "key_points": ["Hook: Knowledge overload problem", "Thesis: Second brain as solution"],
            "sources": ["building-a-second-brain:chunk-1"],
            "target_words": 200
        },
        {
            "section": "What is a Second Brain?",
            "key_points": ["Definition", "Core principles: CODE"],
            "sources": ["building-a-second-brain:chunk-3", "chunk-4"],
            "target_words": 400
        }
    ],
    "total_target_words": 1500
}
```

### MCP Tool: `update_outline`
```python
update_outline(
    article_id: str,
    section_index: int,
    updates: dict   # {section, key_points, sources, target_words}
) -> {
    "status": "updated",
    "outline": [...]
}
```

### Tasks

1. [ ] Design outline generation prompt (chain-of-thought for structure)
2. [ ] Implement source material aggregation
3. [ ] Create `articles` Firestore collection
4. [ ] Implement `create_article_outline` MCP tool
5. [ ] Implement `update_outline` MCP tool
6. [ ] Add outline visualization helper (Markdown export)

### Success Metrics

- Outlines contain 4-7 logical sections
- Each section has 2-4 key points
- 90%+ of key points link to actual KB chunks
- Outline generation < 15 seconds

---

## Story 6.3: AI-Assisted Draft Generation

**Status:** Planned

**Summary:** Expand outline sections into polished prose with proper source attribution, consistent voice, and markdown formatting.

### Draft Generation Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **Section-by-Section** | Generate one section at a time | Iterative refinement |
| **Full Draft** | Generate complete first draft | Quick start |
| **Expand** | Elaborate on existing content | Adding depth |
| **Rewrite** | Rewrite section with new angle | Changing direction |

### MCP Tool: `expand_section`
```python
expand_section(
    article_id: str,
    section_index: int,
    style_guidance: str = None,    # Optional: "more conversational", "add examples"
    include_quotes: bool = True,   # Embed source quotes
    max_words: int = None          # Override target from outline
) -> {
    "section": "What is a Second Brain?",
    "content": "A Second Brain is an external...",
    "word_count": 412,
    "sources_cited": ["building-a-second-brain:chunk-3"],
    "status": "drafted"
}
```

### MCP Tool: `generate_full_draft`
```python
generate_full_draft(
    article_id: str,
    voice: str = "professional",    # professional | casual | academic
    include_introduction: bool = True,
    include_conclusion: bool = True
) -> {
    "article_id": "...",
    "draft": "# Building a Second Brain...\n\n## Introduction...",
    "word_count": 1523,
    "sections_completed": 6,
    "sources_cited": ["source-1", "source-2"],
    "status": "first_draft"
}
```

### MCP Tool: `refine_section`
```python
refine_section(
    article_id: str,
    section_index: int,
    instruction: str    # "Make it more concise", "Add a practical example"
) -> {
    "section": "...",
    "previous_content": "...",
    "new_content": "...",
    "word_count_delta": -45
}
```

### Source Citation Format

```markdown
According to Tiago Forte, "progressive summarization is the key to
making notes actionable" [^1].

[^1]: Building a Second Brain, Chapter 5 (chunk-id: abc123)
```

### Tasks

1. [ ] Design section expansion prompt with source integration
2. [ ] Implement citation/reference tracking
3. [ ] Create voice/style templates (professional, casual, academic)
4. [ ] Implement `expand_section` MCP tool
5. [ ] Implement `generate_full_draft` MCP tool
6. [ ] Implement `refine_section` MCP tool
7. [ ] Add word count tracking and progress updates

### Success Metrics

- Generated prose is coherent and flows naturally
- 80%+ of claims have source citations
- Voice consistency maintained across sections
- Section expansion < 20 seconds

---

## Story 6.4: Article Development Log (Blog Journal)

**Status:** Planned

**Summary:** Track article development across multiple sessions. Maintain history of changes, decisions, and progress for each article.

### Session Logging

Every interaction with an article logs:
- Date and time
- Action performed (outline, draft, edit, review)
- Changes made (word count delta, sections modified)
- Notes (user's thoughts, decisions, next steps)

### MCP Tool: `get_article_status`
```python
get_article_status(
    article_id: str = None,   # Specific article
    status_filter: str = None # "drafting", "review", etc.
) -> {
    "articles": [
        {
            "article_id": "second-brain-for-developers",
            "title": "Building a Second Brain for Developers",
            "status": "drafting",
            "progress": 0.65,  # 65% of target word count
            "word_count": 975,
            "target_word_count": 1500,
            "last_session": {
                "date": "2026-01-02",
                "action": "Expanded introduction and section 1"
            },
            "sessions_count": 3,
            "days_in_progress": 5
        }
    ]
}
```

### MCP Tool: `log_session`
```python
log_session(
    article_id: str,
    action: str,      # "outline", "draft", "edit", "review", "publish"
    notes: str = None # User's notes
) -> {
    "session_id": "sess-123",
    "logged": True
}
```

### MCP Tool: `get_article_history`
```python
get_article_history(
    article_id: str
) -> {
    "article_id": "...",
    "title": "...",
    "created_at": "...",
    "sessions": [
        {"date": "2026-01-01", "action": "Created outline", "notes": "..."},
        {"date": "2026-01-02", "action": "Drafted sections 1-2", "notes": "..."}
    ],
    "word_count_history": [0, 200, 650, 975]
}
```

### Tasks

1. [ ] Add `sessions` array to article schema
2. [ ] Implement automatic session logging on article modifications
3. [ ] Implement `get_article_status` MCP tool
4. [ ] Implement `log_session` MCP tool
5. [ ] Implement `get_article_history` MCP tool
6. [ ] Add progress calculation (word count / target)

### Success Metrics

- All article modifications are logged
- Session history is retrievable and accurate
- Progress tracking helps resume work after breaks
- Dashboard view shows all active articles

---

## Story 6.5: Article Series & Consolidation

**Status:** Planned

**Summary:** Plan multi-part article series and consolidate related articles into long-form content (ebooks, guides).

### Series Management

```
Series: "Productivity Deep Dive" (5 parts)
├── Part 1: The Second Brain Concept [published]
├── Part 2: PARA Method Explained [drafting]
├── Part 3: Progressive Summarization [outline]
├── Part 4: CODE Framework [idea]
└── Part 5: Putting It All Together [idea]
```

### MCP Tool: `create_series`
```python
create_series(
    title: str,
    description: str,
    article_ids: list = None,    # Existing articles to include
    planned_parts: list = None   # Titles of planned articles
) -> {
    "series_id": "productivity-series",
    "title": "Productivity Deep Dive",
    "parts": [...]
}
```

### MCP Tool: `consolidate_articles`
```python
consolidate_articles(
    article_ids: list,
    title: str,
    format: str = "guide"    # guide | ebook | mega-post
) -> {
    "consolidated_id": "...",
    "title": "The Complete Guide to...",
    "content": "...",
    "word_count": 8500,
    "source_articles": [...]
}
```

### Tasks

1. [ ] Create `article_series` Firestore collection
2. [ ] Add `series_id` field to articles
3. [ ] Implement `create_series` MCP tool
4. [ ] Implement `add_to_series`, `reorder_series` tools
5. [ ] Implement `consolidate_articles` MCP tool
6. [ ] Add series progress tracking

### Success Metrics

- Series can contain 2-10 articles
- Consolidation maintains coherent flow
- Cross-references between series parts work correctly

---

## Story 6.6: Obsidian Export & Publishing Workflow

**Status:** Planned

**Summary:** Export finished articles to Obsidian vault with proper frontmatter, wikilinks to sources, and optional GitHub publishing.

### Export Format

```markdown
---
title: "Building a Second Brain for Developers"
date: 2026-01-15
status: published
tags: [productivity, pkm, developers]
sources:
  - "[[Building a Second Brain]]"
  - "[[The PARA Method]]"
series: "Productivity Deep Dive"
part: 1
---

# Building a Second Brain for Developers

A Second Brain is an external system...

## References

- Building a Second Brain by Tiago Forte
- The PARA Method by Tiago Forte
```

### MCP Tool: `export_to_obsidian`
```python
export_to_obsidian(
    article_id: str,
    vault_path: str = None,      # Default from config
    folder: str = "Blog",        # Subfolder in vault
    create_source_links: bool = True
) -> {
    "file_path": "/vault/Blog/second-brain-for-developers.md",
    "word_count": 1523,
    "sources_linked": 2,
    "status": "exported"
}
```

### MCP Tool: `publish_to_github`
```python
publish_to_github(
    article_id: str,
    repo: str = None,            # Default from config
    branch: str = "main",
    commit_message: str = None
) -> {
    "commit_sha": "abc123",
    "file_path": "content/blog/second-brain-for-developers.md",
    "status": "published"
}
```

### Tasks

1. [ ] Design Obsidian-compatible frontmatter schema
2. [ ] Implement wikilink generation for source references
3. [ ] Implement `export_to_obsidian` MCP tool
4. [ ] Add image handling (if articles reference images)
5. [ ] Implement `publish_to_github` MCP tool
6. [ ] Add publish status tracking

### Success Metrics

- Exported files render correctly in Obsidian
- Wikilinks resolve to existing notes
- Frontmatter is valid YAML
- GitHub commits succeed without conflicts

---

## Story 6.7: Claude Code Integration for Article Editing

**Status:** Planned

**Summary:** Seamless integration with Claude Code for VS Code-based article editing with AI assistance.

### Workflow

```
1. User: "Let's work on my second brain article"
2. Claude: Opens article in VS Code via file path
3. User edits in VS Code with Claude assistance
4. Claude: Tracks changes, suggests improvements
5. User: "Save my progress"
6. Claude: Updates Firestore, logs session
```

### MCP Tool: `open_article_for_editing`
```python
open_article_for_editing(
    article_id: str
) -> {
    "file_path": "/tmp/kx-hub/articles/second-brain-for-developers.md",
    "article_id": "...",
    "status": "drafting",
    "instruction": "Edit in VS Code. Use 'save_article_edits' when done."
}
```

### MCP Tool: `save_article_edits`
```python
save_article_edits(
    article_id: str,
    file_path: str = None   # If different from default
) -> {
    "word_count": 1650,
    "word_count_delta": 125,
    "sections_modified": ["Introduction", "Conclusion"],
    "status": "saved"
}
```

### Claude Code Assistance Features

- **Continue writing**: "Continue from where I left off"
- **Improve section**: "Make this section more engaging"
- **Add sources**: "Find KB sources to support this claim"
- **Check consistency**: "Does this contradict anything in my KB?"
- **Suggest next steps**: "What should I work on next?"

### Tasks

1. [ ] Design local file sync mechanism (Firestore ↔ local markdown)
2. [ ] Implement `open_article_for_editing` MCP tool
3. [ ] Implement `save_article_edits` MCP tool
4. [ ] Add file watcher for auto-save (optional)
5. [ ] Implement consistency check with KB
6. [ ] Add "suggest sources" feature

### Success Metrics

- Seamless round-trip: Firestore → local file → Firestore
- No data loss during editing
- Changes tracked accurately
- Integration feels natural in Claude Code workflow

---

## Implementation Plan

### Phase 1: Foundation (Stories 6.1, 6.2)
- Set up Firestore collections
- Implement idea extraction and outline generation
- Basic MCP tools for idea and outline management

### Phase 2: Drafting (Stories 6.3, 6.4)
- AI-powered draft generation
- Session logging and progress tracking
- Iterative refinement tools

### Phase 3: Publishing (Stories 6.5, 6.6)
- Series management
- Obsidian export
- GitHub publishing

### Phase 4: Integration (Story 6.7)
- Claude Code workflow
- Local file sync
- Advanced editing features

---

## Summary

| Story | Description | Priority | Effort |
|-------|-------------|----------|--------|
| 6.1 | Blog Idea Extraction from Knowledge Base | High | 4-6h |
| 6.2 | Article Structure & Outline Generation | High | 6-8h |
| 6.3 | AI-Assisted Draft Generation | High | 8-10h |
| 6.4 | Article Development Log (Blog Journal) | Medium | 4-6h |
| 6.5 | Article Series & Consolidation | Low | 4-6h |
| 6.6 | Obsidian Export & Publishing Workflow | Medium | 4-6h |
| 6.7 | Claude Code Integration for Article Editing | Medium | 6-8h |

**Total Estimated Effort:** 36-50 hours

**Key Deliverables:**
- 3 new Firestore collections (articles, article_ideas, article_series)
- ~15 new MCP tools for article management
- Complete workflow from idea → published article
- Integration with Obsidian and GitHub

---

## Open Questions

1. **Voice Training**: Should we support custom voice/style profiles?
2. **Image Support**: How to handle images in articles (upload to GCS)?
3. **Collaboration**: Any need for multi-user editing (future)?
4. **SEO Metadata**: Should we generate meta descriptions, keywords?
5. **Publishing Platforms**: Beyond Obsidian - Medium, Substack, Ghost?

---

*This document will be updated as implementation progresses. See [backlog.md](backlog.md) for related stories and dependencies.*
