"""Streamlit UI for the AI SQL Data Analyst.

Run:  streamlit run app.py
"""
from pathlib import Path

import streamlit as st

from src.database import check_database
from src.ollama_client import OllamaClient, OllamaError
from src.sql_analyst import SQLAnalyst

st.set_page_config(page_title="AI SQL Data Analyst", page_icon="📊", layout="wide")

GENERAL_EXAMPLES = [
    "Which product category generates the most revenue?",
    "Which iPhone model sells the most?",
    "Which state has the highest return rate?",
    "How did monthly revenue change during 2025?",
]

# seed_data.py writes the products it made weak on purpose; offer them as examples
story_file = Path(__file__).parent / "database" / "underperformers.txt"
STORY_EXAMPLES = []
if story_file.exists():
    for line in story_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            STORY_EXAMPLES.append(f"Why did {line.split('|')[0]} not sell much?")

st.session_state.setdefault("question", "")

# ------------------------------ sidebar ------------------------------ #
with st.sidebar:
    st.header("Setup")
    client = OllamaClient()
    models = client.list_models()
    if models:
        st.success("Ollama is running")
        default = models.index(client.model) if client.model in models else 0
        client.model = st.selectbox("Model", models, index=default)
    else:
        st.error("Ollama not reachable. Run `ollama serve`.")

    db_ok, db_message = check_database()
    (st.success if db_ok else st.error)(db_message)

    st.header("Try an example")
    for ex in STORY_EXAMPLES + GENERAL_EXAMPLES:
        st.button(ex, on_click=lambda ex=ex: st.session_state.update(question=ex), use_container_width=True)

# ------------------------------- main -------------------------------- #
st.title("📊 AI SQL Data Analyst")
st.caption("Ask a business question about NovaCart. The AI plans the analysis, writes SQL, checks it, runs it and explains the result.")

question = st.text_input("Your question", key="question", placeholder="Why did the iPhone 14 128GB not sell much?")

if st.button("Analyze", type="primary"):
    if not question.strip():
        st.warning("Please type a question first.")
    elif not db_ok:
        st.error(db_message)
    else:
        analyst = SQLAnalyst(client)
        try:
            with st.status("Analyzing...", expanded=True) as status:
                report = analyst.analyze(question.strip(), progress=st.write)
                status.update(label="Analysis complete", state="complete", expanded=False)
        except OllamaError as e:
            st.error(str(e))
            st.stop()

        st.subheader("Answer")
        st.markdown(report.answer)

        st.subheader("How the answer was built")
        st.caption(f"Question type: {report.plan.get('question_type')}")
        for sr in report.steps:
            icon = "✅" if sr.error is None else "❌"
            note = " (auto-repaired)" if sr.repaired and sr.error is None else ""
            with st.expander(f"{icon} Step {sr.step['id']}: {sr.step['goal']}{note}"):
                if sr.step.get("hypothesis"):
                    st.caption(f"Hypothesis: {sr.step['hypothesis']}")
                if sr.sql:
                    st.code(sr.sql, language="sql")
                if sr.error:
                    st.error(sr.error)
                elif sr.result is not None:
                    df = sr.result.to_dataframe()
                    if df.empty:
                        st.info("Query returned no rows.")
                    else:
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        if len(df.columns) == 2 and len(df) <= 30 and df.iloc[:, 1].dtype.kind in "if":
                            st.bar_chart(df.set_index(df.columns[0]))
                    st.caption(f"{sr.result.row_count} rows | {sr.result.elapsed_ms:.0f} ms | attempts: {sr.attempts}")