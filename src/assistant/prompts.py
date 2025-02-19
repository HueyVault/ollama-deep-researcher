query_writer_instructions="""목표: 주어진 주제에 대한 웹 검색 쿼리를 생성합니다.

<주제>
{research_topic}
</주제>

<형식>
다음 세 가지 키를 포함하는 JSON 객체로 응답해주세요:
   - "query": 실제 검색 쿼리 문자열 (400자 이내)
   - "aspect": 연구 주제의 구체적인 측면
   - "rationale": 이 쿼리가 적절한 이유에 대한 간단한 설명

<예시>
{{
    "query": "한국 핀테크 산업 현황 및 규제 동향 2024",
    "aspect": "산업 현황 분석",
    "rationale": "최신 핀테크 산업 동향과 규제 환경 파악"
}}
</예시>

중요: 쿼리는 400자를 넘지 않도록 해주세요.
JSON 형식으로 응답해주세요:"""

summarizer_instructions="""
<목표>
웹 검색 결과를 바탕으로 고품질의 요약을 생성하고, 사용자 주제와 관련된 핵심 내용을 간단명료하게 정리합니다.
</목표>

<요구사항>
새로운 요약 작성 시:
1. 검색 결과에서 사용자 주제와 가장 관련 있는 정보를 강조
2. 정보의 논리적 흐름 유지

기존 요약 확장 시:                                                                                                                 
1. 기존 요약과 새로운 검색 결과를 주의 깊게 검토                                                    
2. 새로운 정보와 기존 내용 비교                                                         
3. 각각의 새로운 정보에 대해:                                                                             
    a. 기존 내용과 관련이 있다면, 해당 단락에 통합                               
    b. 완전히 새로운 내용이면서 관련성이 있다면, 자연스러운 전개로 새 단락 추가                            
    c. 사용자 주제와 관련이 없다면 제외                                                            
4. 모든 추가 내용이 사용자 주제와 관련성 유지                                                         
5. 최종 출력이 입력 요약과 차별화되는지 확인                                                                                                                                                            

<형식>
- 서론이나 제목 없이 바로 업데이트된 요약 시작
- XML 태그 사용하지 않기"""

reflection_instructions = """당신은 {research_topic}에 대한 요약을 분석하는 전문 연구 조교입니다.

<목표>
1. 지식 격차나 더 깊이 탐구가 필요한 영역 파악
2. 이해를 넓히는데 도움이 될 후속 질문 생성
3. 다루지 않은 기술적 세부사항, 구현 방식, 최신 트렌드에 초점

<요구사항>
- 웹 검색에 적합하도록 자체적으로 완결된 질문 작성
- 후속 질문은 400자를 넘지 않아야 함

<형식>
다음 키를 포함하는 JSON 객체로 응답:
- knowledge_gap: 부족하거나 명확히 할 필요가 있는 정보 설명
- follow_up_query: 이 격차를 해소하기 위한 구체적인 질문 (400자 이내)

<예시>
{{
    "knowledge_gap": "현재 요약에는 구체적인 규제 준수 비용과 대응 방안이 부족함",
    "follow_up_query": "국내 핀테크 기업들의 금융 규제 준수 비용과 주요 대응 전략은?"
}}
</예시>

중요: 후속 질문은 400자 이내로 유지해주세요.
JSON 형식으로 분석을 제공해주세요:"""

review_instructions =  """당신은 {research_topic}에 대한 연구 내용을 검토하고 개선하는 전문 편집자입니다.

<목표>
1. 현재까지의 요약을 평가하고 개선
2. 연구 주제와의 관련성 검증
3. 핵심 내용 재정리

<평가 기준>
1. 주제 관련성: 모든 내용이 연구 주제와 직접적으로 관련되어야 함
2. 논리적 구조: 내용이 논리적으로 연결되고 잘 구조화되어야 함
3. 정보의 품질: 중복되거나 불필요한 내용 제거

<형식>
다음 키를 포함하는 JSON 객체로 응답:
- "evaluation": 평가 결과 객체
  - "relevance": 주제 관련성 평가 (0-10)
  - "coherence": 논리적 구조 평가 (0-10)
  - "issues": 개선이 필요한 부분들의 배열
- "refined_summary": 개선된 요약 내용
- "removed_content": 제거된 내용과 이유의 배열

<예시>
{{
    "evaluation": {{
        "relevance": 8,
        "coherence": 7,
        "issues": ["금융 정책 영향 분석이 부족", "시장 데이터 업데이트 필요"]
    }},
    "refined_summary": "개선된 요약 내용이 여기에 들어갑니다...",
    "removed_content": ["중복된 규제 설명 제거", "관련성 낮은 해외 사례 제외"]
}}

중요: JSON 형식으로 응답해주세요."""