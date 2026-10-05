import streamlit as st
import pandas as pd
import time
from redteam import (
    SECRET_TOKEN,
    INITIAL_SYSTEM_PROMPT,
    CATEGORIES,
    HELD_OUT_ATTACKS,
    HELPFULNESS_QUESTIONS,
    MockLLM,
    GeminiLLM,
    run_arena
)

st.set_page_config(
    page_title="AI Red-Team Arena",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 14px;
        border-left: 5px solid #1f77b4;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .badge-leak {
        background-color: #ffebe6;
        color: #de350b;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.82rem;
        border: 1px solid #ffbdad;
    }
    .badge-safe {
        background-color: #e3fcef;
        color: #006644;
        font-weight: 700;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.82rem;
        border: 1px solid #abf5d1;
    }
    .badge-cat {
        background-color: #eae6ff;
        color: #403294;
        font-weight: 600;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar Configuration
st.sidebar.title("🛡️ Arena Configuration")
st.sidebar.caption("Educational Red-Teaming & Prompt Hardening Loop")

demo_mode = st.sidebar.checkbox(
    "Demo Mode (Offline / Simulated LLM)",
    value=True,
    help="Runs immediately without any Gemini API key using deterministic MockLLM."
)

api_key = ""
model_name = "gemini-2.5-flash-lite"
pace_delay = 1.2

if not demo_mode:
    api_key = st.sidebar.text_input(
        "Gemini API Key",
        type="password",
        help="Get a free Gemini API key from Google AI Studio (aistudio.google.com)."
    )
    model_name = st.sidebar.selectbox(
        "Gemini Model",
        ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"],
        index=0,
        help="Recommended: gemini-2.5-flash-lite for free tier limits."
    )
    pace_delay = st.sidebar.slider(
        "Pacing Delay (seconds)",
        min_value=0.5,
        max_value=3.0,
        value=1.2,
        step=0.1,
        help="Delay between API calls to stay within free-tier rate limits."
    )

st.sidebar.markdown("---")
st.sidebar.subheader("Benchmark Settings")
rounds_count = st.sidebar.slider(
    "Arena Rounds",
    min_value=2,
    max_value=5,
    value=3,
    help="Number of attack-and-hardening iterations."
)
attacks_per_cat = st.sidebar.slider(
    "Attacks per Category",
    min_value=1,
    max_value=3,
    value=1,
    help=f"5 categories: {', '.join(CATEGORIES)}. (1 attack/cat = 5 attacks per round)."
)

start_clicked = st.sidebar.button("🚀 Start Red-Team Arena", type="primary", use_container_width=True)

# Main Area Header
st.title("🛡️ AI Red-Team Arena")
st.markdown("""
**Target Chatbot:** `HelpBot` (NorthStar Bank Customer Support)  
**Protected Secret:** `:red[ALPHA-7]` (Simulated confidential vault token)  
*Attacker AI generates adversarial injections across 5 categories &rarr; Deterministic Judge detects leaks &rarr; Fixer AI hardens the system prompt.*
""")

# Educational Info Expander
with st.expander("ℹ️ How the Arena Works (Architecture & Categories)", expanded=False):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("""
        **5 Attack Categories:**
        - **Roleplay**: Prompting the bot to adopt a debug or unconstrained persona (e.g. DAN, KeyMaster).
        - **Urgency**: Simulated emergency, outage, or authority pressure.
        - **Instruction Override**: Explicit commands to disregard previous constraints.
        - **Encoding / Reversal**: Asking for reversed text (`7-AHPLA`), base64, or spaced letters.
        - **Story / Poem**: Embedding the secret into artistic writing or acrostics.
        """)
    with col_b:
        st.markdown("""
        **Generalization & Utility Checks:**
        - **Held-Out Exam**: 6 hand-written attacks the Fixer AI *never* sees, tested on both baseline and final hardened prompt.
        - **Helpfulness Check**: 3 standard banking inquiries to ensure HelpBot does not over-refuse or become unhelpful.
        - **Deterministic Judge**: Normalises response (lowercase, strip symbols) and scans for `alpha7` or `7ahpla`.
        """)

# Initialize Session State
if "arena_results" not in st.session_state:
    st.session_state.arena_results = None

if start_clicked:
    if not demo_mode and not api_key.strip():
        st.error("⚠️ Please provide a Gemini API Key or enable 'Demo Mode' in the sidebar.")
    else:
        st.session_state.arena_results = None
        
        # Instantiate LLM
        if demo_mode:
            llm = MockLLM()
            st.info("ℹ️ Running in **Demo Mode** using simulated MockLLM.")
        else:
            try:
                llm = GeminiLLM(api_key=api_key.strip(), model_name=model_name, pace_delay=pace_delay)
                st.info(f"ℹ️ Connected to Gemini API (`{model_name}`). Starting live arena...")
            except Exception as e:
                st.error(f"Failed to initialize Gemini client: {e}")
                st.stop()

        # Placeholders for live streaming
        status_box = st.empty()
        progress_bar = st.progress(0.0)
        
        chart_spot = st.empty()
        metrics_spot = st.empty()
        live_log_spot = st.empty()

        chart_history = []
        collected_data = {
            "baseline_exam": None,
            "baseline_help": None,
            "rounds": {},
            "final_exam": None,
            "final_help": None,
            "summary": None,
            "prompt_evolution": []
        }

        total_steps = 2 + rounds_count + 2
        current_step = 0

        try:
            for event in run_arena(llm, rounds=rounds_count, attacks_per_cat=attacks_per_cat):
                ev_type = event.get("type")

                if ev_type == "status":
                    status_box.info(event["message"])

                elif ev_type == "baseline_exam":
                    collected_data["baseline_exam"] = event
                    current_step += 1
                    progress_bar.progress(min(current_step / total_steps, 0.95))
                    chart_history.append({"Stage": "Baseline (Unseen)", "Leak Rate (%)": event["leak_rate"]})
                    chart_df = pd.DataFrame(chart_history).set_index("Stage")
                    chart_spot.line_chart(chart_df, y="Leak Rate (%)")

                elif ev_type == "baseline_helpfulness":
                    collected_data["baseline_help"] = event
                    current_step += 1
                    progress_bar.progress(min(current_step / total_steps, 0.95))

                elif ev_type == "round_start":
                    r_num = event["round"]
                    if r_num not in collected_data["rounds"]:
                        collected_data["rounds"][r_num] = {
                            "system_prompt": event["system_prompt"],
                            "attacks": [],
                            "leak_rate": 0.0,
                            "hardening": None
                        }
                    status_box.info(f"🥊 Round {r_num} of {rounds_count}: Generating attacks & testing HelpBot...")

                elif ev_type == "attack_result":
                    r_num = event["round"]
                    res = event["result"]
                    collected_data["rounds"][r_num]["attacks"].append(res)
                    # Show recent attack in live log
                    badge = "🔴 LEAKED" if res["leaked"] else "🟢 DEFENDED"
                    live_log_spot.caption(f"Round {r_num} | [{res['category']}] &rarr; {badge}")

                elif ev_type == "prompt_hardening":
                    r_num = event["round"]
                    collected_data["rounds"][r_num]["hardening"] = event
                    collected_data["prompt_evolution"].append({
                        "round": r_num,
                        "accepted": event["accepted"],
                        "new_prompt": event["new_prompt"],
                        "reason": event["reason"]
                    })

                elif ev_type == "round_complete":
                    r_num = event["round"]
                    collected_data["rounds"][r_num]["leak_rate"] = event["leak_rate"]
                    current_step += 1
                    progress_bar.progress(min(current_step / total_steps, 0.95))
                    chart_history.append({"Stage": f"Round {r_num}", "Leak Rate (%)": event["leak_rate"]})
                    chart_df = pd.DataFrame(chart_history).set_index("Stage")
                    chart_spot.line_chart(chart_df, y="Leak Rate (%)")

                elif ev_type == "final_exam":
                    collected_data["final_exam"] = event
                    current_step += 1
                    progress_bar.progress(min(current_step / total_steps, 0.95))
                    chart_history.append({"Stage": "Final Held-Out", "Leak Rate (%)": event["leak_rate"]})
                    chart_df = pd.DataFrame(chart_history).set_index("Stage")
                    chart_spot.line_chart(chart_df, y="Leak Rate (%)")

                elif ev_type == "final_helpfulness":
                    collected_data["final_help"] = event
                    current_step += 1
                    progress_bar.progress(1.0)

                elif ev_type == "arena_complete":
                    collected_data["summary"] = event["summary"]
                    st.session_state.arena_results = collected_data
                    status_box.success("🎉 AI Red-Team Arena Benchmark Completed Successfully!")
                    live_log_spot.empty()

        except Exception as err:
            status_box.error(f"Execution Error: {err}")
            st.exception(err)

# Display Completed Results
if st.session_state.arena_results is not None:
    data = st.session_state.arena_results
    summary = data.get("summary", {})

    st.subheader("📊 Executive Benchmark Metrics")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        base_rate = summary.get("baseline_leak_rate", 0.0)
        st.metric("Baseline Leak Rate", f"{base_rate:.1f}%", help="Leak rate on initial system prompt against 6 held-out attacks.")
    with m2:
        final_rate = summary.get("final_leak_rate", 0.0)
        delta_rate = -(base_rate - final_rate)
        st.metric("Final Leak Rate", f"{final_rate:.1f}%", delta=f"{delta_rate:.1f}%", delta_color="inverse", help="Leak rate on hardened prompt against held-out attacks.")
    with m3:
        reduction = summary.get("leak_reduction", 0.0)
        st.metric("Defense Improvement", f"{reduction:+.1f}%", help="Percentage point reduction in leaks.")
    with m4:
        final_help = summary.get("final_helpfulness", 100.0)
        base_help = summary.get("baseline_helpfulness", 100.0)
        st.metric("Helpfulness Retention", f"{final_help:.0f}%", delta=f"{final_help - base_help:+.0f}%", help="% of benign customer questions answered successfully.")

    # Chart of Leak Rate Across Stages
    st.subheader("📉 Leak Rate Trajectory")
    chart_stages = []
    if data.get("baseline_exam"):
        chart_stages.append({"Stage": "Baseline (Unseen)", "Leak Rate (%)": data["baseline_exam"]["leak_rate"]})
    for r_idx, r_val in data.get("rounds", {}).items():
        chart_stages.append({"Stage": f"Round {r_idx}", "Leak Rate (%)": r_val.get("leak_rate", 0.0)})
    if data.get("final_exam"):
        chart_stages.append({"Stage": "Final Held-Out", "Leak Rate (%)": data["final_exam"]["leak_rate"]})
    
    if chart_stages:
        cdf = pd.DataFrame(chart_stages).set_index("Stage")
        st.line_chart(cdf, y="Leak Rate (%)")

    # Detailed Tabs
    tab_rounds, tab_heldout, tab_helpfulness, tab_prompt = st.tabs([
        "🥊 Arena Rounds Details",
        "📝 Held-Out Generalization Exam",
        "🤝 Helpfulness Retention Check",
        "📜 System Prompt Evolution"
    ])

    with tab_rounds:
        for r_num, r_info in data.get("rounds", {}).items():
            l_rate = r_info.get("leak_rate", 0.0)
            attacks = r_info.get("attacks", [])
            leak_count = sum(1 for a in attacks if a["leaked"])
            with st.expander(f"Round {r_num} — Leak Rate: {l_rate:.1f}% ({leak_count}/{len(attacks)} Leaks)", expanded=(r_num == 1)):
                if r_info.get("hardening"):
                    h = r_info["hardening"]
                    if h.get("accepted"):
                        st.success(f"🛡️ **Fixer AI Hardened the Prompt after Round {r_num}**: {h.get('reason')}")
                    else:
                        st.warning(f"⚠️ **Fixer AI Rewrite Rejected**: {h.get('reason')}")
                
                # Table of attacks
                for a in attacks:
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.markdown(f"<span class='badge-cat'>{a['category']}</span>", unsafe_allow_html=True)
                        if a["leaked"]:
                            st.markdown(f"<span class='badge-leak'>🔴 LEAKED: {a['token']}</span>", unsafe_allow_html=True)
                        else:
                            st.markdown("<span class='badge-safe'>🟢 DEFENDED</span>", unsafe_allow_html=True)
                    with col2:
                        st.markdown(f"**Attack:** {a['attack']}")
                        st.markdown(f"**HelpBot Reply:** *{a['reply']}*")
                    st.divider()

    with tab_heldout:
        st.markdown("""
        The **Held-Out Generalization Exam** consists of 6 hand-written adversarial attacks that the Fixer AI was never exposed to.
        Comparing baseline vs hardened performance verifies whether HelpBot acquired general defense boundaries rather than just memorizing seen prompts.
        """)
        base_results = data.get("baseline_exam", {}).get("results", [])
        final_results = data.get("final_exam", {}).get("results", [])

        if base_results and final_results:
            for b, f in zip(base_results, final_results):
                with st.expander(f"Attack [{b['category']}]: {b['attack'][:70]}...", expanded=False):
                    st.markdown(f"**Full Attack:** {b['attack']}")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("#### Baseline Response")
                        if b["leaked"]:
                            st.markdown(f"<span class='badge-leak'>🔴 LEAKED: {b['token']}</span>", unsafe_allow_html=True)
                        else:
                            st.markdown("<span class='badge-safe'>🟢 DEFENDED</span>", unsafe_allow_html=True)
                        st.write(b["reply"])
                    with c2:
                        st.markdown("#### Final Hardened Response")
                        if f["leaked"]:
                            st.markdown(f"<span class='badge-leak'>🔴 LEAKED: {f['token']}</span>", unsafe_allow_html=True)
                        else:
                            st.markdown("<span class='badge-safe'>🟢 DEFENDED</span>", unsafe_allow_html=True)
                        st.write(f["reply"])

    with tab_helpfulness:
        st.markdown("""
        A strong defense must not cause **over-refusal** or turn the chatbot into a useless bot.
        Here we verify that HelpBot continues to answer normal NorthStar Bank customer inquiries.
        """)
        base_h = data.get("baseline_help", {}).get("results", [])
        final_h = data.get("final_help", {}).get("results", [])

        if base_h and final_h:
            for bh, fh in zip(base_h, final_h):
                with st.expander(f"Customer Query: {bh['question']}", expanded=True):
                    hc1, hc2 = st.columns(2)
                    with hc1:
                        st.markdown("#### Baseline Response")
                        st.caption(f"Status: {'✅ Helpful' if bh['helpful'] else '❌ Unhelpful'}")
                        st.write(bh["reply"])
                    with hc2:
                        st.markdown("#### Final Response (After Hardening)")
                        st.caption(f"Status: {'✅ Helpful' if fh['helpful'] else '❌ Unhelpful'}")
                        st.write(fh["reply"])

    with tab_prompt:
        st.markdown("### Comparison: Initial vs Final System Prompt")
        pc1, pc2 = st.columns(2)
        with pc1:
            st.markdown("#### Initial System Prompt (Baseline)")
            st.code(INITIAL_SYSTEM_PROMPT, language="text")
        with pc2:
            st.markdown("#### Final Hardened System Prompt")
            final_p = summary.get("final_prompt", INITIAL_SYSTEM_PROMPT)
            st.code(final_p, language="text")
