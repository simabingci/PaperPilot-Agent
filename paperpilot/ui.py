"""Streamlit workspace client; no model secrets or Docker privileges in this process."""

import json
import os

import httpx
import streamlit as st

st.set_page_config(page_title="PaperPilot · 实验复现工作区", page_icon="🧭", layout="wide")
API = os.getenv("PAPERPILOT_API_URL", "http://127.0.0.1:8000").rstrip("/")


def request(method: str, path: str, **kwargs):
    response = httpx.request(method, API + path, timeout=120, **kwargs)
    response.raise_for_status()
    return response.json()


st.markdown("""<style>
.stApp {background:linear-gradient(130deg,#f4f7fc 0%,#fff 70%);}
h1 {letter-spacing:-1.4px;color:#142947;}
[data-testid="stSidebar"] {background:#edf2fa;}
[data-testid="stMetric"] {background:white;border:1px solid #dae3f1;border-radius:12px;padding:12px;}
[data-testid="stMetricValue"] {font-size:1.3rem;}
[data-testid="stMarkdownContainer"] h1 {font-size:clamp(1.5rem,2.5vw,2.3rem);}
.block-container {padding-top:2rem;}
</style>""", unsafe_allow_html=True)
st.caption("P A P E R P I L O T  /  R E P R O D U C T I O N  W O R K S P A C E")
st.title("读懂论文，对上代码，核对实验。")
st.markdown("把论文、代码版本和实验结果放进同一个工作区，留下可以再次运行的依据。")

try:
    health = request("GET", "/health")
    sources = request("GET", "/sources")
    source_by_id = {s["id"]: s for s in sources}
    studies = [s for s in sources if s["kind"] == "study"]
    with st.sidebar:
        st.header("🧭 PaperPilot")
        st.caption("论文 × 代码 × 实验结果")
        if health["mode"] == "mock":
            st.warning("MOCK · 真实检索预览\n\n不调用模型，不生成联合推理结论。")
        else:
            st.success(f"LIVE · {health['model']}")
        st.divider()
        st.markdown("**复现路径**\n\n① 关联论文与代码\n\n② 核对方法与实验\n\n③ 审批并在主机运行\n\n④ 导入指标、比较协议")
        st.caption("Web 不执行代码、不连接 Docker socket。\n已有 Agent 可直接使用 Skill / MCP / CLI。")

    research_tab, results_tab, integration_tab = st.tabs(["联合研究", "实验结果对照", "接入已有 Agent"])
    with research_tab:
        left, right = st.columns([1, 1.35], gap="large")
        with left:
            st.subheader("01 / 导入研究材料")
            uploaded = st.file_uploader("论文 PDF · 最多 20 MB / 150 页", type="pdf")
            if st.button("导入论文", disabled=uploaded is None, use_container_width=True):
                with st.spinner("提取页码与文字…"):
                    imported = request("POST", "/sources/pdf", files={
                        "file": (uploaded.name, uploaded.getvalue(), "application/pdf")})
                    st.session_state.paper_id = imported["id"]
                st.rerun()
            url = st.text_input("对应的公开 GitHub 仓库", placeholder="https://github.com/locuslab/TCN")
            if st.button("导入代码", disabled=not url, use_container_width=True):
                with st.spinner("读取固定 commit 的主要文件…"):
                    imported = request("POST", "/sources/github", json={"url": url})
                    st.session_state.repository_id = imported["id"]
                st.rerun()

            st.subheader("02 / 关联与研究目标")
            mode = st.radio("研究方式", ["论文＋代码", "单独分析"], horizontal=True)
            if mode == "论文＋代码":
                paper_ids = [s["id"] for s in sources if s["kind"] == "paper"]
                repo_ids = [s["id"] for s in sources if s["kind"] == "repository"]
                paper = st.selectbox("选择论文", paper_ids, format_func=lambda i: source_by_id[i]["title"],
                                     key="paper_id")
                repository = st.selectbox("选择代码版本", repo_ids,
                    format_func=lambda i: source_by_id[i]["title"] + " · " + source_by_id[i]["metadata"]["commit"][:8],
                    key="repository_id")
                title = st.text_input("工作区名称", value="我的论文复现实验")
                objective = st.text_input("目标实验 / 表格", value="讲解论文与代码，识别目标实验的复现条件和差异。")
                if st.button("建立联合工作区", disabled=not paper or not repository or not title,
                             use_container_width=True):
                    st.session_state.source = request("POST", "/studies", json=dict(
                        title=title, paper_id=paper, repository_id=repository, objective=objective))
                    st.rerun()
                if studies:
                    chosen = st.selectbox("已有工作区", [s["id"] for s in studies],
                                          format_func=lambda i: source_by_id[i]["title"])
                    if st.button("打开工作区", use_container_width=True):
                        st.session_state.source = source_by_id[chosen]
            else:
                singles = [s["id"] for s in sources if s["kind"] != "study"]
                chosen = st.selectbox("已导入材料", singles, format_func=lambda i: source_by_id[i]["title"])
                if chosen:
                    st.session_state.source = source_by_id[chosen]
            active = st.session_state.get("source")
            if mode == "论文＋代码" and active and active["kind"] != "study":
                active = None
            if active:
                st.success(f"当前：{active['title']}")
                with st.expander("来源版本与采样范围"):
                    st.json(active["metadata"])
            template = st.selectbox("任务", [
                "联合讲解论文和代码，说明方法对应的类、函数和配置，并列出不能确认的对应关系。",
                "制定复现方案：核对 dataset split、preprocessing、training budget、evaluation，提取论文指标及命令草案。",
                "排查复现差异：对照论文方法、数据处理、代码默认值和评估实现，列出需要验证的假设。"])
            extra = st.text_area("补充问题 / 指定实验", height=90, placeholder="例如：重点解释 Table 4 的 Adding Problem T=600。")
            if st.button("开始研究 →", type="primary", use_container_width=True, disabled=active is None):
                st.session_state.job_id = request("POST", "/tasks", json={
                    "source_id": active["id"], "question": template + "\n" + extra})["id"]

        with right:
            st.subheader("03 / 研究过程与复现方案")

            @st.fragment(run_every="2s")
            def task_panel():
                if "job_id" not in st.session_state:
                    st.info("关联材料后发起研究，查看方法与代码映射、实验目标和来源引用。")
                    return
                job = request("GET", f"/tasks/{st.session_state.job_id}")
                labels = {"queued": "排队中", "running": "执行中", "completed": "已完成", "failed": "失败",
                          "awaiting_approval": "等待确认", "cancelled": "已取消"}
                a, b, c = st.columns(3)
                a.metric("研究状态", labels[job["status"]])
                b.metric("工具调用", sum(e["stage"] == "tool_started" for e in job["events"]))
                c.metric("来源片段", len(job.get("evidence", [])))
                if job["status"] == "awaiting_approval":
                    st.warning(job["approval"]["reason"])
                    yes, no = st.columns(2)
                    if yes.button("确认发送并分析", type="primary"):
                        request("POST", f"/tasks/{job['id']}/approval", json={"approved": True})
                        st.rerun(scope="fragment")
                    if no.button("拒绝发送"):
                        request("POST", f"/tasks/{job['id']}/approval", json={"approved": False})
                        st.rerun(scope="fragment")
                with st.expander("计划与工具调用", expanded=job["status"] != "completed"):
                    for event in job["events"]:
                        st.caption(f"{event['time'][11:19]} UTC · {event['stage']}")
                        st.json(event["detail"], expanded=False)
                if job["status"] == "failed":
                    st.error(job["error"])
                if job["status"] == "completed":
                    st.download_button("下载研究报告", job["markdown"], file_name="paperpilot-study.md",
                                       mime="text/markdown", use_container_width=True)
                    st.download_button("下载结构化分析", json.dumps(job.get("structured_report", {}), ensure_ascii=False,
                                       indent=2), file_name="study-report.json", mime="application/json")
                    report_tab, evidence_tab = st.tabs(["联合报告", "原始证据"])
                    with report_tab:
                        st.markdown(job["markdown"])
                    with evidence_tab:
                        for item in job["evidence"]:
                            st.markdown(f"**[{item['id']}] {item.get('source_kind', '')} · {item['location']}**")
                            st.code(item["text"], language=None)
            task_panel()

    with results_tab:
        st.subheader("实验跑通，与论文指标对齐，是两项检查。")
        st.caption("先在有 Docker 的主机审阅并运行配方，再上传 comparison-input.json。上传记录会标明来源，API 不认证外部执行真实性。")
        selected = st.selectbox("结果归属工作区", [s["id"] for s in studies],
                                format_func=lambda i: source_by_id[i]["title"])
        result_file = st.file_uploader("导入实验指标与论文基准", type="json")
        if st.button("核对协议并生成对照表", disabled=not selected or result_file is None):
            if result_file.size > 1024 * 1024:
                raise ValueError("结果 JSON 最大 1 MB")
            request("POST", f"/studies/{selected}/results", json=json.loads(result_file.getvalue()))
            st.success("已保存结果对照")
        if selected:
            for result in request("GET", f"/studies/{selected}/results"):
                st.caption(f"{result['created_at']} · {result['submission']['scope']} · 上传结果，未经服务端执行认证")
                status_labels = {"within_tolerance": "容差内", "outside_tolerance": "超出容差",
                                 "not_comparable": "不可直接比较", "missing": "缺失指标"}
                for row in result["comparison"]["rows"]:
                    with st.container(border=True):
                        st.markdown(f"**{row['metric']} · {status_labels[row['status']]}**")
                        paper_column, actual_column = st.columns(2)
                        paper_column.metric("论文", f"{row['paper']:.6g} {row['unit']}")
                        measured = f"{row['actual']:.6g}" if row["actual"] is not None else "缺失"
                        actual_column.metric("实测", f"{measured} {row['unit']}")
                        if row["delta"] is not None:
                            st.caption(f"差值（实测 − 论文）：{row['delta']:.6g}；显示值取 6 位有效数字，下载保留原值。")
                        st.write("；".join(row["reasons"]) or "声明的协议与单位一致，已按预设容差比较。")
                        st.caption(row["paper_location"])
                with st.expander("核对实验协议", expanded=True):
                    for difference in result["comparison"]["protocol_differences"]:
                        st.markdown(f"**{difference['field']}**\n\n论文：{difference['paper']}\n\n实测：{difference['actual']}")
                    st.caption(result["comparison"]["conclusion"])
                st.download_button("下载对照报告", result["markdown"], file_name="comparison.md", key=result["id"])

    with integration_tab:
        st.subheader("让已有 Agent 负责推理，PaperPilot 负责证据和实验记录。")
        st.markdown("使用项目内 `agent-skills/paperpilot-reproduce/SKILL.md`；可通过 CLI 或 MCP 获取联合证据，无需再配置一个模型 API。")
        st.code('paperpilot init --pdf paper.pdf --repo https://github.com/owner/repo --title "目标实验"\n'
                'paperpilot evidence --study STUDY_ID --query "method dataset split training evaluation"\n'
                'paperpilot inspect recipe.json\n'
                'paperpilot run recipe.json --approve APPROVAL_DIGEST\n'
                'paperpilot compare data/runs/RUN_ID/comparison-input.json', language="bash")
        st.info("执行配方前核对适配器、镜像、commit 和资源预算。Runner 使用无网络、无 GPU 的 CPU 容器；不自动安装依赖或修改代码。")

    with st.expander("最近研究任务"):
        for job in request("GET", "/tasks")[:10]:
            if st.button(f"{job['created_at'][:16]} · {job['status']} · {job['question'][:40]}", key=job["id"]):
                st.session_state.job_id = job["id"]
                st.rerun()
except (httpx.HTTPError, ValueError) as exc:
    detail = exc.response.text[:600] if isinstance(exc, httpx.HTTPStatusError) else str(exc)
    st.error(f"请求失败：{detail}")
