"""Streamlit thin client: no credentials, models or analysis logic in the browser layer."""

import os

import httpx
import streamlit as st

st.set_page_config(page_title="PaperPilot Agent · 科研与代码助手", page_icon="🧭", layout="wide")
API = os.getenv("PAPERPILOT_API_URL", "http://127.0.0.1:8000").rstrip("/")


def request(method: str, path: str, **kwargs):
    response = httpx.request(method, API + path, timeout=120, **kwargs)
    response.raise_for_status()
    return response.json()


st.markdown("""<style>
.stApp {background:linear-gradient(130deg,#f5f8ff 0%,#fff 65%);}
h1 {letter-spacing:-1.5px;color:#142947;}
[data-testid="stSidebar"] {background:#edf2fa;}
[data-testid="stMetric"] {background:white;border:1px solid #dae3f1;border-radius:14px;padding:14px;}
[data-testid="stMetricValue"] {font-size:1.35rem;}
[data-testid="stMarkdownContainer"] h1 {font-size:clamp(1.5rem,2.5vw,2.3rem);}
.block-container {padding-top:2.4rem;}
</style>""", unsafe_allow_html=True)

st.caption("P A P E R P I L O T  /  E V I D E N C E  F I R S T")
st.title("让研究与代码，都有据可循。")
st.markdown("上传论文或读取公开仓库，让 Agent 规划任务、调用工具，并交付可追溯的研究报告。")

try:
    health = request("GET", "/health")
    with st.sidebar:
        st.header("🧭 PaperPilot Agent")
        st.caption("科研与开源代码分析助手")
        if health["mode"] == "mock":
            st.warning("MOCK · 模拟模式\n\n真实解析与工具检索；不调用大模型，不生成模型分析结论。")
        else:
            st.success(f"LIVE · {health['model']}")
            st.caption("每次任务发送给模型前，均需确认。")
        st.divider()
        st.markdown("**工作流程**\n\n① 导入来源\n\n② 描述任务\n\n③ 查看计划与工具\n\n④ 核对引用并下载")
        st.caption("只读分析 · 不执行仓库脚本\n\nCPU 稀疏向量检索 · 无需 GPU")

    left, right = st.columns([1, 1.3], gap="large")
    with left:
        st.subheader("01 / 选择研究材料")
        pdf_tab, github_tab = st.tabs(["📄 论文 PDF", "⌘ GitHub 仓库"])
        with pdf_tab:
            uploaded = st.file_uploader("上传可提取文字的 PDF（最多 20 MB / 150 页）", type="pdf")
            if st.button("解析论文", disabled=uploaded is None, use_container_width=True):
                with st.spinner("提取文字、记录页码并分块…"):
                    st.session_state.source = request("POST", "/sources/pdf", files={
                        "file": (uploaded.name, uploaded.getvalue(), "application/pdf")})
        with github_tab:
            url = st.text_input("公开仓库根地址", placeholder="https://github.com/pallets/click")
            if st.button("读取仓库", disabled=not url, use_container_width=True):
                with st.spinner("读取固定 commit 下的主要文件…"):
                    st.session_state.source = request("POST", "/sources/github", json={"url": url})
        if "source" in st.session_state:
            source = st.session_state.source
            st.success(f"已导入：{source['title']}")
            st.caption(f"{source['chunks']} 个证据分块 · {source['kind']}")
            with st.expander("查看来源与采样范围"):
                st.json(source["metadata"])

        st.subheader("02 / 交给 Agent 的任务")
        question = st.text_area("任务描述", value="分析核心方法、实验依据和复现条件（method, experiments, reproduction）。",
                                height=125)
        if st.button("开始分析 →", type="primary", use_container_width=True,
                     disabled="source" not in st.session_state or len(question.strip()) < 2):
            st.session_state.job_id = request("POST", "/tasks", json={
                "source_id": st.session_state.source["id"], "question": question})["id"]

    with right:
        st.subheader("03 / 任务工作台")

        @st.fragment(run_every="2s")
        def task_panel():
            if "job_id" not in st.session_state:
                st.info("导入材料并发起任务后，这里会显示真实执行过程和报告。")
                return
            job = request("GET", f"/tasks/{st.session_state.job_id}")
            labels = {"queued": "排队中", "running": "执行中", "completed": "已完成",
                      "failed": "失败", "awaiting_approval": "等待确认", "cancelled": "已取消"}
            a, b, c = st.columns(3)
            a.metric("任务状态", labels[job["status"]])
            b.metric("工具调用", sum(e["stage"] == "tool_started" for e in job["events"]))
            c.metric("来源片段", len(job.get("evidence", [])))
            if job["status"] == "awaiting_approval":
                st.warning(job["approval"]["reason"])
                st.json(job["approval"])
                yes, no = st.columns(2)
                if yes.button("确认发送并分析", type="primary"):
                    request("POST", f"/tasks/{job['id']}/approval", json={"approved": True})
                    st.rerun(scope="fragment")
                if no.button("拒绝发送"):
                    request("POST", f"/tasks/{job['id']}/approval", json={"approved": False})
                    st.rerun(scope="fragment")
            with st.expander("查看计划与工具调用记录", expanded=job["status"] != "completed"):
                for event in job["events"]:
                    st.caption(f"{event['time'][11:19]} UTC · {event['stage']}")
                    st.json(event["detail"], expanded=False)
            if job["status"] == "failed":
                st.error(job["error"])
            if job["status"] == "completed":
                st.download_button("↓ 下载 Markdown 报告", job["markdown"], file_name="paperpilot-report.md",
                                   mime="text/markdown", use_container_width=True)
                report_tab, evidence_tab = st.tabs(["分析报告", "原始证据"])
                with report_tab:
                    st.markdown(job["markdown"])
                with evidence_tab:
                    for item in job["evidence"]:
                        st.markdown(f"**[{item['id']}] {item['location']}**")
                        st.code(item["text"], language=None)
        task_panel()

    with st.expander("最近任务（本实例共享工作区）"):
        for job in request("GET", "/tasks")[:10]:
            if st.button(f"{job['created_at'][:16]} · {job['status']} · {job['question'][:45]}", key=job["id"]):
                st.session_state.job_id = job["id"]
                st.rerun()
except httpx.HTTPError as exc:
    # UI boundary: explain connection/API failure without replacing it with fabricated output.
    detail = exc.response.text[:600] if isinstance(exc, httpx.HTTPStatusError) else str(exc)
    st.error(f"服务请求失败：{detail}")
