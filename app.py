import streamlit as st
import pandas as pd
from io import BytesIO
import pickle

st.set_page_config(
    layout="wide",
    page_title="Systematic Literature Review Assistant",
    # menu_items={"Get help": "https://google.com"},
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


# st.title("Systematic Literature Review Assistant")
st.markdown(
    """
<div style='background-color:#f5f7fb;padding:18px;border-radius:8px;text-align: justify; font-size: 20px;'>
<h1 style="color:#0b3d91">Systematic Literature Review Assistant</h1>
<p style='color:#0b3d91;font-size:20px'>
<b>Streamline your paper screening process.</b>
<br>
This tool is designed to help researchers manually filter Scopus search results. 
Upload your raw CSV, review papers one by one, and export a clean dataset for your study.
</p>
</div>
<br>
""",
    unsafe_allow_html=True,
)

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
        col1.button(
            "✅ Keep (Next)",
            on_click=click,
            use_container_width=True,
        )
        col2.button(
            "❌ Remove by title",
            on_click=remove_title,
            use_container_width=True,
        )
        col3.button(
            "❌ Remove by abstract", on_click=remove_abstract, use_container_width=True
        )
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
                f'<p style="font-size:20px;">{df.loc[current_index, "Authors"]}</p>',
                unsafe_allow_html=True,
            )
            st.subheader("DOI")
            st.markdown(
                f'<a href="https://doi.org/{df.loc[current_index, "DOI"]}>[DOI]</a> \\
                    <a href="https://doi.org/{df.loc[current_index, "Link"]}>[Scopus Link]</a>'
            )
            st.subheader("Keywards")
            st.markdown(
                f'<p style="font-size:18px;">{df.loc[current_index, "Author Keywords"]}</p>',
                unsafe_allow_html=True,
            )
            st.subheader("Abstract")
            st.markdown(
                f'<p style="font-size:18px;">{df.loc[current_index, "Abstract"]}</p>',
                unsafe_allow_html=True,
            )

    else:
        st.success("🎉 Screening Complete!")

        # st.text(f"Total numbers of papers: {len(df)}")
        # st.text(f"removed paper by title: {len(st.session_state.r_title)}")
        # st.text(f"removed paper by abstract: {len(st.session_state.r_abstract)}")
        df_clean = df.copy()
        to_drop = st.session_state.r_title + st.session_state.r_abstract
        df_clean = df_clean.drop(index=to_drop)

        # df_clean = df_clean.drop(index=st.session_state.r_abstract)
        df_r_title = df.loc[st.session_state.r_title].reset_index(drop=True)
        df_r_abstract = df.loc[st.session_state.r_abstract].reset_index(drop=True)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Papers", len(df))
        c2.metric("Included", len(df_clean))
        c3.metric("Excluded", len(to_drop))
        c4.metric("Excluded (Title)", len(df_r_title))
        c5.metric("Excluded (Abstract)", len(df_r_abstract))
        # excel_file = "cleaned_data.xlsx"
        st.divider()

        # EID Generation
        if not df_clean.empty:
            eids = df_clean["EID"].astype(str).values
            outputs = f"EID({' OR '.join(eids)})"
            st.subheader("Scopus Advanced Search Query")
            st.caption(
                "Copy this string to Scopus to download full metadata/PDFs for your selected papers."
            )
            st.code(outputs, language="text", wrap_lines=True)
        st.divider()
        # Excel Export
        meterics = {
            "Total Papers": len(df),
            "Included": len(df_clean),
            "Excluded": len(to_drop),
            "Excluded (Title)": len(df_r_title),
            "Excluded (Abstract)": len(df_r_abstract),
        }
        df_meterics = pd.DataFrame(meterics, index=[0]).T.reset_index(names="Meterics")
        df_meterics.columns = ["Meterics", ""]
        excel_buffer = BytesIO()
        pd.io.formats.excel.ExcelFormatter.header_style = None
        with pd.ExcelWriter(excel_buffer) as writer:
            df_meterics.to_excel(writer, sheet_name="Meterics", index=False)
            df_clean.to_excel(writer, sheet_name="Included", index=False)
            df_r_title.to_excel(writer, sheet_name="Excluded (Title)", index=False)
            df_r_title.to_excel(writer, sheet_name="Excluded (Abstract)", index=False)
            df.to_excel(writer, sheet_name="Original Raw", index=False)
        excel_buffer.seek(0)

        st.subheader("Export Results")
        st.caption(
            "Generates an Excel file with separate sheets for included and excluded papers."
        )
        st.download_button(
            label="Download Final Excel Report",
            data=excel_buffer.getvalue(),
            file_name="slr_results_final.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
