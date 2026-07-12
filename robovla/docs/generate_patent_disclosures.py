#!/usr/bin/env python3
"""
RoboVLA V2.0 - 专利交底书自动生成脚本
根据技术模块配置自动生成 5 项发明专利交底书 Markdown

使用: python docs/generate_patent_disclosures.py
输出: docs/patents/ 目录
"""

import os
import json
from datetime import datetime

PATENT_TEMPLATES = {
    "P01_轻量VLA多模态融合": {
        "title": "一种面向工业场景的轻量化视觉-语言-动作多模态融合推理方法",
        "field": "人工智能/机器人控制",
        "abstract": (
            "本发明公开一种面向工业场景的轻量化视觉-语言-动作(VLA)多模态融合推理方法。"
            "包括：采集拖拽示教轨迹，将视觉特征(工件位置、姿态)、自然语言指令(产线口语)与"
            "动作序列(关节角度、末端姿态)映射到统一特征空间；通过交叉注意力机制融合多模态信息；"
            "在边缘设备(Jetson Orin)上部署量化的 Transformer 模型进行推理。"
            "解决了传统示教编程无法适应工件位置变化的问题，实现了单次示教即可自适应泛化。"
        ),
        "claims": [
            "一种轻量化VLA推理方法，包括以下步骤：\nS1: 采集拖拽示教轨迹数据...\nS2: 提取视觉特征...\nS3: 多模态特征融合...",
            "根据权利要求1所述的方法，其中S2中视觉特征通过预训练的ResNet-50骨干网络提取...",
            "根据权利要求1所述的方法，其中通过4-bit量化在Jetson Orin上实现≤700ms的端到端推理延迟...",
            "一种存储介质，其上存储有计算机程序，该程序被处理器执行时实现权利要求1-3中任一项所述的方法。",
            "一种工业机器人系统，包括协作机械臂、2D工业相机、边缘计算设备，所述边缘计算设备执行权利要求1-3中任一项所述的方法。",
        ],
        "figures": [
            "图1: VLA多模态融合架构总览",
            "图2: 交叉注意力融合模块结构",
            "图3: 推理流程时序图",
        ]
    },
    "P02_模仿学习泛化": {
        "title": "一种基于单次示教的模仿学习工业装配泛化方法",
        "field": "人工智能/机器人学习",
        "abstract": (
            "本发明公开一种基于单次示教的模仿学习工业装配泛化方法。通过录制单次工人拖拽示教轨迹，"
            "结合视觉偏移补偿和B样条轨迹平滑，在5分钟内完成本地模型训练。在后续运行中，"
            "系统自动根据工件实际位置计算偏移量并修正运动轨迹。解决了传统机器人编程需要专业技术人才、"
            "换产时间长的问题，适用于中小制造企业的多品种小批量生产场景。"
        ),
        "claims": [
            "一种基于单次示教的模仿学习方法，包括以下步骤：\nS1: 录制拖拽示教轨迹...\nS2: B样条平滑...\nS3: 本地5分钟快速训练...",
            "根据权利要求1所述的方法，其中视觉偏移补偿通过SIFT特征匹配计算X/Y偏移...",
            "根据权利要求1所述的方法，其中模仿学习模型采用行为克隆(BC)加残差补偿的混合策略...",
            "一种工业机器人控制系统，执行权利要求1-3所述的方法。",
        ],
        "figures": [
            "图1: 单次示教泛化流程",
            "图2: 轨迹平滑前后对比",
            "图3: 视觉偏移补偿示意",
        ]
    },
    "P03_跨品牌硬件抽象": {
        "title": "一种跨品牌协作机器人统一软件插件架构及方法",
        "field": "机器人控制/软件架构",
        "abstract": (
            "本发明公开一种跨品牌协作机器人统一软件插件架构。通过定义统一的RobotBase抽象基类，"
            "封装connect/get_state/move_joint/enable_drag_mode/estop等标准接口，"
            "各品牌(遨博、越疆、宇树等)通过实现具体插件适配器来屏蔽SDK差异。"
            "上层应用(视觉、决策、UI)无需修改即可切换不同品牌机器人。"
            "解决了工业机器人软件生态碎片化、客户切换品牌成本高的问题。"
        ),
        "claims": [
            "一种跨品牌机器人统一软件插件架构，包括：抽象基类层定义标准接口；插件适配器层封装各品牌SDK差异...",
            "根据权利要求1所述的架构，其中标准接口包括运动控制、状态查询、拖拽示教、急停等...",
            "根据权利要求1所述的架构，其中通过工厂模式动态加载插件，配置文件切换品牌...",
            "一种实现权利要求1-3架构的计算机可读存储介质。",
        ],
        "figures": [
            "图1: 五层解耦架构总览",
            "图2: 插件工厂动态加载流程",
            "图3: 接口适配层示意",
        ]
    },
    "P04_离线边缘推理": {
        "title": "一种面向工业机器人的离线边缘语音-视觉-动作多模态推理系统",
        "field": "边缘计算/人工智能",
        "abstract": (
            "本发明公开一种面向工业机器人的离线边缘多模态推理系统。在边缘计算设备(Jetson Orin)上"
            "同时部署量化VLA模型、本地LLM(DeepSeek-R1 7B)、离线ASR/语音合成引擎，"
            "实现完全断网运行。系统包括：LLM指令解析模块、ASR语音采集模块、"
            "VLA动作推理模块、TTS语音播报模块的协调调度机制。"
            "解决了工厂担心数据上云安全、网络不稳定导致停产的痛点。"
        ),
        "claims": [
            "一种工业机器人离线边缘推理系统，包括：VLA推理引擎、本地LLM模块、离线ASR模块、TTS播报模块...",
            "根据权利要求1所述的系统，其中LLM模块通过4-bit量化部署7B参数模型...",
            "根据权利要求1所述的系统，其中VLA推理与LLM采用共享显存优化策略...",
            "一种边缘计算设备，包括处理器和存储器，执行权利要求1-3所述的系统功能。",
        ],
        "figures": [
            "图1: 离线边缘推理系统架构",
            "图2: 多模块算力调度时序图",
            "图3: 断网全功能运行示意",
        ]
    },
    "P05_一机一码加密": {
        "title": "一种工业软件离线授权与全链路数据加密保护方法",
        "field": "信息安全/工业软件",
        "abstract": (
            "本发明公开一种工业软件离线授权与全链路数据加密方法。包括：采集Jetson硬件序列号(SHA256)"
            "生成唯一授权码；对任务模型、工件图像使用AES-256加密存储；实现一键不可逆数据清零(删除密钥+覆写文件)；"
            "操作日志全链路留痕,保留180天可追溯。解决了工业软件盗版、客户工厂数据泄露、"
            "合规审计等场景的痛点。"
        ),
        "claims": [
            "一种工业软件离线授权方法，包括：采集硬件特征信息；SHA256生成授权码；离线校验...",
            "根据权利要求1所述的方法，其中数据加密采用AES-256+CBC模式...",
            "根据权利要求1所述的方法，其中一键数据清零包括删除密钥文件、n次覆写原始数据...",
            "一种存储介质，其上存储实现权利要求1-3方法的程序。",
        ],
        "figures": [
            "图1: 一机一码授权流程",
            "图2: AES-256加密/解密架构",
            "图3: 数据清零时序示意",
        ]
    },
}


def generate_patent_doc(patent_id: str, patent_info: dict, output_dir: str) -> str:
    """生成单份专利交底书 Markdown"""
    now = datetime.now().strftime("%Y-%m-%d")

    lines = []
    lines.append(f"# 发明专利技术交底书")
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("|------|------|")
    lines.append(f"| 发明名称 | {patent_info['title']} |")
    lines.append(f"| 技术领域 | {patent_info['field']} |")
    lines.append(f"| 申请类型 | 发明专利 |")
    lines.append(f"| 交底日期 | {now} |")
    lines.append(f"| 发明人 | [填写] |")
    lines.append(f"| 申请人 | [填写] |")
    lines.append("")

    lines.append("## 一、技术领域")
    lines.append(f"本发明涉及{patent_info['field']}技术领域。")
    lines.append("")

    lines.append("## 二、背景技术(现有技术的不足)")
    lines.append(
        "在传统工业机器人示教编程中，需要专业技术工程师使用专用示教器逐点编程，"
        "当工件位置、来料角度发生变化时需要重新编程。此外，现有工业机器人系统"
        "普遍依赖云端推理、对不同品牌机器人缺乏统一软件接口等问题。"
    )
    lines.append("")

    lines.append("## 三、发明内容")
    lines.append(f"### 技术方案概述")
    lines.append(patent_info['abstract'])
    lines.append("")

    lines.append("### 技术效果")
    lines.append("1. **降低使用门槛**：工人拖拽即可完成示教，无需编程技能")
    lines.append("2. **快速适配**：单次示教5分钟内完成训练部署")
    lines.append("3. **通用性强**：跨品牌硬件统一接口，一套软件适配多品牌")
    lines.append("4. **离线安全**：全功能本地运行，数据不出工厂")
    lines.append("")

    lines.append("## 四、附图说明")
    for fig in patent_info.get('figures', []):
        lines.append(f"- {fig}")
    lines.append("")

    lines.append("## 五、权利要求书")
    for i, claim in enumerate(patent_info.get('claims', []), 1):
        lines.append(f"### 权利要求 {i}")
        lines.append(claim)
        lines.append("")

    lines.append("## 六、具体实施方式")
    lines.append("")
    lines.append("### 实施例1：3C电子小件锁付场景")
    lines.append(
        "在某3C电子工厂的螺丝锁付产线上，部署本发明系统：\n"
        "1. 工人拖拽机械臂完成一次锁付动作(约30秒)\n"
        "2. 系统自动记录轨迹+视觉特征，B样条平滑后5分钟完成本地训练\n"
        "3. 在生产中，系统自动识别工件位置±15mm偏移，自适应调整夹取路径\n"
        "4. 72小时连续运行无故障，锁付成功率≥96%"
    )
    lines.append("")

    lines.append("### 实施例2：五金件上下料场景")
    lines.append(
        "在五金冲压件上下料产线：\n"
        "1. 操作工通过语音指令'更换3号工件'切换生产任务\n"
        "2. 离线LLM解析指令后，加载对应任务模型\n"
        "3. 系统自动完成新工件视觉标定和路径规划\n"
        "4. 切换全过程无需工程师介入，操作工口述即可完成"
    )
    lines.append("")

    lines.append("---")
    lines.append(f"*本文档由 RoboVLA 专利引擎自动生成，日期: {now}*")
    lines.append(f"*专利编号: {patent_id}*")

    content = "\n".join(lines)

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{patent_id}_{patent_info['title'][:20]}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def main():
    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "docs", "patents"
    )

    print(f"RoboVLA 专利交底书生成器")
    print(f"输出目录: {output_dir}")
    print(f"共 {len(PATENT_TEMPLATES)} 项专利")
    print()

    for patent_id, info in PATENT_TEMPLATES.items():
        path = generate_patent_doc(patent_id, info, output_dir)
        print(f"  ✅ {patent_id}: {path}")

    print()
    print(f"全部专利交底书生成完成! 共 {len(PATENT_TEMPLATES)} 份。")
    print(f"文件位置: {output_dir}/")
    print()
    print("下一步:")
    print("  1. 补充发明人和申请人信息")
    print("  2. 使用 Visio/PPT 绘制附图")
    print("  3. 提交知识产权代理机构审核")


if __name__ == "__main__":
    main()
