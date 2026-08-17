import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="RAG Chatbot", page_icon="📚")
st.title("Document RAG Chatbot")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

uploaded_files = st.sidebar.file_uploader(
    "Upload PDF documents",
    type=["pdf"],
    accept_multiple_files=True,
)

if st.sidebar.button("Ingest PDF docs"):
    if not uploaded_files:
        st.sidebar.warning("Please select at least one PDF file before ingesting.")
    else:
        try:
            upload_payload = []
            for uploaded_file in uploaded_files:
                upload_payload.append(
                    ("files", (uploaded_file.name, uploaded_file.getvalue(), "application/pdf"))
                )

            response = requests.post(
                f"{API_URL}/ingest-files",
                files=upload_payload,
                timeout=180,
            )
            status = response.json()
            if response.ok and status.get("status") == "success":
                st.sidebar.success(
                    f"{status.get('files_uploaded', [])} uploaded and indexed successfully"
                )
            else:
                st.sidebar.error(status.get("message", "Upload failed."))
        except Exception as exc:
            st.sidebar.error(f"Ingestion failed: {exc}")

question = st.chat_input("Ask a question about your documents...")
if question:
    with st.chat_message("user"):
        st.markdown(question)
    st.session_state.messages.append({"role": "user", "content": question})

    try:
        with st.spinner("Searching documentation..."):
            response = requests.post(f"{API_URL}/query", json={"question": question}, timeout=120)
        payload = response.json()
        answer = payload.get("answer", "No answer found.")
        sources = payload.get("sources", [])

        with st.chat_message("assistant"):
            st.markdown(answer)
            # Do not show sources when the assistant returned a clear fallback/not-found message
            fallback_texts = [
                "Information not found in the provided documents.",
                "I don't have enough information in the provided documents to answer this question.",
            ]
            if sources and answer.strip() not in fallback_texts:
                # Show a single bold 'Source:' label followed by deduplicated filenames
                st.markdown("**Source:** " + ", ".join(sources))

        st.session_state.messages.append({"role": "assistant", "content": answer})
    except Exception as exc:
        error_msg = f"Unable to reach the backend service: {exc}"
        with st.chat_message("assistant"):
            st.markdown(error_msg)
        st.session_state.messages.append({"role": "assistant", "content": error_msg})
