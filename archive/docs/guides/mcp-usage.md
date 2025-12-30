# kx-hub MCP Server Guide

This guide shows how to interact with your kx-hub knowledge base through an AI assistant (Claude, etc.) that has the MCP server connected.

---

## Quick Start

Just ask naturally! The AI understands your knowledge base and can help you:

```
"What have I been reading about lately?"
"Find articles about microservices"
"Show me my AI/ML cluster"
"Give me reading recommendations"
```

---

## Searching Your Knowledge Base

### Semantic Search

Ask questions in natural language:

```
"Search for articles about platform engineering"
"Find content related to AI agents and tool use"
"What do I have about software architecture patterns?"
```

### By Author or Source

```
"Show me everything by Martin Fowler"
"What have I saved from Hacker News?"
"Find articles from the Netflix tech blog"
```

### By Tags

```
"Show me articles tagged with 'leadership'"
"Find all my DevOps content"
```

### Combining Filters

```
"Find AI articles by Andrej Karpathy"
"Show me recent platform engineering content from InfoQ"
```

---

## Browsing by Time

### Recent Reading

```
"What did I read yesterday?"
"Show me what I saved last week"
"What have I added in the last 3 days?"
```

### Date Ranges

```
"What did I read between October 15 and October 30?"
"Show me November's reading"
```

### Reading Activity Summary

```
"Give me a reading activity summary for last week"
"How much have I been reading lately?"
```

This shows:
- Chunks added per day
- Top sources
- Top authors
- Reading patterns

---

## Exploring Clusters

Your knowledge base is automatically organized into semantic clusters (topic groups).

### List All Clusters

```
"Show me my knowledge clusters"
"What topic areas do I have?"
"List my clusters by size"
```

### Explore a Specific Cluster

```
"Show me the Platform Engineering cluster"
"What's in cluster-28?"
"Explore my AI/ML cluster"
```

### Search Within a Cluster

```
"Search for 'deployment strategies' in my DevOps cluster"
"Find articles about transformers in my AI cluster"
```

### Find Related Clusters

```
"What clusters are related to my Platform Engineering cluster?"
"Show me topics connected to AI agents"
```

---

## Knowledge Cards

Knowledge cards are AI-generated summaries with key takeaways for each saved article.

### View a Knowledge Card

```
"Show me the knowledge card for that article"
"What are the key takeaways from chunk-xyz?"
```

### Search Knowledge Cards

```
"Search knowledge cards for 'testing strategies'"
"Find summaries about microservices patterns"
```

This searches the condensed summaries rather than full content - great for quick concept lookup.

---

## Reading Recommendations

Get AI-powered recommendations for what to read next, based on your interests.

### Basic Requests

```
"Give me some reading recommendations"
"What should I read next?"
"Find me something interesting to read"
```

### Filter by Topic

**By your clusters:**
```
"Give me recommendations about platform engineering"
"What's new in AI agents?"
"Find articles about DevOps and developer experience"
```

**By specific clusters:**
```
"Get recommendations from cluster-28 and cluster-20"
```

**By source category:**
```
"Give me AI news from trusted sources"
"What's new on the German tech sites?"
"Find me business strategy articles"
```

Available categories:
- **tech** - Engineering blogs (martinfowler, netflix, spotify, stripe, etc.)
- **tech_de** - German tech (heise, golem, t3n)
- **ai** - AI/ML sources (anthropic, openai, huggingface, karpathy)
- **devops** - Platform engineering (devops.com, platformengineering.org, k8s)
- **business** - Strategy (hbr, mckinsey, stratechery, a16z)

### Discovery Modes

**Balanced (default):**
```
"Give me today's reading recommendations"
```
Standard mix of relevance, recency, and depth.

**Fresh:**
```
"What's new this week?"
"Give me fresh AI news"
"Catch me up on recent articles"
```
Prioritizes content from the last 30 days.

**Deep:**
```
"Find me something in-depth to read this weekend"
"Give me substantial articles about software architecture"
```
Prioritizes longer, analytical content. Great for weekend reading.

**Surprise Me:**
```
"Surprise me with something different"
"Help me break out of my filter bubble"
"Show me topics I don't usually read about"
```
High randomization, explores adjacent topics.

### Combining Filters

```
"Give me fresh AI news from trusted sources"
"Find in-depth articles about platform engineering"
"Surprise me with something from the business category"
```

### Other Options

**Include previously shown:**
```
"Show me recommendations again, including ones you've shown before"
```

**Reproducible results:**
```
"Give me consistent recommendations (disable randomization)"
```

---

## Managing Configuration

### View Hot Sites Categories

```
"What sources are in the AI hot sites list?"
"Show me the tech_de domains"
"List all hot site categories"
```

### Add/Remove Sources

```
"Add simonwillison.net to the AI sources"
"Remove medium.com from the tech list"
```

### View Ranking Settings

```
"Show me the current recommendation ranking config"
"What weights are used for recommendations?"
```

### Adjust Ranking Weights

```
"Increase the recency weight for recommendations"
"Make recommendations favor depth over freshness"
```

---

## Knowledge Base Stats

```
"How big is my knowledge base?"
"Show me KB statistics"
"How many articles do I have?"
```

Returns:
- Total chunks
- Number of clusters
- Top sources
- Top authors
- Tag distribution

---

## Example Conversations

**Morning catch-up:**
> "What should I read today? Focus on AI and platform engineering."

**Deep dive research:**
> "Search my knowledge base for everything about event-driven architecture, then give me recommendations for more."

**Weekend reading:**
> "Find me 3 in-depth articles for weekend reading about software architecture."

**Breaking routine:**
> "Surprise me - show me something outside my usual topics."

**German tech news:**
> "Was gibt es Neues auf den deutschen Tech-Seiten?"

**Exploring a topic:**
> "Show me my microservices cluster, then find related clusters I might want to explore."

**Activity review:**
> "Give me a summary of my reading activity this month. What topics have I focused on?"

---

## Tips

1. **Be specific about topics** - The more context you give, the better the results
2. **Use semantic search** - Ask questions naturally rather than keyword matching
3. **Explore clusters** - Your clusters reveal your knowledge domains
4. **Try "surprise me" weekly** - Break out of your filter bubble occasionally
5. **Use "fresh" for news** - When you want to catch up on recent developments
6. **Use "deep" for learning** - When you have time for substantial reading
7. **Check related clusters** - Find connections between your interest areas
8. **Review activity summaries** - Understand your reading patterns

---

## What's Available

### Search Tools
- **Semantic search** - Natural language queries across all content
- **Metadata search** - Filter by author, source, tags
- **Date range search** - Find content from specific periods
- **Relative time search** - "last week", "yesterday", etc.
- **Knowledge card search** - Search AI summaries only

### Cluster Tools
- **List clusters** - See all your topic groups
- **Get cluster** - Explore a specific cluster's contents
- **Search within cluster** - Scoped semantic search
- **Related clusters** - Find connected topics

### Activity Tools
- **Recently added** - Quick access to latest saves
- **Reading activity** - Summary statistics
- **Knowledge base stats** - Overall KB metrics

### Recommendation Tools
- **Get recommendations** - AI-powered reading suggestions
- **Hot sites config** - Manage curated source lists
- **Ranking config** - Adjust recommendation algorithm

---

## Behind the Scenes

When you search, the AI uses vector embeddings to find semantically similar content - not just keyword matching. This means "distributed systems" will find articles about "microservices architecture" even if those exact words aren't used.

When you ask for recommendations, the AI:
1. Analyzes your knowledge base to understand your interests
2. Generates search queries based on your clusters and recent reads
3. Searches curated sources (or specific categories you request)
4. Filters for quality and depth
5. Ranks by relevance, recency, and authority
6. Returns diverse recommendations with explanations of why each was chosen
