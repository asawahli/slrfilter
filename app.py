import streamlit as st
import pandas as pd
from io import BytesIO
import pickle

st.set_page_config(
    layout="wide",
    page_title="temp",
    menu_items={"Get help": "https://google.com"},
)

# # --- Initialize Session State ---
# if "counter" not in st.session_state:
#     st.session_state.counter = 0
# if "r_title" not in st.session_state:
#     st.session_state.r_title = []
# if "r_abstract" not in st.session_state:
#     st.session_state.r_abstract = []
# if "df" not in st.session_state:
#     st.session_state.df = None


# --- Callback Functions ---
def click():
    st.session_state.counter += 1


def remove_title():
    st.session_state.r_title.append(st.session_state.counter)
    st.session_state.counter += 1


def remove_abstract():
    st.session_state.r_abstract.append(st.session_state.counter)
    st.session_state.counter += 1


st.title("Read scopus filter")

uploaded_file = st.file_uploader(
    "Upload Scopus CSV or Saved Session (.pkl)", type=["csv", "pkl"]
)

if uploaded_file is not None:
    # Reset session state when new file uploaded
    if (
        "last_uploaded_file" not in st.session_state
        or st.session_state.last_uploaded_file != uploaded_file.name
    ):
        filename = uploaded_file.name
        if filename.endswith(".csv"):
            st.session_state.clear()
            st.session_state.df = pd.read_csv(uploaded_file)
            st.session_state.counter = 0  # Reset counter if new file
            st.session_state.r_title = []
            st.session_state.r_abstract = []
            st.session_state.last_uploaded_file = filename
            st.success("New CSV loaded successfully!", icon="✅")
        elif filename.endswith(".pkl"):
            # restore session
            try:
                data = pickle.load(uploaded_file)
                st.session_state.clear()
                st.session_state.df = data["df"]
                st.session_state.counter = data["counter"]
                st.session_state.r_title = data["r_title"]
                st.session_state.r_abstract = data["r_abstract"]
                st.session_state.last_uploaded_file = filename
                st.success("Session restored successfully!", icon="🔄")
            except Exception as e:
                st.error(f"Error loading session file: {e}")
    # else:
    #     if "last_uploaded_file" in st.session_state:
    #         del st.session_state["last_uploaded_file"]
    if "df" in st.session_state and st.session_state.df is not None:
        df = st.session_state.df
        current_index = st.session_state.counter

        with st.sidebar:
            st.header("Save Session")
            st.write(f"**Progress:** {current_index}/{len(df)}")
            session_data = {
                "df": df,
                "counter": current_index,
                "r_title": st.session_state.r_title,
                "r_abstract": st.session_state.r_abstract,
            }
            buffer = BytesIO()
            pickle.dump(session_data, buffer)
            buffer.seek(0)
            st.download_button(
                label="💾 Save Progress for Later",
                data=buffer,
                file_name="scopus_session.pkl",
                mime="application/octet-stream",
                help="Download a file you can upload later to continue exactly where you left off.",
            )

    # # It is better to cache this read, but for now this works:
    # df = pd.read_csv(uploaded_file)
    # st.success("File uploaded successfully", icon="✅")

    # Use the session_state counter
    # current_index = st.session_state.counter

    # --- Safety Check: Ensure we haven't gone past the end of the file ---
    if current_index < len(df):
        col1, col2, col3 = st.columns([1, 1, 1])
        # --- FIX 3: Pass function without parentheses ---
        col1.button("Keep", on_click=click, width="stretch")
        col2.button("Remove by title", on_click=remove_title, width="stretch")
        col3.button("Remove by abstract", on_click=remove_abstract, width="stretch")
        # st.divider()
        st.text(f"Current Progress: {current_index}/{len(df)}")
        with st.container():
            st.subheader("Title:")
            st.markdown(
                f'<p style="font-size:24px;">{df.loc[current_index, "Title"]}</p>',
                unsafe_allow_html=True,
            )
            st.subheader("Authors:")
            st.markdown(
                f'<p style="font-size:24px;">{df.loc[current_index, "Authors"]}</p>',
                unsafe_allow_html=True,
            )
            st.subheader("Abstract")
            st.markdown(
                f'<p style="font-size:18px;">{df.loc[current_index, "Abstract"]}</p>',
                unsafe_allow_html=True,
            )

    else:
        st.warning("End of file reached.")
        st.text(f"Total numbers of papers: {len(df)}")
        st.text(f"removed paper by title: {len(st.session_state.r_title)}")
        st.text(f"removed paper by abstract: {len(st.session_state.r_abstract)}")
        df_clean = df.copy()
        df_clean = df_clean.drop(index=st.session_state.r_title)
        df_clean = df_clean.drop(index=st.session_state.r_abstract)
        df_r_title = df.loc[st.session_state.r_title].reset_index(drop=True)
        df_r_abstract = df.loc[st.session_state.r_abstract].reset_index(drop=True)

        # excel_file = "cleaned_data.xlsx"
        excel_buffer = BytesIO()

        with pd.ExcelWriter(excel_buffer) as writer:
            df_clean.to_excel(writer, sheet_name="Cleaned Data", index=False)
            df_r_title.to_excel(writer, sheet_name="removed by title", index=False)
            df_r_title.to_excel(writer, sheet_name="removed by abstract", index=False)
            df.to_excel(writer, sheet_name="Original Data", index=False)
        excel_buffer.seek(0)
        st.download_button(
            "Download as Excel file",
            excel_buffer.getvalue(),
            file_name="cleaned scopus.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.subheader("Cleaned Data")
        st.dataframe(df_clean)
