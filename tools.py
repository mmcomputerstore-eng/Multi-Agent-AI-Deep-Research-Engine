from langchain_core.tools import tool
import requests
from bs4 import BeautifulSoup
from tavily import TavilyClient
import os
from dotenv import load_dotenv

load_dotenv()
from rich import print


def get_tavily_client(api_key: str = None) -> TavilyClient:
    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key:
        raise ValueError("Tavily API key is missing. Set TAVILY_API_KEY in .env or pass it in.")
    return TavilyClient(api_key=key)


@tool
def web_search(query: str) -> str:
    """
    Perform a web search using Tavily API and return the top result.
    Returns: 
        Titles, URL, and snippet of the top search result.
    """
    try:
        print(f"Performing web search for query: {query}")
        client = get_tavily_client()
        response = client.search(query=query, max_results=5)
        if response and 'results' in response and len(response['results']) > 0:
            out = []
            for r in response['results']:
                out.append(f"Title: {r['title']}\nURL: {r['url']}\nSnippet: {r['content'][:300]}\n")
            return "\n----\n".join(out)
        else:
            return "No results found."
    except Exception as e:
        return f"An error occurred during the web search: {str(e)}"


@tool
def web_scrape(url: str) -> str:
    """
    Scrape the content of a web page given its URL.
    Returns:
        The text content of the web page.
    """
    try:
        response = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser') 
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            return soup.get_text(separator='\n', strip=True)[:3000]
        else:
            return f"Failed to retrieve the page. Status code: {response.status_code}"
    except Exception as e:
        return f"An error occurred during web scraping: {str(e)}"
