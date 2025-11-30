import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import firestore
import pandas as pd
from datetime import datetime
import PyPDF2

# --- 1. CONFIGURATION & STATE MANAGEMENT ---
st.set_page_config(
    page_title="TalentScout AI",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inisialisasi Session State (Memori Aplikasi)
if 'jd_input' not in st.session_state:
    st.session_state['jd_input'] = ""
if 'analysis_result' not in st.session_state:
    st.session_state['analysis_result'] = ""
if 'current_view_id' not in st.session_state:
    st.session_state['current_view_id'] = None # None artinya sedang mode "New Chat"

# CSS agar tombol sidebar terlihat seperti List Item (Full Width & Flat)
st.markdown("""
    <style>
    section[data-testid="stSidebar"] .stButton button {
        width: 100%;
        text-align: left;
        border: none;
        background: transparent;
        color: #4a4a4a;
        padding: 10px;
        transition: 0.3s;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        background: #f0f2f6;
        color: #000;
        font-weight: bold;
    }
    /* Highlight tombol New Chat */
    div[data-testid="stSidebarUserContent"] .stButton button:first-child {
        background-color: #f0f2f6;
        border: 1px solid #ddd;
        border-radius: 20px;
        text-align: center;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

PROJECT_ID = "gcp-bnb-marathon-2025"
REGION = "us-central1"

try:
    vertexai.init(project=PROJECT_ID, location=REGION)
    db = firestore.Client(project=PROJECT_ID)
except Exception as e:
    st.error(f"Connection Error: {e}")

# --- 2. FUNCTIONS ---

def reset_app():
    """Fungsi untuk membersihkan layar (New Chat)"""
    st.session_state['jd_input'] = ""
    st.session_state['analysis_result'] = ""
    st.session_state['current_view_id'] = None

def load_history(doc_data, doc_id):
    """Fungsi saat history diklik"""
    st.session_state['jd_input'] = doc_data.get('job_snippet_full', '') # Load JD lama
    st.session_state['analysis_result'] = doc_data.get('analysis', '')   # Load Hasil lama
    st.session_state['current_view_id'] = doc_id

# --- 3. SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("TalentScout AI")
    st.caption("Powered by Gemini 2.0 Flash")
    
    st.divider()
    st.markdown("### ⚙️ Database Admin")
    
    # --- TAMBAHAN BARU: FITUR SEED DATA ---
    if st.button("🔄 Reset & Seed Database", help="Isi database dengan 5 kandidat contoh"):
        try:
            # 1. Hapus Data Lama
            docs = db.collection("candidates").stream()
            for doc in docs: doc.reference.delete()
            
            # 2. Masukkan 5 Kandidat Contoh
            dummies = [
                {"name": "Budi Santoso", "role": "Backend Dev", "skills": "Python, Django, FastAPI, AWS, Docker, Kubernetes."},
                {"name": "Siti Aminah", "role": "Java Dev", "skills": "Java, Spring Boot, Oracle, Banking Systems."},
                {"name": "Rudi Pratama", "role": "Designer", "skills": "Photoshop, Illustrator, Figma, UI/UX."},
                {"name": "Andi Wijaya", "role": "Fullstack JS", "skills": "React, Node.js, MongoDB, Express, AWS."},
                {"name": "Citra Lestari", "role": "Data Analyst", "skills": "Python, SQL, Tableau, PowerBI, Excel."}
            ]
            for d in dummies: db.collection("candidates").add(d)
            st.success(f"✅ {len(dummies)} Kandidat berhasil dimuat!")
            st.rerun()
        except Exception as e:
            st.error(f"Error seeding: {e}")
    # --------------------------------------

    # Tombol Besar "New Analysis"
    if st.button("➕ New Analysis", use_container_width=True):
        reset_app()
        st.rerun() # Refresh halaman

    st.subheader("🕒 History")
    
    # Ambil data dari Firestore
    try:
        # Kita ambil snippet pendek untuk judul tombol
        docs = db.collection("analyzed_jobs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).stream()
        
        for doc in docs:
            data = doc.to_dict()
            doc_id = doc.id
            
            # Buat Judul Pendek (Misal: "Senior Python Devel...")
            full_text = data.get('job_snippet', 'Untitled Job')
            short_title = (full_text[:25] + '..') if len(full_text) > 25 else full_text
            
            # Tampilkan sebagai Tombol
            # Jika tombol ini diklik, jalankan fungsi load_history
            if st.button(f"📄 {short_title}", key=doc_id):
                load_history(data, doc_id)
                st.rerun()
                
    except Exception as e:
        st.caption("No History")

# --- 4. MAIN CONTENT ---

# 1. Buat Kolom dulu
col_input, col_output = st.columns([1, 1.2], gap="large")

# === KOLOM KIRI: INPUT ===
with col_input:
    st.subheader("📥 Job Description")

    # Text Area
    jd_text = st.text_area(
        "Input Job Description:",
        value=st.session_state['jd_input'],
        height=350,
        placeholder="Paste Job Description Here...",
        key="input_area"
    )

    # --- PERBAIKAN DI SINI ---
    # Kita simpan tombol ke dalam variabel bernama 'analyze_btn'
    # Agar bisa dipanggil di logika utama nanti
    analyze_btn = st.button("✨ Analyze Now", type="primary", use_container_width=True)


# === LOGIKA UTAMA (Hanya jalan jika tombol diklik) ===
if analyze_btn and jd_text:
    st.session_state['jd_input'] = jd_text # Simpan input
    
    # Tampilkan loading di area output
    with col_output:
        with st.status("🚀 Gemini 2.0 Flash sedang bekerja...", expanded=True) as status:
            try:
                model = GenerativeModel("gemini-2.0-flash-exp")

                # 1. Analisis JD
                st.write("1️⃣ Menganalisis Kualitas JD...")
                prompt_analyze = f"""
                    Act as a Senior Technical Recruiter & Hiring Manager at a top-tier tech company.
                    Your goal is to extract actionable insights from the provided Job Description (JD) to help interviewers prepare.

                    INPUT JD:
                    ---
                    {jd_text}
                    ---

                    CRITICAL INSTRUCTION:
                    1. **Detect the language** of the Job Description text above.
                    2. **Provide the ENTIRE analysis in that SAME LANGUAGE.**
                    (e.g., If Job Description is Indonesian, Output must be Indonesian. If English, Output English).

                    Perform a deep analysis and output the result in the following STRICT MARKDOWN format:

                    ### 🎯 Critical Skill Breakdown
                    * **Hard Skills:** [Skill 1], [Skill 2], [Skill 3]
                    * **Soft Skills:** [Skill A], [Skill B]

                    ### ⚖️ Job Description Quality Score
                    * **Score:** [X]/10
                    * **Verdict:** [Give a 1-sentence brutally honest critique. E.g., "Too vague about specific tools" or "Excellent and detailed"]

                    ### 🗣️ Interview Guide (Smart Questions)
                    
                    **1. Behavioral Question (STAR Method):**
                    [Question asking for a specific situation related to the role]
                    * *💡 Look for:* [What is a 'Green Flag' in the candidate's answer?]

                    **2. Behavioral Question (STAR Method):**
                    [Question]
                    * *💡 Look for:* [Key indicator]

                    **3. Technical/Case Study Question:**
                    [A specific technical scenario or problem based on the Hard Skills]
                    
                    **4. Technical Question:**
                    [Question]

                    **5. Culture Fit Question:**
                    [Question related to working style described in Job Description]
                    """
                response = model.generate_content(prompt_analyze)
                st.session_state['analysis_result'] = response.text
                
                # --- STEP 2: RANKING KANDIDAT ---
                st.write("2️⃣ Mencocokkan dengan Database (Gemini 2.0)...")
                
                # Import Regex untuk 'memotong' JSON dari teks sampah
                import re 

                candidates_ref = db.collection("candidates").stream()
                candidates = [doc.to_dict() for doc in candidates_ref]
                
                rank_results = []
                prog_bar = st.progress(0)
                
                if not candidates:
                    st.error("Database Kosong! Klik tombol Reset di Sidebar.")
                else:
                    for i, cand in enumerate(candidates):
                        prog_bar.progress((i + 1) / len(candidates))
                        
                        skill_text = cand.get('skills') or cand.get('resume_text') or "-"
                        
                        # Prompt kita buat lebih galak (STRICT)
                        prompt_match = f"""
                        You are an HR Manager. Compare JD vs Candidate.
                        
                        JD: {jd_text[:300]}...
                        CANDIDATE: {cand.get('name')} - {skill_text}
                        
                        Task: Output valid JSON only. No markdown, no introduction.
                        Format: {{"score": 85, "reason": "Reason here"}}
                        """
                        try:
                            res_match = model.generate_content(prompt_match)
                            raw_text = res_match.text
                            
                            # --- PERBAIKAN UTAMA (REGEX) ---
                            # Mencari pola apapun yang diapit kurung kurawal { ... }
                            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                            
                            if match:
                                clean_json = match.group()
                                data = json.loads(clean_json)
                                
                                rank_results.append({
                                    "Nama": cand.get('name'),
                                    "Role": cand.get('role'),
                                    "Match Score": data.get('score', 0),
                                    "Alasan AI": data.get('reason', '-')
                                })
                            else:
                                raise ValueError("Format JSON tidak ditemukan di output AI")

                        except Exception as e:
                            # Tampilkan error aslinya supaya kita tau kenapa
                            rank_results.append({
                                "Nama": cand.get('name'),
                                "Role": cand.get('role'),
                                "Match Score": 0,
                                "Alasan AI": f"Error: {str(e)}" 
                            })
                    
                    # Simpan hasil ranking
                    if rank_results:
                        df_rank = pd.DataFrame(rank_results).sort_values(by="Match Score", ascending=False)
                        st.session_state['ranking_data'] = df_rank
                
                status.update(label="✅ Selesai! Menampilkan hasil...", state="complete", expanded=False)
                
                # --- KUNCI UTAMA: REFRESH OTOMATIS ---
                st.rerun()
                
            except Exception as e:
                st.error(f"Error: {e}")

# === KOLOM KANAN (OUTPUT DISPLAY) ===
with col_output:
    st.subheader("📊 Hasil & Rekomendasi")
    
    # Cek apakah ada data di memori
    if st.session_state.get('analysis_result'):
        
        # 1. AI ANALYSIS
        st.markdown("#### 📝 Analisis JD (AI)")
        with st.container(border=True, height=400):
            st.markdown(st.session_state['analysis_result'])

        st.divider()

        # 2. TOP CANDIDATES
        st.markdown("#### 🏆 Top Candidates")
        
        ranking_data = st.session_state.get('ranking_data')
        
        if ranking_data is not None and not ranking_data.empty:
            # Highlight Juara 1
            top = ranking_data.iloc[0]
            if top['Match Score'] > 75:
                st.success(f"🌟 **Rekomendasi Utama:** {top['Nama']} ({top['Match Score']}/100)")
            
            # Tabel
            st.dataframe(
                ranking_data,
                column_config={
                    "Match Score": st.column_config.ProgressColumn(
                        "Score", format="%d", min_value=0, max_value=100
                    )
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("Belum ada kandidat di database.")

    elif not analyze_btn:
        st.info("👈 Masukkan JD & Klik Analyze untuk memulai.")
