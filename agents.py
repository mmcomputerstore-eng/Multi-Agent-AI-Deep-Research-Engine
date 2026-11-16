from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from tools import web_search, web_scrape
import os
from dotenv import load_dotenv

load_dotenv()

# Best model for fast tool calling & high free tier limits (15-30 RPM, 1M+ context)
DEFAULT_MODEL = "gemini-3.5-flash-lite"

def get_gemini_llm(model_name: str = DEFAULT_MODEL, temperature: float = 0.0, api_key: str = None):
    key = api_key or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ValueError("Google API Key missing. Please set GOOGLE_API_KEY in .env or pass it in.")
    
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=key,
        temperature=temperature,
        max_retries=3,
    )

# Backward-compatible alias
get_groq_llm = get_gemini_llm
get_llm = get_gemini_llm

llm = get_gemini_llm()

# First Agent - Web Search (Optimized with Gemini Flash Lite for fast tool-calls & high RPM)
def create_search_agent(custom_llm=None):
    return create_agent(
        model=custom_llm or llm,
        tools=[web_search],
    )

search_agent = create_search_agent

# Second Agent - Web Scraper / Reader (High context window for full article comprehension)
def create_reader_agent(custom_llm=None):
    return create_agent(
        model=custom_llm or llm,
        tools=[web_scrape],
    )

reader_agent = create_reader_agent

# Writer Chain - Report Synthesizer
writer_prompt = ChatPromptTemplate.from_messages([
    ('system', "You are an expert research writer. Write a clear, structured, and insightful report."),
    ('human', """Write a detailed research report on the topic below.
    Topic: {topic}
    Research Gathered: {research}
    Structure the report as:
    - Introduction
    - Key Findings (minimum 3 well-explained points)
    - Conclusion
    - Sources (list all urls found in research)
    Be detailed, factual, and professional.""")
])

def create_writer_chain(custom_llm=None):
    return writer_prompt | (custom_llm or llm) | StrOutputParser()

writer_chain = create_writer_chain()

# Critic Chain - Strict Evaluation and Scoring
critic_prompt = ChatPromptTemplate.from_messages([
    ('system', 'You are a sharp and constructive research critic. Be honest and specific.'),
    ('human', """Review the research report below and evaluate it strictly.
    Report: {report}
    Response in exact format:
    Score: X/10
    Strengths:
    ---
    ---
    
    Areas to Improve:
    ---
    ---
    
    One line verdict:
    ---""")
])

def create_critic_chain(custom_llm=None):
    return critic_prompt | (custom_llm or llm) | StrOutputParser()

critic_chain = create_critic_chain()
