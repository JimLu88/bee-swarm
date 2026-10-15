"""Expand a reusable task recipe into independent requests for the existing engine."""
from string import Template

RECIPES = {
    "object-brief": {"title": "逐对象整理", "parameters": ["object", "goal"],
        "template": "围绕 $object 完成以下任务：$goal。按结论、关键依据、建议行动组织输出。"},
    "option-comparison": {"title": "逐方案分析", "parameters": ["option", "criteria"],
        "template": "分析方案 $option。比较维度：$criteria。明确优点、代价和适用场景。"},
    "document-brief": {"title": "逐材料提炼", "parameters": ["material", "question"],
        "template": "阅读以下材料并回答 $question。材料：$material。保持原文事实与建议分开。"},
}


def expand_recipe(recipe_id: str, items: list[dict], common: dict | None = None) -> list[str]:
    recipe = RECIPES[recipe_id]
    template = Template(recipe["template"])
    return [template.substitute({key: str(value) for key, value in {**(common or {}), **item}.items()})
            for item in items]
