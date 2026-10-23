"""Read-only business requirements; never a pipeline configuration or dataset."""

import csv
import io
import json

import pandas as pd

from resource_paths import resource_path


KIND_LABELS = {
    "numeric": "数值量 / Laplace候选",
    "categorical": "有限类别 / GRR候选",
    "dictionary_text": "字典或文本 / 需规范化",
    "multivalue": "多值字段 / 需编码设计",
    "identifier": "标识或联系方式 / 默认排除",
    "location": "地址 / 默认排除或地区化",
    "composite": "组合字段 / 需拆分",
    "time": "时间字段 / 需定义分析变量",
    "trajectory": "轨迹 / 当前不支持",
}

CHECKLIST = (
    ("发布任务", "明确希望发布的统计信息和使用者，不用于替代真实运输或安全作业记录。"),
    ("主体与粒度", "选择产生单位或处置单位，固定统计年度；企业、联单、轨迹不可直接混为一行。"),
    ("公开主体名单", "确认名单确实公开且每个主体一行；改成随机编号不等于名单已公开。"),
    ("校准数据", "提供公开、合成或经单独隐私处理的校准依据；仅主体不重叠不保护校准人员。"),
    ("发布数据", "当前没有实际数据；GUI只接收合成或获准公开的演示数据，秘密发布使用正式CLI。"),
    ("数值公开边界", "逐字段确定公开上下界、单位和年度，不能从私有发布数据自动取最小最大值。"),
    ("公开类别域", "确认名录和行业字典版本、分类层级及完整合法取值，不能直接使用样本去重结果。"),
    ("多值与文本", "确认多标签编码；如拆成二元列，每列均占用预算；任意文本和GPS轨迹不支持。"),
    ("校准敏感目标", "当前目标必须为非退化数值字段，且不得出现在公开字段列表中。"),
    ("预算和先验", "由作者确定epsilon、监管先验及参数；需求清单不自动赋值，不代表已获发布授权。"),
    ("公开线性等式", "仅添加经确认的同主体、同年度、同单位等式；缺少收支字段时保持无约束。"),
    ("验证与输出", "准备真实输入和正式配置后重新Validate；没有数据时不得生成发布结果或性能结论。"),
)


def load_requirements() -> dict:
    path = resource_path("demo/assets/hazardous_waste_requirements.json")
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def requirement_rows(catalog: dict, group=None) -> pd.DataFrame:
    rows = []
    for item in catalog["fields"]:
        if group is not None and item["group"] != group:
            continue
        rows.append({
            "原表编号": item["number"],
            "业务分组": item["group"],
            "字段名称": item["name"],
            "建议列名（待确认）": item["key"],
            "字段含义": item["description"],
            "数据形态": KIND_LABELS[item["kind"]],
            "单位/粒度": item["unit"],
            "当前接入建议": item["handling"],
            "来源接口（需求声明）": item["interface"],
            "原表位置": "Sheet1!C{}".format(item["source_row"]),
        })
    return pd.DataFrame(rows)


def requirements_csv(catalog: dict) -> bytes:
    return requirement_rows(catalog).to_csv(index=False).encode("utf-8-sig")


def readiness_checklist_csv() -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["待确认事项", "说明", "作者填写", "证据或来源"])
    writer.writerows((name, detail, "", "") for name, detail in CHECKLIST)
    return stream.getvalue().encode("utf-8-sig")
