import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple


DATA_PATH = Path(__file__).resolve().parent / "docs" / "symptom_qa.json"
DEFAULT_MIN_SCORE = 0.78
DEFAULT_MIN_MARGIN = 0.06

_PREFIXES = (
    "我想问一下",
    "我想问",
    "想问一下",
    "能不能告诉我",
    "可以告诉我",
    "请告诉我",
    "麻烦问一下",
    "麻烦问问",
    "请问一下",
    "请问",
    "安安",
)
_SUFFIXES = ("可以吗", "好吗", "行吗", "呢", "呀", "啊", "嘛", "吧")
_SYMPTOM_ALIASES = {
    "咳嗽与咳痰": ("咳嗽与咳痰", "咳嗽咳痰", "咳嗽", "咳痰", "干咳", "湿咳"),
    "恶心与呕吐": ("恶心与呕吐", "恶心呕吐", "恶心", "呕吐"),
    "呕血与便血": ("呕血与便血", "呕血便血", "呕血", "便血"),
    "尿频、尿急与尿失禁": (
        "尿频尿急与尿失禁",
        "尿频尿急和尿失禁",
        "排尿问题",
        "尿频",
        "尿急",
        "尿失禁",
    ),
    "焦虑与抑郁": ("焦虑与抑郁", "焦虑和抑郁", "焦虑", "抑郁", "情绪"),
}


@dataclass(frozen=True)
class SymptomQaEntry:
    id: str
    symptom: str
    sequence: int
    question: str
    answer: str
    source_row: int


@dataclass(frozen=True)
class SymptomQaMatch:
    entry: SymptomQaEntry
    score: float
    match_type: str


def normalize_question(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).lower()
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "", value)
    value = value.replace("什么意思", "是什么")
    value = value.replace("什么叫做", "什么是")
    value = value.replace("什么叫", "什么是")
    value = value.replace("咋办", "怎么办")
    value = value.replace("如何", "怎么")
    value = value.replace("医务人员", "医护人员")
    value = value.replace("医生", "医护人员")
    value = value.replace("护士", "医护人员")
    value = value.replace("马上", "立即")
    value = value.replace("求救", "求助")

    changed = True
    while changed and value:
        changed = False
        for prefix in _PREFIXES:
            normalized_prefix = re.sub(r"[^\w\u4e00-\u9fff]+", "", prefix)
            if value.startswith(normalized_prefix):
                value = value[len(normalized_prefix) :]
                changed = True
                break
        for suffix in _SUFFIXES:
            if value.endswith(suffix):
                value = value[: -len(suffix)]
                changed = True
                break
    return value


@lru_cache(maxsize=1)
def load_symptom_qa_entries() -> Tuple[SymptomQaEntry, ...]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    items = payload.get("items")
    if not isinstance(items, list) or payload.get("entry_count") != len(items):
        raise ValueError("症状问答库 JSON 结构或条目数量无效")

    entries = tuple(
        SymptomQaEntry(
            id=str(item["id"]),
            symptom=str(item["symptom"]).strip(),
            sequence=int(item["sequence"]),
            question=str(item["question"]).strip(),
            answer=str(item["answer"]).strip(),
            source_row=int(item["source_row"]),
        )
        for item in items
    )
    if any(not entry.symptom or not entry.question or not entry.answer for entry in entries):
        raise ValueError("症状问答库存在空的症状、问题或答案")
    return entries


def _symptom_aliases(symptom: str) -> Tuple[str, ...]:
    aliases = _SYMPTOM_ALIASES.get(symptom, (symptom,))
    return tuple(dict.fromkeys(normalize_question(alias) for alias in aliases if alias))


def _clean_subject(subject: str) -> str:
    value = normalize_question(subject)
    for prefix in ("我的", "我"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
            break
    return value


def _entry_aliases(entry: SymptomQaEntry) -> Tuple[str, ...]:
    question = normalize_question(entry.question)
    aliases = {question}

    what_match = re.fullmatch(r"什么是(.+)", question)
    if what_match:
        subject = _clean_subject(what_match.group(1))
        aliases.update(
            {
                f"{subject}是什么",
                f"{subject}是什么意思",
                f"介绍一下{subject}",
                f"介绍{subject}",
                f"给我讲讲{subject}",
                f"说说{subject}",
            }
        )

    why_match = re.fullmatch(r"为什么会发生(.+)", question)
    if why_match:
        subject = _clean_subject(why_match.group(1))
        aliases.update(
            {
                f"{subject}为什么会发生",
                f"为什么会{subject}",
                f"{subject}为什么",
                f"{subject}是什么原因",
                f"{subject}怎么引起的",
            }
        )

    describe_match = re.fullmatch(r"我该怎么向医护人员(?:描述|表达)(.+)", question)
    if describe_match:
        subject = _clean_subject(describe_match.group(1))
        aliases.update(
            {
                f"怎么描述{subject}",
                f"{subject}怎么描述",
                f"{subject}怎么告诉医护人员",
                f"怎么向医护人员描述{subject}",
            }
        )

    care_match = re.fullmatch(r"出现(.+?)(?:时)?我该怎么办", question)
    if not care_match:
        care_match = re.fullmatch(r"(.+?)的时候我该怎么办", question)
    if care_match:
        subject = _clean_subject(care_match.group(1))
        aliases.update(
            {
                f"{subject}怎么办",
                f"出现{subject}怎么办",
                f"{subject}怎么处理",
            }
        )

    medicine_match = re.fullmatch(r"关于(.+?)的药物我需要知道什么", question)
    if medicine_match:
        subject = _clean_subject(medicine_match.group(1))
        aliases.update(
            {
                f"{subject}用药要注意什么",
                f"{subject}的药需要知道什么",
                f"{subject}用什么药",
            }
        )

    if question == normalize_question("什么情况下需要立即求助"):
        for symptom_alias in _symptom_aliases(entry.symptom):
            aliases.update(
                {
                    f"{symptom_alias}什么情况下需要立即求助",
                    f"{symptom_alias}什么时候需要立即求助",
                    f"{symptom_alias}什么时候要找医护人员",
                }
            )

    if entry.symptom == "谵妄" and "降低谵妄发生的几率" in question:
        aliases.update({"怎么预防谵妄", "怎么降低谵妄发生几率"})

    return tuple(sorted({normalize_question(alias) for alias in aliases if alias}))


@lru_cache(maxsize=1)
def _build_indexes():
    entries = load_symptom_qa_entries()
    exact: Dict[str, list] = {}
    aliases_by_entry: Dict[SymptomQaEntry, Tuple[str, ...]] = {}
    for entry in entries:
        aliases = _entry_aliases(entry)
        aliases_by_entry[entry] = aliases
        for alias in aliases:
            exact.setdefault(alias, []).append(entry)
    return entries, exact, aliases_by_entry


def _mentioned_symptoms(question: str, entries: Iterable[SymptomQaEntry]):
    symptoms = {entry.symptom for entry in entries}
    return {
        symptom
        for symptom in symptoms
        if any(alias and alias in question for alias in _symptom_aliases(symptom))
    }


def match_symptom_question(
    text: str,
    min_score: float = DEFAULT_MIN_SCORE,
    min_margin: float = DEFAULT_MIN_MARGIN,
) -> Optional[SymptomQaMatch]:
    question = normalize_question(text)
    if len(question) < 4:
        return None

    entries, exact, aliases_by_entry = _build_indexes()
    exact_entries = exact.get(question, [])
    if len(exact_entries) == 1:
        return SymptomQaMatch(exact_entries[0], 1.0, "exact")
    if len(exact_entries) > 1:
        return None

    mentioned = _mentioned_symptoms(question, entries)
    candidates = (
        [entry for entry in entries if entry.symptom in mentioned]
        if mentioned
        else list(entries)
    )
    scored = []
    for entry in candidates:
        score = max(
            SequenceMatcher(None, question, alias).ratio()
            for alias in aliases_by_entry[entry]
        )
        scored.append((score, entry))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored or scored[0][0] < min_score:
        return None

    best_score, best_entry = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_score - second_score < min_margin:
        return None
    return SymptomQaMatch(best_entry, best_score, "fuzzy")
