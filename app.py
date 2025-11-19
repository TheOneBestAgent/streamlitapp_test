import streamlit as st
import edge_tts
import asyncio
import re
import tempfile
import os
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION & DICTIONARIES ---

# 1. SPECIFIC OVERRIDES (Highest Priority)
# These are for names that break standard rules or are extremely common
SPECIFIC_NAME_FIXES = {
    "Tokyo": "Toh-kyoh", 
    "Kyoto": "Key-oh-toh",
    "Ryu": "Ree-yoo",
    "Sean": "Shawn", 
    "Sake": "Sah-keh",
    "Kobe": "Koh-bay",
}

# 2. SUFFIX & PATTERN RULES (The "Infinite" Coverage)
# Instead of listing names, we list patterns. 
# E.g., the rule "yama\b" -> "yah-mah" covers: 
# Kageyama, Sugiyama, Yokoyama, Tateyama, etc.
PATTERN_RULES = [
    # --- Consonant + Y + Vowel Patterns (The most common errors in TTS) ---
    # Handles Ryu, Kyu, Nyu, Hyu -> Ree-yoo, Key-yoo, etc.
    (r"\b([BCDFGHJKLMNPQRSTVWXYZ])yu\b", r"\1ee-yoo"), 
    (r"\b([BCDFGHJKLMNPQRSTVWXYZ])yu([a-z]+)", r"\1ee-yoo-\2"), # Mid-word (Ryunosuke)
    
    # Handles Kyo, Ryo, Hyo -> Key-oh, Ree-oh, Hee-oh
    (r"\b([BCDFGHJKLMNPQRSTVWXYZ])yo\b", r"\1ee-oh"),
    (r"\b([BCDFGHJKLMNPQRSTVWXYZ])yo([a-z]+)", r"\1ee-oh-\2"), # Mid-word (Kyosuke)

    # --- Common Name Suffixes ---
    # Names ending in -yama (Mountain) -> yah-mah
    (r"([a-z]+)yama\b", r"\1-yah-mah"),
    # Names ending in -gawa / -kawa (River) -> gah-wah
    (r"([a-z]+)gawa\b", r"\1-gah-wah"),
    (r"([a-z]+)kawa\b", r"\1-kah-wah"),
    # Names ending in -shima / -jima (Island) -> shee-mah
    (r"([a-z]+)shima\b", r"\1-shee-mah"),
    (r"([a-z]+)jima\b", r"\1-jee-mah"),
    # Names ending in -mura (Village) -> moo-rah
    (r"([a-z]+)mura\b", r"\1-moo-rah"),
    # Names ending in -saki / -zaki (Cape) -> sah-key
    (r"([a-z]+)zaki\b", r"\1-zah-key"),
    (r"([a-z]+)saki\b", r"\1-sah-key"),
    # Names ending in -watanabe is unique enough to hardcode pattern
    (r"watanabe\b", "wah-tah-nah-beh"),
    
    # --- Vowel Clarity Rules (General Japanese Sound) ---
    # Ensure 'i' at end of word sounds like 'ee' (e.g. Satoshi -> Satoshee)
    # We use strict constraints here to avoid breaking English words like "Corgi" or "Hi"
    # This regex looks for Japanese-like structures (Consonant-Vowel-Consonant-i)
    (r"\b([BCDFGHJKLMNPQRSTVWXYZ][aeiou][BCDFGHJKLMNPQRSTVWXYZ])i\b", r"\1ee"),
]

# Mock IPA Dictionary (In a full app, you might load a JSON/CSV file here)
IPA_FIXES = {
    "epitome": "eh-pit-oh-me",
    "hyperbole": "high-per-bow-lee",
    "colonel": "ker-nel",
    "worcestershire": "wuss-ter-sher",
    "anesthetist": "ah-nes-the-tist",
    "draught": "draft"
}

# --- TEXT PROCESSING FUNCTIONS ---

@st.cache_data
def load_remote_names(url):
    """
    Fetches a raw text/CSV file of names from a URL.
    Format expected: One name per line, or "Name,Phonetic" per line.
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Simple parser: assumes "Name,Phonetic" or just "Name"
            custom_dict = {}
            lines = response.text.split('\n')
            for line in lines:
                parts = line.split(',')
                if len(parts) == 2:
                    custom_dict[parts[0].strip()] = parts[1].strip()
            return custom_dict
        return {}
    except:
        return {}

def process_text(text, use_aggressive_patterns=True, custom_dict=None):
    """
    Applies phonetic replacements and Japanese Romaji heuristics.
    """
    processed_text = text

    # 0. Apply User/Remote Dictionary (If loaded)
    if custom_dict:
        for word, phonetic in custom_dict.items():
             processed_text = re.sub(rf"\b{word}\b", phonetic, processed_text, flags=re.IGNORECASE)

    # 1. Apply Specific Fixes
    for word, phonetic in SPECIFIC_NAME_FIXES.items():
        processed_text = re.sub(rf"\b{word}\b", phonetic, processed_text, flags=re.IGNORECASE)

    # 2. Apply Pattern Rules (The "Infinite" coverage)
    if use_aggressive_patterns:
        for pattern, replacement in PATTERN_RULES:
            processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)

    # 3. Apply IPA/Dictionary Fixes
    for word, phonetic in IPA_FIXES.items():
        processed_text = re.sub(rf"\b{word}\b", phonetic, processed_text, flags=re.IGNORECASE)
    
    return processed_text

# --- ASYNC TTS GENERATION ---

async def generate_audio_stream(text, voice, rate_str):
    """
    Generates audio using edge-tts and returns the file path.
    """
    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, "tts_output.mp3")
    communicate = edge_tts.Communicate(text, voice, rate=rate_str)
    await communicate.save(output_path)
    return output_path

# --- STREAMLIT UI ---

def main():
    st.set_page_config(page_title="OmniRead TTS", page_icon="🎧", layout="wide")

    st.title("🎧 OmniRead: Edge-TTS Reader")
    
    # Sidebar
    st.sidebar.header("Settings")
    
    # Voice Settings
    voice_options = {
        "English (US) - Guy": "en-US-GuyNeural",
        "English (US) - Jenny": "en-US-JennyNeural",
        "English (UK) - Sonia": "en-GB-SoniaNeural",
        "Japanese - Nanami": "ja-JP-NanamiNeural", 
    }
    selected_voice = voice_options[st.sidebar.selectbox("Voice", list(voice_options.keys()))]
    
    speed = st.sidebar.slider("Speed", 0.5, 2.0, 1.0, 0.1)
    rate_str = f"{int((speed - 1.0) * 100):+d}%"

    # --- ADVANCED DICTIONARY SETTINGS ---
    with st.sidebar.expander("📚 Dictionary & Patterns", expanded=False):
        use_patterns = st.checkbox("Use Smart Pattern Matching", value=True, help="Automatically fixes words ending in -yama, -gawa, -saki, etc.")
        
        # External Dictionary Loader
        st.markdown("### Load Custom Dictionary")
        st.markdown("URL to a raw CSV file (Format: `Name,Phonetic`)")
        dict_url = st.text_input("Dictionary URL", placeholder="https://example.com/names.csv")
        
        custom_dict = {}
        if dict_url:
            with st.spinner("Fetching dictionary..."):
                custom_dict = load_remote_names(dict_url)
                if custom_dict:
                    st.success(f"Loaded {len(custom_dict)} custom names!")
                else:
                    st.error("Could not load dictionary.")

    # Main Input
    input_method = st.radio("Input Method", ["Paste Text", "Upload File"], horizontal=True)
    raw_text = ""
    
    if input_method == "Paste Text":
        raw_text = st.text_area("Enter Text", height=300)
    else:
        uploaded = st.file_uploader("Upload .txt or .md", type=["txt", "md"])
        if uploaded: raw_text = uploaded.getvalue().decode("utf-8")

    # Generation
    if st.button("Generate Audio", type="primary"):
        if raw_text:
            with st.spinner("Processing..."):
                # Process
                final_text = process_text(raw_text, use_aggressive_patterns=use_patterns, custom_dict=custom_dict)
                
                # Debug View
                with st.expander("Debug: Phonetic Changes"):
                    st.text(f"Original: {raw_text[:100]}...")
                    st.text(f"Modified: {final_text[:100]}...")

                # Audio
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    audio_path = loop.run_until_complete(generate_audio_stream(final_text, selected_voice, rate_str))
                    st.audio(audio_path)
                    
                    with open(audio_path, "rb") as f:
                        st.download_button("Download MP3", f, "audio.mp3")
                except Exception as e:
                    st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
