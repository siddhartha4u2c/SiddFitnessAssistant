import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import os

# -----------------------
# Configure API Key
# -----------------------
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# -----------------------
# Load Model
# -----------------------
model = genai.GenerativeModel("gemini-1.5-pro")

# -----------------------
# UI
# -----------------------
st.set_page_config(page_title="Food Calorie Estimator", page_icon="🍽️")

st.title("🍽️ Food Calorie Estimator")
st.write("Upload or take a photo of your meal to estimate calories.")

# -----------------------
# Input options
# -----------------------
option = st.radio(
    "Choose input method:",
    ["Upload Image", "Take Photo"]
)

image = None

# -----------------------
# Upload option
# -----------------------
if option == "Upload Image":
    uploaded_file = st.file_uploader(
        "Upload a food image",
        type=["jpg", "jpeg", "png"]
    )
    if uploaded_file:
        image = Image.open(uploaded_file)

# -----------------------
# Camera option
# -----------------------
elif option == "Take Photo":
    camera_image = st.camera_input("Take a photo")

    if camera_image:
        image = Image.open(camera_image)

# -----------------------
# Show image + process
# -----------------------
if image:
    st.image(image, caption="Selected Image", use_column_width=True)

    if st.button("Estimate Calories 🔍"):
        with st.spinner("Analyzing your food..."):

            # Convert image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format="PNG")
            img_bytes = img_byte_arr.getvalue()

            # Prompt
            prompt = """
            You are a nutrition expert.

            Analyze the food in this image and:
            1. Identify all visible food items
            2. Estimate portion sizes
            3. Provide total calorie estimate
            4. Break down calories per item

            Return response in this format:

            Food Items:
            - Item 1: calories
            - Item 2: calories

            Total Calories: XXXX kcal

            Notes:
            - Mention assumptions
            """

            response = model.generate_content(
                [
                    prompt,
                    {"mime_type": "image/png", "data": img_bytes}
                ]
            )

            st.subheader("📊 Result")
            st.write(response.text)

# -----------------------
# Footer
# -----------------------
st.markdown("---")
st.caption("⚠️ Calorie estimates are approximate and may vary.")
