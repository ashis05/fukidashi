# 🈂️ Manga Translator AI (2026)

![Python](https://img.shields.io/badge/Language-Python-blue)
![AI](https://img.shields.io/badge/AI-OpenAI%20%7C%20EasyOCR-green)
![Framework](https://img.shields.io/badge/Backend-FastAPI-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

An **AI-powered Manga Translation tool** that automatically detects, translates, and replaces text in raw manga pages.  
Designed as a project to explore computer vision, Optical Character Recognition (OCR), prompt engineering with Large Language Models, and automated image inpainting.

---

## ✨ Features

- 🔤 **Automated Text Detection** — Accurately identifies speech bubbles and text regions in raw panels  
- 📖 **Context-Aware Translation** — Leverages LLMs for highly accurate and natural-sounding translations from Japanese to English  
- 🖌️ **Seamless Inpainting** — Automatically cleans up original text from the background before applying translated text  
- 🎨 **Custom Typography** — Renders translated text cleanly back into the speech bubbles  
- ⚡ **Batch Processing** — Translates entire chapters or multiple pages in a single run  

---

## 🧠 Learning Objectives

This project focuses on:
- Integrating OCR engines (like EasyOCR/Tesseract) with image processing libraries (OpenCV)  
- Utilizing AI/LLM APIs for context-specific language translation  
- Handling complex image inpainting and text rendering algorithms  
- Building a robust backend API to handle heavy image processing tasks  

---

## ⚙️ Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/ashis05/manga-translator-ai.git
cd manga-translator-ai
```

### 2. Set Up a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Variables
Create a `.env` file in the root directory and add your API keys:

```env
OPENAI_API_KEY=your_api_key_here
```

### 5. Run the Application
```bash
python main.py
```

---

## 🖥️ Screenshots

| Original Raw Page | Translated Output |
|------------------|------------------|
| *(Add image)*    | *(Add image)*    |

*(Replace with your own screenshots once uploaded to the `/assets` folder.)*

---

## 🧑‍💻 Author

**Ashis Wadhwani**  
📍 Developer & Designer of the project  

🔗 GitHub: https://github.com/ashis05  

---

## 📜 License

This project is licensed under the MIT License — you are free to use, modify, and distribute it with attribution.  
See the `LICENSE` file for full details.

---

## 🚀 Future Enhancements

- Build a user-friendly Web UI for drag-and-drop translations  
- Add support for Korean Manhwa and Chinese Manhua  
- Implement custom font selection based on the emotion of the text  

---

## ⭐ Support

If you like this project, give it a ⭐ on GitHub to support future updates!
