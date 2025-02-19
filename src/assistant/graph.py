import json
from enum import Enum 
from typing_extensions import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
# from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import START, END, StateGraph

from assistant.configuration import Configuration, SearchAPI
from assistant.utils import deduplicate_and_format_sources, tavily_search, format_sources, perplexity_search, save_research_process, clear_session_files
from assistant.state import SummaryState, SummaryStateInput, SummaryStateOutput
from assistant.prompts import query_writer_instructions, summarizer_instructions, reflection_instructions

def generate_query(state: SummaryState, config: RunnableConfig):
    """ Generate a query for web search """
    # 새로운 연구 시작 시 세션 파일 초기화
    clear_session_files()

    query_writer_instructions_formatted = (
        query_writer_instructions.format(research_topic=state.research_topic) +
        "\nYou must respond in the following JSON format only: {\"query\": \"your generated query here\"}"
    )

    configurable = Configuration.from_runnable_config(config)
    llm_json_mode = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp",
        temperature=0,
        convert_system_message_to_human=True
    )
    
    try:
        result = llm_json_mode.invoke(
            [SystemMessage(content=query_writer_instructions_formatted),
            HumanMessage(content=f"Generate a query for web search:")]
        )   
        
        try:
            query = json.loads(result.content)
            query_result = {"search_query": query.get('query', result.content.strip())}
        except json.JSONDecodeError:
            query_result = {"search_query": result.content.strip()}
            
        # 프롬프트와 결과 저장
        save_research_process(
            state,
            "Query Generation Step",
            f"Instructions:\n{query_writer_instructions_formatted}\n\n"
            f"LLM Response:\n{result.content}\n\n"
            f"Final Query:\n{query_result['search_query']}"
        )
        return query_result
    except Exception as e:
        print(f"Error in generate_query: {e}")
        return {"search_query": state.research_topic}

def web_research(state: SummaryState, config: RunnableConfig):
    """ Gather information from the web """
    
    configurable = Configuration.from_runnable_config(config)
    search_api = configurable.search_api.value if isinstance(configurable.search_api, Enum) else configurable.search_api

    # 검색 시작 기록
    save_research_process(
        state,
        "Web Research Step",
        f"Search API: {search_api}\n"
        f"Search Query: {state.search_query}\n"
    )

    if search_api == "tavily":
        search_results = tavily_search(state.search_query, include_raw_content=True, max_results=1)
        search_str = deduplicate_and_format_sources(search_results, max_tokens_per_source=1000, include_raw_content=True)
    elif search_api == "perplexity":
        search_results = perplexity_search(state.search_query, state.research_loop_count)
        search_str = deduplicate_and_format_sources(search_results, max_tokens_per_source=1000, include_raw_content=False)
    else:
        raise ValueError(f"Unsupported search API: {configurable.search_api}")
    
    # 검색 결과 저장
    save_research_process(
        state,
        "Search Results",
        f"Raw Results:\n{search_str}\n\n"
        f"Formatted Sources:\n{format_sources(search_results)}"
    )
    
    return {"sources_gathered": [format_sources(search_results)], 
            "research_loop_count": state.research_loop_count + 1, 
            "web_research_results": [search_str]}

def summarize_sources(state: SummaryState, config: RunnableConfig):
    """ Summarize the gathered sources """
    
    existing_summary = state.running_summary
    most_recent_web_research = state.web_research_results[-1]

    if existing_summary:
        human_message_content = (
            f"<User Input> \n {state.research_topic} \n <User Input>\n\n"
            f"<Existing Summary> \n {existing_summary} \n <Existing Summary>\n\n"
            f"<New Search Results> \n {most_recent_web_research} \n <New Search Results>"
        )
    else:
        human_message_content = (
            f"<User Input> \n {state.research_topic} \n <User Input>\n\n"
            f"<Search Results> \n {most_recent_web_research} \n <Search Results>"
        )

    configurable = Configuration.from_runnable_config(config)
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp",
        temperature=0,
        convert_system_message_to_human=True
    )
    
    # 요약 시작 기록
    save_research_process(
        state,
        "Summarization Step",
        f"Instructions:\n{summarizer_instructions}\n\n"
        f"Input Content:\n{human_message_content}"
    )
    
    result = llm.invoke(
        [SystemMessage(content=summarizer_instructions),
        HumanMessage(content=human_message_content)]
    )

    running_summary = result.content

    while "<think>" in running_summary and "</think>" in running_summary:
        start = running_summary.find("<think>")
        end = running_summary.find("</think>") + len("</think>")
        running_summary = running_summary[:start] + running_summary[end:]

    # 요약 결과 저장
    save_research_process(
        state,
        "Summary Result",
        f"Generated Summary:\n{running_summary}"
    )

    return {"running_summary": running_summary}

def reflect_on_summary(state: SummaryState, config: RunnableConfig):
    """ Reflect on the summary and generate a follow-up query """

    reflection_instructions_formatted = (
        reflection_instructions.format(research_topic=state.research_topic) +
        "\nYou must respond in the following JSON format only: {\"follow_up_query\": \"your generated query here\"}"
    )

    configurable = Configuration.from_runnable_config(config)
    llm_json_mode = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp",
        temperature=0,
        convert_system_message_to_human=True
    )
    
    # 리플렉션 시작 기록
    save_research_process(
        state,
        "Reflection Step",
        f"Instructions:\n{reflection_instructions_formatted}\n\n"
        f"Current Summary:\n{state.running_summary}"
    )
    
    try:
        result = llm_json_mode.invoke(
            [SystemMessage(content=reflection_instructions_formatted),
            HumanMessage(content=f"Identify a knowledge gap and generate a follow-up web search query based on our existing knowledge: {state.running_summary}")]
        )   
        
        try:
            follow_up_query = json.loads(result.content)
            query = follow_up_query.get('follow_up_query')
        except json.JSONDecodeError:
            query = result.content.strip()
            
        if not query:
            query = f"Tell me more about {state.research_topic}"
            
        # 리플렉션 결과 저장
        save_research_process(
            state,
            "Reflection Result",
            f"LLM Response:\n{result.content}\n\n"
            f"Next Query:\n{query}"
        )
            
        return {"search_query": query}
    except Exception as e:
        print(f"Error in reflect_on_summary: {e}")
        return {"search_query": f"Tell me more about {state.research_topic}"}

def finalize_summary(state: SummaryState):
    """ Finalize the summary """
    
    # Format all accumulated sources into a single bulleted list
    all_sources = "\n".join(source for source in state.sources_gathered)
    final_summary = f"## Summary\n\n{state.running_summary}\n\n### Sources:\n{all_sources}"
    
    # 최종 결과 저장
    save_research_process(
        state,
        "Final Research Results",
        f"Research Topic: {state.research_topic}\n\n"
        f"Total Research Loops: {state.research_loop_count}\n\n"
        f"Final Summary:\n{final_summary}"
    )
    
    return {"running_summary": final_summary}
def review_summary(state: SummaryState, config: RunnableConfig):
    """Review and refine the current summary for relevance and coherence"""
    
    review_instructions = """당신은 연구 내용을 검토하고 개선하는 전문 편집자입니다.

<목표>
1. 현재까지의 요약을 평가하고 개선
2. 연구 주제와의 관련성 검증
3. 핵심 내용 재정리

<평가 기준>
1. 주제 관련성: 모든 내용이 연구 주제와 직접적으로 관련되어야 함
2. 논리적 구조: 내용이 논리적으로 연결되고 잘 구조화되어야 함
3. 정보의 품질: 중복되거나 불필요한 내용 제거

<출력 형식>
다음 키를 포함하는 JSON 객체로 응답:
{
    "evaluation": {
        "relevance": "주제 관련성 평가 (0-10)",
        "coherence": "논리적 구조 평가 (0-10)",
        "issues": ["개선이 필요한 부분들"]
    },
    "refined_summary": "개선된 요약 내용",
    "removed_content": ["제거된 내용과 이유"]
}
"""

    review_instructions_formatted = review_instructions.format(
        research_topic=state.research_topic
    )

    configurable = Configuration.from_runnable_config(config)
    llm_json_mode = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp",
        temperature=0,
        convert_system_message_to_human=True
    )
    
    try:
        result = llm_json_mode.invoke(
            [SystemMessage(content=review_instructions_formatted),
             HumanMessage(content=f"연구 주제: {state.research_topic}\n\n"
                                 f"현재 요약:\n{state.running_summary}")]
        )
        
        try:
            review_result = json.loads(result.content)
            
            # 리뷰 결과 저장
            save_research_process(
                state,
                "Summary Review",
                f"Evaluation:\n"
                f"- Relevance Score: {review_result['evaluation']['relevance']}/10\n"
                f"- Coherence Score: {review_result['evaluation']['coherence']}/10\n"
                f"- Issues Identified: {', '.join(review_result['evaluation']['issues'])}\n\n"
                f"Removed Content:\n"
                f"{json.dumps(review_result['removed_content'], indent=2, ensure_ascii=False)}\n\n"
                f"Refined Summary:\n{review_result['refined_summary']}"
            )
            
            return {"running_summary": review_result['refined_summary']}
            
        except json.JSONDecodeError:
            print(f"Error parsing JSON response: {result.content}")
            return {"running_summary": state.running_summary}
            
    except Exception as e:
        print(f"Error in review_summary: {e}")
        return {"running_summary": state.running_summary}
    
def route_research(state: SummaryState) -> Literal["web_research", "review_summary", "finalize_summary"]:
    """웹 검색 진행 중 다음 단계를 결정
    
    research_loop_count:
    1-2회: 계속 검색
    3회: 중간 리뷰
    4-5회: 계속 검색
    6회 이상: 종료
    """
    if state.research_loop_count >= 6:  # 6회 이상이면 종료
        return "finalize_summary"
    elif state.research_loop_count == 3:  # 3회차에 리뷰
        return "review_summary"
    return "web_research"

def route_after_review(state: SummaryState) -> Literal["generate_query", "finalize_summary"]:
    """리뷰 후 다음 단계를 결정
    
    research_loop_count:
    3회 리뷰 후: 다시 검색으로
    6회 이상: 종료
    """
    if state.research_loop_count >= 6:  # 6회 이상이면 종료
        return "finalize_summary"
    return "generate_query"  # 그 외에는 다시 검색
    
# Add nodes and edges 
builder = StateGraph(SummaryState, input=SummaryStateInput, output=SummaryStateOutput, config_schema=Configuration)

# Add nodes
builder.add_node("generate_query", generate_query)
builder.add_node("web_research", web_research)
builder.add_node("summarize_sources", summarize_sources)
builder.add_node("reflect_on_summary", reflect_on_summary)
builder.add_node("review_summary", review_summary)
builder.add_node("finalize_summary", finalize_summary)

# Add edges
builder.add_edge(START, "generate_query")
builder.add_edge("generate_query", "web_research")
builder.add_edge("web_research", "summarize_sources")
builder.add_edge("summarize_sources", "reflect_on_summary")
builder.add_conditional_edges(
    "reflect_on_summary",
    route_research,
    {
        "web_research": "generate_query",
        "review_summary": "review_summary",
        "finalize_summary": "finalize_summary"
    }
)
builder.add_conditional_edges(
    "review_summary",
    route_after_review,
    {
        "generate_query": "generate_query",
        "finalize_summary": "finalize_summary"
    }
)
builder.add_edge("finalize_summary", END)
# builder.add_edge(START, "generate_query")
# builder.add_edge("generate_query", END)


graph = builder.compile()