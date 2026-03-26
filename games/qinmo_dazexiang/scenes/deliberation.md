# 密谋

## 场景概述

夜深了。雨势稍减，但天空依然漆黑。

陈胜招呼你靠近。吴广也在。他们压低声音，在雨声中说着什么。

你听见了几个字：**"误期当斩……逃亡……不如……大事。"**

陈胜看着你。他没有废话：

> "壮士不死则已，死即举大名耳。王侯将相宁有种乎！"

吴广接过话：

> "如今大雨，十日必不能至。纵不死于戍边，亦死于鞭笞。不如就死。与其跪着死，不如站着反。"

他们等待你的回应。

## 陈胜观察你

陈胜的目光在你脸上停留了几秒。他似乎在判断什么。

"你叫什么？"他忽然问。"你是哪里人？"

这不是寒暄。这是在决定是否让你加入。

## 你的回应

你可以：

**表明立场**
- 热血回应：表示愿意同生共死
- 冷静追问：起义的计划是什么？
- 有所保留：你们有多少人支持？
- 沉默以对：不做承诺，继续观察
- 临阵退缩：表示自己只想回家种田
- 劝阻他们：也许还有别的办法

---

## GM_COMMAND（默认/沉默）

action_tag: keep_silent
player_input: 你没有立即表态，而是保持了沉默
next_scene: kill_officer

## GM_COMMAND（决策参与）

action_tag: make_plans
player_input: 参与决策，计划下一步行动
next_scene: spirit_awakened

## GM_COMMAND（逃跑）

action_tag: run_away
player_input: 考虑逃离
next_scene: spirit_awakened

## GM_COMMAND（热血回应）

action_tag: speak_up_for_others
player_input: 表示愿意同生共死
next_scene: spirit_awakened
