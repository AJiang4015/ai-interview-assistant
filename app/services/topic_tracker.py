"""Knowledge tree topic coverage tracker for interview sessions.

Loads knowledge tree JSON configs and tracks which topics have been
covered in each interview session, providing next-topic suggestions.
"""

import json
from pathlib import Path
from typing import Optional

from app.storage.interview_store import InterviewStore
from app.utils.logger import get_logger

logger = get_logger(__name__)

TREE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_trees"


class TopicTracker:
    """Track topic coverage for interview sessions using knowledge tree configs."""

    def __init__(self, interview_store: InterviewStore, tree_dir: str = None):
        self._store = interview_store
        self._tree_dir = Path(tree_dir) if tree_dir else TREE_DIR
        self._tree_cache: dict[str, dict] = {}

    def get_tree(self, position: str) -> Optional[dict]:
        """Load the knowledge tree for a given position."""
        if position in self._tree_cache:
            return self._tree_cache[position]

        filepath = self._tree_dir / f"{position}.json"
        if not filepath.exists():
            logger.warning(f"Knowledge tree not found: {filepath}")
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                tree = json.load(f)
            self._tree_cache[position] = tree
            logger.info(f"Loaded knowledge tree: {position} ({len(tree.get('categories', []))} categories)")
            return tree
        except Exception as e:
            logger.error(f"Failed to load knowledge tree {filepath}: {e}")
            return None

    def get_coverage(self, session_id: str, position: str) -> dict:
        """Get topic coverage statistics for a session."""
        tree = self.get_tree(position)
        if not tree:
            return {"categories": {}, "weakest": None, "untouched": [], "total_covered": 0, "total_topics": 0}

        # Collect covered topics from the database
        questions = self._store.get_questions(session_id)
        covered_topics = set()
        covered_categories = {}
        for q in questions:
            topic = q.get("topic", "") or ""
            category = q.get("category", "") or ""
            if topic:
                covered_topics.add(topic)
            if category:
                if category not in covered_categories:
                    covered_categories[category] = set()
                covered_categories[category].add(topic)

        # Match against tree structure
        total_topics = 0
        categories_info = {}
        for cat in tree.get("categories", []):
            cat_name = cat["name"]
            topics_in_cat = [t["name"] for t in cat.get("topics", [])]
            total_topics += len(topics_in_cat)
            covered_in_cat = covered_categories.get(cat_name, set())
            covered_count = sum(1 for t in topics_in_cat if t in covered_in_cat)
            categories_info[cat_name] = {
                "total": len(topics_in_cat),
                "covered": covered_count,
                "topics": {t: t in covered_in_cat for t in topics_in_cat},
            }

        # Find weakest category
        untouched = [name for name, info in categories_info.items() if info["covered"] == 0]
        weakest = min(categories_info, key=lambda k: (
            categories_info[k]["covered"] / max(categories_info[k]["total"], 1)
        )) if categories_info else None

        return {
            "categories": categories_info,
            "weakest": weakest,
            "untouched": untouched,
            "total_covered": len(covered_topics),
            "total_topics": total_topics,
        }

    def get_next_suggestion(self, session_id: str, position: str) -> dict:
        """Suggest the next topic/category to focus on."""
        coverage = self.get_coverage(session_id, position)
        tree = self.get_tree(position)
        if not tree:
            return {"category": None, "topic": None, "reason": "知识树未加载"}

        categories = tree.get("categories", [])

        # 1. Pick untouched category first
        if coverage["untouched"]:
            cat_name = coverage["untouched"][0]
            cat = next((c for c in categories if c["name"] == cat_name), None)
            if cat:
                topics = cat.get("topics", [])
                # Pick first topic without unmet prerequisites
                for t in topics:
                    prereqs = t.get("prerequisites", [])
                    unmet = self.suggest_prerequisites(t["name"], position)
                    if not unmet:
                        return {
                            "category": cat_name,
                            "topic": t["name"],
                            "reason": f"「{cat_name}」方向尚未考察，建议从「{t['name']}」开始",
                        }
                # Fallback: first topic
                return {
                    "category": cat_name,
                    "topic": topics[0]["name"],
                    "reason": f"「{cat_name}」方向尚未考察",
                }

        # 2. Pick weakest covered category
        cat_name = coverage["weakest"]
        cat = next((c for c in categories if c["name"] == cat_name), None)
        if cat:
            for t in cat.get("topics", []):
                if t["name"] not in set(
                    q.get("topic", "") for q in self._store.get_questions(session_id)
                ):
                    prereqs = t.get("prerequisites", [])
                    unmet = self.suggest_prerequisites(t["name"], position)
                    if not unmet:
                        return {
                            "category": cat_name,
                            "topic": t["name"],
                            "reason": f"「{cat_name}」方向覆盖不足，建议出「{t['name']}」",
                        }

        # 3. All covered
        return {"category": None, "topic": None, "reason": "所有知识点已覆盖"}

    def suggest_prerequisites(self, topic_name: str, position: str) -> list:
        """Check if prerequisites for a topic are covered. Returns unmet prerequisites."""
        tree = self.get_tree(position)
        if not tree:
            return []

        # Find the topic in the tree
        for cat in tree.get("categories", []):
            for t in cat.get("topics", []):
                if t["name"] == topic_name:
                    return t.get("prerequisites", [])
        return []

    def get_coverage_summary_text(self, session_id: str, position: str) -> str:
        """Generate a human-readable coverage summary for the LLM prompt."""
        coverage = self.get_coverage(session_id, position)
        if not coverage["categories"]:
            return ""

        lines = ["当前面试覆盖情况："]
        for cat_name, info in coverage["categories"].items():
            status = "✓" if info["covered"] == info["total"] else "△" if info["covered"] > 0 else "○"
            lines.append(f"  {status} {cat_name}: {info['covered']}/{info['total']} 题")
        lines.append(f"→ 薄弱方向：{coverage['weakest'] or '无'}")
        if coverage["untouched"]:
            lines.append(f"→ 未覆盖方向：{'、'.join(coverage['untouched'])}")
        return "\n".join(lines)

    def get_tree_structure_text(self, position: str) -> str:
        """Generate a compact text representation of the knowledge tree for the prompt."""
        tree = self.get_tree(position)
        if not tree:
            return ""

        lines = []
        for cat in tree.get("categories", []):
            topics = [t["name"] for t in cat.get("topics", [])]
            lines.append(f"  {cat['name']}: {' → '.join(topics)}")
        return "\n".join(lines)