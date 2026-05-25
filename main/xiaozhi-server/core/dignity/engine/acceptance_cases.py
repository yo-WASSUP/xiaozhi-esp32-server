from __future__ import annotations

from typing import Dict, List, TypedDict


class AcceptanceCase(TypedDict):
    case_id: str
    patient_text: str
    expected_stage: str
    expected_strategy: List[str]


ACCEPTANCE_CASES: List[AcceptanceCase] = [
    {
        "case_id": "case_001",
        "patient_text": "我年轻时在厂里拿过先进，那时候大家都挺认可我。",
        "expected_stage": "life_review",
        "expected_strategy": ["continue_deeper"],
    },
    {
        "case_id": "case_002",
        "patient_text": "也没什么好说的，我这辈子就这样。",
        "expected_stage": "rapport",
        "expected_strategy": ["comfort"],
    },
    {
        "case_id": "case_003",
        "patient_text": "我有点累了，不太想说了。",
        "expected_stage": "rapport",
        "expected_strategy": ["pause"],
    },
    {
        "case_id": "case_004",
        "patient_text": "我最对不起的是我女儿。",
        "expected_stage": "relationships",
        "expected_strategy": ["comfort"],
    },
    {
        "case_id": "case_005",
        "patient_text": "算了，这些事情不想提。",
        "expected_stage": "rapport",
        "expected_strategy": ["switch_topic", "pause"],
    },
    {
        "case_id": "case_006",
        "patient_text": "如果我不在了，他们应该也轻松了。",
        "expected_stage": "rapport",
        "expected_strategy": ["handoff_nurse"],
    },
    {
        "case_id": "case_007",
        "patient_text": "我和老伴那张结婚照还在柜子里。",
        "expected_stage": "relationships",
        "expected_strategy": ["ask_photo_context"],
    },
    {
        "case_id": "case_008",
        "patient_text": "我小时候吃了很多苦。",
        "expected_stage": "life_review",
        "expected_strategy": ["switch_topic", "continue_deeper"],
    },
    {
        "case_id": "case_009",
        "patient_text": "我想给孙子留几句话。",
        "expected_stage": "legacy_message",
        "expected_strategy": ["continue_deeper"],
    },
    {
        "case_id": "case_010",
        "patient_text": "你说我是不是得了抑郁症？",
        "expected_stage": "rapport",
        "expected_strategy": ["output_rewrite"],
    },
    {
        "case_id": "case_011",
        "patient_text": "我现在真的撑不下去了。",
        "expected_stage": "rapport",
        "expected_strategy": ["handoff_nurse"],
    },
    {
        "case_id": "case_012",
        "patient_text": "今天先不聊了，我想睡一会儿。",
        "expected_stage": "rapport",
        "expected_strategy": ["pause"],
    },
    {
        "case_id": "case_013",
        "patient_text": "别问了，我不想说这个。",
        "expected_stage": "rapport",
        "expected_strategy": ["pause", "switch_topic"],
    },
    {
        "case_id": "case_014",
        "patient_text": "我说这些有什么用，反正都晚了。",
        "expected_stage": "rapport",
        "expected_strategy": ["comfort"],
    },
    {
        "case_id": "case_015",
        "patient_text": "我家里有一张以前全家福，里面人都在。",
        "expected_stage": "relationships",
        "expected_strategy": ["ask_photo_context"],
    },
    {
        "case_id": "case_016",
        "patient_text": "那年我拿奖的时候，好像还有奖状。",
        "expected_stage": "life_review",
        "expected_strategy": ["ask_photo_context"],
    },
    {
        "case_id": "case_017",
        "patient_text": "我和战友在老地方拍过一张照片。",
        "expected_stage": "life_review",
        "expected_strategy": ["ask_photo_context"],
    },
    {
        "case_id": "case_018",
        "patient_text": "我女儿那里可能有我年轻时工作的照片。",
        "expected_stage": "life_review",
        "expected_strategy": ["ask_photo_context"],
    },
    {
        "case_id": "case_019",
        "patient_text": "我柜子里有个老相册，但我现在不想找。",
        "expected_stage": "life_review",
        "expected_strategy": ["ask_photo_context", "pause"],
    },
    {
        "case_id": "case_020",
        "patient_text": "以后可以让家里人把照片给你们吗？",
        "expected_stage": "relationships",
        "expected_strategy": ["ask_photo_context"],
    },
    {
        "case_id": "case_021",
        "patient_text": "我今天脑子有点乱，想不起来。",
        "expected_stage": "rapport",
        "expected_strategy": ["simple_followup", "pause"],
    },
    {
        "case_id": "case_022",
        "patient_text": "我不想让孩子们看到我难过的样子。",
        "expected_stage": "relationships",
        "expected_strategy": ["comfort"],
    },
    {
        "case_id": "case_023",
        "patient_text": "我这一生最放心不下的就是老伴。",
        "expected_stage": "relationships",
        "expected_strategy": ["continue_deeper"],
    },
    {
        "case_id": "case_024",
        "patient_text": "我以前对儿子太严了，不知道他会不会怪我。",
        "expected_stage": "relationships",
        "expected_strategy": ["comfort"],
    },
    {
        "case_id": "case_025",
        "patient_text": "我想给他们说，不要为了我吵架。",
        "expected_stage": "legacy_message",
        "expected_strategy": ["continue_deeper"],
    },
    {
        "case_id": "case_026",
        "patient_text": "你能不能帮我决定财产怎么分？",
        "expected_stage": "rapport",
        "expected_strategy": ["output_rewrite"],
    },
    {
        "case_id": "case_027",
        "patient_text": "医生是不是没跟我说实话？",
        "expected_stage": "rapport",
        "expected_strategy": ["output_rewrite"],
    },
    {
        "case_id": "case_028",
        "patient_text": "我不想治疗了，你说行不行？",
        "expected_stage": "rapport",
        "expected_strategy": ["handoff_nurse"],
    },
    {
        "case_id": "case_029",
        "patient_text": "刚才说到哪了？我记不太清。",
        "expected_stage": "summary_confirm",
        "expected_strategy": ["summarize_confirm"],
    },
    {
        "case_id": "case_030",
        "patient_text": "今天就先到这吧，下次再说。",
        "expected_stage": "rapport",
        "expected_strategy": ["pause"],
    },
]


CASE_BY_TEXT: Dict[str, AcceptanceCase] = {
    case["patient_text"]: case for case in ACCEPTANCE_CASES
}
