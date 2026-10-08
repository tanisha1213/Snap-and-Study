import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import streamlit as st
from google import genai
from google.genai import types

from prompts import (
    SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
    SUMMARY_REQUEST_PROMPT,
)

# Model configuration
MODEL_NAME = "gemini-2.5-flash"

st.set_page_config(
    page_title="Snap & Study — AI Vision Study Assistant",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


def get_secret(key_name: str, default: str = "") -> str:
    """Retrieve secret from Streamlit secrets or environment variables safely."""
    try:
        if key_name in st.secrets and st.secrets[key_name]:
            return str(st.secrets[key_name]).strip()
    except Exception:
        pass
    env_val = os.environ.get(key_name, "")
    if env_val and env_val.strip():
        return env_val.strip()
    return default


@st.cache_resource
def get_gemini_client(api_key: str):
    """Build and cache the Gemini client once per session to avoid re-creation on reruns."""
    return genai.Client(api_key=api_key)


def ask_gemini(parts):
    """Send parts (text and/or image data) to the persistent Gemini chat session."""
    if "chat" not in st.session_state or st.session_state.chat is None:
        return "⚠️ Gemini chat session is not active. Please check your API key or start a new session."
    try:
        response = st.session_state.chat.send_message(parts)
        if hasattr(response, "text") and response.text:
            return response.text
        return "⚠️ Received an empty response from Gemini. Please try rephrasing your question or uploading a clearer image."
    except Exception as error:
        return f"⚠️ Error communicating with Gemini API: {error}"


def send_email(to_address: str, user_name: str, summary_text: str):
    """Send revision notes to the student's email using Gmail SMTP."""
    gmail_address = get_secret("GMAIL_ADDRESS")
    gmail_app_password = get_secret("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_app_password:
        return (
            False,
            "Gmail credentials missing in secrets.toml (`GMAIL_ADDRESS` & `GMAIL_APP_PASSWORD` required).",
        )

    if not to_address or "@" not in to_address or "." not in to_address:
        return False, "Invalid recipient email address provided."

    if not summary_text or not summary_text.strip():
        return False, "No revision summary available to send."

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎓 Snap & Study - Revision Notes for {user_name}"
        msg["From"] = f"Snap & Study Assistant <{gmail_address}>"
        msg["To"] = to_address

        plain_text = (
            f"Hello {user_name},\n\n"
            f"Here is your personalized Revision Summary from your Snap & Study session:\n\n"
            f"{'='*60}\n\n"
            f"{summary_text}\n\n"
            f"{'='*60}\n\n"
            f"Keep up the great work!\n"
            f"— Your Snap & Study AI Assistant\n"
        )
        msg.attach(MIMEText(plain_text, "plain", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, gmail_app_password)
            server.send_message(msg)

        return True, f"Revision summary sent successfully to {to_address}!"
    except Exception as error:
        return False, f"Failed to send email via SMTP: {error}"


def render_message(message):
    """Render a message dictionary (role, kind, content) in Streamlit chat UI."""
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.markdown(message["content"])
        elif message["kind"] == "image":
            st.image(
                message["content"],
                caption="📸 Uploaded Study Material",
                use_container_width=True,
            )


def add_message(role, kind, content):
    """Add a message to st.session_state.messages and render it on screen."""
    st.session_state.messages.append(
        {"role": role, "kind": kind, "content": content}
    )
    render_message(st.session_state.messages[-1])


# Secrets Validation
gemini_api_key = get_secret("GEMINI_API_KEY")

# STEP 1: ONBOARDING SCREEN
if "onboarded" not in st.session_state or not st.session_state.onboarded:
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        st.title("🎓 Snap & Study")
        st.caption("AI Vision Study Assistant for Students")
        st.write("Upload textbook problems, handwritten notes, or diagrams to get step-by-step explanations and revision notes.")
        st.markdown("---")

        if not gemini_api_key:
            st.error(
                "⚠️ **GEMINI_API_KEY missing in secrets.toml**\n\n"
                "Please configure `GEMINI_API_KEY` in `.streamlit/secrets.toml` to continue."
            )

        with st.form("onboarding_form"):
            st.subheader("Student Onboarding")
            name_input = st.text_input("Your Full Name", placeholder="e.g. Alex Johnson")
            email_input = st.text_input("Your Email Address", placeholder="e.g. alex@example.com")

            submitted = st.form_submit_button("🚀 Start Studying", use_container_width=True, type="primary")

            if submitted:
                clean_name = name_input.strip()
                clean_email = email_input.strip()

                if not clean_name:
                    st.warning("Please enter your name.")
                elif not clean_email or "@" not in clean_email or "." not in clean_email:
                    st.warning("Please enter a valid email address.")
                elif not gemini_api_key:
                    st.error("Cannot start session without a valid GEMINI_API_KEY.")
                else:
                    st.session_state.name = clean_name
                    st.session_state.email = clean_email

                    try:
                        client = get_gemini_client(gemini_api_key)
                        st.session_state.chat = client.chats.create(
                            model=MODEL_NAME,
                            config=types.GenerateContentConfig(
                                system_instruction=SYSTEM_PROMPT
                            ),
                        )
                        st.session_state.messages = []
                        st.session_state.current_summary = None
                        st.session_state.onboarded = True
                        st.rerun()
                    except Exception as err:
                        st.error(f"Failed to create Gemini chat session: {err}")
    st.stop()
else:
    # STEP 2: MAIN APPLICATION INTERFACE
    # Sidebar
    with st.sidebar:
        st.title("🎓 Snap & Study")
        st.caption("AI Study Companion")
        st.markdown("---")

        st.markdown(f"👤 **Student:** {st.session_state.get('name', 'Student')}")
        st.markdown(f"✉️ **Email:** `{st.session_state.get('email', 'N/A')}`")

        st.markdown("---")
        st.markdown("💡 **Study Tips**")
        st.markdown(
            "- 📸 **Clear Photos**: Ensure notes or formulas are well-lit.\n"
            "- 💬 **Follow-ups**: Ask *'Explain step 2 in simpler terms'*.\n"
            "- 📝 **Revision Notes**: Click **Generate Revision Summary** when done!"
        )

        st.markdown("---")
        if st.button("🔄 Start New Study Session", use_container_width=True):
            st.session_state.onboarded = False
            st.session_state.messages = []
            st.session_state.current_summary = None
            st.session_state.chat = None
            st.rerun()

    # Main Header & Action Toolbar
    header_col, action_col = st.columns([5, 3], vertical_alignment="center")

    with header_col:
        st.title("🎓 Snap & Study")
        st.caption(f"Logged in as **{st.session_state.get('name', 'Student')}** (`{st.session_state.get('email', 'N/A')}`)")

    with action_col:
        summary_disabled = len(st.session_state.get("messages", [])) < 1
        if st.button("📝 Generate Revision Summary", disabled=summary_disabled, use_container_width=True, type="primary"):
            with st.spinner("Analyzing study session and generating revision summary..."):
                summary_result = ask_gemini([SUMMARY_REQUEST_PROMPT])
                st.session_state.current_summary = summary_result
                st.success("Revision summary generated below!")

    # Revision Summary Display Area
    if st.session_state.get("current_summary"):
        with st.expander("📌 **Current Revision Summary Sheet**", expanded=True):
            st.markdown(st.session_state.current_summary)
            st.markdown("---")

            email_col1, email_col2 = st.columns([3, 1])
            with email_col1:
                target_email = st.text_input("Recipient Email", value=st.session_state.get("email", ""))
            with email_col2:
                st.write("")  # Alignment spacer
                st.write("")
                if st.button("✉️ Send Notes to Email", use_container_width=True):
                    with st.spinner("Sending revision notes via email..."):
                        success, msg = send_email(target_email, st.session_state.get("name", "Student"), st.session_state.current_summary)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)

    st.markdown("---")

    # Render Chat History
    if not st.session_state.get("messages"):
        welcome_text = WELCOME_MESSAGE_TEMPLATE.format(name=st.session_state.get("name", "Student"))
        add_message("assistant", "text", welcome_text)
    else:
        for message in st.session_state.messages:
            render_message(message)

    # Chat Input (Supports Text and Image Uploads)
    user_input = st.chat_input(
        "Ask a question, or attach a photo of textbook/notes...",
        accept_file=True,
        file_type=["jpg", "jpeg", "png"],
    )

    if user_input:
        photo = user_input.files[0] if user_input.files else None
        text = user_input.text.strip() if user_input.text else ""
        parts = []

        if photo is not None:
            photo_bytes = photo.getvalue()
            mime_type = photo.type if photo.type else "image/jpeg"
            add_message("user", "image", photo_bytes)
            parts.append(types.Part.from_bytes(data=photo_bytes, mime_type=mime_type))

        if text:
            add_message("user", "text", text)
            parts.append(text)
        elif photo is not None:
            default_prompt = "Please analyze this study material / question photo and explain the concepts and step-by-step solution clearly."
            parts.append(default_prompt)

        with st.spinner("Snap & Study is thinking..."):
            answer = ask_gemini(parts)
            add_message("assistant", "text", answer)
