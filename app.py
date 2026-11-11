import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO
import pickle
from datetime import datetime
import re
import plotly.express as px
from utils import (
    highlight_text,
    find_doi_duplicates,
    find_title_duplicates,
    normalize_doi,
    normalize_title,
)

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


def back():
    if st.session_state.counter > 0:
        st.session_state.counter -= 1
        prev_idx = st.session_state.counter

        # remove from exclusion lists if previsolyy removed
        if prev_idx in st.session_state.r_title:
            st.session_state.r_title.remove(prev_idx)
        if prev_idx in st.session_state.r_abstract:
            st.session_state.r_abstract.remove(prev_idx)
        if "included" in st.session_state and prev_idx in st.session_state.included:
            st.session_state.included.remove(prev_idx)


#################################################################
def _build_dup_summary_msg(doi_dropped, title_dropped):
    total_dropped = doi_dropped + title_dropped
    if total_dropped > 0:
        details = []
        if doi_dropped > 0:
            details.append(f"{doi_dropped} by DOI")
        if title_dropped > 0:
            details.append(f"{title_dropped} by title")
        breakdown = f" ({', '.join(details)})"
        return f"Duplicate review complete. Removed {total_dropped} paper(s) in total{breakdown}."
    return "Duplicate review complete. No duplicate papers removed."


@st.dialog("⚠️ Duplicate DOIs Detected", width="large", dismissible=False)
def doi_duplicate_dialog():
    dup_indices = st.session_state.doi_duplicates
    st.write(
        f"Found **{len(dup_indices)} paper(s)** with identical DOIs to existing records."
    )
    st.caption(
        "Would you like to automatically remove these duplicate records (keeping the first occurrence)?"
    )

    with st.expander(
        f"📄 View Duplicate Papers ({len(dup_indices)} duplicate(s))", expanded=False
    ):
        df = st.session_state.df
        dup_set = set(dup_indices)
        norm_dois = df["DOI"].apply(normalize_doi)
        dup_doi_values = set(norm_dois.loc[dup_indices].dropna())
        matched_mask = norm_dois.isin(dup_doi_values)

        preview_df = df.loc[matched_mask].copy()
        preview_df["Row"] = preview_df.index + 1
        preview_df["Status"] = [
            "🗑️ Remove (Duplicate)" if idx in dup_set else "✅ Keep (First)"
            for idx in preview_df.index
        ]
        preview_df["_norm_doi"] = norm_dois.loc[matched_mask]
        preview_df = preview_df.sort_values(by=["_norm_doi", "Row"])

        cols_to_show = [
            c
            for c in ["Row", "Status", "Title", "Authors", "Year", "DOI"]
            if c in preview_df.columns
        ]
        st.dataframe(
            preview_df[cols_to_show], use_container_width=True, hide_index=True
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.button(
            "🗑️ Remove Duplicate DOIs", use_container_width=True, type="primary"
        ):
            st.session_state.df = st.session_state.df.drop(
                index=dup_indices
            ).reset_index(drop=True)
            st.session_state.doi_removed = len(dup_indices)
            st.session_state.doi_duplicates = []
            st.session_state.show_doi_dialog = False
            # Check if there are title duplicates next
            with st.spinner("Checking remaining papers for duplicate titles...", show_time=True):
                title_pairs = find_title_duplicates(st.session_state.df)
            if title_pairs:
                st.session_state.title_dup_pairs = title_pairs
                st.session_state.current_pair_idx = 0
                st.session_state.indices_to_drop = set()
                st.session_state.show_title_dialog = True
            else:
                st.session_state.dup_checked = True
                st.session_state.dup_status_msg = _build_dup_summary_msg(
                    st.session_state.doi_removed, 0
                )
            st.rerun()

    with col2:
        if st.button("Keep All / Skip", use_container_width=True, type="secondary"):
            st.session_state.doi_removed = 0
            st.session_state.doi_duplicates = []
            st.session_state.show_doi_dialog = False
            with st.spinner("Checking remaining papers for duplicate titles...", show_time=True):
                title_pairs = find_title_duplicates(st.session_state.df)
            if title_pairs:
                st.session_state.title_dup_pairs = title_pairs
                st.session_state.current_pair_idx = 0
                st.session_state.indices_to_drop = set()
                st.session_state.show_title_dialog = True
            else:
                st.session_state.dup_checked = True
                st.session_state.dup_status_msg = (
                    "DOI duplicates skipped. No suspected duplicate titles found."
                )
            st.rerun()


@st.dialog("🔍 Suspected Duplicate Papers by Title", width="large", dismissible=False)
def title_duplicate_dialog():
    pairs = st.session_state.title_dup_pairs
    current_idx = st.session_state.current_pair_idx
    total_pairs = len(pairs)
    df = st.session_state.df

    # Advance past any pairs whose studies no longer exist or are already marked for deletion
    while current_idx < total_pairs:
        pair = pairs[current_idx]
        if (
            pair["idx_a"] not in df.index
            or pair["idx_b"] not in df.index
            or pair["idx_a"] in st.session_state.indices_to_drop
            or pair["idx_b"] in st.session_state.indices_to_drop
        ):
            current_idx += 1
        else:
            break
    st.session_state.current_pair_idx = current_idx

    if current_idx >= total_pairs:
        # All pairs reviewed: apply deletions
        title_dropped = len(st.session_state.indices_to_drop)
        if title_dropped:
            st.session_state.df = st.session_state.df.drop(
                index=list(st.session_state.indices_to_drop)
            ).reset_index(drop=True)
        st.session_state.title_removed = title_dropped
        doi_dropped = st.session_state.get("doi_removed", 0)
        st.session_state.dup_status_msg = _build_dup_summary_msg(
            doi_dropped, title_dropped
        )
        st.session_state.indices_to_drop = set()
        st.session_state.show_title_dialog = False
        st.session_state.dup_checked = True
        st.rerun()
        return

    pair = pairs[current_idx]
    idx_a, idx_b, score = pair["idx_a"], pair["idx_b"], pair["score"]

    st.write(
        f"**Pair {current_idx + 1} of {total_pairs}** — Similarity Match: `{score}%`"
    )
    st.info(
        "Compare the two studies below and choose which one to delete, or keep both."
    )

    row_a = df.loc[idx_a]
    row_b = df.loc[idx_b]

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(f"### Study A (Row {idx_a + 1})")
        st.markdown(f"**Title:** {row_a.get('Title', 'N/A')}")
        st.markdown(f"**Authors:** {row_a.get('Authors', 'N/A')}")
        st.markdown(f"**Year:** {row_a.get('Year', 'N/A')}")
        doi_a = row_a.get("DOI", "")
        if pd.notna(doi_a) and str(doi_a).strip():
            st.caption(f"DOI: {doi_a}")
        if st.button(
            "🗑️ Delete Study A",
            key=f"del_a_{current_idx}",
            use_container_width=True,
            type="primary",
        ):
            st.session_state.indices_to_drop.add(idx_a)
            st.session_state.current_pair_idx += 1
            st.rerun()

    with col_b:
        st.markdown(f"### Study B (Row {idx_b + 1})")
        st.markdown(f"**Title:** {row_b.get('Title', 'N/A')}")
        st.markdown(f"**Authors:** {row_b.get('Authors', 'N/A')}")
        st.markdown(f"**Year:** {row_b.get('Year', 'N/A')}")
        doi_b = row_b.get("DOI", "")
        if pd.notna(doi_b) and str(doi_b).strip():
            st.caption(f"DOI: {doi_b}")
        if st.button(
            "🗑️ Delete Study B",
            key=f"del_b_{current_idx}",
            use_container_width=True,
            type="primary",
        ):
            st.session_state.indices_to_drop.add(idx_b)
            st.session_state.current_pair_idx += 1
            st.rerun()

    st.divider()
    c_keep, c_skip = st.columns([1, 1])
    with c_keep:
        if st.button("⏭️ Keep Both (Not Duplicate)", use_container_width=True):
            st.session_state.current_pair_idx += 1
            st.rerun()
    with c_skip:
        if st.button("⏩ Finish & Skip Remaining", use_container_width=True):
            title_dropped = len(st.session_state.indices_to_drop)
            if title_dropped:
                st.session_state.df = st.session_state.df.drop(
                    index=list(st.session_state.indices_to_drop)
                ).reset_index(drop=True)
            st.session_state.title_removed = title_dropped
            doi_dropped = st.session_state.get("doi_removed", 0)
            st.session_state.dup_status_msg = _build_dup_summary_msg(
                doi_dropped, title_dropped
            )
            st.session_state.indices_to_drop = set()
            st.session_state.show_title_dialog = False
            st.session_state.dup_checked = True
            st.rerun()


#################################################################


# st.title("Systematic Literature Review Assistant")
st.markdown(
    """
<div style='background-color:#f5f7fb;padding:18px;border-radius:8px;text-align: justify; font-size: 20px;'>
<h1 style="color:#0b3d91">Systematic Literature Review Assistant</h1>
<p style='color:#0b3d91;font-size:20px'>
<b>Streamline your paper screening process.</b>
<br>
This tool is designed to help researchers manually filter Scopus search results. 
Upload your raw CSV from scopus database, review papers one by one, and export a clean dataset for your study.
<ul style='color:#0b3d91;font-size:20px'>
 <li>Minimum columns required: Authors, Title,Year, Authors keywords, Abstract, DOI, link, EID </li>
 <li>Session could be saved from sidebar</li>
</ul>
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
            with st.spinner("Loading CSV and checking for duplicate papers...", show_time=True):
                raw_df = pd.read_csv(uploaded_file)
                st.session_state.df = raw_df
                st.session_state.counter = 0  # Reset counter if new file
                st.session_state.r_title = []
                st.session_state.r_abstract = []
                st.session_state.last_uploaded_file = filename
                st.session_state.dup_checked = False
                st.session_state.saved_highlight_terms = ""
                st.session_state.saved_highlightx_terms = ""
                st.session_state.raw_total = len(raw_df)
                st.session_state.doi_removed = 0
                st.session_state.title_removed = 0

                # Check DOI duplicates
                doi_dups = find_doi_duplicates(raw_df)
                if doi_dups:
                    st.session_state.doi_duplicates = doi_dups
                    st.session_state.show_doi_dialog = True
                    st.session_state.show_title_dialog = False
                else:
                    st.session_state.doi_duplicates = []
                    st.session_state.show_doi_dialog = False
                    # Check Title duplicates
                    title_pairs = find_title_duplicates(raw_df)
                    if title_pairs:
                        st.session_state.title_dup_pairs = title_pairs
                        st.session_state.current_pair_idx = 0
                        st.session_state.indices_to_drop = set()
                        st.session_state.show_title_dialog = True
                    else:
                        st.session_state.dup_checked = True
                        st.session_state.dup_status_msg = (
                            "No duplicate papers found (checked by DOI and Title)."
                        )
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
                st.session_state.saved_highlight_terms = data.get("highlight_terms", "")
                st.session_state.saved_highlightx_terms = data.get("highlightx_terms", "")
                st.session_state.raw_total = data.get("raw_total", len(data["df"]))
                st.session_state.doi_removed = data.get("doi_removed", 0)
                st.session_state.title_removed = data.get("title_removed", 0)
                st.session_state.last_uploaded_file = filename
                st.session_state.dup_checked = True
                st.success("Session restored successfully!", icon="🔄")
            except Exception as e:
                st.error(f"Error loading session file: {e}")

    if st.session_state.get("show_doi_dialog", False):
        doi_duplicate_dialog()
    elif st.session_state.get("show_title_dialog", False):
        title_duplicate_dialog()

    if not st.session_state.get("dup_checked", True):
        st.info(
            "⏳ Please complete the duplicate review in the dialog above before screening."
        )
        if st.button("🔍 Reopen Duplicate Review", type="primary"):
            st.rerun()
        st.stop()

    if st.session_state.get("dup_status_msg"):
        st.info(st.session_state.dup_status_msg, icon="✨")
        st.toast(st.session_state.dup_status_msg, icon="✨")
        st.session_state.dup_status_msg = None
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
                "highlight_terms": st.session_state.get(
                    "highlight_terms",
                    st.session_state.get("saved_highlight_terms", ""),
                ),
                "highlightx_terms": st.session_state.get(
                    "highlightx_terms",
                    st.session_state.get("saved_highlightx_terms", ""),
                ),
                "raw_total": st.session_state.get("raw_total", len(df)),
                "doi_removed": st.session_state.get("doi_removed", 0),
                "title_removed": st.session_state.get("title_removed", 0),
            }
            buffer = BytesIO()
            pickle.dump(session_data, buffer)
            now = datetime.now().strftime("%Y-%m-%d_%H%M")
            buffer.seek(0)
            st.download_button(
                label="💾 Save Progress for Later",
                data=buffer,
                file_name=f"session_{now}.pkl",
                mime="application/octet-stream",
                help="Download a file you can upload later to continue exactly where you left off.",
            )
            st.html("<div style='height: 75px;'></div>")
            kofi_html = "<script type='text/javascript' src='https://storage.ko-fi.com/cdn/widget/Widget_2.js'></script><script type='text/javascript'>kofiwidget2.init('Support me on Ko-fi', '#72a4f2', 'O1E628CFB4');kofiwidget2.draw();</script>"
            st.iframe(kofi_html)
    else:
        st.stop()

    # # It is better to cache this read, but for now this works:
    # df = pd.read_csv(uploaded_file)
    # st.success("File uploaded successfully", icon="✅")

    # Use the session_state counter
    # current_index = st.session_state.counter

    # --- Safety Check: Ensure we haven't gone past the end of the file ---
    if current_index < len(df):
        col1, col2, col3, col4 = st.columns([1, 1, 1, 0.5])
        # --- FIX 3: Pass function without parentheses ---
        col1.button(
            "Include (Next)",
            icon="✅",
            on_click=click,
            use_container_width=True,
            key="include_key",
            type="primary",
        )
        col2.button(
            "Remove by title",
            icon="❌",
            on_click=remove_title,
            use_container_width=True,
            type="secondary",
        )
        col3.button(
            "Remove by abstract",
            icon="❌",
            on_click=remove_abstract,
            use_container_width=True,
            type="secondary",
        )
        col4.button(
            "Back",
            on_click=back,
            use_container_width=True,
            type="secondary",
            disabled=(current_index == 0),
        )
        # st.divider()
        cols = st.columns(4)
        cols[0].text(f"Current Progress: {current_index}/{len(df)}")
        cols[1].text(
            f"Included: {st.session_state.counter - len(st.session_state.r_title) - len(st.session_state.r_abstract)}"
        )
        cols[2].text(f"Removed by Title: {len(st.session_state.r_title)}")
        cols[3].text(f"Removed by Abstract: {len(st.session_state.r_abstract)}")
        st.progress(current_index / len(df))
        with st.container():
            st.subheader("Title:")
            st.markdown(
                f'<p style="font-size:24px;">{df.loc[current_index, "Title"]}</p>',
                unsafe_allow_html=True,
            )
            col1, col2, col3 = st.columns(3)
            col1.subheader("Authors:")
            col1.markdown(
                f'<p style="font-size:20px;">{df.loc[current_index, "Authors"]}</p>',
                unsafe_allow_html=True,
            )
            col2.subheader("Year")
            # col2.text(df.loc[current_index, 'Year'])
            col2.markdown(
                f'<p style="font-size:20px;">{df.loc[current_index, "Year"]}</p>',
                unsafe_allow_html=True,
            )
            col3.subheader("DOI")
            doi = df.loc[current_index, "DOI"]
            link = df.loc[current_index, "Link"]
            if pd.isna(doi):
                link_text = f'''
                <a>[DOI Unavailable]</a>   
                <a href="{link}">[Scopus Link]</a>
                '''
            else:
                link_text = f'''
                <a href="https://doi.org/{doi}">[DOI]</a>   
                <a href="{link}">[Scopus Link]</a>
                '''
            # if doi is not np.nan:
            #     link_text = f'''
            #     <a href="https://doi.org/{doi}">[DOI]</a>
            #     <a href="{link}">[Scopus Link]</a>
            #     '''
            # else:
            #     link_text = f'''
            #     <a>[DOI Unavailable]</a>
            #     <a href="{link}">[Scopus Link]</a>
            #     '''
            col3.markdown(link_text, unsafe_allow_html=True)
            st.subheader("Keywords")
            st.markdown(
                f'<p style="font-size:18px;">{df.loc[current_index, "Author Keywords"]}</p>',
                unsafe_allow_html=True,
            )
            st.subheader("Abstract")
            col_1, col_2 = st.columns(2)
            if "highlight_terms" not in st.session_state:
                st.session_state.highlight_terms = st.session_state.get(
                    "saved_highlight_terms", ""
                )
            if "highlightx_terms" not in st.session_state:
                st.session_state.highlightx_terms = st.session_state.get(
                    "saved_highlightx_terms", ""
                )
            highlight_terms = col_1.text_input(
                "Highlight words (Green):", key="highlight_terms"
            )
            highlightx_terms = col_2.text_input(
                "Highlight words (Red):", key="highlightx_terms"
            )
            st.session_state.saved_highlight_terms = highlight_terms
            st.session_state.saved_highlightx_terms = highlightx_terms
            abstract = df.loc[current_index, "Abstract"]
            highlight_abstract = highlight_text(
                abstract, highlight_terms, highlightx_terms
            )
            # st.markdown(
            #     f'<p style="font-size:18px;text-align: justify;">{df.loc[current_index, "Abstract"]}</p>',
            #     unsafe_allow_html=True,
            # )
            st.markdown(
                f'<p style="font-size:18px;text-align: justify;">{highlight_abstract}</p>',
                unsafe_allow_html=True,
            )

    else:
        st.success("🎉 Screening Complete!")

        st.button("Back to Last Paper", on_click=back, type="secondary")

        # st.text(f"Total numbers of papers: {len(df)}")
        # st.text(f"removed paper by title: {len(st.session_state.r_title)}")
        # st.text(f"removed paper by abstract: {len(st.session_state.r_abstract)}")
        df_clean = df.copy()
        to_drop = st.session_state.r_title + st.session_state.r_abstract
        df_clean = df_clean.drop(index=to_drop)

        # df_clean = df_clean.drop(index=st.session_state.r_abstract)
        df_r_title = df.loc[st.session_state.r_title].reset_index(drop=True)
        df_r_abstract = df.loc[st.session_state.r_abstract].reset_index(drop=True)

        raw_total = st.session_state.get("raw_total", len(df))
        doi_removed = st.session_state.get("doi_removed", 0)
        title_removed = st.session_state.get("title_removed", 0)
        dup_removed_total = doi_removed + title_removed

        d1, d2, d3 = st.columns(3)
        d1.metric("Raw Papers Uploaded", raw_total)
        d2.metric("Duplicates Removed (DOI)", doi_removed)
        d3.metric("Duplicates Removed (Title)", title_removed)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Papers", len(df))
        c2.metric("Included", len(df_clean))
        c3.metric("Excluded", len(to_drop))
        c4.metric("Excluded (Title)", len(df_r_title))
        c5.metric("Excluded (Abstract)", len(df_r_abstract))

        pie_data = pd.DataFrame(
            {
                "type": ["Included", "Excluded (Title)", "Excluded (Abstract)"],
                "Count": [len(df_clean), len(df_r_title), len(df_r_abstract)],
            }
        )
        fig = px.pie(
            pie_data,
            "type",
            "Count",
            color="type",
            hole=0.4,
            color_discrete_map={
                "Included": "forestgreen",
                "Excluded (Title)": "red",
                "Excluded (Abstract)": "pink",
            },
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        # fig.update_layout(margin=dict(t=0, l=0, r=0, b=0))

        st.plotly_chart(
            fig,
            width="content",
        )

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
            "Raw Papers Uploaded": raw_total,
            "Duplicates Removed (Total)": dup_removed_total,
            "Duplicates Removed (DOI)": doi_removed,
            "Duplicates Removed (Title)": title_removed,
            "Screened Papers (After Dedup)": len(df),
            "Included": len(df_clean),
            "Excluded (Screening Total)": len(to_drop),
            "Excluded (Title)": len(df_r_title),
            "Excluded (Abstract)": len(df_r_abstract),
        }
        df_meterics = pd.DataFrame(meterics, index=[0]).T.reset_index(names="Meterics")
        df_meterics.columns = ["Meterics", ""]
        excel_buffer = BytesIO()
        # pd.io.formats.excel.ExcelFormatter.header_style = None # remove formatting of excel file
        with pd.ExcelWriter(excel_buffer) as writer:
            df_meterics.to_excel(writer, sheet_name="Meterics", index=False)
            df_clean.to_excel(writer, sheet_name="Included", index=False)
            df_r_title.to_excel(writer, sheet_name="Excluded (Title)", index=False)
            df_r_abstract.to_excel(
                writer, sheet_name="Excluded (Abstract)", index=False
            )
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
