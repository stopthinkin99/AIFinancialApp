import os
import io
import json
import imaplib
import email
import glob
import pandas as pd
from datetime import datetime
import pdfplumber
import docx
import google.generativeai as genai
from api_key import gemini_api_key
import time

# Configure the Gemini model
genai.configure(api_key=gemini_api_key)

generation_config = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048
}

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

model = genai.GenerativeModel(
    model_name="gemini-1.0-pro",
    generation_config=generation_config,
    safety_settings=safety_settings,
)

# Function to read resumes from email
def fetch_resumes_from_email():
    email_resumes = []
    try:
        # Connect to the IMAP server
        print("Connecting to IMAP server...")
        mail = imaplib.IMAP4_SSL('imap.gmail.com')
        mail.login('your_email@gmail.com', 'your_app_password')  # Use App Password if 2FA is enabled
        mail.select('inbox')
        
        # Get today's date in the required format
        today_date = datetime.now().strftime("%d-%b-%Y")
        
        # Search for emails from today
        result, data = mail.search(None, f'(SINCE {today_date})')
        
        if result != 'OK':
            print(f"Error searching emails: {result}")
            return email_resumes

        # Fetch email ids
        for num in data[0].split():
            result, data = mail.fetch(num, '(RFC822)')
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Check the email subject or body for keywords
            subject = msg['subject'].lower() if msg['subject'] else ""
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body += part.get_payload(decode=True).decode('utf-8')
            else:
                body = msg.get_payload(decode=True).decode('utf-8')

            if "resume" in subject or "cv" in subject or "application" in subject or \
               "resume" in body or "cv" in body or "application" in body:
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    if part.get('Content-Disposition') is None:
                        continue
                    filename = part.get_filename()
                    # Check if the part has a filename and the desired extension
                    if filename and (filename.endswith('.pdf') or filename.endswith('.docx')):
                        print(f"Found attachment: {filename}")
                        email_resumes.append((filename, part.get_payload(decode=True)))
        mail.logout()
        print("Emails with resumes fetched successfully.")
    except Exception as e:
        print(f"An error occurred while fetching resumes: {e}")
    return email_resumes

# Function to read resumes from local folder
def fetch_resumes_from_folder(folder_path):
    local_resumes = []
    for file in glob.glob(os.path.join(folder_path, '*')):
        if file.endswith('.pdf') or file.endswith('.docx'):
            with open(file, 'rb') as f:
                local_resumes.append((os.path.basename(file), f.read()))
    return local_resumes

# Function to save binary data to a file
def save_to_file(content, filename):
    with open(filename, 'wb') as f:
        f.write(content)

# Function to read PDF files
def read_pdf(file):
    with pdfplumber.open(io.BytesIO(file)) as pdf:
        full_text = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text.append(text)
    return "\n".join(full_text)

# Function to read DOCX files
def read_docx(file):
    doc = docx.Document(io.BytesIO(file))
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    return "\n".join(full_text)

# Function to extract entities using Gemini model
def extract_entities(text):
    prompt = f"""Extract from the following resume text in this format:
                "name": The person's full name (string).
                "email": The person's email address (string).
                "contact_number": The person's contact number (string).
                "education": A list of education details, each containing (select the 1st degree):
                - "degree": The degree obtained (string).
                - "specialization": The field of study (string).
                - "institution": The name of the institution (string).
                - "year_of_passing": The year of graduation (integer).
                "education": A list of education details, each containing (select the 2nd degree):
                - "degree": The degree obtained (string).
                - "specialization": The field of study (string).
                - "institution": The name of the institution (string).
                - "year_of_passing": The year of graduation (integer).
                "skills": A list of skills (strings).
                "experience": A list of experience details, each containing:
                - "company": The name of the company (string).
                - "role": The role at the company (string).
                - "duration": The duration of employment (string).
                - "description": A description of the job responsibilities (string).
                - "suitable_role":also your work is to detect the suitable  positions based on skills and experience(string).
                -"Years of Experience"/"years of experience":  It should count the years of work experience or months if experience is 6 years then 6 given or if experience is 6 years 3 months then should be 6.3 and if 4 months experience then 0.4, it should detect and  get the experience from resume ,it should create only one column of Years of Experience  (float).
                     
                \n\n
                then text is:   \n\n{text}\n\n.Provide the output in a structured JSON format."""

    response = model.generate_content(prompt)
    return response.text

# Function to clean and fix JSON
def clean_json_response(json_str):
    # Remove leading/trailing whitespaces
    json_str = json_str.strip()
    # Remove surrounding ```json and ```
    if json_str.startswith("```json"):
        json_str = json_str[len("```json"):].strip()
    if json_str.endswith("```"):
        json_str = json_str[:-len("```")].strip()
    # Replace any incorrect JSON formatting here if necessary
    return json_str

# Function to parse JSON or dictionary response
def parse_response(response_text):
    try:
        cleaned_response = clean_json_response(response_text)
        response_data = json.loads(cleaned_response)
        return response_data
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        print(f"Raw response: {response_text}")
        return None

# Main function to process resumes
def process_resumes():
    folder_path = r"E:\Download\attachments"  # Replace with your actual folder path
    all_resumes = fetch_resumes_from_email() + fetch_resumes_from_folder(folder_path)
    print(f"Total resumes found: {len(all_resumes)}")
    
    extracted_data = []
    retry_attempts = 3

    for filename, resume_content in all_resumes:
        print(f"Processing {filename}...")
        for attempt in range(retry_attempts):
            try:
                if filename.endswith('.pdf'):
                    file_content = read_pdf(resume_content)
                elif filename.endswith('.docx'):
                    file_content = read_docx(resume_content)
                else:
                    print(f"Unsupported file format for {filename}")
                    break

                if file_content.strip() == "":
                    print(f"The file {filename} does not contain any text that can be extracted.")
                    break

                # Extract entities using Gemini model
                extracted_info = extract_entities(file_content)

                if not extracted_info.strip():
                    print(f"The model returned an empty response for {filename}")
                    break

                # Parse response as JSON
                extracted_json = parse_response(extracted_info)
                if extracted_json:
                    extracted_data.append(extracted_json)
                    print(f"Extracted data for {filename}")
                    break
                else:
                    print(f"Failed to parse JSON for {filename}")
                    if attempt < retry_attempts - 1:
                        print(f"Retrying {filename}... ({attempt + 1}/{retry_attempts})")
                        time.sleep(5)  # Wait before retrying
                        continue
                    else:
                        print(f"Failed to process {filename} after {retry_attempts} attempts.")
                        break
            except Exception as e:
                print(f"An error occurred while processing {filename}: {e}")
                if attempt < retry_attempts - 1:
                    print(f"Retrying {filename}... ({attempt + 1}/{retry_attempts})")
                    time.sleep(5)  # Wait before retrying
                    continue
                else:
                    print(f"Failed to process {filename} after {retry_attempts} attempts.")
                    break

    # Save extracted data to a DataFrame and CSV
    if extracted_data:
        df = pd.DataFrame(extracted_data)
        output_csv_path = os.path.join(folder_path, "extracted_resumes.csv")
        df.replace('[]', ' ', inplace=True)
        df.to_csv(output_csv_path, index=False)
        print(f"Extracted data saved to {output_csv_path}")
    else:
        print("No data extracted to save.")

# Run the process
process_resumes()
