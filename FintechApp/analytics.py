import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from io import BytesIO
import re
import openai
import random
from datetime import datetime

# Set up OpenAI API key
openai.api_key = 'your_openai_api_key'

# Configure the path to tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def extract_text_from_pdf(file_stream):
    document = fitz.open(stream=file_stream, filetype="pdf")
    text = ""
    for page_num in range(document.page_count):
        page = document.load_page(page_num)
        pix = page.get_pixmap()
        img = Image.open(BytesIO(pix.tobytes()))
        text += pytesseract.image_to_string(img)
    return text

def analyze_text_with_ai(text):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": f"Extract the total earned and total spent from this financial statement: {text}"}
        ],
    )
    analysis_content = response['choices'][0]['message']['content']
    
    # Extracting date of the balance sheet for title
    date_match = re.search(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', text)
    date_str = date_match.group() if date_match else "Unknown Date"
    balance_date = datetime.strptime(date_str, '%m/%d/%Y').strftime('%B %d, %Y') if date_match else "Unknown Date"
    
    # Generate random titles
    titles_analytics1 = [
        "Your Financial Wrap",
        "Welcome to Your Financial Wrap",
        "Discover Your Financial Journey",
        "Your Financial Summary",
        "Financial Insights for You",
        "Your Financial Recap"
    ]
    
    titles_analytics2 = [
        f"Detailed Analysis - {balance_date}",
        f"In-Depth Financial Review - {balance_date}",
        f"Financial Breakdown - {balance_date}",
        f"Comprehensive Financial Analysis - {balance_date}",
        f"Detailed Financial Overview - {balance_date}"
    ]
    
    title_analytics1 = random.choice(titles_analytics1)
    title_analytics2 = random.choice(titles_analytics2)
    
    # Combining analysis with titles
    return {
        "analysis": analysis_content,
        "title_analytics1": title_analytics1,
        "title_analytics2": title_analytics2
    }
