#!/usr/bin/env python3
"""Web Scrape MCP Server - Provides URL content extraction via Playwright and SearXNG search."""

import asyncio
import argparse
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from playwright.async_api import async_playwright, Browser, Page


class WebScrapeServer:
    """MCP Server with web scraping capabilities using Playwright and SearXNG search."""

    def __init__(self):
        self.server = Server("web-search-mcp")
        self.browser: Browser | None = None
        self._page_pool: list[Page] = []
        self._max_pages = 2

    async def get_page(self) -> Page:
        """Get or create a page for browser operations."""
        if self.browser is None:
            raise RuntimeError("Browser not initialized")

        if self._page_pool:
            return self._page_pool.pop()

        context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        context.set_default_timeout(30000)
        page = await context.new_page()
        return page

    def release_page(self, page: Page) -> None:
        """Release a page back to the pool."""
        if len(self._page_pool) < self._max_pages:
            self._page_pool.append(page)
        else:
            try:
                asyncio.get_event_loop().run_until_complete(page.close())
            except Exception:
                pass

    async def scrape_url(self, url: str) -> dict[str, Any]:
        """Scrape text content from a URL."""
        page = await self.get_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            title = await page.title()

            text_content = ""
            content_selectors = [
                "article", "[role='main']", "#content",
                ".post-content", ".entry-content", "main",
            ]

            for selector in content_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        for el in elements[:3]:
                            text = await el.inner_text()
                            if len(text) > 100:
                                text_content = text
                                break
                        if text_content:
                            break
                except Exception:
                    continue

            if not text_content:
                try:
                    text_content = await page.inner_text("body")
                except Exception:
                    pass

            if not text_content:
                text_content = await page.evaluate("""() => {
                    const el = document.querySelector('article') 
                        || document.querySelector('[role="main"]')
                        || document.body;
                    return el ? el.innerText : '';
                }""")

            text_content = "\n".join(
                line for line in text_content.split("\n") if line.strip()
            )

            links = await page.query_selector_all("a[href]")
            link_list: list[dict[str, str]] = []
            for link in links[:50]:
                try:
                    href = await link.get_attribute("href") or ""
                    text = (await link.inner_text() or "").strip()
                    if text and href:
                        link_list.append({"text": text, "url": href})
                except Exception:
                    continue

            return {
                "title": title,
                "url": url,
                "content": text_content[:50000] if text_content else "",
                "links": link_list,
            }
        finally:
            self.release_page(page)

    async def search_searxng(self, arguments: dict) -> str:
        """Search using a self-hosted SearXNG instance via its JSON API."""
        query = arguments.get("query", "")
        if not query:
            raise ValueError("Query is required for searxng_search")

        searxng_url = arguments.get("searxng_url", "http://localhost:8080").rstrip("/")
        categories = arguments.get("categories", "general")
        language = arguments.get("language", "all")
        pageno = int(arguments.get("pageno", 1))
        safe_search = int(arguments.get("safe_search", 0))
        max_results = int(arguments.get("max_results", 10))

        params = {
            "q": query,
            "format": "json",
            "categories": categories,
            "language": language,
            "pageno": pageno,
            "safesearch": safe_search,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{searxng_url}/search",
                    data=params,
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as e:
                return f"Error connecting to SearXNG instance at {searxng_url}: {e}"
            except Exception as e:
                return f"Error querying SearXNG: {e}"

        results = data.get("results", [])
        number_of_results = data.get("number_of_results", 0)
        suggestions = data.get("suggestions", [])

        # Limit results to max_results
        displayed_results = results[:max_results]

        if not displayed_results:
            return f"No results found for '{query}'."

        # Build formatted output
        lines: list[str] = []
        lines.append(f"Search Results for \"{query}\"")
        lines.append("=" * 40)
        lines.append("")

        for i, result in enumerate(displayed_results, 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")
            engines = result.get("engines", [])
            engine_str = ", ".join(engines) if engines else "unknown"

            lines.append(f"{i}. {title}")
            lines.append(f"   URL: {url}")
            lines.append(f"   Engine: {engine_str}")
            if content:
                # Truncate long snippets to ~300 characters
                snippet = content[:300]
                if len(content) > 300:
                    snippet += "..."
                lines.append(f"   Snippet: {snippet}")
            lines.append("")

        # Footer with total results and suggestions
        lines.append("-" * 40)
        if number_of_results:
            lines.append(f"Found ~{number_of_results:,} results (page {pageno})")
        else:
            lines.append(f"Found {len(displayed_results)} results (page {pageno})")

        if suggestions:
            suggestion_str = ", ".join(suggestions[:5])
            lines.append(f"Suggestions: {suggestion_str}")

        return "\n".join(lines)

    async def handle_list_tools(self):
        """Handler for listing available tools."""
        return [
            Tool(
                name="web_scrape",
                description=(
                    "Navigate directly to a URL using a headless browser and extract the text content. "
                    "Use this tool to read the full text of any webpage."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The full URL to scrape (e.g., 'https://example.com')",
                        },
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="searxng_search",
                description=(
                    "Search the web using a self-hosted SearXNG instance. "
                    "SearXNG is a free internet metasearch engine that aggregates results from multiple "
                    "search services without tracking users. You must have a SearXNG instance running. "
                    "Setup: docker run -d -p 8080:8080 searxng/searxng"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query (e.g., 'latest AI news')",
                        },
                        "searxng_url": {
                            "type": "string",
                            "description": "URL of the SearXNG instance (default: http://localhost:8080)",
                        },
                        "categories": {
                            "type": "string",
                            "description": (
                                "Search category: general, images, videos, news, map, music, it, "
                                "science, files, social_media (default: general)"
                            ),
                        },
                        "language": {
                            "type": "string",
                            "description": (
                                "Language code for search results (e.g., 'en', 'de', 'fr', 'all'). "
                                "Default: all"
                            ),
                        },
                        "pageno": {
                            "type": "integer",
                            "description": "Page number starting from 1 (default: 1)",
                        },
                        "safe_search": {
                            "type": "integer",
                            "description": (
                                "Safe search level: 0=None, 1=Moderate, 2=Strict (default: 0)"
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default: 10)",
                        },
                    },
                    "required": ["query"],
                },
            ),
        ]

    async def handle_call_tool(self, name: str, arguments: dict):
        """Handler for calling tools."""
        try:
            if name == "web_scrape":
                url = arguments.get("url", "")
                if not url:
                    raise ValueError("URL is required for web_scrape")

                if not url.startswith(("http://", "https://")):
                    url = "https://" + url

                result = await self.scrape_url(url)

                output_parts: list[str] = []
                if result.get("title"):
                    output_parts.append(f"Title: {result['title']}")
                if result.get("content"):
                    output_parts.append(f"\n{result['content']}")

                if result.get("links"):
                    link_text = "\nLinks:\n" + "\n".join(
                        f"- {link['text']}: {link['url']}"
                        for link in result["links"][:20]
                    )
                    output_parts.append(link_text)

                return [TextContent(type="text", text="\n".join(output_parts))]

            elif name == "searxng_search":
                result = await self.search_searxng(arguments)
                return [TextContent(type="text", text=result)]

            else:
                raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            error_msg = f"Error executing '{name}': {str(e)}"
            return [TextContent(type="text", text=error_msg)]

    async def run(self):
        """Run the MCP server."""
        pm = await async_playwright().start()
        try:
            self.browser = await pm.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            # Register tools using class methods
            self.server.list_tools()(self.handle_list_tools)
            self.server.call_tool()(self.handle_call_tool)

            async with stdio_server() as (read_stream, write_stream):
                init_options = self.server.create_initialization_options()
                await self.server.run(read_stream, write_stream, init_options)

        finally:
            if self.browser:
                await self.browser.close()


def main():
    """Entry point for the MCP server."""
    parser = argparse.ArgumentParser(description="Web Search MCP Server")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    server = WebScrapeServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()