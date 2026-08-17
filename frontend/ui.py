"""Shared styling and small presentational helpers.

The CSS only targets classes defined here plus a handful of Streamlit's stable
data-testid hooks, so a Streamlit upgrade cannot silently break the layout.
"""

from typing import List, Optional

import streamlit as st

import api_client

ACTIVE_PROJECT_KEY = "active_project"

_CSS = """
<style>
:root {
    --rag-accent: #4f46e5;
    --rag-border: #e4e6ef;
    --rag-muted: #6b7280;
    --rag-surface: #f7f8fc;
}

/* Tighten the default top padding so the page title sits higher */
.block-container { padding-top: 2.4rem; padding-bottom: 4rem; max-width: 1100px; }

/* Sidebar navigation links, rendered by sidebar_nav() below the brand */
.st-key-sidebar_nav { margin: 0.1rem 0 0.7rem 0; }
.st-key-sidebar_nav a { border-radius: 8px; padding: 0.3rem 0.5rem; }
.st-key-sidebar_nav a:hover { background: var(--rag-surface); }

.rag-brand {
    display: flex; align-items: center; gap: 0.6rem;
    padding: 0 0 0.85rem 0; margin-bottom: 0.5rem;
    border-bottom: 1px solid var(--rag-border);
}
.rag-brand-mark {
    width: 34px; height: 34px; border-radius: 9px; flex: 0 0 34px;
    background: var(--rag-accent); color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.05rem;
}
.rag-brand-text { line-height: 1.15; }
.rag-brand-title { font-weight: 650; font-size: 0.98rem; }
.rag-brand-sub { font-size: 0.74rem; color: var(--rag-muted); }

.rag-page-title { font-size: 1.55rem; font-weight: 680; margin: 0 0 0.15rem 0; }
.rag-page-sub { color: var(--rag-muted); font-size: 0.9rem; margin-bottom: 1.4rem; }

/* Pills: source citations and index status */
.rag-chips { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.7rem; }
.rag-chip {
    display: inline-flex; align-items: center; gap: 0.35rem;
    padding: 0.2rem 0.6rem; border-radius: 999px;
    font-size: 0.76rem; line-height: 1.5;
    background: var(--rag-surface); border: 1px solid var(--rag-border);
    color: #374151;
}
.rag-chip-label { color: var(--rag-muted); font-size: 0.76rem; margin-right: 0.1rem; }
.rag-pill {
    display: inline-flex; align-items: center; gap: 0.3rem;
    padding: 0.12rem 0.55rem; border-radius: 999px;
    font-size: 0.72rem; font-weight: 550; white-space: nowrap;
}
.rag-pill-ok { background: #e8f5ee; color: #12683c; border: 1px solid #bfe3cd; }
.rag-pill-wait { background: #fff6e5; color: #8a5a00; border: 1px solid #f2ddb4; }

.rag-doc-name { font-weight: 550; font-size: 0.92rem; word-break: break-all; }
.rag-doc-meta { color: var(--rag-muted); font-size: 0.76rem; }

/* Chat bubbles */
[data-testid="stChatMessage"] {
    background: transparent; border: 1px solid var(--rag-border);
    border-radius: 12px; padding: 0.85rem 1rem; margin-bottom: 0.7rem;
}

.rag-empty {
    border: 1px dashed var(--rag-border); border-radius: 12px;
    padding: 2rem 1.5rem; text-align: center; color: var(--rag-muted);
    background: var(--rag-surface);
}
.rag-empty-title { font-weight: 600; color: #374151; margin-bottom: 0.3rem; }

/* File-explorer tiles. st.container(key=...) emits an st-key-<key> class, so
   these rules attach to specific containers instead of Streamlit internals. */
[class*="st-key-tile_"] {
    border: 1px solid transparent; border-radius: 12px;
    padding: 0.9rem 0.4rem 0.5rem 0.4rem; text-align: center;
    transition: background 120ms ease, border-color 120ms ease;
}
[class*="st-key-tile_"]:hover {
    background: var(--rag-surface); border-color: var(--rag-border);
}
[class*="st-key-tile_"] .stButton button { justify-content: center; }
/* The tile's label button carries the name: no chrome, just text */
[class*="st-key-tile_"] .stButton button p { font-weight: 550; font-size: 0.88rem; }

.rag-tile-icon { font-size: 2.5rem; line-height: 1.1; }
.rag-tile-meta { color: var(--rag-muted); font-size: 0.73rem; min-height: 1rem; }

/* Project picker, pinned to the left of the chat input in st.bottom */
.st-key-chat_project_select { margin-bottom: 0; }
.st-key-chat_project_select div[data-baseweb="select"] > div { border-radius: 10px; }

/* Breadcrumb above an opened project */
.rag-crumb { font-size: 0.92rem; color: var(--rag-muted); padding-top: 0.35rem; }
.rag-crumb strong { color: #1f2430; font-weight: 620; }
</style>
"""


def bootstrap_page() -> None:
    """Inject the shared CSS. Called once per rerun from the entry script."""
    st.markdown(_CSS, unsafe_allow_html=True)


def sidebar_brand() -> None:
    st.sidebar.markdown(
        """
        <div class="rag-brand">
            <div class="rag-brand-mark">◆</div>
            <div class="rag-brand-text">
                <div class="rag-brand-title">Document RAG</div>
                <div class="rag-brand-sub">Ask your own documents</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_nav(pages: List["st.Page"]) -> None:
    """Render the page links ourselves, so they sit below the brand header."""
    with st.sidebar.container(key="sidebar_nav"):
        for page in pages:
            st.page_link(page, use_container_width=True)


def page_heading(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="rag-page-title">{title}</div>'
        f'<div class="rag-page-sub">{subtitle}</div>',
        unsafe_allow_html=True,
    )


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f'<div class="rag-empty"><div class="rag-empty-title">{title}</div>{body}</div>',
        unsafe_allow_html=True,
    )


def render_sources(sources: List[str]) -> None:
    if not sources:
        return
    chips = "".join(f'<span class="rag-chip">📄 {source}</span>' for source in sources)
    st.markdown(
        f'<div class="rag-chips"><span class="rag-chip-label">Sources</span>{chips}</div>',
        unsafe_allow_html=True,
    )


def index_pill(indexed: bool, chunks: int) -> str:
    if indexed:
        unit = "chunk" if chunks == 1 else "chunks"
        return f'<span class="rag-pill rag-pill-ok">Indexed · {chunks} {unit}</span>'
    return '<span class="rag-pill rag-pill-wait">Not ingested</span>'


def backend_online() -> bool:
    """Whether the backend answers /health. Pages report failures inline."""
    return api_client.is_online()


def project_names(projects: List[dict]) -> List[str]:
    return [project["name"] for project in projects]


def remembered_project(names: List[str]) -> Optional[str]:
    """The project selected on either page, or None if none was chosen yet.

    Returning None matters on the Chat page: with nothing remembered the picker
    falls back to general chat rather than silently grounding in some project.
    """
    current = st.session_state.get(ACTIVE_PROJECT_KEY)
    return current if current in names else None


def remember_project(name: Optional[str]) -> None:
    """Remember the chosen project, or forget it when general chat is chosen."""
    if name:
        st.session_state[ACTIVE_PROJECT_KEY] = name
    else:
        st.session_state.pop(ACTIVE_PROJECT_KEY, None)
