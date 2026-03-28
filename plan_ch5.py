"""Plan Chapter 5 — generate 2-3 plot branches via LLM."""
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from meta_writing.llm import LLMClient, MODEL_SONNET

PROJECT_DIR = Path(__file__).parent

SYSTEM = """\
你是一位经验丰富的网络小说策划编辑。你的任务是为下一章生成2-3个可选的情节分支。

## 输出格式

严格输出JSON，不要包含markdown代码块标记。格式如下：

{
  "branches": [
    {
      "title": "分支标题",
      "outline": "详细大纲（800-1200字），包括具体场景、对话方向、感官描写方向",
      "characters_involved": ["角色名1", "角色名2"],
      "consequences": "这个分支对后续剧情的影响",
      "foreshadowing_opportunities": ["可以推进的伏笔1", "可以推进的伏笔2"],
      "satisfaction_type": "medium/major",
      "hook_type": "emotional/suspense/reversal",
      "hook_description": "章节末尾钩子的具体内容",
      "tension_impact": "tension_maintain/tension_increase",
      "risk_level": "safe/bold"
    }
  ],
  "context_notes": "对当前剧情走向的分析"
}

## 关键约束

1. 每个分支必须自然衔接上一章结尾
2. 不能违反已建立的世界规则（微感只读物体痕迹，不能读心）
3. 感情线要慢——第5章不能出现告白、拥抱等亲密行为
4. 每个分支要有明确的"这一章解决了什么 + 留下了什么悬念"
5. 优先推进已有伏笔，而不是引入全新的设定
"""


async def main():
    story_data = PROJECT_DIR / "story_data"

    # Load context
    xia_fu = (story_data / "characters" / "xia_fu.yaml").read_text(encoding="utf-8")
    wen_ye = (story_data / "characters" / "wen_ye.yaml").read_text(encoding="utf-8")
    liang_shu = (story_data / "characters" / "liang_shu.yaml").read_text(encoding="utf-8")
    world_rules = (story_data / "world_rules.yaml").read_text(encoding="utf-8")
    foreshadowing = (story_data / "foreshadowing.yaml").read_text(encoding="utf-8")
    story_core = (story_data / "story_core.yaml").read_text(encoding="utf-8")

    # Read chapter endings for context
    ch3_text = (PROJECT_DIR / "chapters" / "003.md").read_text(encoding="utf-8")
    ch4_text = (PROJECT_DIR / "chapters" / "004.md").read_text(encoding="utf-8")

    user_message = f"""## Story Bible

### 故事核心
{story_core}

### 角色
#### 夏浮
{xia_fu}

#### 温野
{wen_ye}

#### 梁书
{liang_shu}

### 世界规则
{world_rules}

### 伏笔状态
{foreshadowing}

## 已完成章节概要

### 第1章
夏浮在书店打工，展现听觉型微感的日常。她听见旧诗集里退回它的人的哭声，听见玻璃瓶里三下敲击的声音。她把这些写在笔记本上。书店的租约快到期了。

### 第2章
温野的视角。他在拍即将被拆的旧楼，看见墙壁上几十年来的温度痕迹层叠。他来书店，和夏浮初次交流。他以为自己只是观察力强，还不知道自己有微感。

### 第3章（最后2000字）
{ch3_text[-2000:]}

### 第4章（完整）
{ch4_text}

## 规划要求

请为第5章规划2-3个情节分支。

关键考量：
1. 第4章结尾温野说"也许你能帮他"，把照片留给了夏浮。这句话的含义需要在第5章回响——不是立刻行动，而是在夏浮心里发酵。
2. 笔记本里现在有两张照片（门环+柜子），这是声音博物馆的雏形萌芽，但角色们还不自知。
3. 书店还有87天。梁书姐的压力在第4章被搁置了（因为葬礼），第5章应该让这条线有推进。
4. 温野的纪录片项目（fs_003）还没有被正式展现过——他拍的东西、他在做什么、为什么做。
5. 两人的关系处于微妙节点：夏浮在台阶上说出了"左边""衣服"，等于半暴露了能力。温野没有追问。但这种"不追问"本身在制造张力。
6. 禁忌层已揭示（微感无法关闭），第5章应该展现这之后的"日常"——过载之后的后遗症是什么？
7. 真相层（第7章揭示）还有2章的铺垫空间，第5章可以开始暗示"两种微感互补"的可能性。

请生成JSON。
"""

    llm = LLMClient()
    print("正在规划第5章...")
    print(f"输入长度: ~{len(user_message)} 字符\n")

    response = await llm.complete(
        system=SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        model=MODEL_SONNET,
        max_tokens=8192,
        temperature=0.8,
    )

    # Try to parse JSON
    text = response.text.strip()
    # Remove markdown code block if present
    if text.startswith("```"):
        first_newline = text.index("\n")
        last_fence = text.rfind("```")
        if last_fence > first_newline:
            text = text[first_newline + 1:last_fence].strip()

    try:
        result = json.loads(text)
        # Pretty-print
        output = json.dumps(result, ensure_ascii=False, indent=2)
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        print("保存原始输出...")
        output = text

    output_path = PROJECT_DIR / "_planner_result_ch5.json"
    output_path.write_text(output, encoding="utf-8")

    print(f"\n规划完成!")
    print(f"保存到: {output_path}")
    print(f"Token: 输入 {response.usage.get('input_tokens', 0):,}, 输出 {response.usage.get('output_tokens', 0):,}")

    # Display branches
    try:
        data = json.loads(output)
        print(f"\n{'='*60}")
        print(f"共 {len(data['branches'])} 个分支：\n")
        for i, b in enumerate(data["branches"], 1):
            print(f"  [{i}] {b['title']}")
            print(f"      风险: {b.get('risk_level', '?')} | 张力: {b.get('tension_impact', '?')}")
            print(f"      角色: {', '.join(b.get('characters_involved', []))}")
            print(f"      钩子: {b.get('hook_description', '')[:80]}...")
            print()
        print(f"分析: {data.get('context_notes', '')[:200]}")
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
