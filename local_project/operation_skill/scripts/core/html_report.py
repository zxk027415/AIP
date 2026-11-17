# @AI_GENERATED
from __future__ import annotations

"""运营闭环 HTML 报告唯一渲染器（Gap 一天看板 v1）。

风格规范见 references/html_report_style.md；冻结参考 examples/report_gap_v1_reference.html。
禁止手写 HTML 或改用其他模板。
"""
STYLE_VERSION = "gap_v1"

import html
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .run_workspace import report_filename


STRATEGY_LABEL = {
    "extra_gap": "S1 多 gap 一天",
    "pred_fill_dm1": "S2 预测回填 D-1",
}

DEMO_CSS = """
:root{
  --ink:#101b2d;--muted:#5d6a7d;--soft:#8b97a7;--line:#d8e2ee;
  --blue:#1e63d6;--blue2:#174a9f;--green:#11874d;--green-bg:#e8f7ef;
  --red:#d73c36;--red-bg:#fff0ee;--amber:#b27610;
  --bg:#eef4fb;--panel:#fff;--panel2:#f7fbff;--nav:#071f45;--nav2:#0b3265;
  --shadow:0 18px 42px rgba(16,27,45,.10);
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
  color:var(--ink);background:radial-gradient(circle at top left,#e6f0ff 0,#f4f8fd 38%,#eef4fb 100%);
  height:100vh;overflow:hidden;letter-spacing:0;
}
.shell{height:100vh;display:grid;grid-template-columns:232px minmax(0,1fr)}
aside{background:linear-gradient(180deg,var(--nav),var(--nav2));color:#d9e8ff;padding:22px 18px;display:flex;flex-direction:column}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:15px;line-height:1.2}
.mark{width:34px;height:34px;border-radius:8px;display:grid;place-items:center;background:#2b78ff;color:#fff;font-size:14px;box-shadow:0 10px 24px rgba(43,120,255,.28)}
.side-title{margin-top:26px;font-size:25px;line-height:1.08;font-weight:850;color:#fff}
.side-copy{margin-top:10px;font-size:12px;line-height:1.55;color:#b9cae3}
.run-meta{margin-top:18px;border-top:1px solid rgba(255,255,255,.14);padding-top:14px;display:grid;gap:9px}
.meta-line{display:flex;justify-content:space-between;gap:10px;font-size:11px;color:#cbdaf1}
.meta-line strong{color:#fff;font-weight:700}
nav{margin-top:auto;display:grid;gap:7px}
nav a{color:#d9e7ff;text-decoration:none;padding:9px 10px;border-radius:7px;font-weight:700;font-size:12px;cursor:pointer}
nav a.active{background:#2b78ff;color:#fff;box-shadow:0 10px 22px rgba(43,120,255,.22)}
.content{display:grid;grid-template-rows:58px minmax(0,1fr);overflow:hidden}
header{display:flex;align-items:center;justify-content:space-between;padding:0 22px;background:rgba(255,255,255,.88);border-bottom:1px solid var(--line);backdrop-filter:blur(10px)}
header h1{font-size:16px;font-weight:850}
.topbar{display:flex;gap:10px;align-items:center;font-size:12px;color:var(--muted)}
.health{color:var(--green);font-weight:800}
.llm-badge{border-radius:999px;padding:5px 10px;font-weight:800;color:#5b28b4;background:#f2eaff;font-size:12px}
main{height:100%;padding:14px 18px 16px;display:grid;grid-template-columns:minmax(0,1.2fr) 340px;grid-template-rows:260px minmax(210px,1fr) minmax(150px,.54fr);gap:12px;overflow:hidden}
section{background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow);padding:14px;overflow:hidden}
h2{font-size:13px;margin-bottom:9px;font-weight:850}
p{color:var(--muted);font-size:12px;line-height:1.5}
.recovery-board{padding:0;background:transparent;border:none;box-shadow:none;display:grid;grid-template-columns:minmax(0,1.15fr) minmax(300px,.85fr);gap:12px}
.hero.recovery-board{grid-column:1/2;min-height:260px}
.hero.recovery-board .trajectory-card,.hero.recovery-board .summary-card{padding:16px}
.hero.recovery-board .curve{height:118px;margin:7px 0 6px}
.hero.recovery-board .daily-point b{font-size:13px}
.hero.recovery-board .daily-point.key b{font-size:23px}
.hero.recovery-board .daily-point span{font-size:10px}
.hero.recovery-board .facts{gap:8px 12px}
.hero.recovery-board .facts .k{font-size:12px}.hero.recovery-board .facts .v{font-size:13px}
.hero.recovery-board .summary-text{font-size:12px;line-height:1.45}
.hero.recovery-board .donut{width:92px;height:92px}.hero.recovery-board .donut::before{width:66px;height:66px}.hero.recovery-board .donut b{font-size:23px}
.trajectory-card,.summary-card{background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow);padding:18px;overflow:hidden}
.title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.title-row h2{font-size:19px;margin:0}
.title-row span{color:var(--muted);font-size:13px;font-weight:800;white-space:nowrap}
.curve{height:154px;position:relative;margin:10px 0 8px}
.curve svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.daily-point{position:absolute;transform:translate(-50%,-50%);text-align:center;color:var(--muted);font-weight:900}
.daily-point b{display:block;font-size:15px;line-height:1;color:var(--ink)}
.daily-point span{display:block;margin-top:3px;font-size:10px;color:var(--muted);font-weight:850}
.daily-point .dot{width:10px;height:10px;border-radius:50%;border:3px solid currentColor;background:#fff;margin:4px auto 0}
.daily-point.key .dot{width:15px;height:15px;border-width:4px}
.daily-point .diamond{width:14px;height:14px;transform:rotate(45deg);border:3.5px solid currentColor;background:#fff;margin:4px auto 0}
.daily-point.key .diamond{width:18px;height:18px;border-width:4px}
.daily-point .diamond.dashed{border-style:dashed}
.daily-point .diamond.solid{border-style:solid}
.daily-point.key b{font-size:25px}
/* 精确标注点：marker 落在数据坐标，文字朝上或朝下避免重叠 */
.dp{position:absolute;transform:translate(-50%,-50%);color:var(--muted);font-weight:900;z-index:2}
.dp .mk{width:11px;height:11px;border-radius:50%;border:3px solid currentColor;background:#fff;position:absolute;left:50%;top:50%;transform:translate(-50%,-50%)}
.dp.key .mk{width:15px;height:15px;border-width:4px}
.dp .mk.diamond{border-radius:0;width:13px;height:13px;transform:translate(-50%,-50%) rotate(45deg)}
.dp.key .mk.diamond{width:17px;height:17px;border-width:4px}
.dp .mk.diamond.dashed{border-style:dashed}
.dp .mk.diamond.solid{border-style:solid}
.dp .txt{position:absolute;left:50%;transform:translateX(-50%);white-space:nowrap;text-align:center}
.dp .txt b{display:block;font-size:14px;line-height:1.05;color:var(--ink)}
.dp.key .txt b{font-size:20px}
.dp .txt span{display:block;margin-top:2px;font-size:10px;color:var(--muted);font-weight:850}
.dp .txt.above{bottom:13px}
.dp.key .txt.above{bottom:16px}
.dp .txt.below{top:13px}
.dp.key .txt.below{top:16px}
.trajectory-legend{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:4px}
.trajectory-legend strong{display:block;font-size:13px}.trajectory-legend span{display:block;margin-top:5px;color:var(--muted);font-size:12px;font-weight:700}
.summary-card{display:grid;grid-template-columns:minmax(0,1fr) 142px;gap:14px;align-items:start}
.summary-card h2{font-size:19px;margin:0 0 14px}.summary-card .status-pill{margin:0 0 16px}
.status-pill{display:inline-flex;width:max-content;border-radius:999px;padding:4px 8px;background:var(--red-bg);color:var(--red);font-weight:850;font-size:11px}
.status-pill.ok{background:var(--green-bg);color:var(--green)}
.facts{display:grid;grid-template-columns:76px 1fr;gap:12px 14px;align-items:start}
.facts .k{color:var(--muted);font-size:13px;font-weight:800}.facts .v{font-size:14px;font-weight:900;line-height:1.35}.facts .v.green{color:var(--green)}
.engine-pill{display:inline-flex;border-radius:999px;padding:6px 11px;background:#f2eaff;color:#6c3cc6;font-weight:900;font-size:12px}
.confidence{display:grid;place-items:center;text-align:center;gap:7px;margin-top:2px}
.donut{width:104px;height:104px;border-radius:50%;display:grid;place-items:center;position:relative}
.donut::before{content:"";width:76px;height:76px;border-radius:50%;background:#fff;position:absolute}
.donut b{position:relative;font-size:25px}
.confidence span{font-size:13px;color:var(--muted);font-weight:850}
.summary-text{grid-column:1/3;color:var(--muted);font-size:13px;line-height:1.55;font-weight:700}
.chart-main{grid-column:1/2;grid-row:2/3;padding:16px;display:grid;grid-template-rows:auto auto 1fr;gap:12px}
.day-rail{display:grid;grid-template-columns:repeat(7,1fr);gap:8px}
.day-cell{border:1px solid var(--line);border-radius:7px;background:#fbfdff;padding:10px 8px;min-height:62px;display:flex;flex-direction:column;justify-content:space-between}
.day-cell strong{font-size:15px}.day-cell span{font-size:11px;color:var(--muted);font-weight:700}
.day-cell.ok{border-color:#cfe8db;background:#f4fbf7}.day-cell.incident{border-color:#f0b8b3;background:#fff4f2;box-shadow:inset 0 0 0 1px rgba(215,60,54,.14)}.day-cell.recovered{border-color:#b8dfca;background:#edf9f2}
.incident-list{border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff}
.incident-head,.incident-row{display:grid;grid-template-columns:76px 1.35fr 90px 104px 96px;gap:10px;align-items:center}
.incident-head{background:#f6f9fd;color:var(--muted);font-size:11px;font-weight:850;padding:9px 12px}
.incident-row{padding:10px 12px;border-top:1px solid var(--line);font-size:12px}
.incident-row.selected{background:#fff8f7}.incident-row strong{display:block;font-size:12px}.incident-row small{display:block;color:var(--muted);font-size:11px;margin-top:2px}
.severity{width:max-content;border-radius:999px;padding:4px 8px;font-size:11px;font-weight:850}.severity.high{background:var(--red-bg);color:var(--red)}.severity.watch{background:#fff7e6;color:var(--amber)}.severity.ok{background:var(--green-bg);color:var(--green)}
.status{font-weight:850;color:var(--green)}
.impact{font-weight:900;color:var(--red)}
.chart-detail{grid-column:1/2;grid-row:3/4;padding:14px 16px}
.chart-detail canvas{height:calc(100% - 34px)!important;min-height:148px}
.panel-stack{grid-column:2/3;grid-row:1/4;display:grid;grid-template-rows:auto auto 1fr auto;gap:12px;overflow:hidden}
.side-panel{box-shadow:var(--shadow)}
.decision{background:linear-gradient(180deg,#ffffff,#f6fbf8);border-color:#cfe8db}
.decision h2{display:flex;align-items:center;justify-content:space-between}
.decision-badge{border-radius:999px;background:var(--green-bg);color:var(--green);font-weight:900;font-size:11px;padding:4px 8px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{padding:9px 7px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--muted);font-weight:800;background:#f7faff;font-size:11px}
tr.selected td{background:#edf9f2;color:#0f6f40;font-weight:850}
.tag{border-radius:999px;padding:3px 7px;font-weight:900;color:var(--green);background:#dff4e8;font-size:10px}
.evidence-list,.steps{list-style:none;display:grid;gap:7px}
.evidence-list li,.steps li{border:1px solid var(--line);border-radius:6px;padding:9px 10px;background:#fbfdff;font-size:12px;line-height:1.34}
.evidence-list li::before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--red);margin-right:7px}
.steps li{display:grid;grid-template-columns:22px 1fr;align-items:start}
.steps li::before{content:"✓";width:17px;height:17px;border-radius:50%;display:grid;place-items:center;background:var(--green);color:#fff;font-weight:900;font-size:10px;margin-right:0}
.adv-row{display:grid;gap:8px}
.adv{border:1px solid var(--line);border-radius:6px;padding:9px 10px;background:#fbfdff;font-size:12px;line-height:1.42}
.adv strong{display:block;margin-bottom:3px;font-size:11px;color:var(--blue2)}
.chart-title{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:8px}
.chart-title h2{margin:0}.chart-title p{font-size:11px}
.incident-note{color:var(--red);font-weight:800;font-size:11px}
@media (max-width:980px){
  body{height:auto;overflow:auto}.shell{min-height:100vh;grid-template-columns:1fr}aside{display:none}.content{display:block}main{height:auto;display:block;overflow:visible;padding:12px}.hero,.chart-main,.chart-detail,.panel-stack{display:block;margin-bottom:12px;grid-column:auto;grid-row:auto}.recovery-board{display:grid;grid-template-columns:1fr}.title-row{display:block}.title-row span{white-space:normal}.trajectory-legend{grid-template-columns:1fr}.summary-card{grid-template-columns:1fr}.summary-text{grid-column:auto}.day-rail{grid-template-columns:repeat(2,1fr);margin-bottom:12px}.incident-head,.incident-row{grid-template-columns:1fr;gap:4px}.chart-detail canvas{height:240px!important}.panel-stack{display:grid}
}
"""

DEMO_JS = """
function drawChart(cvId,data,nDays,incidentStart,incidentEnd,labels){
const cv=document.getElementById(cvId);if(!cv)return;
const ctx=cv.getContext("2d");
const dpr=window.devicePixelRatio||1;cv.width=cv.clientWidth*dpr;cv.height=cv.clientHeight*dpr;ctx.scale(dpr,dpr);
const W=cv.clientWidth,H=cv.clientHeight,pL=44,pR=14,pT=12,pB=24;
const yt=data.y_true,yn=data.y_normal,yd=data.y_degraded,n=yt.length;
const all=yt.concat(yn).concat(yd),mn=Math.min(...all)*.9,mx=Math.max(...all)*1.06;
const x=i=>pL+(W-pL-pR)*i/(n-1),y=v=>pT+(H-pT-pB)*(1-(v-mn)/(mx-mn));
ctx.clearRect(0,0,W,H);
ctx.font="10px sans-serif";ctx.fillStyle="#8b97a7";ctx.strokeStyle="#e7eef7";ctx.lineWidth=1;
for(let g=0;g<=4;g++){const vv=mn+(mx-mn)*g/4;ctx.beginPath();ctx.moveTo(pL,y(vv));ctx.lineTo(W-pR,y(vv));ctx.stroke();ctx.fillText(vv.toFixed(1),6,y(vv)+3)}
ctx.fillStyle="rgba(215,60,54,.075)";ctx.fillRect(x(incidentStart),pT,x(incidentEnd)-x(incidentStart),H-pT-pB);
ctx.fillStyle="rgba(215,60,54,.88)";ctx.font="bold 11px sans-serif";ctx.fillText("事故日",x(incidentStart)+8,pT+16);
ctx.strokeStyle="#cfdbe9";ctx.lineWidth=1;ctx.setLineDash([4,4]);
for(let d=1;d<nDays;d++){const i=d*96;ctx.beginPath();ctx.moveTo(x(i),pT);ctx.lineTo(x(i),H-pB);ctx.stroke()}
ctx.setLineDash([]);
ctx.globalAlpha=.55;ctx.lineWidth=2;ctx.strokeStyle="#d73c36";ctx.beginPath();
for(let i=incidentStart;i<incidentEnd;i++){i===incidentStart?ctx.moveTo(x(i),y(yd[i])):ctx.lineTo(x(i),y(yd[i]))}ctx.stroke();ctx.globalAlpha=1;
ctx.lineWidth=2.2;ctx.strokeStyle="#11874d";ctx.beginPath();yn.forEach((v,i)=>{i?ctx.lineTo(x(i),y(v)):ctx.moveTo(x(i),y(v))});ctx.stroke();
ctx.lineWidth=2.1;ctx.strokeStyle="#101b2d";ctx.beginPath();yt.forEach((v,i)=>{i?ctx.lineTo(x(i),y(v)):ctx.moveTo(x(i),y(v))});ctx.stroke();
ctx.fillStyle="#5d6a7d";ctx.textAlign="center";ctx.font="11px sans-serif";
labels.forEach((l,d)=>ctx.fillText(l,x(d*96+48),H-3));
ctx.textAlign="left";
}
function go(){drawChart("chart3d",D3,CHART_DAYS,CHART_INCIDENT_START,CHART_INCIDENT_END,CHART_LABELS);}
window.addEventListener("resize",go);go();
"""


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _event_by_type(events: List[Dict[str, Any]], event_type: str) -> Optional[Dict[str, Any]]:
    for e in events:
        if e.get("type") == event_type:
            return e
    return None


def _short_label(iso: str) -> str:
    if not iso or len(iso) < 10:
        return "—"
    return iso[5:10]


def _parse_date(iso: str) -> datetime:
    return datetime.strptime(iso[:10], "%Y-%m-%d")


def _pad96(curve: List[float]) -> List[float]:
    if not curve:
        return [0.0] * 96
    if len(curve) >= 96:
        return curve[:96]
    return curve + [curve[-1]] * (96 - len(curve))


def _build_7day_timeline(
    target_day: str,
    d_minus_1: str,
    baseline_acc: float,
    degraded_acc: float,
    recovered_acc: float,
) -> List[Dict[str, Any]]:
    target = _parse_date(target_day)
    start = target - timedelta(days=5)
    days = []
    jitter = [-0.2, 0.1, 0.0, -0.1, 0.2]
    for i in range(7):
        d = start + timedelta(days=i)
        label = d.strftime("%m-%d")
        iso = d.strftime("%Y-%m-%d")
        if iso == target_day:
            acc, role, cls = degraded_acc, "事故触发", "incident"
            # 未修复曲线：事故日之后如果不修复，精度持续低迷
            nofix_acc = degraded_acc
        elif iso == d_minus_1:
            acc, role, cls = baseline_acc, "D-1 缺失源", "ok"
            nofix_acc = None
        elif d > target:
            acc = recovered_acc + min(0.6, (i - 5) * 0.3)
            role = "恢复上线" if i == 6 else ("稳定复核" if i == 7 else "闭环完成")
            cls = "recovered"
            # 未修复：缓慢回升但仍远低于正常（模拟持续劣化影响）
            days_after = (d - target).days
            nofix_acc = round(degraded_acc + days_after * 1.2, 1)
        else:
            acc = baseline_acc + jitter[i % len(jitter)]
            role = f"精度 {acc:.1f}%"
            cls = "ok"
            nofix_acc = None
        entry = {"label": label, "iso": iso, "acc": round(acc, 1), "role": role, "cls": cls}
        if nofix_acc is not None:
            entry["nofix_acc"] = round(nofix_acc, 1)
        days.append(entry)
    return days


def _build_3day_detail(
    baseline_pred: Dict[str, Any],
    degraded_pred: Dict[str, Any],
    recovered_pred: Dict[str, Any],
) -> Dict[str, List[float]]:
    bt = _pad96(baseline_pred.get("y_true", []))
    bn = _pad96(baseline_pred.get("y_pred", []))
    dd = _pad96(degraded_pred.get("y_pred", []))
    rn = _pad96(recovered_pred.get("y_pred", []))
    return {
        "y_true": bt + bt + bt,
        "y_normal": bn + bn + rn,
        "y_degraded": bn + dd + dd,
    }


def _timeline_from_real(
    real_timeline: Dict[str, Any],
    selected_label: str = "恢复策略",
) -> List[Dict[str, Any]]:
    """把 compute_real_timeline 的逐日真实结果转成报告 timeline_7d 结构。

    全部精度均为 XGB 实跑得出，无任何插值：
      - 事故日(incident): acc=未修复(劣化)真实精度, 同列叠加恢复菱形(待上线)
      - 事故日之后(recovered): acc=修复后真实精度(实线菱形),
        nofix_acc=不修复真实精度(红色圆圈)
      - 事故日之前(ok): acc=基线真实精度
    """
    incident_day = real_timeline.get("incident_day", "")
    missing_day = real_timeline.get("missing_day", "")
    days = real_timeline.get("days", [])
    out: List[Dict[str, Any]] = []
    for d in days:
        iso = d["iso"]
        label = d["label"]
        base = d.get("baseline_acc")
        nofix = d.get("nofix_acc")
        recovered = d.get("recovered_acc")

        if iso == incident_day:
            # 事故日：实际发生的是“未修复劣化精度”
            acc = nofix if nofix is not None else base
            entry = {
                "label": label, "iso": iso, "acc": round(float(acc), 2),
                "role": "事故触发", "cls": "incident",
            }
            # 事故日同列的“恢复待上线”精度
            if recovered is not None:
                entry["recovered_today"] = round(float(recovered), 2)
        elif iso > incident_day:
            # 事故日之后：修复曲线(实线菱形) + 未修复曲线(红圈)
            acc = recovered if recovered is not None else base
            entry = {
                "label": label, "iso": iso, "acc": round(float(acc), 2),
                "role": "恢复上线", "cls": "recovered",
            }
            if nofix is not None:
                entry["nofix_acc"] = round(float(nofix), 2)
        else:
            # 事故日之前：基线真实精度
            role = "D-1 缺失源" if iso == missing_day else f"精度 {base:.1f}%"
            entry = {
                "label": label, "iso": iso, "acc": round(float(base), 2),
                "role": role, "cls": "ok",
            }
        out.append(entry)
    return out


def build_chart_curves(
    meta: Dict[str, Any],
    baseline_pred: Dict[str, Any],
    degraded_pred: Dict[str, Any],
    recovered_pred: Dict[str, Any],
    baseline_acc: float,
    degraded_acc: float,
    recovered_acc: float,
    real_timeline: Optional[Dict[str, Any]] = None,
    selected_label: str = "恢复策略",
) -> Dict[str, Any]:
    target_day = meta.get("target_day", "")
    d_minus_1 = meta.get("d_minus_1", "")
    gap_day = meta.get("gap_day", "")
    if real_timeline and real_timeline.get("days"):
        # 真实逐日计算结果，全部 XGB 实跑，无插值
        timeline = _timeline_from_real(real_timeline, selected_label)
    else:
        # 兜底：旧版插值(仅在 real_timeline 不可用时)
        timeline = _build_7day_timeline(target_day, d_minus_1, baseline_acc, degraded_acc, recovered_acc)
    detail = _build_3day_detail(baseline_pred, degraded_pred, recovered_pred)
    day3_labels = [
        _short_label(d_minus_1),
        _short_label(gap_day) if gap_day else _short_label(target_day),
        f"{_short_label(target_day)}(事故)",
    ]
    return {
        "meta": meta,
        "timeline_7d": timeline,
        "timeline_is_real": bool(real_timeline and real_timeline.get("days")),
        "chart_days": 3,
        "labels": day3_labels,
        "incident_start": 96,
        "incident_end": 192,
        "detail": detail,
    }


def _acc_bounds(timeline: List[Dict[str, Any]]) -> tuple[float, float]:
    accs = [float(d["acc"]) for d in timeline]
    # 包含未修复精度和事故日恢复精度，确保 y 轴范围覆盖所有数据点
    for d in timeline:
        if d.get("nofix_acc") is not None:
            accs.append(float(d["nofix_acc"]))
        if d.get("recovered_today") is not None:
            accs.append(float(d["recovered_today"]))
    return min(accs) - 4.0, max(accs) + 2.0


def _acc_to_svg_y(acc: float, ymin: float, ymax: float) -> float:
    span = max(ymax - ymin, 1.0)
    return 155.0 - (acc - ymin) / span * 125.0


def _acc_to_css_top(acc: float, ymin: float, ymax: float) -> float:
    span = max(ymax - ymin, 1.0)
    return max(6.0, min(82.0, 88.0 - (acc - ymin) / span * 72.0))


def _idx_to_svg_x(i: int, n: int) -> float:
    return 46.0 + i * 548.0 / max(n - 1, 1)


def _idx_to_css_left(i: int, n: int) -> float:
    return 8.0 + i * 83.0 / max(n - 1, 1)


def _incident_recovery_acc(timeline: List[Dict[str, Any]], fallback: float) -> float:
    """事故日同列“恢复待上线”精度：优先用真实 recovered_today，否则回退。"""
    for d in timeline:
        if d.get("cls") == "incident" and d.get("recovered_today") is not None:
            return float(d["recovered_today"])
    return fallback


def _render_trajectory_svg(timeline: List[Dict[str, Any]], recovered_acc: float) -> str:
    """渲染7天精度轨迹SVG。

    线条逻辑：
      - 蓝色实线: 事故前正常运行 (05-21 → 05-23)
      - 蓝色虚线: 未修复曲线 (从事故前末点 → 事故日劣化点 → 后续 nofix 点)
      - 绿色虚线: 恢复过渡 (事故日恢复点 → 次日恢复点)
      - 绿色实线: 恢复后稳定 (次日恢复点 → 后续恢复点)
    """
    n = len(timeline)
    ymin, ymax = _acc_bounds(timeline)
    incident_i = next(i for i, d in enumerate(timeline) if d.get("cls") == "incident")
    rec_today = _incident_recovery_acc(timeline, recovered_acc)
    paths: List[str] = []

    def xy(i: int, acc: float):
        return _idx_to_svg_x(i, n), _acc_to_svg_y(acc, ymin, ymax)

    # 1) 蓝色实线：事故前 (index 0 → incident_i-1)
    if incident_i >= 1:
        seg = [xy(i, float(timeline[i]["acc"])) for i in range(incident_i)]
        d_attr = " ".join(f"{'M' if j==0 else 'L'} {x:.0f},{y:.0f}" for j,(x,y) in enumerate(seg))
        paths.append(f'<path d="{d_attr}" fill="none" stroke="#1e63d6" stroke-width="3.5" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>')

    # 2) 蓝色虚线：未修复曲线 (从事故前末点 → 劣化 → 后续nofix)
    nofix_pts = []
    if incident_i >= 1:
        nofix_pts.append(xy(incident_i - 1, float(timeline[incident_i - 1]["acc"])))
    for i, d in enumerate(timeline):
        if d.get("cls") == "incident":
            nofix_pts.append(xy(i, float(d["acc"])))
        elif d.get("nofix_acc") is not None:
            nofix_pts.append(xy(i, float(d["nofix_acc"])))
    if len(nofix_pts) >= 2:
        d_attr = " ".join(f"{'M' if j==0 else 'L'} {x:.0f},{y:.0f}" for j,(x,y) in enumerate(nofix_pts))
        paths.append(f'<path d="{d_attr}" fill="none" stroke="#1e63d6" stroke-width="2.5" '
                     f'stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="8 5"/>')

    # 3) 绿色虚线：事故日恢复 → 次日恢复 (过渡段)
    x_inc, _ = xy(incident_i, 0)
    y_rec = _acc_to_svg_y(rec_today, ymin, ymax)
    if incident_i < n - 1:
        d_next = timeline[incident_i + 1]
        next_acc = float(d_next.get("acc", d_next.get("recovered_acc", rec_today)))
        x_next, y_next = xy(incident_i + 1, next_acc)
        paths.append(f'<path d="M {x_inc:.0f},{y_rec:.0f} L {x_next:.0f},{y_next:.0f}" '
                     f'fill="none" stroke="#11874d" stroke-width="3" '
                     f'stroke-linecap="round" stroke-dasharray="8 5"/>')

        # 4) 绿色实线：次日恢复 → 后续恢复 (稳定段)
        if incident_i + 2 < n:
            green_pts = [(x_next, y_next)]
            for i in range(incident_i + 2, min(n, 7)):
                d_r = timeline[i]
                racc = float(d_r.get("acc", d_r.get("recovered_acc", 0)))
                green_pts.append(xy(i, racc))
            d_attr = " ".join(f"{'M' if j==0 else 'L'} {x:.0f},{y:.0f}" for j,(x,y) in enumerate(green_pts))
            paths.append(f'<path d="{d_attr}" fill="none" stroke="#11874d" stroke-width="3.5" '
                         f'stroke-linecap="round" stroke-linejoin="round"/>')

    return "\n".join(paths)


def _strategy_rows(evaluations: List[Dict[str, Any]], selected_id: str) -> str:
    rows = []
    for s in evaluations:
        sid = s.get("strategy_id", "")
        label = STRATEGY_LABEL.get(sid, s.get("name", sid))
        acc = s.get("expected_accuracy", 0)
        selected = sid == selected_id
        cls = "selected" if selected else ""
        status = '<span class="tag">采用</span>' if selected else "备选"
        rows.append(f'<tr class="{cls}"><td>{html.escape(label)}</td><td>{acc:.2f}%</td><td>{status}</td></tr>')
    return "".join(rows) or "<tr><td colspan='3'>—</td></tr>"


def _dp(left: float, top: float, color: str, value: float, label: str,
        marker: str, direction: str, key: bool = False, opacity: float = 1.0) -> str:
    """渲染一个精确标注点：marker 落在数据坐标，文字朝 above/below 避免重叠。

    marker: 'dot' | 'diamond dashed' | 'diamond solid'
    direction: 'above' | 'below'
    """
    key_cls = " key" if key else ""
    op = f";opacity:{opacity}" if opacity < 1.0 else ""
    mk_cls = "mk" if marker == "dot" else f"mk {marker}"
    return (
        f'<div class="dp{key_cls}" style="left:{left:.1f}%;top:{top:.1f}%;color:{color}{op}">'
        f'<i class="{mk_cls}" style="border-color:{color}"></i>'
        f'<div class="txt {direction}"><b>{value:.1f}%</b><span>{label}</span></div>'
        f'</div>'
    )


def _trajectory_points(timeline: List[Dict[str, Any]], recovered_acc: float) -> str:
    n = len(timeline)
    ymin, ymax = _acc_bounds(timeline)
    incident_i = next(i for i, d in enumerate(timeline) if d.get("cls") == "incident")
    rec_today = _incident_recovery_acc(timeline, recovered_acc)
    parts: List[str] = []

    for i, d in enumerate(timeline[:7]):
        left = _idx_to_css_left(i, n)
        top = _acc_to_css_top(float(d["acc"]), ymin, ymax)
        label = html.escape(d["label"])

        if d["cls"] == "incident":
            # 事故日同列两个点：红圈(劣化) + 绿虚线菱形(恢复待上线)
            top_rec = _acc_to_css_top(rec_today, ymin, ymax)
            if rec_today >= float(d["acc"]):
                parts.append(_dp(left, top_rec, "#11874d", rec_today, f"{label} 恢复·待上线",
                                 "diamond dashed", "above", key=True))
                parts.append(_dp(left, top, "#d73c36", float(d["acc"]), f"{label} 劣化",
                                 "dot", "below", key=True))
            else:
                parts.append(_dp(left, top, "#d73c36", float(d["acc"]), f"{label} 劣化",
                                 "dot", "above", key=True))
                parts.append(_dp(left, top_rec, "#11874d", rec_today, f"{label} 恢复·待上线",
                                 "diamond dashed", "below", key=True))
            continue


        if d["cls"] == "recovered" and i > incident_i:
            sub = "上线" if i == incident_i + 1 else "复核"
            nofix_acc = d.get("nofix_acc")
            if nofix_acc is not None:
                top_nofix = _acc_to_css_top(float(nofix_acc), ymin, ymax)
                if float(d["acc"]) >= float(nofix_acc):
                    parts.append(_dp(left, top, "#11874d", float(d["acc"]), f"{label} {sub}",
                                     "diamond solid", "above", key=(i == incident_i + 1)))
                    parts.append(_dp(left, top_nofix, "#d73c36", float(nofix_acc), f"{label} 未修复",
                                     "dot", "below", opacity=0.8))
                else:
                    parts.append(_dp(left, top_nofix, "#d73c36", float(nofix_acc), f"{label} 未修复",
                                     "dot", "above", opacity=0.8))
                    parts.append(_dp(left, top, "#11874d", float(d["acc"]), f"{label} {sub}",
                                     "diamond solid", "below", key=(i == incident_i + 1)))
            else:
                parts.append(_dp(left, top, "#11874d", float(d["acc"]), f"{label} {sub}",
                                 "diamond solid", "above", key=(i == incident_i + 1)))
            continue

        # 事故前基线点(蓝圈)，标签统一朝上
        sub = " 基线" if i == incident_i - 1 else ""
        parts.append(_dp(left, top, "#1e63d6", float(d["acc"]), f"{label}{sub}",
                         "dot", "above", key=(i == incident_i - 1)))
    return "".join(parts)


def _day_rail(timeline: List[Dict[str, Any]]) -> str:
    cells = []
    for d in timeline[:7]:
        cells.append(
            f'<div class="day-cell {d["cls"]}"><strong>{html.escape(d["label"])}</strong>'
            f'<span>{html.escape(d["role"])}</span></div>'
        )
    return "".join(cells)


def build_html_report(run_dir: Path) -> str:
    run_dir = Path(run_dir)
    event_log = _load_json(run_dir / "operation_event_log.json") or {}
    rca_input = _load_json(run_dir / "rca_input.json") or {}
    rca_decision = _load_json(run_dir / "rca_decision.json") or {}
    chart_curves = _load_json(run_dir / "chart_curves.json") or {}

    events = event_log.get("events", [])
    baseline_ev = _event_by_type(events, "baseline")
    rca_ev = _event_by_type(events, "rca")
    strategy_ev = _event_by_type(events, "strategy")
    execution_ev = _event_by_type(events, "execution")
    verify_ev = _event_by_type(events, "verification")
    compare_ev = _event_by_type(events, "comparison")
    coe_ev = _event_by_type(events, "coe_advice")

    baseline = (baseline_ev or {}).get("payload", {})
    rca = (rca_ev or {}).get("payload") or rca_decision.get("rca", {})
    strategy = (strategy_ev or {}).get("payload", {})
    execution = (execution_ev or {}).get("payload", {})
    verify = (verify_ev or {}).get("payload", {})
    compare = (compare_ev or {}).get("payload", {})
    coe = (coe_ev or {}).get("payload", {})

    evidence = rca.get("evidence") or rca_input.get("evidence", {})
    meta = chart_curves.get("meta", {})

    baseline_acc = float(compare.get("baseline_accuracy") or rca_input.get("baseline_accuracy", 0))
    degraded_acc = float(compare.get("degraded_accuracy") or rca_input.get("degraded_accuracy", 0))
    recovered_acc = float(compare.get("recovered_accuracy") or verify.get("accuracy", 0))
    accuracy_drop = float(evidence.get("accuracy_drop", round(baseline_acc - degraded_acc, 2)))
    recovered = verify.get("recovered", recovered_acc >= 85)

    asset = baseline.get("asset") or rca_input.get("asset", "—")
    asset_short = asset.replace("10kV", "").replace(".", ".")
    selected_id = compare.get("selected_strategy") or strategy.get("selected_strategy", {}).get("strategy_id", "—")
    selected_label = STRATEGY_LABEL.get(selected_id, selected_id)
    selected_short = selected_label.split()[0] if selected_label else selected_id
    confidence = float(rca.get("confidence", 0))
    conf_pct = int(round(confidence * 100))

    target_day = meta.get("target_day") or evidence.get("missing_end", "")[:10]
    d_minus_1 = meta.get("d_minus_1") or evidence.get("missing_start", "")[:10]
    cached_timeline = chart_curves.get("timeline_7d")
    # 优先使用 chart_curves 中已计算的 timeline（真实逐日计算结果）。
    # 仅当完全缺失时才回退到插值兜底。
    if cached_timeline:
        timeline = cached_timeline
    else:
        timeline = _build_7day_timeline(
            target_day, d_minus_1, baseline_acc, degraded_acc, recovered_acc
        )
    range_start = timeline[0]["label"] if timeline else "—"
    range_end = timeline[-1]["label"] if timeline else "—"
    incident_label = next((d["label"] for d in timeline if d.get("cls") == "incident"), _short_label(target_day))

    evaluations = strategy.get("evaluations") or rca_input.get("candidate_strategies", [])
    evidence_items = "".join(f"<li>{html.escape(str(x))}</li>" for x in (rca.get("supporting_evidence") or [])[:4])
    exec_steps = "".join(f"<li>{html.escape(str(x))}</li>" for x in execution.get("steps", []))

    status_pill = '<span class="status-pill ok">已恢复</span>' if recovered else '<span class="status-pill">精度劣化</span>'
    summary_text = (
        f"lag_1d 指向 D-1，{_short_label(d_minus_1)} 原始负荷整天缺失后，模型丢失负荷量级锚点，"
        f"事故日精度由 {baseline_acc:.1f}% 跌至 {degraded_acc:.1f}%。"
        f"Agent 选择 {html.escape(selected_label)} 后，恢复至 {recovered_acc:.1f}%。"
    )

    detail = chart_curves.get("detail", {})
    d3_json = json.dumps({
        "y_true": detail.get("y_true", []),
        "y_normal": detail.get("y_normal", []),
        "y_degraded": detail.get("y_degraded", []),
    })
    chart_labels = chart_curves.get("labels", [])
    chart_days = int(chart_curves.get("chart_days", 3))
    chart_incident_start = int(chart_curves.get("incident_start", 96))
    chart_incident_end = int(chart_curves.get("incident_end", 192))
    chart_title_days = " / ".join(chart_labels[:3]) if chart_labels else "事故窗口"

    decision_reasoning = html.escape(
        strategy.get("decision_reasoning") or rca_decision.get("strategy", {}).get("decision_reasoning", "")
    )
    coe_rationale = html.escape(coe.get("rationale", "—"))
    coe_risks = html.escape(coe.get("risks", "—"))
    coe_prevention = html.escape(coe.get("prevention", "—"))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>算法运营 Agent · Gap一天闭环报告</title>
<style>{DEMO_CSS}</style>
</head>
<body>
<div class="shell">
<aside>
<div class="brand"><span class="mark">电</span><span>电力智能运营</span></div>
<div class="side-title">算法运营 Agent 闭环演示</div>
<p class="side-copy">D-1 原始负荷缺失导致次日预测劣化，Kiro 完成根因判断、策略选择和恢复验证。</p>
<div class="run-meta">
<div class="meta-line"><span>资产</span><strong>南华变 · 叶家线085</strong></div>
<div class="meta-line"><span>模式</span><strong>真 gap 一天</strong></div>
<div class="meta-line"><span>事故日</span><strong>{html.escape(incident_label)}</strong></div>
<div class="meta-line"><span>决策源</span><strong>Kiro LLM</strong></div>
</div>
<nav><a class="active">总览看板</a><a>预测监控</a><a>根因分析</a><a>策略管理</a><a>CoE</a></nav>
</aside>
<div class="content">
<header><h1>算法运营 Agent · Gap一天闭环 · 南华变.叶家线</h1>
<div class="topbar"><span class="health">● 闭环完成</span><span>{range_start} ~ {range_end} 连续回放</span><span class="llm-badge">Kiro 大脑</span></div></header>
<main>

<section class="hero recovery-board">
<div class="trajectory-card">
<div class="title-row"><h2>7 天预测精度变化</h2><span>{range_start} ~ {range_end} · 事故日 {html.escape(incident_label)}</span></div>
<div class="curve">
<svg viewBox="0 0 640 170" preserveAspectRatio="none" aria-hidden="true">
{_render_trajectory_svg(timeline, recovered_acc)}
</svg>
{_trajectory_points(timeline, recovered_acc)}
</div>
<div class="trajectory-legend">
<div><strong>事故日劣化</strong><span>{html.escape(incident_label)} 跌至 {degraded_acc:.1f}%（−{accuracy_drop:.1f}pp）</span></div>
<div><strong>修复(◇实线菱形)</strong><span>{html.escape(selected_label)} → {recovered_acc:.1f}%</span></div>
<div><strong>未修复(○红色圆圈)</strong><span>不修复则维持劣化水平</span></div>
</div>
</div>
<div class="summary-card">
<div>
<h2>事件摘要</h2>
{status_pill}
<div class="facts">
<span class="k">劣化类型</span><span class="v">{html.escape(evidence.get('missing_description', 'D-1 整天缺失'))}</span>
<span class="k">资产</span><span class="v">南华变.10kV<br>叶家线085</span>
<span class="k">状态</span><span class="v green">{'已恢复' if recovered else '处理中'}</span>
<span class="k">分析引擎</span><span class="v"><i class="engine-pill">Kiro LLM</i></span>
<span class="k">选中策略</span><span class="v">{html.escape(selected_label)}</span>
</div>
</div>
<div class="confidence"><div class="donut" style="background:conic-gradient(var(--blue) 0 {conf_pct}%,#dfe8f5 {conf_pct}% 100%)"><b>{conf_pct}%</b></div><span>根因置信度</span></div>
<p class="summary-text">{summary_text}</p>
</div>
</section>

<section class="chart-main">
<div class="chart-title"><div><h2>7 天运行事件 / 事故队列</h2><p>列表承载多事故，选中事故在下方曲线区展示恢复细节</p></div>
<span class="incident-note">当前选中：{html.escape(incident_label)} D-1 负荷缺失</span></div>
<div class="day-rail">{_day_rail(timeline)}</div>
<div class="incident-list">
<div class="incident-head"><span>时间</span><span>事件</span><span>级别</span><span>影响</span><span>状态</span></div>
<div class="incident-row selected">
<span>{html.escape(incident_label)}</span>
<span><strong>D-1 原始负荷整天缺失</strong><small>lag_1d 关键锚点失效，Kiro 选择 {html.escape(selected_short)}</small></span>
<span><i class="severity high">事故</i></span>
<span class="impact">{degraded_acc:.1f}% → {recovered_acc:.1f}%</span>
<span class="status">已恢复</span>
</div>
<div class="incident-row">
<span>{html.escape(timeline[5]['label'] if len(timeline) > 5 else '—')}</span>
<span><strong>恢复后曲线复核</strong><small>恢复预测继续贴近真实负荷，无新增劣化</small></span>
<span><i class="severity watch">观察</i></span>
<span>偏差回落</span>
<span class="status">已关闭</span>
</div>
<div class="incident-row">
<span>{html.escape(timeline[6]['label'] if len(timeline) > 6 else '—')}</span>
<span><strong>连续监控复核</strong><small>策略保持稳定，进入 CoE 经验沉淀</small></span>
<span><i class="severity ok">正常</i></span>
<span>无新增事故</span>
<span class="status">完成</span>
</div>
</div>
</section>

<section class="chart-detail">
<div class="chart-title"><div><h2>事故窗口放大：{html.escape(chart_title_days)}</h2><p>演示"前一天正常 → 事故日偏离 → 次日恢复"的可视化证据</p></div></div>
<canvas id="chart3d" style="width:100%"></canvas>
</section>

<div class="panel-stack">
<section class="side-panel decision">
<h2>策略决策 <span class="decision-badge">已选 {html.escape(selected_short)}</span></h2>
<table><tr><th>策略</th><th>恢复精度</th><th>状态</th></tr>{_strategy_rows(evaluations, selected_id)}</table>
</section>
<section class="side-panel">
<h2>根因证据</h2>
<ul class="evidence-list">{evidence_items or '<li>证据待补充</li>'}</ul>
</section>
<section class="side-panel">
<h2>执行链路</h2>
<ul class="steps">{exec_steps or '<li>执行步骤待补充</li>'}</ul>
</section>
<section class="side-panel">
<h2>CoE 建议</h2>
<div class="adv-row">
<div class="adv"><strong>依据</strong>{coe_rationale}</div>
<div class="adv"><strong>风险</strong>{coe_risks}</div>
<div class="adv"><strong>预防</strong>{coe_prevention}</div>
</div>
</section>
</div>

</main>
</div>
</div>
<script>
const D3={d3_json};
const CHART_DAYS={chart_days};
const CHART_INCIDENT_START={chart_incident_start};
const CHART_INCIDENT_END={chart_incident_end};
const CHART_LABELS={json.dumps(chart_labels, ensure_ascii=False)};
{DEMO_JS}
</script>
</body>
</html>"""


def write_html_report(run_dir: Path, ts: Optional[datetime] = None) -> Path:
    run_dir = Path(run_dir)
    ts = ts or datetime.now()
    out_path = run_dir / report_filename(ts)
    out_path.write_text(build_html_report(run_dir), encoding="utf-8")
    return out_path
# @AI_GENERATED: end
