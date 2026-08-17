"""Projects page, laid out like a file explorer.

The top level is a grid of project folders. Opening one replaces the grid with
that project's documents, reached through a breadcrumb, so only one level of
content is ever on screen.
"""

import streamlit as st

import api_client
import ui

OPEN_KEY = "open_project"
TILES_PER_ROW = 4


def _open_project(name: str) -> None:
    st.session_state[OPEN_KEY] = name
    ui.remember_project(name)


def _close_project() -> None:
    st.session_state[OPEN_KEY] = None


def _uploader_key() -> str:
    """A changing key clears the file_uploader after a successful upload."""
    return f"uploader_{st.session_state.get('uploader_round', 0)}"


def _reset_uploader() -> None:
    st.session_state["uploader_round"] = st.session_state.get("uploader_round", 0) + 1


def _human_size(size_bytes: int) -> str:
    mb = size_bytes / (1024 * 1024)
    return f"{mb:.1f} MB" if mb >= 0.1 else f"{max(size_bytes // 1024, 1)} KB"


def _rows(items: list, per_row: int = TILES_PER_ROW):
    """Yield (column, item, index) triples, a fixed number of columns per row."""
    for start in range(0, len(items), per_row):
        columns = st.columns(per_row, gap="small")
        for offset, (column, item) in enumerate(
            zip(columns, items[start : start + per_row])
        ):
            yield column, item, start + offset


def _new_project_tile(column) -> None:
    with column.container(key="tile_new", border=False):
        st.markdown('<div class="rag-tile-icon">➕</div>', unsafe_allow_html=True)
        with st.popover("New project", use_container_width=True):
            with st.form("create_project", clear_on_submit=True, border=False):
                name = st.text_input("Project name", placeholder="e.g. Network Policies")
                if st.form_submit_button("Create", use_container_width=True):
                    try:
                        created = api_client.create_project(name)
                        _open_project(created["project"])
                        st.rerun()
                    except api_client.ApiError as error:
                        st.error(str(error))
        st.markdown('<div class="rag-tile-meta">&nbsp;</div>', unsafe_allow_html=True)


def _folder_tile(column, project: dict, position: int) -> None:
    with column.container(key=f"tile_folder_{position}", border=False):
        st.markdown('<div class="rag-tile-icon">📁</div>', unsafe_allow_html=True)
        if st.button(
            project["name"],
            key=f"open_{position}",
            type="tertiary",
            use_container_width=True,
        ):
            _open_project(project["name"])
            st.rerun()
        documents = project["document_count"]
        label = "item" if documents == 1 else "items"
        st.markdown(
            f'<div class="rag-tile-meta">{documents} {label} · '
            f'{project["chunk_count"]} chunks</div>',
            unsafe_allow_html=True,
        )


def _document_tile(column, project: str, document: dict, position: int) -> None:
    filename = document["filename"]
    with column.container(key=f"tile_doc_{position}", border=False):
        st.markdown('<div class="rag-tile-icon">📄</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="rag-doc-name">{filename}</div>'
            f'<div class="rag-tile-meta">{_human_size(document["size_bytes"])}<br>'
            f'{ui.index_pill(document["indexed"], document["chunks"])}</div>',
            unsafe_allow_html=True,
        )
        with st.popover("⋯", use_container_width=True):
            st.caption(filename)
            if st.button(
                "Ingest",
                key=f"ingest_{position}",
                use_container_width=True,
                disabled=document["indexed"],
            ):
                try:
                    with st.spinner(f"Indexing {filename}..."):
                        result = api_client.ingest(project, filename)
                    st.toast(f"Indexed {result['chunks_indexed']} chunks from {filename}")
                    st.rerun()
                except api_client.ApiError as error:
                    st.error(str(error))
            if st.button(
                "Delete",
                key=f"delete_{position}",
                use_container_width=True,
                type="primary",
            ):
                try:
                    api_client.delete_document(project, filename)
                    st.toast(f"Deleted {filename}")
                    st.rerun()
                except api_client.ApiError as error:
                    st.error(str(error))


ui.page_heading("Projects", "Each project is a separate knowledge base.")

if not ui.backend_online():
    st.error(f"The backend is not reachable at {api_client.API_URL}. Start it, then reload.")
    st.stop()

try:
    projects = api_client.list_projects()
except api_client.ApiError as error:
    st.error(str(error))
    st.stop()

names = ui.project_names(projects)
opened = st.session_state.get(OPEN_KEY)
if opened not in names:
    # The open project was deleted, or this is a fresh session.
    opened = None
    st.session_state[OPEN_KEY] = None

if opened is None:
    tiles = [None] + projects  # None is the "new project" tile
    for column, item, position in _rows(tiles):
        if item is None:
            _new_project_tile(column)
        else:
            _folder_tile(column, item, position)

    if not projects:
        st.caption("No projects yet. Create one to get started.")
    st.stop()

# --- inside a project ---------------------------------------------------------
try:
    documents = api_client.list_documents(opened)["documents"]
except api_client.ApiError as error:
    st.error(str(error))
    st.stop()

back, crumb, menu = st.columns([1.5, 5, 1], vertical_alignment="center")
if back.button("← All projects", type="tertiary"):
    _close_project()
    st.rerun()
crumb.markdown(
    f'<div class="rag-crumb">Projects / <strong>{opened}</strong></div>',
    unsafe_allow_html=True,
)
with menu.popover("⋯", use_container_width=True):
    st.caption(
        f"Deleting **{opened}** removes its folder, every PDF inside it and all "
        "indexed chunks."
    )
    if st.button("Delete project", type="primary", use_container_width=True):
        try:
            api_client.delete_project(opened)
            st.session_state.get("histories", {}).pop(opened, None)
            _close_project()
            st.rerun()
        except api_client.ApiError as error:
            st.error(str(error))

pending = [document for document in documents if not document["indexed"]]
add, ingest_all, _spacer = st.columns([1.5, 1.8, 4], vertical_alignment="center")

with add.popover("＋ Add PDFs", use_container_width=True):
    uploaded = st.file_uploader(
        "Select PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key=_uploader_key(),
    )
    if st.button("Upload", use_container_width=True, disabled=not uploaded):
        try:
            with st.spinner("Uploading..."):
                result = api_client.upload_documents(
                    opened,
                    [(item.name, item.getvalue()) for item in uploaded],
                )
            st.toast(f"Uploaded {len(result['files_uploaded'])} file(s)")
            if result.get("files_rejected"):
                st.warning(f"Skipped: {', '.join(result['files_rejected'])}")
            _reset_uploader()
            st.rerun()
        except api_client.ApiError as error:
            st.error(str(error))

if ingest_all.button(
    f"Ingest pending ({len(pending)})",
    use_container_width=True,
    disabled=not pending,
    type="primary",
):
    try:
        with st.spinner("Indexing documents..."):
            result = api_client.ingest(opened)
        st.toast(f"Indexed {result['chunks_indexed']} new chunks")
        st.rerun()
    except api_client.ApiError as error:
        st.error(str(error))

if not documents:
    ui.empty_state("This project is empty", "Use ＋ Add PDFs to upload documents.")
else:
    for column, document, position in _rows(documents):
        _document_tile(column, opened, document, position)
