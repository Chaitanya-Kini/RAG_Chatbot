"""Entry point. Declares the sidebar navigation and runs the selected page.

The navigation is created with position="hidden" and the links are rendered by
ui.sidebar_nav() instead. Streamlit always draws its built-in nav at the very top
of the sidebar, above anything the script writes, so hiding it is what lets the
brand header sit above Chat and Projects.
"""

import streamlit as st

import ui

st.set_page_config(
    page_title="Document RAG Chatbot",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

chat_page = st.Page(
    "views/chat.py",
    title="Chat",
    icon=":material/forum:",
    default=True,
)
projects_page = st.Page(
    "views/projects.py",
    title="Projects",
    icon=":material/folder_open:",
)
pages = [chat_page, projects_page]

selected_page = st.navigation(pages, position="hidden")

ui.bootstrap_page()
ui.sidebar_brand()
ui.sidebar_nav(pages)

selected_page.run()
