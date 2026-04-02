from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List

import requests


@dataclass
class TopicPlan:
    topic: str
    queries: List[str]
    tags: List[str]
    source: str


class TopicInterpreter:
    """Interpret a free-form topic into arXiv-searchable queries.

    If OpenAI-compatible credentials are available, it uses an LLM.
    Otherwise it falls back to deterministic keyword expansion.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def interpret(self, topic: str, max_queries: int = 8) -> TopicPlan:
        if self.api_key:
            plan = self._interpret_with_llm(topic, max_queries=max_queries)
            if plan.queries:
                return plan
        return self._fallback_plan(topic, max_queries=max_queries)

    def _interpret_with_llm(self, topic: str, max_queries: int = 8) -> TopicPlan:
        url = self.base_url.rstrip("/") + "/chat/completions"
        prompt = (
            "You are an arXiv query planner. Return JSON only with keys: "
            "queries (array of strings), tags (array of strings). "
            f"Generate up to {max_queries} precise arXiv search queries for this topic: {topic}"
        )
        payload: Dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=45)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            data = self._safe_parse_json(content)
            queries = self._clean_queries(data.get("queries", []), max_queries=max_queries)
            tags = [str(x).strip() for x in data.get("tags", []) if str(x).strip()]
            return TopicPlan(topic=topic, queries=queries, tags=tags[:12], source="llm")
        except Exception:
            return TopicPlan(topic=topic, queries=[], tags=[], source="llm-failed")

    def _safe_parse_json(self, text: str) -> Dict:
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n", "", text)
            text = text.rstrip("`").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _clean_queries(self, queries: List[str], max_queries: int) -> List[str]:
        seen = set()
        out: List[str] = []
        for q in queries:
            qq = str(q).strip()
            if not qq:
                continue
            key = qq.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(qq)
            if len(out) >= max_queries:
                break
        return out

    def _fallback_plan(self, topic: str, max_queries: int = 8) -> TopicPlan:
        tokens = [t for t in re.split(r"[\s,;，。]+", topic.lower()) if t]
        core = " ".join(tokens[:8]).strip() or topic.strip()

        templates = [
            f'all:"{core}"',
            f'ti:"{core}"',
            f'all:"{core}" AND (all:"survey" OR all:"benchmark")',
            f'all:"{core}" AND (all:"autonomous driving" OR all:"self-driving")',
            f'all:"{core}" AND (all:"gaussian splatting" OR all:"3dgs")',
            f'all:"{core}" AND (all:"scene reconstruction" OR all:"world model")',
            f'all:"{core}" AND (all:"controllable" OR all:"control")',
            f'all:"{core}" AND (all:"simulation" OR all:"generation")',
        ]

        queries = self._clean_queries(templates, max_queries=max_queries)
        tags = [t for t in tokens[:12]]
        return TopicPlan(topic=topic, queries=queries, tags=tags, source="fallback")

