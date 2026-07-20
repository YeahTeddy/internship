"""告警工具 — 天气风险告警"""

import json

from langchain_core.tools import tool

from app.core.logger import get_logger

logger = get_logger(__name__)


def build_alert(risk_level, reasons, traffic_count, visibility_score=None):
    """构建告警信息"""
    if risk_level < 2:
        return None
    return {
        "alert_level": risk_level,
        "alert_type": "rain_fog_traffic_risk",
        "alert_status": "pending",
        "alert_message": "；".join(reasons)[:500],
        "vehicle_density": traffic_count,
        "threshold_value": visibility_score,
    }


@tool
def assess_weather_risk(
    vehicle_count: int = 0,
    visibility_level: str = "clear",
    precipitation: str = "none",
) -> str:
    """评估恶劣天气下的交通风险等级。

    Args:
        vehicle_count: 当前检测到的车辆数
        visibility_level: 能见度等级（clear/light_fog/heavy_fog/night）
        precipitation: 降水情况（none/rain/heavy_rain）

    Returns:
        JSON 字符串，包含风险等级和告警建议
    """
    try:
        risk_level = 0
        reasons = []

        # 能见度评估
        if visibility_level == "heavy_fog":
            risk_level += 2
            reasons.append("重度雾霾，能见度极低")
        elif visibility_level == "light_fog":
            risk_level += 1
            reasons.append("轻度雾霾，能见度下降")
        elif visibility_level == "night":
            risk_level += 1
            reasons.append("夜间行车，视野受限")

        # 降水评估
        if precipitation == "heavy_rain":
            risk_level += 2
            reasons.append("暴雨天气，路面湿滑")
        elif precipitation == "rain":
            risk_level += 1
            reasons.append("降雨天气，注意减速")

        # 车流密度评估
        if vehicle_count >= 60:
            risk_level += 2
            reasons.append(f"车流密集（{vehicle_count} 辆）")
        elif vehicle_count >= 25:
            risk_level += 1
            reasons.append(f"车流较多（{vehicle_count} 辆）")

        # 生成告警
        alert = build_alert(risk_level, reasons, vehicle_count)
        result = {
            "risk_level": risk_level,
            "risk_description": "高风险" if risk_level >= 4 else "中风险" if risk_level >= 2 else "低风险",
            "reasons": reasons,
            "vehicle_count": vehicle_count,
            "visibility": visibility_level,
            "precipitation": precipitation,
            "alert": alert,
            "recommendation": _get_recommendation(risk_level),
        }
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": f"风险评估失败: {str(e)}"}, ensure_ascii=False)


def _get_recommendation(level):
    if level >= 4:
        return "建议：启动应急预案，限制车速，发布预警信息"
    elif level >= 2:
        return "建议：加强巡逻，提醒司机减速慢行"
    elif level >= 1:
        return "建议：关注天气变化，做好预警准备"
    return "天气状况良好，正常通行"


ALERT_TOOLS = [assess_weather_risk]
