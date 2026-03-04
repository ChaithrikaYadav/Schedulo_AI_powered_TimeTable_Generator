import streamlit as st
from timetable_generator import build_timetable

st.set_page_config(page_title="AI Timetable Generator", layout="wide")

st.title("📅 AI-Based Timetable Generator")
st.markdown("Generate and view smart timetables instantly for your department.")

department = st.selectbox("Select Department", ["School of Computer Science & Engineering", "School of Management", "IILM Law School", "School of Hospitality & Services Management"])

st.write("---")

if st.button("Generate Timetable"):
    with st.spinner("⏳ Generating structured timetable..."):
        try:
            # Cache results for speed
            @st.cache_data
            def get_timetable(dept):
                return build_timetable(dept)

            timetable = get_timetable(department)
            st.success("✅ Timetable successfully generated!")

            for sec, df in timetable.items():
                st.subheader(f"🧩 Section: {sec}")
                st.dataframe(df.style.set_properties(**{
                    'text-align': 'center',
                    'border': '1px solid #ddd'
                }), use_container_width=True)

        except Exception as e:
            st.error(f"❌ Error: {e}")


