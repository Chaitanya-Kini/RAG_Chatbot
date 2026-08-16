from typing import Any, Dict, List


def evaluate_groundedness(answer: str, sources: List[str]) -> Dict[str, Any]:
    has_citation = bool(sources)
    is_grounded = "Information not found in 3GPP documentation." not in answer if answer else False
    return {
        "citation_present": has_citation,
        "grounded_response": is_grounded,
        "score": 1.0 if has_citation and is_grounded else 0.0,
    }


def evaluate_answer_relevancy(question: str, answer: str) -> Dict[str, Any]:
    question_tokens = set(question.lower().split())
    answer_tokens = set(answer.lower().split())
    overlap = len(question_tokens & answer_tokens)
    relevance = overlap / max(1, len(question_tokens))
    return {
        "relevance_score": round(relevance, 3),
        "is_relevant": relevance > 0.0,
    }
