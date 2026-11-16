from agents import (
    create_search_agent,
    create_reader_agent,
    create_writer_chain,
    create_critic_chain,
    get_gemini_llm
)
from langchain_core.messages import HumanMessage
import re
import time


def extract_text_content(content) -> str:
    """Extract plain text from string or structured Gemini message content list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
            elif hasattr(item, "text"):
                parts.append(str(item.text))
        return "".join(parts) if parts else str(content)
    if hasattr(content, "content"):
        return extract_text_content(content.content)
    return str(content)


def extract_urls(text: str) -> list[str]:
    """Extract http/https URLs from text."""
    pattern = r'https?://[^\s<>"\'\)\]\}]+'
    urls = re.findall(pattern, text)
    cleaned = []
    for u in urls:
        u = u.rstrip('.,;:')
        if u and u not in cleaned:
            cleaned.append(u)
    return cleaned


def run_research_pipeline(topic: str, custom_llm=None, progress_callback=None) -> dict:
    """
    Run the end-to-end multi-agent research pipeline using Google Gemini:
    1. Search Agent: Tavily Search + initial synthesis (Gemini Flash Lite)
    2. Reader Agent: Scrapes and extracts top URL content (Gemini Flash Lite 1M context)
    3. Writer Chain: Synthesizes structured markdown research report
    4. Critic Chain: Evaluates facts, structure, provides score and feedback

    Includes rate-limit pacing to respect Google AI Studio Free Tier limits.
    """
    state = {'topic': topic, 'steps': {}}
    start_time = time.time()

    # Step 1: Search for the topic
    t0 = time.time()
    if progress_callback:
        progress_callback(1, "Searching web sources...", "running", None)
    print('\n', ' ='*50)
    print(f"Step 1: Searching for the topic: {topic}")
    print(' ='*50)

    search = create_search_agent(custom_llm)
    search_prompt = (
        f"Perform a targeted search to find recent, reliable and detailed information on: {topic}. "
        f"List key findings and explicitly include source URLs."
    )
    search_result = search.invoke({'messages': [HumanMessage(content=search_prompt)]})
    state['search_result'] = extract_text_content(search_result['messages'][-1].content)
    
    # Extract discovered URLs from tool messages and search output
    urls = []
    for msg in search_result.get('messages', []):
        if msg.__class__.__name__ == 'ToolMessage':
            urls.extend(extract_urls(str(msg.content)))
    urls.extend(extract_urls(state['search_result']))
    
    # Deduplicate while preserving order
    unique_urls = []
    for u in urls:
        if u not in unique_urls:
            unique_urls.append(u)
    state['urls'] = unique_urls
    state['steps']['search_time'] = round(time.time() - t0, 2)
    print(f"\nDiscovered {len(unique_urls)} URLs. Top URL: {unique_urls[0] if unique_urls else 'None'}")
    if progress_callback:
        progress_callback(1, f"Found {len(unique_urls)} sources", "complete", {
            "search_result": state['search_result'],
            "urls": unique_urls
        })

    # Free Tier pacing: short pause between calls to respect RPM limits
    time.sleep(1.0)

    # Step 2: Scrape top URL from the search result
    t0 = time.time()
    if progress_callback:
        progress_callback(2, "Reading & scraping top article...", "running", None)
    print('\n', ' ='*50)
    print(f"Step 2: Scraping top URL for the topic: {topic}")
    print(' ='*50)

    top_url = unique_urls[0] if unique_urls else None
    state['top_url'] = top_url
    reader = create_reader_agent(custom_llm)

    if top_url:
        reader_prompt = f"Scrape this top source URL and extract key factual information on {topic}: {top_url}"
    else:
        reader_prompt = f"Based on the following search result, extract and scrape the top URL for {topic}:\n{state['search_result'][:1500]}"

    try:
        reader_result = reader.invoke({'messages': [HumanMessage(content=reader_prompt)]})
        state['scrape_result'] = extract_text_content(reader_result['messages'][-1].content)
    except Exception as e:
        state['scrape_result'] = f"Scraping note: {str(e)}"

    state['steps']['scrape_time'] = round(time.time() - t0, 2)
    print(f"\nScrape Result:\n{state['scrape_result'][:300]}...")
    if progress_callback:
        progress_callback(2, "Content scraped successfully", "complete", {
            "scrape_result": state['scrape_result']
        })

    # Free Tier pacing
    time.sleep(1.0)

    # Step 3: Writer chain
    t0 = time.time()
    if progress_callback:
        progress_callback(3, "Writing comprehensive research report...", "running", None)
    print('\n', ' ='*50)
    print(f"Step 3: Writing a detailed research report for the topic: {topic}")
    print(' ='*50)

    writer = create_writer_chain(custom_llm)
    research_combined = (
        f"Search Result:\n{state['search_result']}\n\n"
        f"Top Source Scraped ({top_url or 'N/A'}):\n{state['scrape_result']}"
    )
    writer_result = writer.invoke({
        'topic': topic,
        'research': research_combined
    })
    state['report'] = extract_text_content(writer_result)
    state['steps']['writer_time'] = round(time.time() - t0, 2)
    print(f"\nResearch Report:\n{state['report'][:300]}...")
    if progress_callback:
        progress_callback(3, "Report generated", "complete", {
            "report": state['report']
        })

    # Free Tier pacing
    time.sleep(1.0)

    # Step 4: Critic chain
    t0 = time.time()
    if progress_callback:
        progress_callback(4, "Critiquing research report & scoring...", "running", None)
    print('\n', ' ='*50)
    print(f"Step 4: Critiquing the research report for the topic: {topic}")
    print(' ='*50)

    critic = create_critic_chain(custom_llm)
    critic_result = critic.invoke({
        'report': state['report']
    })
    state['feedback'] = extract_text_content(critic_result)
    state['steps']['critic_time'] = round(time.time() - t0, 2)
    state['total_time'] = round(time.time() - start_time, 2)
    print(f"\nCritique Report:\n{state['feedback']}")
    if progress_callback:
        progress_callback(4, "Evaluation complete", "complete", {
            "feedback": state['feedback']
        })

    return state


if __name__ == "__main__":
    topic = input("Enter the research topic: ")
    run_research_pipeline(topic)
