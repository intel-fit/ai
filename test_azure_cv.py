"""import os
import requests
from dotenv import load_dotenv

load_dotenv()

AZURE_CV_KEY = os.getenv("AZURE_COMPUTER_VISION_KEY")
AZURE_CV_ENDPOINT = os.getenv("AZURE_COMPUTER_VISION_ENDPOINT")

if not AZURE_CV_KEY or not AZURE_CV_ENDPOINT:
    raise RuntimeError("Azure Computer Vision API info not set in .env")

# 분석할 이미지 파일
IMAGE_PATH = r"C:\Users\Master\Pictures\food.jpg"


# Computer Vision URL
analyze_url = f"{AZURE_CV_ENDPOINT}/vision/v3.2/analyze?visualFeatures=Tags,Description"

# 이미지 바이너리 읽기
with open(IMAGE_PATH, "rb") as f:
    img_data = f.read()

# 요청 헤더
headers = {
    "Ocp-Apim-Subscription-Key": AZURE_CV_KEY,
    "Content-Type": "application/octet-stream"
}

# 요청 보내기
response = requests.post(analyze_url, headers=headers, data=img_data)

if response.status_code != 200:
    print("Error:", response.status_code, response.text)
else:
    analysis = response.json()
    tags = [tag['name'] for tag in analysis.get("tags", [])]
    description = analysis.get("description", {}).get("captions", [{}])[0].get("text", "")
    print("Tags:", tags)
    print("Description:", description)
"""