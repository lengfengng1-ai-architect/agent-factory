import os
import shutil
import sys
import subprocess
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from langchain.tools import tool, BaseTool
from langchain.messages import ToolMessage, SystemMessage
from ddgs import DDGS
from app import models
from app.database import workspace_dir
from app.logger import get_logger, truncate_for_log

logger = get_logger(__name__)

# Playwright browser state — thread-local for LangChain ToolNode multi-thread safety
import threading
_thread_local = threading.local()
_browser_launch_error: Optional[str] = None

# Shared browser state persisted to file for cross-process/thread access
def _browser_state_path(agent_id: int) -> str:
    return os.path.join(get_workspace_path(agent_id), "browser_state.json")

def _update_browser_state(agent_id: int, url: str = None, title: str = None):
    """Update browser state persisted to agent workspace (cross-process safe)."""
    path = _browser_state_path(agent_id)
    state = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass
    if url is not None:
        state["url"] = url
    if title is not None:
        state["title"] = title
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)

def _read_browser_state(agent_id: int) -> dict:
    """Read persisted browser state."""
    path = _browser_state_path(agent_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _get_thread_browser():
    """Get or create a thread-local Playwright browser instance."""
    # Check if existing browser is still healthy
    if hasattr(_thread_local, 'browser') and _thread_local.browser:
        try:
            if _thread_local.browser.is_connected():
                # Quick health check: try to get browser version
                _thread_local.browser.new_context().close()
                return _thread_local.browser
        except Exception:
            # Browser is dead, clean up and recreate
            pass

    # Clean up any stale resources
    if hasattr(_thread_local, 'pw') and _thread_local.pw:
        try:
            _thread_local.pw.stop()
        except Exception:
            pass

    from playwright.sync_api import sync_playwright
    _thread_local.pw = sync_playwright().start()

    browsers_dir = _get_browsers_dir()
    if browsers_dir:
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_dir
        if not _is_chromium_installed(browsers_dir):
            if not _install_chromium(browsers_dir):
                global _browser_launch_error
                _browser_launch_error = (
                    "Chromium browser not found. Please run the following command to install it:\n"
                    f"  PLAYWRIGHT_BROWSERS_PATH={browsers_dir} playwright install chromium"
                )
                raise RuntimeError(_browser_launch_error)

    _thread_local.browser = _thread_local.pw.chromium.launch(headless=True)
    _thread_local.agent_pages = {}  # Reset page cache on browser recreate
    _browser_launch_error = None
    return _thread_local.browser

def _get_thread_agent_page(agent_id: int):
    """Get or create a thread-local browser page for an agent."""
    if not hasattr(_thread_local, 'agent_pages'):
        _thread_local.agent_pages = {}
    if agent_id not in _thread_local.agent_pages:
        browser = _get_thread_browser()
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        _thread_local.agent_pages[agent_id] = {"context": context, "page": page}
    return _thread_local.agent_pages[agent_id]["page"]

def _screenshot_thread_agent_page(agent_id: int, page) -> str:
    """Take a screenshot and save to agent workspace (thread-local)."""
    ws = get_workspace_path(agent_id)
    path = os.path.join(ws, "browser_latest.png")
    page.screenshot(path=path, full_page=False)
    return path

def close_thread_agent_browser(agent_id: int):
    """Close thread-local browser context for an agent."""
    if hasattr(_thread_local, 'agent_pages') and agent_id in _thread_local.agent_pages:
        try:
            _thread_local.agent_pages[agent_id]["context"].close()
        except Exception:
            pass
        del _thread_local.agent_pages[agent_id]

def close_all_thread_browsers():
    """Close all thread-local browser contexts and the browser."""
    if hasattr(_thread_local, 'agent_pages'):
        for agent_id in list(_thread_local.agent_pages.keys()):
            close_thread_agent_browser(agent_id)
        delattr(_thread_local, 'agent_pages')
    if hasattr(_thread_local, 'browser'):
        try:
            _thread_local.browser.close()
        except Exception:
            pass
        delattr(_thread_local, 'browser')
    if hasattr(_thread_local, 'pw'):
        try:
            _thread_local.pw.stop()
        except Exception:
            pass
        delattr(_thread_local, 'pw')


# Legacy names for backward compatibility (async API removed)
_pw_sync = None
_browser_sync = None
_agent_pages_sync: Dict[int, Dict[str, Any]] = {}


def _get_browsers_dir() -> str:
    """Get the directory where Playwright browsers should be installed."""
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            bundled = os.path.join(meipass, "playwright-browsers")
            if os.path.isdir(bundled):
                return bundled
        data_dir = os.environ.get("AGENT_FACTORY_DATA_DIR")
        if not data_dir:
            data_dir = os.path.join(Path.home(), ".agent-factory")
        return os.path.join(data_dir, "playwright-browsers")
    return ""

def _is_chromium_installed(browsers_dir: str) -> bool:
    """Check if Chromium is installed in the given browsers directory."""
    if not browsers_dir or not os.path.isdir(browsers_dir):
        return False
    for entry in os.listdir(browsers_dir):
        if entry.startswith("chromium"):
            marker = os.path.join(browsers_dir, entry, "INSTALLATION_COMPLETE")
            if os.path.exists(marker):
                return True
    return False

def _install_chromium(browsers_dir: str) -> bool:
    """Try to install Chromium using Playwright CLI."""
    try:
        env = os.environ.copy()
        env["PLAYWRIGHT_BROWSERS_PATH"] = browsers_dir
        import playwright
        driver_dir = Path(playwright.__file__).parent / "driver"
        if sys.platform == "win32":
            driver = driver_dir / "playwright.cmd"
        else:
            driver = driver_dir / "playwright.sh"
        if driver.exists():
            subprocess.run([str(driver), "install", "chromium"], env=env, check=True, capture_output=True)
            return True
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], env=env, check=True, capture_output=True)
        return True
    except Exception:
        return False





def get_workspace_path(agent_id: int) -> str:
    """Get the workspace directory path for an agent."""
    path = os.path.join(workspace_dir, str(agent_id))
    os.makedirs(path, exist_ok=True)
    return path


def _web_search_raw(query: str) -> str:
    """Raw web search implementation (not a tool — used by _create_search_tool)."""
    try:
        logger.info(f"[WEB SEARCH] query={query}")
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                logger.info(f"[WEB SEARCH EMPTY] query={query}")
                return "No results found."
            result_text = "\n\n".join(
                [
                    f"Title: {r['title']}\nSnippet: {r['body']}\nURL: {r.get('href', 'N/A')}"
                    for r in results
                ]
            )
            logger.info(f"[WEB SEARCH OK] query={query} results={len(results)}")
            return result_text, results
    except Exception as e:
        logger.exception(f"[WEB SEARCH ERROR] query={query} error={e}")
        return f"Search error: {e}", []


def _create_search_tool(agent_id: int):
    from app.redis_client import add_chat_source

    @tool
    def web_search(query: str) -> str:
        """Search the web for information using DuckDuckGo.

        IMPORTANT: This tool ONLY returns search result titles, snippets,
        and URLs. It does NOT read the actual web page content.

        For real-time data (weather, news, sports scores, current events,
        prices, statistics, etc.), you MUST use browser_navigate + browser_get_text
        after web_search to read the full page content. Search snippets alone
        are often outdated or incomplete for real-time information.

        Best for: finding relevant URLs to explore, discovering multiple
        sources for the same topic.

        Workflow for real-time queries:
        1. web_search(query) → get URLs
        2. browser_navigate(best_url) → load page
        3. browser_get_text() → read full content
        4. If data is missing or incomplete, try the NEXT URL from search results

        Args:
            query: The search query string.
        """
        try:
            logger.info(f"[WEB SEARCH] agent_id={agent_id} query={query}")
            result_text, results = _web_search_raw(query)
            if not results:
                logger.info(f"[WEB SEARCH EMPTY] agent_id={agent_id} query={query}")
                return result_text
            # Record each search result URL as a source
            for r in results:
                href = r.get("href", "")
                title = r.get("title", "")
                if href:
                    try:
                        add_chat_source(agent_id, href, title, "search")
                    except Exception:
                        pass  # Don't fail search if source tracking fails
            logger.info(f"[WEB SEARCH OK] agent_id={agent_id} query={query} results={len(results)}")
            return result_text
        except Exception as e:
            logger.exception(f"[WEB SEARCH ERROR] agent_id={agent_id} query={query} error={e}")
            return f"Search error: {e}"

    return web_search


def _resolve_path(file_path: str, root_dir: str) -> str:
    """Resolve a path relative to root_dir and enforce sandboxing."""
    full_path = os.path.join(root_dir, file_path)
    real_path = os.path.realpath(full_path)
    real_root = os.path.realpath(root_dir)
    if not real_path.startswith(real_root):
        raise ValueError("Access denied: path is outside the allowed directory.")
    return real_path


def _create_file_tools(root_dir: str) -> List[BaseTool]:
    """Create file management tools scoped to root_dir."""

    @tool
    def read_file(file_path: str) -> str:
        """Read the contents of a file.

        Args:
            file_path: Path to the file relative to the workspace root.
        """
        try:
            real_path = _resolve_path(file_path, root_dir)
            with open(real_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"

    @tool
    def write_file(file_path: str, content: str) -> str:
        """Write content to a file.

        Args:
            file_path: Path to the file relative to the workspace root.
            content: The content to write.
        """
        try:
            real_path = _resolve_path(file_path, root_dir)
            os.makedirs(os.path.dirname(real_path), exist_ok=True)
            with open(real_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"File written successfully: {file_path}"
        except Exception as e:
            return f"Error writing file: {e}"

    @tool
    def list_directory(directory: str = ".") -> str:
        """List files and directories in a specified folder.

        Args:
            directory: Directory path relative to the workspace root.
        """
        try:
            real_path = _resolve_path(directory, root_dir)
            items = os.listdir(real_path)
            return "\n".join(items) if items else "(empty directory)"
        except Exception as e:
            return f"Error listing directory: {e}"

    @tool
    def copy_file(source_path: str, destination_path: str) -> str:
        """Create a copy of a file in a specified location.

        Args:
            source_path: Source file path relative to the workspace root.
            destination_path: Destination file path relative to the workspace root.
        """
        try:
            real_src = _resolve_path(source_path, root_dir)
            real_dst = _resolve_path(destination_path, root_dir)
            os.makedirs(os.path.dirname(real_dst), exist_ok=True)
            shutil.copy2(real_src, real_dst)
            return f"File copied from {source_path} to {destination_path}"
        except Exception as e:
            return f"Error copying file: {e}"

    @tool
    def move_file(source_path: str, destination_path: str) -> str:
        """Move or rename a file from one location to another.

        Args:
            source_path: Source file path relative to the workspace root.
            destination_path: Destination file path relative to the workspace root.
        """
        try:
            real_src = _resolve_path(source_path, root_dir)
            real_dst = _resolve_path(destination_path, root_dir)
            os.makedirs(os.path.dirname(real_dst), exist_ok=True)
            shutil.move(real_src, real_dst)
            return f"File moved from {source_path} to {destination_path}"
        except Exception as e:
            return f"Error moving file: {e}"

    @tool
    def file_delete(file_path: str) -> str:
        """Delete a file.

        Args:
            file_path: Path to the file relative to the workspace root.
        """
        try:
            real_path = _resolve_path(file_path, root_dir)
            os.remove(real_path)
            return f"File deleted: {file_path}"
        except Exception as e:
            return f"Error deleting file: {e}"

    @tool
    def file_search(pattern: str, directory: str = ".") -> str:
        """Recursively search for files matching a regex pattern.

        Args:
            pattern: Regex pattern to match filenames.
            directory: Directory to search in, relative to the workspace root.
        """
        import re

        try:
            real_path = _resolve_path(directory, root_dir)
            matches = []
            for root, _, files in os.walk(real_path):
                for f in files:
                    if re.search(pattern, f):
                        rel = os.path.relpath(os.path.join(root, f), real_path)
                        matches.append(rel)
            return "\n".join(matches) if matches else "No matches found."
        except Exception as e:
            return f"Error searching files: {e}"

    return [
        read_file,
        write_file,
        list_directory,
        copy_file,
        move_file,
        file_delete,
        file_search,
    ]


def _create_browser_tools(agent_id: int) -> List[BaseTool]:
    """Create browser automation tools for an agent (sync for LangChain compatibility)."""

    @tool
    def browser_navigate(url: str) -> str:
        """Navigate to a specific URL and load the full page content.

        Use this tool to READ THE FULL CONTENT of web pages. This is
        ESSENTIAL for real-time data that search snippets cannot provide:
        - Weather forecasts, current conditions
        - News articles, current events
        - Sports scores, live updates
        - Prices, statistics, product information
        - Any data that changes frequently

        After navigation, the page waits 1 second for dynamic content
        (JavaScript-rendered data) to load, then takes a screenshot.

        IMPORTANT: If the first URL doesn't have the data you need,
        try OTHER URLs from the search results. Do NOT give up after
        one attempt.

        Typical workflow for real-time queries:
        1. web_search("topic") → get multiple URLs
        2. browser_navigate("https://best-url.com") → load page
        3. browser_get_text() → read full content
        4. If data is missing: browser_navigate("https://next-url.com") → try again

        Args:
            url: The URL to navigate to (must include http:// or https://).
        """
        try:
            logger.info(f"[BROWSER NAVIGATE] agent_id={agent_id} url={url}")
            page = _get_thread_agent_page(agent_id)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            # Wait for dynamic content (JavaScript-rendered data) to load
            page.wait_for_timeout(1000)
            title = page.title()
            _update_browser_state(agent_id, url=page.url, title=title)
            _screenshot_thread_agent_page(agent_id, page)

            # Record as a browsed source
            try:
                from app.redis_client import add_chat_source
                add_chat_source(agent_id, url, title, "browse")
            except Exception:
                pass

            logger.info(f"[BROWSER NAVIGATE OK] agent_id={agent_id} title={title}")
            return f"Navigated to: {url}\nPage title: {title}"
        except Exception as e:
            logger.exception(f"[BROWSER NAVIGATE ERROR] agent_id={agent_id} url={url} error={e}")
            return f"Browser navigation error: {e}"

    @tool
    def browser_click(selector_or_text: str) -> str:
        """Click an element on the page by CSS selector or text content.

        Use this when you need to interact with the current page:
        - Click a "Load more" or "Next page" button to see more content
        - Click a link to navigate to a related page
        - Submit a form after filling it with browser_type
        - Accept cookies or dismiss popups that block content

        After clicking, the page will wait for network idle and a
        screenshot is automatically saved.

        Args:
            selector_or_text: CSS selector (e.g., '#submit', '.button', 'a[href="/login"]')
                             or visible text content of the element to click.
        """
        try:
            logger.info(f"[BROWSER CLICK] agent_id={agent_id} selector={selector_or_text}")
            page = _get_thread_agent_page(agent_id)
            try:
                page.click(selector_or_text, timeout=5000)
            except Exception:
                page.get_by_text(selector_or_text, exact=False).first.click(timeout=5000)
            page.wait_for_load_state("networkidle", timeout=10000)
            title = page.title()
            _update_browser_state(agent_id, url=page.url, title=title)
            _screenshot_thread_agent_page(agent_id, page)
            logger.info(f"[BROWSER CLICK OK] agent_id={agent_id} title={title}")
            return f"Clicked '{selector_or_text}'. Current page: {title}"
        except Exception as e:
            logger.exception(f"[BROWSER CLICK ERROR] agent_id={agent_id} selector={selector_or_text} error={e}")
            return f"Browser click error: {e}"

    @tool
    def browser_type(selector: str, text: str) -> str:
        """Type text into an input field.

        Use this to interact with forms and search boxes on the current page:
        - Fill a search box and then click the search button
        - Enter credentials or form data
        - Type a query into a website's internal search

        After typing, a screenshot is automatically saved.

        Args:
            selector: CSS selector of the input field (e.g., '#search-input', 'input[name="q"]').
            text: Text to type into the field.
        """
        try:
            logger.info(f"[BROWSER TYPE] agent_id={agent_id} selector={selector} text_len={len(text)}")
            page = _get_thread_agent_page(agent_id)
            page.fill(selector, text, timeout=10000)
            _screenshot_thread_agent_page(agent_id, page)
            logger.info(f"[BROWSER TYPE OK] agent_id={agent_id}")
            return f"Typed '{text}' into '{selector}'"
        except Exception as e:
            logger.exception(f"[BROWSER TYPE ERROR] agent_id={agent_id} selector={selector} error={e}")
            return f"Browser type error: {e}"

    @tool
    def browser_get_text() -> str:
        """Extract the full visible text content from the current browser page.

        Use this AFTER browser_navigate to read the actual page content.
        This returns the FULL TEXT of the page (up to 12,000 chars).

        IMPORTANT: If the extracted text does NOT contain the information
        you need, do NOT give up. Navigate to another URL from the search
        results and try again.

        Best for: extracting text content, structured data, news articles,
        documentation, product information, or any information from web pages.

        Returns the main readable text, excluding scripts and styles.
        """
        try:
            logger.info(f"[BROWSER GET_TEXT] agent_id={agent_id}")
            page = _get_thread_agent_page(agent_id)
            # Wait for dynamic content and network requests to settle
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            page.wait_for_timeout(800)

            # Extract text using multiple strategies for dynamic sites
            result = page.evaluate(r"""() => {
                // Page title
                const pageTitle = document.title;

                // Meta tags
                const metaDesc = document.querySelector('meta[name="description"]')?.content || '';
                const metaKeywords = document.querySelector('meta[name="keywords"]')?.content || '';
                const ogTitle = document.querySelector('meta[property="og:title"]')?.content || '';
                const ogDesc = document.querySelector('meta[property="og:description"]')?.content || '';

                // Extract from window.__INITIAL_STATE__
                let initialState = null;
                try {
                    if (window.__INITIAL_STATE__) {
                        initialState = JSON.stringify(window.__INITIAL_STATE__, null, 2).slice(0, 3000);
                    }
                } catch(e) {}

                // Generic JSON data in script tags
                let scriptData = [];
                const genericKeys = ['data', 'config', 'props', 'state', 'initialData', 'payload', 'content', 'result', 'items', 'list', 'details', 'pageData', 'appData'];
                const keyPattern = genericKeys.join('|');
                document.querySelectorAll('script').forEach(s => {
                    const txt = s.innerText || s.textContent || '';
                    if (!txt.includes('{') && !txt.includes('[')) return;
                    const matches = txt.match(new RegExp('\\{[^{}]*"(' + keyPattern + ')"[^{}]*\\}', 'gi'));
                    if (matches) scriptData.push(...matches.slice(0, 5));
                });

                // Table data extraction
                let tableData = [];
                document.querySelectorAll('table').forEach(table => {
                    const rows = [];
                    table.querySelectorAll('tr').forEach(tr => {
                        const cells = [];
                        tr.querySelectorAll('td, th').forEach(cell => {
                            const text = cell.innerText?.trim() || '';
                            if (text) cells.push(text);
                        });
                        if (cells.length) rows.push(cells.join(' | '));
                    });
                    if (rows.length) tableData.push(rows.join('\n'));
                });

                // Largest content block by word count
                let largestBlock = '';
                let maxWords = 0;
                const candidates = document.querySelectorAll('p, div, article, section, main');
                candidates.forEach(el => {
                    const text = el.innerText?.trim() || '';
                    const wordCount = text.split(/\s+/).length;
                    if (wordCount > maxWords && text.length > largestBlock.length) {
                        maxWords = wordCount;
                        largestBlock = text;
                    }
                });

                // Main page text (cleaned)
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('script, style, nav, header, footer, aside, iframe').forEach(el => el.remove());
                const mainText = clone.innerText?.trim() || '';

                return {
                    pageTitle: pageTitle,
                    mainText: mainText.slice(0, 8000),
                    metaDescription: metaDesc,
                    metaKeywords: metaKeywords,
                    ogTitle: ogTitle,
                    ogDescription: ogDesc,
                    tables: tableData.slice(0, 5),
                    largestContentBlock: largestBlock.slice(0, 3000),
                    initialState: initialState,
                    scriptSnippets: scriptData.slice(0, 10),
                };
            }""")

            parts = []

            # Add page title for context
            title = result.get("pageTitle", "")
            if title:
                parts.append(f"Page Title: {title}")
                parts.append("")

            # Add meta description if found
            metaDesc = result.get("metaDescription", "")
            if metaDesc:
                parts.append("=== Meta Description ===")
                parts.append(metaDesc)
                parts.append("")

            # Add meta keywords if found
            metaKeywords = result.get("metaKeywords", "")
            if metaKeywords:
                parts.append("=== Meta Keywords ===")
                parts.append(metaKeywords)
                parts.append("")

            # Add Open Graph data if found
            ogTitle = result.get("ogTitle", "")
            ogDesc = result.get("ogDescription", "")
            if ogTitle or ogDesc:
                parts.append("=== Open Graph Data ===")
                if ogTitle:
                    parts.append(f"og:title: {ogTitle}")
                if ogDesc:
                    parts.append(f"og:description: {ogDesc}")
                parts.append("")

            # Add table data if found
            tables = result.get("tables", [])
            if tables:
                parts.append("=== Tables ===")
                for i, t in enumerate(tables):
                    parts.append(f"--- Table {i+1} ---")
                    parts.append(t)
                parts.append("")

            # Add largest content block if found
            largestBlock = result.get("largestContentBlock", "")
            if largestBlock:
                parts.append("=== Largest Content Block ===")
                parts.append(largestBlock)
                parts.append("")

            # Add initial state if found
            init = result.get("initialState")
            if init:
                parts.append("=== Page Initial State (from JS) ===")
                parts.append(init)
                parts.append("")

            # Add script snippets if found
            scripts = result.get("scriptSnippets", [])
            if scripts:
                parts.append("=== Script Data Snippets ===")
                parts.extend(scripts)
                parts.append("")

            # Add main text
            main = result.get("mainText", "")
            if main:
                parts.append("=== Page Text ===")
                parts.append(main)

            full = "\n".join(parts).strip()
            if not full:
                logger.info(f"[BROWSER GET_TEXT EMPTY] agent_id={agent_id}")
                return "(page has no visible text)"
            if len(full) > 12000:
                full = full[:12000] + "\n... (truncated)"
            logger.info(f"[BROWSER GET_TEXT OK] agent_id={agent_id} len={len(full)} tables={len(tables)} scripts={len(scripts)} blocks={1 if largestBlock else 0}")
            return full
        except Exception as e:
            logger.exception(f"[BROWSER GET_TEXT ERROR] agent_id={agent_id} error={e}")
            return f"Browser get_text error: {e}"

    @tool
    def browser_screenshot() -> str:
        """Take a screenshot of the current page.

        Use this to capture the current visual state of the browser
        for the user to see. This is also done automatically after
        navigate, click, and type operations.

        Returns the file path of the saved screenshot.
        """
        try:
            logger.info(f"[BROWSER SCREENSHOT] agent_id={agent_id}")
            page = _get_thread_agent_page(agent_id)
            path = _screenshot_thread_agent_page(agent_id, page)
            logger.info(f"[BROWSER SCREENSHOT OK] agent_id={agent_id} path={path}")
            return f"Screenshot saved: {path}"
        except Exception as e:
            logger.exception(f"[BROWSER SCREENSHOT ERROR] agent_id={agent_id} error={e}")
            return f"Browser screenshot error: {e}"

    return [
        browser_navigate,
        browser_click,
        browser_type,
        browser_get_text,
        browser_screenshot,
    ]


@tool
def get_current_time() -> str:
    """Get the current system date and time.

    Use this tool whenever the user asks about:
    - Current date, time, day of week, month, year
    - Upcoming holidays, events, or deadlines relative to "now"
    - Age calculations, duration since/until a specific date
    - Any query containing words like "today", "now", "current", "今年",
      "今天", "现在", "最近", " upcoming", "deadline"

    LLMs do NOT have accurate knowledge of the current date/time.
    Always call this tool first for any time-sensitive query.

    Returns:
        A string with the current date, time, and timezone in Chinese.
    """
    from datetime import datetime, timezone
    import time
    tz = time.strftime("%Z")
    now = datetime.now()
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[now.weekday()]
    result = (
        f"当前系统时间：{now.strftime('%Y年%m月%d日')} {weekday} "
        f"{now.strftime('%H:%M:%S')}（时区：{tz}）"
    )
    logger.info(f"[GET CURRENT TIME] {result}")
    return result


def get_agent_tools(
    agent: models.Agent, override_root_dir: Optional[str] = None
) -> List[BaseTool]:
    """Build tool list for an agent based on its config."""
    tools: List[BaseTool] = []
    cfg = agent.config or {}

    # Always inject current time tool — LLMs have no reliable clock
    tools.append(get_current_time)

    if cfg.get("enable_browsing"):
        tools.append(_create_search_tool(agent.id))
        tools.extend(_create_browser_tools(agent.id))

    if cfg.get("enable_file_access"):
        root = override_root_dir or cfg.get("file_access_root", "")
        if root:
            if not os.path.isabs(root):
                root = os.path.join(workspace_dir, root)
        else:
            root = get_workspace_path(agent.id)
        os.makedirs(root, exist_ok=True)
        tools.extend(_create_file_tools(root))

    logger.info(f"[GET AGENT TOOLS] agent_id={agent.id} tools={[t.name for t in tools]}")
    return tools


_BROWSER_TOOL_GUIDE = (
    "\n\n--- CRITICAL: Browser Tool Usage Rules ---\n"
    "You have web_search and browser automation tools. You CAN and SHOULD "
    "use them WITHOUT asking for permission. Do NOT say you need user authorization. "
    "Do NOT say you cannot access real-time data. You CAN access ANY public web page.\n\n"
    "RULE 1 — NEVER ask permission: When user asks for data, DIRECTLY call tools. "
    "Do NOT preface with 'I cannot' or 'I need authorization'. Just DO IT.\n\n"
    "RULE 2 — Real-time data workflow (weather, news, prices, statistics, etc.):\n"
    "   Step 1: web_search(query) → get URLs\n"
    "   Step 2: browser_navigate(url) → load page\n"
    "   Step 3: browser_get_text() → extract data\n"
    "   Step 4: If data missing → browser_navigate(next_url) → try again\n"
    "   Step 5: Keep trying DIFFERENT URLs until data is found\n\n"
    "RULE 3 — web_search ONLY gives summaries. For actual data you MUST use "
    "browser_navigate + browser_get_text. Summaries are NOT sufficient.\n\n"
    "RULE 4 — Many modern websites serve data via JavaScript. The browser_get_text "
    "tool handles this by waiting for JS to execute and extracting from the rendered "
    "DOM. It also attempts to read structured data from page scripts "
    "(window.__INITIAL_STATE__, etc.), meta tags, and HTML tables.\n\n"
    "RULE 5 — If you see '-', 'N/A', or empty values, it means "
    "the page uses heavy JS rendering. Try:\n"
    "   a) Wait — the tool already waits for JS, but some sites need more time\n"
    "   b) Try another URL from search results\n"
    "   c) Look for data in tables, meta tags, or the page text even if formatted strangely\n\n"
    "RULE 6 — Do NOT apologize for uncertainty. Do NOT disclaim limitations. "
    "Report what you found, even if incomplete. If you found partial data, report it."
)


def _has_browser_tools(tools: List[BaseTool]) -> bool:
    """Check if the tool list includes browser automation tools."""
    return any(t.name.startswith("browser_") for t in tools) if tools else False


def _inject_browser_guide(messages, system_prompt, tools):
    """Inject browser tool usage guide into messages or system_prompt.
    
    Returns (new_messages, new_system_prompt).
    """
    if not _has_browser_tools(tools):
        return messages, system_prompt
    
    guide = _BROWSER_TOOL_GUIDE
    new_messages = list(messages)
    
    if new_messages and isinstance(new_messages[0], SystemMessage):
        new_messages[0] = SystemMessage(content=new_messages[0].content + guide)
        return new_messages, system_prompt
    
    if system_prompt:
        return new_messages, system_prompt + guide
    
    return new_messages, guide.strip()


async def run_llm_with_tools(llm, messages, tools, system_prompt=None, middleware=None):
    """Run LLM with tool calling loop (non-streaming). Returns final text content.

    Uses langchain.agents.create_agent for 1.x recommended agent execution.
    Supports optional middleware for error handling, summarization, etc.
    """
    messages, system_prompt = _inject_browser_guide(messages, system_prompt, tools)
    
    if not tools:
        if system_prompt:
            messages = [SystemMessage(content=system_prompt)] + messages
        response = await llm.ainvoke(messages)
        return response.content

    from langchain.agents import create_agent

    kwargs = {}
    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    if middleware:
        kwargs["middleware"] = middleware

    agent = create_agent(llm, tools=tools, **kwargs)
    result = await agent.ainvoke({"messages": messages})
    last_msg = result["messages"][-1]
    return last_msg.content


def get_agent_middleware(agent: models.Agent):
    """Build middleware list for an agent based on its config.

    Supported middleware:
    - ToolCallLimitMiddleware: limit tool calls per run/thread
    - SummarizationMiddleware: auto-summarize when context window fills
    """
    from langchain.agents.middleware import (
        ToolCallLimitMiddleware,
        SummarizationMiddleware,
    )

    cfg = agent.config or {}
    middleware = []

    # Tool call limits
    tool_limits = cfg.get("tool_call_limits")
    if tool_limits:
        if isinstance(tool_limits, dict):
            # Per-tool limits
            for tool_name, limits in tool_limits.items():
                middleware.append(ToolCallLimitMiddleware(
                    tool_name=tool_name,
                    run_limit=limits.get("run_limit"),
                    thread_limit=limits.get("thread_limit"),
                ))
        elif isinstance(tool_limits, int):
            # Global limit
            middleware.append(ToolCallLimitMiddleware(run_limit=tool_limits))

    # Summarization
    summarization = cfg.get("summarization")
    if summarization:
        summary_model = summarization.get("model", agent.model)
        trigger = summarization.get("trigger", ("tokens", 4000))
        keep = summarization.get("keep", ("messages", 20))
        middleware.append(SummarizationMiddleware(
            model=summary_model,
            trigger=trigger,
            keep=keep,
        ))

    return middleware
