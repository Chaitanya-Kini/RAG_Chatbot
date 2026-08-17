"""Chat page.

Selecting a project grounds the answer in that project's documents only.
Selecting "General chat" sends the question straight to the model with no
document context, which is also the default when nothing has been selected.

The project picker sits in st.bottom, in a column to the left of the chat input,
so the two controls stay pinned together at the bottom of the page.
"""

import streamlit as st

import api_client
import ui

# Answers the backend produces when retrieval found nothing useful. Citations are
# meaningless in that case, so they are suppressed.
FALLBACK_ANSWERS = {
    "Information not found in the provided documents.",
    "I don't have enough information in the provided documents to answer this question.",
}

# Sentinel for the "no project" option. The leading em dash cannot appear in a
# project name (names must start with a letter or digit), so this can never
# collide with a real project.
GENERAL = "—general—"


def _history(key: str) -> list:
    """Chat history, kept per project so switching does not mix conversations."""
    histories = st.session_state.setdefault("histories", {})
    return histories.setdefault(key, [])


ui.page_heading("Chat", "Ask your documents, or the model directly.")

if not ui.backend_online():
    st.error(f"The backend is not reachable at {api_client.API_URL}. Start it, then reload.")
    st.stop()

try:
    projects = api_client.list_projects()
except api_client.ApiError as error:
    st.error(str(error))
    st.stop()

names = ui.project_names(projects)
options = [GENERAL] + names
remembered = ui.remembered_project(names)

# The picker is rendered before the messages so `selected` is known while drawing
# them, but st.bottom pins it to the bottom of the page next to the chat input.
with st.bottom:
    picker, box = st.columns([1.4, 5], gap="small", vertical_alignment="center")
    with picker:
        selected = st.selectbox(
            "Project",
            options,
            index=options.index(remembered) if remembered else 0,
            format_func=lambda name: "💬 General chat" if name == GENERAL else f"📁 {name}",
            label_visibility="collapsed",
            key="chat_project_select",
        )
    with box:
        placeholder = (
            "Ask anything..." if selected == GENERAL else f"Ask about '{selected}'..."
        )
        question = st.chat_input(placeholder)

project = None if selected == GENERAL else selected
ui.remember_project(project)

if project is None:
    st.caption(
        "General chat: answers come from the model's own knowledge, not from your documents."
    )
else:
    details = next(item for item in projects if item["name"] == project)
    if details["indexed_count"] == 0:
        ui.empty_state(
            f"'{project}' has no indexed documents",
            "Upload PDFs on the Projects page and run Ingest to build the knowledge base.",
        )

history = _history(selected)
for message in history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            ui.render_sources(message.get("sources", []))

if question:
    history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    spinner = "Thinking..." if project is None else f"Searching '{project}'..."
    with st.chat_message("assistant"):
        try:
            with st.spinner(spinner):
                payload = api_client.query(question, project)
            answer = payload.get("answer", "No answer found.")
            sources = payload.get("sources", [])
            if answer.strip() in FALLBACK_ANSWERS:
                sources = []
            st.markdown(answer)
            ui.render_sources(sources)
            history.append({"role": "assistant", "content": answer, "sources": sources})
        except api_client.ApiError as error:
            message = f"Query failed: {error}"
            st.error(message)
            history.append({"role": "assistant", "content": message, "sources": []})
