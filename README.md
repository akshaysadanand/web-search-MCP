# Web Search MCP

An open-source Model Context Protocol (MCP) server that provides web scraping capabilities using a headless Chromium browser powered by [Playwright](https://playwright.dev/) and web search via [SearXNG](https://github.com/searxng/searxng).

## Features

- **Web Scraping** — Navigate to any URL and extract structured text content using a full headless browser
- **Smart Content Extraction** — Automatically detects and extracts main article content using common HTML selectors (`article`, `[role="main"]`, `main`, etc.)
- **Link Discovery** — Extracts up to 50 links from each scraped page with anchor text and URLs
- **Page Title Extraction** — Returns the HTML `<title>` of each page
- **Async Browser Pooling** — Efficiently manages a pool of up to 2 browser pages for concurrent operations
- **Anti-Bot Headers** — Uses realistic user-agent and viewport settings to improve compatibility
- **Web Search** — Search the web using a self-hosted SearXNG instance without tracking or profiling users

## Installation

### Prerequisites

- **Python 3.12+**
- **[uv](https://github.com/astral-sh/uv)** — Fast Python package installer and virtual environment manager
- **[Docker](https://www.docker.com/)** — Required for running a SearXNG instance (for search functionality)

### Setup

1. **Clone the repository**
    ```bash
    git clone https://github.com/akshay/akshaysadanand/web-search-MCP.git
    cd web-search-MCP
    ```

2. **Install dependencies**
    ```bash
    uv sync
    ```

3. **Install Playwright browsers**
    ```bash
    uv run playwright install chromium
    ```

4. **Set up SearXNG (for search functionality)**

    The easiest way is using Docker Compose (includes pre-configured settings with JSON API enabled):

    ```bash
    docker compose up -d
    ```

    Or manually with Docker:

    ```bash
    docker run -d --name searxng -p 8080:8080 \
      -v $(pwd)/searxng/settings.yml:/etc/searxng/settings.yml:ro \
      searxng/searxng
    ```

    > **Note:** This repository includes a pre-configured `searxng/settings.yml` with the JSON output format enabled, which is required for the MCP server to work properly.
5. **Verify installation**
    ```bash
    uv run web-search-mcp
    ```

## Usage

### Running the Server

The MCP server runs as a stdio-based process. It is designed to be launched by an MCP client (Claude Desktop, Cursor, etc.).

```bash
uv run web-search-mcp
```

### Configuration for MCP Clients

#### Claude Desktop

Add the following to your Claude Desktop `settings.json` (open with `Claude > Settings > Developers`):

```json
{
  "mcpServers": {
    "web-search-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/web-search-MCP",
        "run",
        "python",
        "-m",
        "search_mcp.server"
      ]
    }
  }
}
```

#### Cursor / Other MCP Clients

Configure the server to connect via stdio:

| Setting | Value |
|---------|-------|
| Command | `uv` |
| Arguments | `--directory /path/to/web-search-MCP run python -m search_mcp.server` |

## Available Tools

### `web_scrape`

Navigate directly to a URL using a headless Chromium browser and extract the text content.

**Input Schema:**

| Parameter | Type   | Required | Description                              |
|-----------|--------|----------|------------------------------------------|
| `url`     | string | Yes      | The full URL to scrape (e.g., `https://example.com`) |

**Example Usage:**

```json
{
  "url": "https://example.com"
}
```

**Output Format:**

The tool returns a structured response containing:
- **Title** — The page's `<title>` element text
- **Content** — Extracted main body text (up to 50,000 characters)
- **Links** — Up to 20 links with anchor text and href values

**Example Response:**
```
Title: Example Domain

Example Domain
...extracted page content...

Links:
- More information: https://www.iana.org/domains/example
```

### `searxng_search`

Search the web using a self-hosted SearXNG instance. SearXNG is a free internet metasearch engine that aggregates results from multiple search services (Google, DuckDuckGo, Bing, Wikipedia, and many more) without tracking or profiling users.

**Prerequisites:** You must have a SearXNG instance running. The easiest way is via Docker:
```bash
docker run -d -p 8080:8080 searxng/searxng
```

**Input Schema:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | string | Yes | — | The search query (e.g., `'latest AI news'`) |
| `searxng_url` | string | No | `http://localhost:8080` | URL of the SearXNG instance |
| `categories` | string | No | `general` | Search category: `general`, `images`, `videos`, `news`, `map`, `music`, `it`, `science`, `files`, `social_media` |
| `language` | string | No | `all` | Language code (e.g., `'en'`, `'de'`, `'fr'`) |
| `pageno` | integer | No | `1` | Page number starting from 1 |
| `safe_search` | integer | No | `0` | Safe search level: `0`=None, `1`=Moderate, `2`=Strict |
| `max_results` | integer | No | `10` | Maximum number of results to return |

**Example Usage:**

```json
{
  "query": "latest AI news",
  "categories": "general",
  "language": "en",
  "max_results": 5
}
```

**Output Format:**

The tool returns a formatted list of search results:

```
Search Results for "latest AI news"

1. OpenAI Releases GPT-5
   URL: https://openai.com/research/gpt5
   Engine: google, bing
   Snippet: OpenAI today released GPT-5, the latest iteration of their language model with improved reasoning capabilities...

2. Latest Developments in Artificial Intelligence
   URL: https://techcrunch.com/ai-news
   Engine: duckduckgo
   Snippet: A comprehensive overview of the latest developments in AI including breakthroughs in computer vision...

----------------------------------------
Found ~1,234,567 results (page 1)
Suggestions: ai news today, machine learning updates
```

Each result includes the title, URL, source engine(s), and a content snippet.

## SearXNG Configuration

This repository includes a pre-configured `searxng/settings.yml` that enables the JSON output format required by the MCP server. The key configuration change is:

```yaml
formats:
  - html
  - json
```

Without JSON format enabled, the MCP server cannot receive search results in the structured format it expects.

## Architecture

### Server Class: `WebScrapeServer`

The server is built around the `WebScrapeServer` class which manages:

- **Browser Lifecycle** — Initializes a single Chromium instance via Playwright, shared across all requests
- **Page Pool** — Maintains a pool of up to 2 `Page` objects to avoid repeated browser context creation overhead
- **Content Extraction Pipeline** — Multi-strategy approach:
  1. Tries common content selectors (`article`, `[role="main"]`, `#content`, `.post-content`, `.entry-content`, `main`)
  2. Falls back to `<body>` inner text
  3. Uses JavaScript evaluation as a final fallback

### Key Components

| Component | Description |
|-----------|-------------|
| `get_page()` | Returns an available page from the pool, or creates a new one with configured user-agent and viewport |
| `release_page(page)` | Returns a page to the pool, or closes it if the pool is full |
| `scrape_url(url)` | Core scraping logic — navigates, extracts content and links |
| `search_searxng(arguments)` | Searches a SearXNG instance via its JSON API using POST requests |
| `handle_list_tools()` | MCP handler that registers available tools |
| `handle_call_tool(name, arguments)` | MCP handler that dispatches tool calls to the appropriate function |

### Browser Configuration

| Setting | Value |
|---------|-------|
| Engine | Chromium (headless) |
| User-Agent | Chrome 120 on macOS 10_15_7 |
| Viewport | 1920 × 1080 |
| Timeout | 30 seconds |
| Wait Strategy | `domcontentloaded` + 2s pause for JS rendering |

## Development

### Project Structure

```
web-search-MCP/
├── docker-compose.yml    # Docker Compose for SearXNG setup
├── pyproject.toml        # Project metadata and dependencies
├── uv.lock               # Lock file for reproducible builds
├── .gitignore            # Git ignore rules
├── searxng/
│   └── settings.yml      # SearXNG config with JSON API enabled
└── search_mcp/
    ├── __init__.py       # Package init
    └── server.py         # MCP server implementation
```

### Running in Debug Mode

```bash
uv run python -m search_mcp.server --debug
```

### Adding New Tools

To add a new tool, extend the `WebScrapeServer` class:

1. Add a new method for the tool logic
2. Register it in `handle_list_tools()` by appending to the returned `Tool` list
3. Add a dispatch case in `handle_call_tool()`

## Dependencies

| Package     | Version   | Purpose                          |
|-------------|-----------|----------------------------------|
| `mcp`       | >=1.27.1  | MCP server framework             |
| `playwright`| >=1.59.0  | Headless browser automation      |
| `httpx`     | >=0.27.0  | Async HTTP client for SearXNG API|

## License

This project is open source.
