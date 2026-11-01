"""Local paper reader and learning workspace; no model API calls."""

import hashlib
import re

import streamlit as st

from paperpilot.config import Settings
from paperpilot.learning import context, markdown, sessions
from paperpilot.reader import paper_source, pdf_path, read_page, render_page
from paperpilot.store import Store

st.set_page_config(page_title="PaperPilot · 阅读", page_icon="📖", layout="wide")
st.set_option("client.toolbarMode", "minimal")
st.markdown("""<style>
.stApp {background:#fff;color:#1d1d1f;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
.block-container {max-width:1380px;padding-top:2.5rem;}
h1 {letter-spacing:-1px;}
.stButton button,.stDownloadButton button {border-radius:12px;min-height:44px;}
@media(max-width:900px){[data-testid="stHorizontalBlock"]{flex-direction:column;}
[data-testid="stColumn"]{width:100%;flex:1 1 100%;}}
@media(max-width:640px){.block-container{padding:1.5rem 1rem;}}
</style>""", unsafe_allow_html=True)
st.title("PaperPilot")
st.caption("读原文，理解方法，留下自己的思考。")
config = Settings(PAPERPILOT_MODE="mock")
config.prepare()
store = Store(config.data_dir)
records = sessions(store)
if not records:
    st.info("把论文交给 Codex，请它使用 paperpilot-study。开始后，你的原文与学习笔记会出现在这里。")
    with st.expander("查看开始命令"):
        st.code('paperpilot --data-dir ./data learn start --pdf paper.pdf --goal "读懂方法与实验"')
else:
    record = st.selectbox("选择论文与学习目标", records,
                          format_func=lambda r: r["title"] + " · " + r["goal"][:24])
    paper = paper_source(store, record["source_id"])
    progress = context(store, record["id"])
    st.caption(record["goal"])
    reading, notes, results = st.tabs(["一起读", "学习笔记", "实验结果"])
    with reading:
        lesson_column, page_column = st.columns([1, 1.15], gap="large")
        with lesson_column:
            lessons = record["lessons"]
            if not lessons:
                st.info("学习目标已保存。回到 Codex，先从研究问题开始。")
                current = None
            else:
                selected = st.selectbox("正在阅读的概念", range(len(lessons)), index=len(lessons)-1,
                    format_func=lambda i: f"{i+1}. {lessons[i]['concept']}", key=record["id"])
                current = lessons[selected]
                st.subheader(current["concept"])
                st.markdown(current["explanation"])
                st.markdown("**想一想**")
                st.write(current["question"])
                if "answer" in current:
                    st.markdown("**我的回答**")
                    st.write(current["answer"])
                if "review" in current:
                    st.markdown("**反馈**")
                    st.write(current["review"]["feedback"])
                elif "skipped" in current:
                    st.caption("本题已跳过：" + current["skipped"])
                else:
                    st.caption("回到 Codex 回答或讨论，再刷新此页。")
                with st.expander("依据与待确认项"):
                    references = current["evidence"] + current.get("review", {}).get("evidence", [])
                    for ref in references:
                        st.caption(ref["location"])
                        st.write(ref["quote"])
                    for assumption in current["assumptions"]:
                        st.write(assumption)
            if progress["review_queue"]:
                with st.expander(f"待复习 · {len(progress['review_queue'])} 个概念"):
                    for item in progress["review_queue"]:
                        st.markdown(f"**{item['concept']}**")
                        st.write(item["feedback"])
                    st.caption("根据 Agent 的最近反馈整理，不是客观掌握率。")
        with page_column:
            st.subheader("原文")
            references = current["evidence"] if current else []
            cited_pages = []
            for ref in references:
                match = re.search(r"PDF 第 (\d+) 页", ref["location"])
                number = ref.get("page") or (int(match[1]) if match else None)
                if number is not None and number not in cited_pages:
                    cited_pages.append(number)
            if cited_pages:
                st.caption("当前概念依据：" + "、".join(f"第 {p} 页" for p in cited_pages))
            page = st.number_input("物理页码", min_value=1, max_value=paper["metadata"]["pages"],
                value=cited_pages[0] if cited_pages else 1, step=1,
                key=f"page-{record['id']}-{current['concept'] if current else 'start'}")
            path = pdf_path(store, paper)
            if path.exists():
                st.image(render_page(path, page), width="stretch")
                with st.expander("提取文字"):
                    st.text(read_page(store, paper["id"], page)["text"])
                st.download_button("下载原论文", path.read_bytes(), file_name="paper.pdf", mime="application/pdf")
            else:
                st.info("旧记录没有保存原 PDF。关联同一份原件后，即可查看公式与图表。")
                original = st.file_uploader("关联原论文", type="pdf")
                if original is not None and st.button("关联原件"):
                    data = original.getvalue()
                    if hashlib.sha256(data).hexdigest() != paper["metadata"]["sha256"]:
                        st.error("文件与当前论文记录不一致，请选择导入时的原件。")
                    else:
                        path.parent.mkdir(exist_ok=True)
                        path.write_bytes(data)
                        st.rerun()
    with notes:
        st.caption(f"已记录 {len(record['lessons'])} 个概念；理解反馈由 Agent 提供。")
        st.markdown(markdown(record))
        st.download_button("下载学习笔记", markdown(record), file_name="paperpilot-notes.md", mime="text/markdown")
    with results:
        imported = store.results(record["source_id"])
        if not imported:
            st.info("当前工作区还没有导入实验结果。先读懂方法，再确定要验证的实验。")
        for result in imported:
            st.markdown(result["markdown"])
            st.caption(result["provenance"])
            st.download_button("下载实验对照", result["markdown"], file_name="comparison.md", key=result["id"])
st.button("刷新记录")
